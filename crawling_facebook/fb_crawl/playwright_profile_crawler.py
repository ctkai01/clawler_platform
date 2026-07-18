from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from time import monotonic as _monotonic
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Response, async_playwright

from fb_crawl.playwright_page_crawler import EXTRACT_PAGE_NAME_JS
from fb_crawl.profile_parser import (
    REACTION_LABELS,
    comment_story_id,
    extract_embedded_payloads,
    extract_graphql_payloads,
    merge_post_fields,
    parse_comments_from_payload,
    parse_posts_from_payload,
    parsed_comment_to_comment,
    parsed_post_to_post,
    post_id_from_url,
    top_comments,
)
from fb_crawl.types import CheckpointError, Post

logger = logging.getLogger(__name__)

MAX_COMMENTS = 100


def normalize_profile_url(url: str) -> str:
    url = url.strip().rstrip("/")
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url}"
    return url


def profile_posts_url(profile_url: str) -> str:
    base = normalize_profile_url(profile_url)
    if re.search(r"/(posts|photos|videos|friends|about)(/|$)", base):
        return base
    return f"{base}/posts"


def within_date_range(published_at_iso: str | None, cutoff: datetime) -> bool:
    if not published_at_iso:
        return True
    try:
        dt = datetime.fromisoformat(published_at_iso.replace("Z", "+00:00"))
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff


_ARIA_REACTION_RE = re.compile(
    r"^(Like|Love|Care|Haha|Wow|Sad|Angry)\s*:\s*([\d.,]+)\s*([KM])?\s*people",
    re.IGNORECASE,
)
_ARIA_POPUP_REACTION_RE = re.compile(
    r"Show\s+([\d,]+)\s+people who reacted with (\w+)", re.IGNORECASE
)


def _parse_dom_count(num: str, suffix: str | None = None) -> int:
    value = float(num.replace(",", ""))
    if suffix:
        if suffix.upper() == "K":
            value *= 1_000
        elif suffix.upper() == "M":
            value *= 1_000_000
    return int(value)


class PlaywrightProfileCrawler:
    """Crawls public posts on a personal Facebook profile timeline.

    Unlike PlaywrightPageCrawler (DOM scraping of a Page's feed), this
    sniffs GraphQL responses + embedded <script type="application/json">
    payloads while scrolling the timeline — ported from the reference
    project at /home/ctkai/Documents/facebook_profile (see profile_parser.py
    docstring). Session/proxy handling mirrors PlaywrightPageCrawler so it
    plugs into the same AccountPool/ProxyPool-driven batch_tasks.py flow —
    the reference project's own facebook_state.json file is not used here.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        storage_state_path: str | Path | dict | None = None,
        user_agent: str | None = None,
        proxy_server: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
        days_back: float = 7,
        max_posts: int = 200,
        top_comment_limit: int = 100,
        scroll_pause_ms: int = 1800,
        max_idle_scrolls: int = 8,
        max_scroll_rounds: int = 400,
        max_scroll_seconds: float = 900.0,
        max_comments: int = MAX_COMMENTS,
        public_only: bool = True,
        concurrency: int = 3,
    ) -> None:
        self.headless = headless
        self.storage_state_path = storage_state_path
        # Matches the reference project's UA exactly (crawl_facebook_profile.py)
        # — deliberately not the newer Chrome/128 UA still used by
        # PlaywrightPageCrawler, after this UA/context combo (+ no stealth, no
        # launch args) was confirmed NOT to trigger the www->web.facebook.com
        # Comet redirect that broke post parsing in production.
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.proxy_server = proxy_server
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.days_back = days_back
        self.max_posts = max_posts
        self.top_comment_limit = top_comment_limit
        self.scroll_pause_ms = scroll_pause_ms
        self.max_idle_scrolls = max_idle_scrolls
        self.max_scroll_rounds = max_scroll_rounds
        self.max_scroll_seconds = max_scroll_seconds
        self.max_comments = max_comments
        self.public_only = public_only
        self.concurrency = max(1, concurrency)
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> PlaywrightProfileCrawler:
        self._pw = await async_playwright().start()
        # No launch args, no stealth patching, no explicit timezone_id, no
        # set_default_timeout — deliberately matching the reference project's
        # browser/context setup exactly (crawl_facebook_profile.py's
        # crawl_profile()). A real incident: with the stealth/hardened setup
        # PlaywrightPageCrawler uses, Facebook silently redirected this
        # session's profile timeline from www.facebook.com to
        # web.facebook.com (the Comet UI), whose GraphQL/embedded-JSON
        # payload shapes this parser doesn't recognize — 38k+ payloads
        # collected, 0 posts extracted. The reference project's plainer
        # setup never saw that redirect on the same profile/account family.
        self._browser = await self._pw.chromium.launch(headless=self.headless)
        context_kwargs: dict = {
            "viewport": {"width": 1400, "height": 900},
            "locale": "vi-VN",
            "user_agent": self.user_agent,
        }
        if isinstance(self.storage_state_path, dict):
            context_kwargs["storage_state"] = self.storage_state_path
        elif self.storage_state_path and Path(self.storage_state_path).exists():
            context_kwargs["storage_state"] = str(self.storage_state_path)
        if self.proxy_server:
            proxy_kwargs: dict = {"server": self.proxy_server}
            if self.proxy_username:
                proxy_kwargs["username"] = self.proxy_username
            if self.proxy_password:
                proxy_kwargs["password"] = self.proxy_password
            context_kwargs["proxy"] = proxy_kwargs
        self._context = await self._browser.new_context(**context_kwargs)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def save_session(self, path: str | Path) -> None:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(path))

    async def login_interactive(
        self,
        login_url: str = "https://www.facebook.com/",
        *,
        timeout_sec: int = 300,
    ) -> bool:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        page = await self._context.new_page()
        await page.goto(login_url, wait_until="domcontentloaded")
        print("Mở trình duyệt — hãy đăng nhập Facebook.")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_sec
        while loop.time() < deadline:
            cookies = await self._context.cookies("https://www.facebook.com")
            if any(c["name"] == "c_user" for c in cookies):
                await page.close()
                return True
            await asyncio.sleep(2)
        await page.close()
        return False

    async def refresh_login(self, uid: str, password: str, two_fa_secret: str | None) -> dict | None:
        """Same mbasic.facebook.com auto-relogin flow as
        PlaywrightPageCrawler.refresh_login — see that docstring."""
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        page = await self._context.new_page()
        try:
            await page.goto("https://mbasic.facebook.com/", wait_until="domcontentloaded")
            await page.fill("input[name='email']", uid)
            await page.fill("input[name='pass']", password)
            await page.click("input[type='submit']")
            await page.wait_for_timeout(3000)

            if await page.locator("input[name='approvals_code']").count() > 0:
                if not two_fa_secret:
                    logger.error("FB yêu cầu 2FA nhưng account %s không có two_fa_secret", uid)
                    return None
                import pyotp

                code = pyotp.TOTP(two_fa_secret.replace(" ", "")).now()
                await page.fill("input[name='approvals_code']", code)
                await page.click("input[type='submit']")
                await page.wait_for_timeout(3000)

            cookies = await self._context.cookies("https://www.facebook.com")
            if not any(c["name"] == "c_user" for c in cookies):
                logger.error("Đăng nhập lại tự động thất bại cho account %s", uid)
                return None
            return await self._context.storage_state()
        finally:
            await page.close()

    async def fetch_profile_name(self, profile_url: str) -> str | None:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        page = await self._context.new_page()
        try:
            await page.goto(normalize_profile_url(profile_url), wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            if "checkpoint" in page.url:
                raise CheckpointError(f"Session bị checkpoint khi mở profile {profile_url} ({page.url})")
            name = await page.evaluate(EXTRACT_PAGE_NAME_JS)
            name = (name or "").strip()
            return name or None
        except CheckpointError:
            raise
        except Exception as exc:
            logger.warning("Không lấy được tên profile %s: %s", profile_url, exc)
            return None
        finally:
            await page.close()

    async def _save_response_payload(self, response: Response, bucket: list[Any]) -> None:
        url = response.url
        if "graphql" not in url and "api/graphql" not in url:
            return
        try:
            text = await response.text()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Không đọc được response %s: %s", url, exc)
            return
        for payload in extract_graphql_payloads(text):
            bucket.append(payload)

    async def _scroll_timeline(self, page: Page, payloads: list[Any], cutoff: datetime) -> None:
        idle_rounds = 0
        last_count = 0
        round_count = 0
        processed_count = 0
        posts: dict[str, dict[str, Any]] = {}
        start_time = _monotonic()

        # idle_rounds/cutoff không phải điều kiện dừng đáng tin cậy tuyệt đối: nếu
        # Facebook liên tục nạp nội dung nền (gợi ý bạn bè, story, widget...) mỗi
        # lần cuộn, payloads vẫn tăng liên tục nên idle_rounds không bao giờ đạt
        # ngưỡng; và nếu không tìm được bài nào có published_at hợp lệ (vd. do bộ
        # lọc post chặt), điều kiện dừng sớm theo cutoff cũng không bao giờ kích
        # hoạt. Vì vậy BẮT BUỘC phải có giới hạn cứng tuyệt đối (số vòng + thời
        # gian) độc lập với 2 điều kiện trên để vòng lặp không bao giờ treo vô hạn
        # — real incident: chạy > 53 phút không log được gì trước khi có giới hạn
        # này.
        while idle_rounds < self.max_idle_scrolls:
            round_count += 1
            if round_count > self.max_scroll_rounds:
                logger.warning(
                    "Đạt giới hạn cứng %s vòng cuộn, dừng scroll (khả năng Facebook "
                    "liên tục nạp nội dung nền không phải bài viết thật).",
                    self.max_scroll_rounds,
                )
                break
            elapsed = _monotonic() - start_time
            if elapsed > self.max_scroll_seconds:
                logger.warning(
                    "Đạt giới hạn cứng %.0fs cuộn timeline, dừng scroll (khả năng "
                    "Facebook liên tục nạp nội dung nền không phải bài viết thật).",
                    self.max_scroll_seconds,
                )
                break

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(self.scroll_pause_ms)

            html = await page.content()
            payloads.extend(extract_embedded_payloads(html))

            current_count = len(payloads)
            if current_count == last_count:
                idle_rounds += 1
            else:
                idle_rounds = 0
            last_count = current_count

            # Chỉ parse các payload MỚI kể từ vòng trước, không xử lý lại toàn bộ
            # payload đã thu từ đầu mỗi vòng — nếu không, chi phí mỗi vòng tăng
            # dần theo O(tổng payload đã thấy), làm vòng lặp ngày càng chậm và có
            # thể góp phần gây ra tình trạng "treo" khi payloads bị nạp liên tục
            # không dừng.
            for payload in payloads[processed_count:]:
                merge_posts(posts, parse_posts_from_payload(payload))
            processed_count = current_count

            dated_posts = [p for p in posts.values() if p.get("published_at")]
            if dated_posts:
                oldest = min(
                    datetime.fromisoformat(p["published_at"].replace("Z", "+00:00"))
                    for p in dated_posts
                )
                if oldest < cutoff and len(posts) >= 5:
                    logger.info("Đã cuộn tới bài cũ hơn %s ngày, dừng scroll.", self.days_back)
                    break

    async def _reaction_totals_from_popup(self, page: Page) -> dict[str, int] | None:
        trigger = page.get_by_role(
            "button", name=re.compile(r"^(Like|Love|Care|Haha|Wow|Sad|Angry): ", re.I)
        ).first
        if await trigger.count() == 0:
            return None
        try:
            await trigger.click(timeout=3000, force=True)
            await page.wait_for_timeout(1500)
            tab_labels = await page.evaluate(
                """() => {
                    const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
                    for (const d of dialogs) {
                        const tabs = Array.from(d.querySelectorAll('[role="tab"]'));
                        if (tabs.length) {
                            return tabs.map(t => t.getAttribute('aria-label')).filter(Boolean);
                        }
                    }
                    return [];
                }"""
            )
        except Exception:  # noqa: BLE001
            return None
        finally:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)

        reactions: dict[str, int] = {}
        total = 0
        for label in tab_labels or []:
            match = _ARIA_POPUP_REACTION_RE.search(label)
            if not match:
                continue
            count = _parse_dom_count(match.group(1))
            kind = match.group(2)
            if kind.upper() == "ALL":
                total = count
            else:
                reactions[REACTION_LABELS.get(kind.upper(), kind.lower())] = count

        if not reactions:
            return None
        return {"total": total or sum(reactions.values()), **reactions}

    async def _reaction_totals_from_dom(self, page: Page) -> dict[str, int] | None:
        popup_result = await self._reaction_totals_from_popup(page)
        if popup_result:
            return popup_result

        try:
            labels = await page.evaluate(
                """() => {
                    const dialog = document.querySelector('div[role="dialog"]');
                    const root = dialog || document.body;
                    return Array.from(root.querySelectorAll('[aria-label]'))
                        .map(e => e.getAttribute('aria-label'));
                }"""
            )
        except Exception:  # noqa: BLE001
            return None

        reactions: dict[str, int] = {}
        for label in labels or []:
            if not label:
                continue
            match = _ARIA_REACTION_RE.match(label.strip())
            if not match:
                continue
            name, num, suffix = match.groups()
            label_key = REACTION_LABELS.get(name.upper(), name.lower())
            count = _parse_dom_count(num, suffix)
            reactions[label_key] = max(reactions.get(label_key, 0), count)

        if not reactions:
            return None
        return {"total": sum(reactions.values()), **reactions}

    async def _fetch_post_comments(self, post: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        post_url = post.get("post_url")
        if not post_url:
            return []

        # Reels đăng lên timeline thực chất là 1 Story "bọc" quanh 1 Video có ID
        # khác hẳn (vd. story_id trong post_url dạng /reel/<video_id>/). Khi xem
        # Reels, Facebook preload sẵn dữ liệu của nhiều reel khác đang chờ kế tiếp
        # trong cùng payload — nếu chỉ so khớp đúng 1 post_id có thể dính nhầm dữ
        # liệu (comment, feedback) của Story wrapper vốn không phản ánh đúng số
        # liệu người dùng thấy trên video. Ưu tiên video_id (từ URL) làm nguồn xác
        # thực khi nó khác post_id. (Reel/video posts đã bị lọc bỏ trước khi tới
        # đây — xem discover_posts — nhưng giữ logic này để chính xác cho các bài
        # thường mà post_id trích từ node khác với id trích từ URL.)
        video_id = post_id_from_url(post_url)
        reference_ids = {rid for rid in (post.get("post_id"), video_id) if rid}
        authoritative_id = video_id if video_id and video_id != post.get("post_id") else None

        comment_payloads: list[Any] = []

        async def on_response(response: Response) -> None:
            await self._save_response_payload(response, comment_payloads)

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            page = await self._context.new_page()
            page.on("response", on_response)
            try:
                await self._fetch_post_comments_once(
                    page, post, comment_payloads, reference_ids=reference_ids, authoritative_id=authoritative_id
                )
                break
            except CheckpointError:
                # Account-level failure, not per-post — retrying just means
                # 3 more requests against an already-dead session. Must
                # propagate immediately (finally below still closes the
                # page) so the caller isolates the account instead of this
                # being swallowed as a per-post warning (real incident:
                # exactly that swallowing let a checkpointed account keep
                # getting reused/hammered for every remaining post).
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("Lỗi lấy comment %s (lần %d/3): %s", post_url, attempt, exc)
                await asyncio.sleep(min(2 * attempt, 8))
            finally:
                await page.close()
        else:
            if last_exc:
                logger.warning("Bỏ qua comment cho %s sau 3 lần thử: %s", post_url, last_exc)

        comments: dict[str, dict[str, Any]] = {}
        for payload in comment_payloads:
            for comment in parse_comments_from_payload(payload):
                cid = comment.get("comment_id")
                story_id = comment_story_id(cid)
                if story_id and story_id not in reference_ids:
                    # Comment thuộc 1 post/reel khác bị preload chung payload —
                    # bỏ qua.
                    continue
                key = cid or f"{comment['author']}:{comment['content'][:40]}"
                comments[key] = comment

        if comments:
            post["comment_count"] = max(post.get("comment_count", 0), len(comments))

        return top_comments(list(comments.values()), self.top_comment_limit)

    async def _fetch_post_comments_once(
        self,
        page: Page,
        post: dict[str, Any],
        comment_payloads: list[Any],
        *,
        reference_ids: set[str],
        authoritative_id: str | None,
    ) -> None:
        post_url = post["post_url"]
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            payloads_before = len(comment_payloads)
            if attempt == 1:
                await page.goto(post_url, wait_until="domcontentloaded", timeout=60_000)
            else:
                await page.reload(wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2500)
            if "checkpoint" in page.url:
                # Previously only checked once, on the initial timeline
                # load — a checkpoint hit while opening an individual post's
                # permalink (here) went completely undetected: the account
                # stayed marked LIVE and kept getting reused/hammered
                # against Facebook for every remaining post. Real incident.
                raise CheckpointError(
                    f"Session bị checkpoint khi mở bài viết {post_url} ({page.url})"
                )

            for selector in (
                "div[aria-label*='comment' i]",
                "div[aria-label*='bình luận' i]",
                "span:has-text('Comment')",
                "span:has-text('Bình luận')",
            ):
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0:
                        await locator.click(timeout=3000)
                        await page.wait_for_timeout(1500)
                        break
                except Exception:  # noqa: BLE001
                    continue

            try:
                sort_button = page.locator("div[role='button']", has_text="Most relevant").first
                if await sort_button.count() > 0:
                    await sort_button.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                    all_comments_option = page.locator(
                        "div[role='menuitem'], div[role='menuitemradio']", has_text="All comments"
                    ).first
                    if await all_comments_option.count() > 0:
                        await all_comments_option.click(timeout=3000)
                        await page.wait_for_timeout(2000)
            except Exception:  # noqa: BLE001
                pass

            last_payload_count = len(comment_payloads)
            idle_rounds = 0
            for _ in range(14):
                await page.mouse.wheel(0, 1800)
                await page.wait_for_timeout(1200)
                current_count = len(comment_payloads)
                if current_count == last_payload_count:
                    idle_rounds += 1
                else:
                    idle_rounds = 0
                last_payload_count = current_count
                if idle_rounds >= 4:
                    break

            html = await page.content()
            comment_payloads.extend(extract_embedded_payloads(html))

            authoritative_matches: list[dict[str, Any]] = []
            fallback_matches: list[dict[str, Any]] = []
            for payload in comment_payloads:
                for parsed_post in parse_posts_from_payload(payload):
                    pid = parsed_post.get("post_id")
                    if pid not in reference_ids:
                        continue
                    if authoritative_id and pid == authoritative_id:
                        authoritative_matches.append(parsed_post)
                    else:
                        fallback_matches.append(parsed_post)

            found_post_reactions = False
            for parsed_post in authoritative_matches or fallback_matches:
                if parsed_post.get("reactions", {}).get("total"):
                    post["reactions"] = parsed_post["reactions"]
                    found_post_reactions = True
                if parsed_post.get("comment_count"):
                    post["comment_count"] = max(
                        post.get("comment_count", 0), parsed_post["comment_count"]
                    )

            if not found_post_reactions:
                dom_reactions = await self._reaction_totals_from_dom(page)
                if dom_reactions:
                    post["reactions"] = dom_reactions
                    found_post_reactions = True

            if found_post_reactions or attempt == max_attempts:
                break
            # Reload-and-retry only helps when this attempt got NOTHING at
            # all (page failed to load/hydrate) — a real transient issue.
            # If comments/payloads DID come through but reactions
            # specifically didn't, that's a structural mismatch (e.g. video
            # posts render their reaction bar in a DOM shape neither the
            # JSON-payload path nor _reaction_totals_from_dom recognizes),
            # not a timing fluke — an identical reload would fail the exact
            # same way, just doubling the cost of every such post for
            # nothing. Real incident: this cost 2x page-load+comment-scroll
            # on every video post on a profile with mostly video content.
            if len(comment_payloads) > payloads_before:
                break

    async def discover_posts(self, profile_url: str, *, profile_id: str) -> tuple[str | None, list[Post]]:
        """Full discover+scroll+parse+comments pass over one profile's
        timeline. Returns (profile_name, posts) — posts are
        fb_crawl.types.Post objects (comments populated), newest first,
        capped at max_posts. Mirrors crawl_profile() in the reference
        project but everything happens through self._context
        (AccountPool-sourced session/proxy) instead of a fresh
        async_playwright().start() per call.

        profile_id must be a stable identifier (extracted by the caller via
        fb_crawl.parser.extract_page_id — works for /people/<slug>/<id>,
        profile.php?id=, and plain vanity-slug URLs alike), not the raw URL:
        it becomes documents.owner_external_id, so a profile's posts stay
        linked together even if the URL form used to reach it varies."""
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")

        profile_url = normalize_profile_url(profile_url)
        timeline_url = profile_posts_url(profile_url)
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_back)

        payloads: list[Any] = []
        posts_map: dict[str, dict[str, Any]] = {}

        page = await self._context.new_page()

        async def on_response(response: Response) -> None:
            await self._save_response_payload(response, payloads)

        page.on("response", on_response)
        try:
            await page.goto(timeline_url, wait_until="domcontentloaded", timeout=90_000)
            await page.wait_for_timeout(4000)
            if "checkpoint" in page.url:
                raise CheckpointError(f"Session bị checkpoint khi mở profile {profile_url} ({page.url})")

            profile_name = await page.evaluate(EXTRACT_PAGE_NAME_JS)
            profile_name = (profile_name or "").strip() or None

            await self._scroll_timeline(page, payloads, cutoff)

            # TEMP DEBUG — remove after diagnosing why 0 posts were found in
            # production (worked fine, 5 posts, locally with a manually
            # logged-in session): capture what the crawling account actually
            # saw at the end of scrolling, to check for Facebook silently
            # serving a generic/degraded surface instead of the real
            # timeline for this URL (documented precedent — see
            # EXTRACT_PAGE_NAME_JS's JUNK_NAMES comment in
            # playwright_page_crawler.py).
            try:
                await page.screenshot(path="/tmp/profile_debug.png")
                logger.warning(
                    "DEBUG profile scroll end: url=%s title=%s payloads=%d",
                    page.url, await page.title(), len(payloads),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("DEBUG screenshot failed: %s", exc)
        finally:
            await page.close()

        for payload in payloads:
            merge_posts(posts_map, parse_posts_from_payload(payload))

        filtered: list[dict[str, Any]] = []
        for raw_post in posts_map.values():
            if self.public_only and raw_post.get("is_public") is False:
                continue
            if not within_date_range(raw_post.get("published_at"), cutoff):
                continue
            post_url = raw_post.get("post_url") or ""
            is_reel_or_video_url = "/reel/" in post_url or "/videos/" in post_url
            if is_reel_or_video_url or raw_post.get("is_video"):
                # Reel/video dùng post_id khác với video_id thật (post_url dạng
                # /reel/<video_id>/ hoặc /videos/<video_id>/), và khi xem Facebook
                # preload sẵn dữ liệu của nhiều video khác trong cùng payload nên
                # comment/reaction dễ lấy nhầm từ video không liên quan. Ngoài ra 1
                # post bình thường (/posts/pfbid...) vẫn có thể chỉ chứa video đính
                # kèm — is_video (phát hiện qua __typename Video của attachment)
                # bắt được cả trường hợp này. Bỏ qua theo yêu cầu — không cần crawl
                # bài reel/video (tốn 1 lượt mở trang+cuộn comment đầy đủ mỗi bài).
                continue
            filtered.append(raw_post)
        filtered.sort(key=lambda item: item.get("published_at") or "", reverse=True)
        filtered = filtered[: self.max_posts]

        logger.info("Profile %s: thu được %d bài public trong %d ngày.", profile_url, len(filtered), self.days_back)

        # Comment-fetching is the slow part (one full page visit + comment
        # scroll per post) — run up to `concurrency` posts at once instead
        # of strictly sequentially (unlike the reference project's plain
        # for-loop), same pattern as PlaywrightPageCrawler.fetch_posts_from_urls.
        sem = asyncio.Semaphore(self.concurrency)
        done = 0

        async def build_post(raw_post: dict[str, Any]) -> Post:
            nonlocal done
            post_url = raw_post.get("post_url") or raw_post.get("post_id")
            started = _monotonic()
            async with sem:
                raw_comments = await self._fetch_post_comments(raw_post)
            done += 1
            logger.info(
                "[%d/%d] Xong bài %s: %d comment (%.1fs)",
                done, len(filtered), post_url, len(raw_comments), _monotonic() - started,
            )
            post = parsed_post_to_post(raw_post, profile_id=profile_id, author=profile_name)
            post.comments = [parsed_comment_to_comment(c) for c in raw_comments][: self.max_comments]
            return post

        tasks = [asyncio.ensure_future(build_post(raw_post)) for raw_post in filtered]
        try:
            posts = list(await asyncio.gather(*tasks))
        except BaseException:
            # If one post's fetch raises (most importantly CheckpointError —
            # see _fetch_post_comments), the other concurrently-running
            # posts must not keep going: they'd keep hitting Facebook on
            # the same now-dead/checkpointed session for nothing.
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return profile_name, posts


def merge_posts(existing: dict[str, dict[str, Any]], new_posts: list[dict[str, Any]]) -> None:
    for post in new_posts:
        post_id = post.get("post_id")
        if not post_id:
            continue
        if post_id not in existing:
            existing[post_id] = post
            continue
        merge_post_fields(existing[post_id], post)
