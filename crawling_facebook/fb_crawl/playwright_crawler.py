from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright_stealth import Stealth

from fb_crawl.facebook_extract import (
    EXPAND_COMMENTS_JS,
    EXTRACT_MEDIA_JS,
    EXTRACT_POST_PAGE_JS,
    build_post_from_page_data,
    hydrate_precise_comment_times,
)
from fb_crawl.parser import (
    dedupe_post_urls,
    extract_group_id,
    extract_post_id,
    normalize_group_post_url,
    save_time_debug_html,
)
from fb_crawl.types import CheckpointError, NotGroupMemberError, Post

logger = logging.getLogger(__name__)

MAX_COMMENTS = 100

DISCOVER_FEED_URLS_JS = """
(groupId) => {
  const byPostId = new Map();

  function addPost(postId) {
    const id = String(postId || '').trim();
    if (!id || !/^\\d+$/.test(id)) return;
    byPostId.set(id, `https://www.facebook.com/groups/${groupId}/permalink/${id}/`);
  }

  function scanAnchor(a) {
    const href = (a.href || '').split('#')[0];
    if (!href || !href.includes('facebook.com')) return;

    let m = href.match(/\\/groups\\/[^/?#]+\\/(?:posts|permalink)\\/(\\d+)/i);
    if (m) {
      addPost(m[1]);
      return;
    }

    if (groupId && (href.includes(`set=g.${groupId}`) || href.includes(`set=gm.${groupId}`))) {
      const fbid = href.match(/[?&]fbid=(\\d+)/i)?.[1];
      if (fbid) addPost(fbid);
      return;
    }

    m = href.match(/facebook\\.com\\/[^/?#]+\\/videos\\/(\\d+)/i)
      || href.match(/[?&]v=(\\d+)/i)
      || href.match(/story_fbid=(\\d+)/i);
    if (m) addPost(m[1]);
  }

  document.querySelectorAll('[role="article"] a[href]').forEach(scanAnchor);
  if (byPostId.size < 2) {
    document.querySelectorAll('a[href]').forEach(scanAnchor);
  }

  return [...byPostId.values()];
}
"""

SCROLL_FEED_JS = """
() => {
  const main = document.querySelector('[role="main"]');
  if (main && main.scrollHeight > main.clientHeight + 50) {
    main.scrollTop = Math.min(main.scrollTop + main.clientHeight * 2, main.scrollHeight);
    return 'main';
  }
  window.scrollTo(0, document.body.scrollHeight);
  return 'window';
}
"""

EXTRACT_GROUP_NAME_JS = """
() => {
  function cleanTitle(raw) {
    return (raw || '')
      // See EXTRACT_PAGE_NAME_JS's cleanTitle comment — unread-badge
      // prefix like "(1) Facebook" isn't part of the real name.
      .replace(/^\\(\\d+\\+?\\)\\s*/, '')
      .replace(/\\s*\\|\\s*Facebook.*$/i, '')
      .replace(/\\s*-\\s*Facebook.*$/i, '')
      // See EXTRACT_PAGE_NAME_JS's cleanTitle comment — verified-badge
      // screen-reader label bleeding into the name.
      .replace(/\\s*(Verified account|Tài khoản đã xác minh)\\s*$/i, '')
      .trim();
  }

  // See EXTRACT_PAGE_NAME_JS's JUNK_NAMES comment — same fix, needed here
  // too so a degraded session's generic Watch/Notifications surface doesn't
  // get accepted as this group's real name.
  const JUNK_NAMES = /^(all|tất cả|watch|reels|notifications|thông báo)$/i;

  const og = document.querySelector('meta[property="og:title"]');
  if (og && og.content) {
    const t = cleanTitle(og.content);
    if (t && !/^facebook$/i.test(t) && !JUNK_NAMES.test(t)) return t;
  }

  for (const sel of ['h1[dir="auto"]', 'h1', '[role="main"] h1', 'a[href*="/groups/"] span']) {
    const el = document.querySelector(sel);
    const t = (el && el.innerText || '').trim();
    if (t && t.length < 200 && !/^(facebook|nhóm)$/i.test(t) && !JUNK_NAMES.test(t)) return t;
  }

  const title = cleanTitle(document.title);
  if (title && !/^facebook$/i.test(title) && !JUNK_NAMES.test(title)) return title;
  return '';
}
"""


class PlaywrightGroupCrawler:
    def __init__(
        self,
        *,
        headless: bool = True,
        storage_state_path: str | Path | dict | None = None,
        user_agent: str | None = None,
        proxy_server: str | None = None,
        proxy_username: str | None = None,
        proxy_password: str | None = None,
        scroll_pause_ms: int = 1500,
        max_scrolls: int = 50,
        max_comments: int = MAX_COMMENTS,
        concurrency: int = 3,
    ) -> None:
        self.headless = headless
        # Either a path to a Playwright storage_state JSON file, or the
        # already-parsed storage_state dict itself (e.g. read from
        # fb_accounts.session_data) — new_context() below accepts both.
        self.storage_state_path = storage_state_path
        # Matches auto_generate_states.py/create_profile.py (the tools that
        # actually create fb_accounts.session_data via a real login) —
        # replaying a session under a DIFFERENT Chrome version than the one
        # it was created with is a fingerprint mismatch Facebook's
        # anti-fraud system can flag; a wave of fresh accounts hit
        # CHECKPOINT within ~20 minutes on Group/Page specifically (not
        # Profile, whose own default already matched at Chrome/124) right
        # after this UA drifted to 128 here.
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        )
        self.proxy_server = proxy_server
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.scroll_pause_ms = scroll_pause_ms
        self.max_scrolls = max_scrolls
        self.max_comments = max_comments
        self.concurrency = max(1, concurrency)
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> PlaywrightGroupCrawler:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            timeout=120_000,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        context_kwargs: dict = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "vi-VN",
            "timezone_id": "Asia/Ho_Chi_Minh",
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
        # Longer default so proxy latency doesn't cause spurious timeouts.
        self._context.set_default_timeout(45_000)
        await Stealth().apply_stealth_async(self._context)
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
        print("Session sẽ tự lưu khi đăng nhập thành công.")

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_sec
        while loop.time() < deadline:
            cookies = await self._context.cookies("https://www.facebook.com")
            if any(c["name"] == "c_user" for c in cookies):
                print("Đăng nhập thành công!")
                await page.close()
                return True
            await asyncio.sleep(2)

        print("Hết thời gian chờ — chưa phát hiện đăng nhập.")
        await page.close()
        return False

    async def refresh_login(self, uid: str, password: str, two_fa_secret: str | None) -> dict | None:
        """Đăng nhập lại tự động qua mbasic.facebook.com khi session đã hết
        hạn (SessionExpiredError) — dùng ngay context đang mở (giữ nguyên
        proxy/UA của batch), không mở context mới. Trả về storage_state đầy
        đủ (cookies + origins/localStorage) nếu thành công, None nếu thất
        bại — caller coi thất bại như checkpoint (không tự refresh được)."""
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

    async def fetch_group_name(self, group_url: str) -> str | None:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        page = await self._context.new_page()
        try:
            await page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            if "checkpoint" in page.url:
                raise CheckpointError(f"Session bị checkpoint khi mở group {group_url} ({page.url})")
            name = await page.evaluate(EXTRACT_GROUP_NAME_JS)
            name = (name or "").strip()
            # A "Join Group" button alone does NOT mean the feed is hidden
            # — that button shows for every non-member on every group,
            # member-restricted or not. Real incident: flagged a group as
            # not_a_member even though the same non-member account could
            # browse its posts fine in a real browser. Only treat it as
            # actually blocked when there's ALSO no real post link
            # findable on the page (the same detection discover_feed_post_urls
            # uses) — that's the real "can't see content" signal.
            if await self._has_join_wall(page):
                group_id = extract_group_id(group_url) or ""
                feed_urls = await page.evaluate(DISCOVER_FEED_URLS_JS, group_id)
                if not feed_urls:
                    raise NotGroupMemberError(
                        f"Tài khoản chưa tham gia group '{name or group_url}' — "
                        "chỉ thấy được thông tin công khai, không thấy bài viết"
                    )
            return name or None
        except (NotGroupMemberError, CheckpointError):
            raise
        except Exception as exc:
            logger.warning("Không lấy được tên nhóm %s: %s", group_url, exc)
            return None
        finally:
            await page.close()

    @staticmethod
    async def _has_join_wall(page: Page) -> bool:
        return await page.evaluate(
            """() => {
                const needles = ['join group', 'tham gia nhóm', 'yêu cầu tham gia', 'request to join'];
                const els = document.querySelectorAll('[role="button"], a, span');
                for (const el of els) {
                    const text = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (needles.includes(text)) return true;
                }
                return false;
            }"""
        )

    async def discover_feed_post_urls(
        self,
        group_url: str,
        *,
        max_scrolls: int | None = None,
    ) -> list[str]:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")

        group_id = extract_group_id(group_url)
        if not group_id:
            raise ValueError(f"Không tìm thấy group_id: {group_url}")

        scrolls = max_scrolls or self.max_scrolls
        page = await self._context.new_page()
        collected: set[str] = set()
        try:
            await page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)

            stale_rounds = 0
            for _ in range(scrolls):
                found = await page.evaluate(DISCOVER_FEED_URLS_JS, group_id)
                before = len(collected)
                collected.update(found)
                if len(collected) == before:
                    stale_rounds += 1
                    if stale_rounds >= 2:
                        break
                else:
                    stale_rounds = 0
                await page.evaluate(SCROLL_FEED_JS)

                # Jittered pause instead of a fixed interval, plus an
                # occasional longer "reading" pause — a metronome-regular
                # scroll cadence is itself a bot signal.
                pause = random.randint(max(500, self.scroll_pause_ms - 500), self.scroll_pause_ms + 700)
                if random.random() < 0.15:
                    pause += random.randint(2000, 4000)
                await page.wait_for_timeout(pause)

            urls = dedupe_post_urls(list(collected), group_id)
            logger.info("Discovered %d post URLs in group %s", len(urls), group_id)
            return urls
        finally:
            await page.close()

    async def fetch_posts_from_urls(
        self,
        urls: list[str],
        *,
        group_id: str | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[Post]:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        if not urls:
            return []

        urls = dedupe_post_urls(urls, group_id)
        total = len(urls)
        logger.info("Fetching %d posts (concurrency=%d)", total, self.concurrency)
        posts: list[Post] = []
        sem = asyncio.Semaphore(self.concurrency)
        done = 0

        async def fetch_one(url: str) -> Post | None:
            nonlocal done
            async with sem:
                page = await self._context.new_page()
                try:
                    canonical = normalize_group_post_url(url, group_id) or url
                    post = await self._extract_post_page(page, canonical)
                    done += 1
                    if on_progress:
                        on_progress(done, total, canonical)
                    if post and (post.topic or post.content or post.author):
                        if group_id and post.group_id in ("unknown", ""):
                            post.group_id = group_id
                        post.comments = post.comments[: self.max_comments]
                        return post
                except CheckpointError:
                    # Account-level, not per-post — must propagate (unlike
                    # the generic except below) so the caller isolates the
                    # account instead of silently hammering the same
                    # checkpointed session for every remaining post.
                    raise
                except Exception as exc:
                    done += 1
                    exc_str = str(exc)
                    if "net::ERR_" in exc_str or "Timeout" in exc_str:
                        # Same signal batch_tasks.py's per-target handler
                        # uses to trigger a proxy reset — swallowing this as
                        # a per-post warning (old behavior) let a genuinely
                        # dead proxy get reused for every remaining post in
                        # the batch instead of ever getting rotated. Raise
                        # so it propagates instead.
                        raise
                    logger.warning("Không crawl được %s: %s", url, exc)
                finally:
                    await page.close()
            return None

        results = await asyncio.gather(*(fetch_one(url) for url in urls))
        posts = [p for p in results if p is not None]
        return posts

    async def _expand_comments(self, page: Page) -> None:
        target = await page.evaluate(
            """() => {
              function parseIntCount(raw) {
                if (!raw) return 0;
                let s = String(raw).trim().replace(/\\s/g, '').replace(',', '.');
                const km = s.match(/^([\\d.]+)([KkMm])$/);
                if (km) {
                  const n = parseFloat(km[1]);
                  if (!Number.isFinite(n)) return 0;
                  return Math.round(n * (km[2].toLowerCase() === 'm' ? 1e6 : 1e3));
                }
                const n = parseFloat(s);
                return Number.isFinite(n) ? Math.round(n) : 0;
              }
              for (const el of document.querySelectorAll('[aria-label], span, div')) {
                const text = (el.getAttribute('aria-label') || el.innerText || '').trim();
                const m = text.match(/([\\d.,]+\\s*[KkMm]?)\\s*bình luận/i)
                  || text.match(/([\\d.,]+\\s*[KkMm]?)\\s*comments?/i);
                if (m) return parseIntCount(m[1]);
              }
              return 0;
            }"""
        )
        capped_target = min(self.max_comments, target) if target > 0 else 0
        if capped_target <= 0:
            return
        # Needs enough rounds to both page through top-level comments AND
        # expand each one's nested replies — the old floor (4 rounds min)
        # left small threads with reply chains only partially expanded.
        max_rounds = min(30, max(10, capped_target + 6))
        await page.evaluate(
            EXPAND_COMMENTS_JS,
            {"maxRounds": max_rounds, "targetCount": capped_target},
        )

    async def _wait_for_post_ready(self, page: Page) -> None:
        try:
            await page.wait_for_selector('[role="article"]', timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(1200)

    async def _try_play_video(self, page: Page) -> None:
        has_video = await page.evaluate(
            """() => {
              if (document.querySelector('video')) return true;
              for (const el of document.querySelectorAll('[aria-label]')) {
                const l = el.getAttribute('aria-label') || '';
                if (/phát video|play video/i.test(l)) return true;
              }
              return false;
            }"""
        )
        if not has_video:
            return
        for selector in (
            '[aria-label="Phát video"]',
            '[aria-label="Play video"]',
            '[aria-label*="Phát video"]',
            '[aria-label*="Play video"]',
        ):
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(1500)
                    return
            except Exception:
                continue

    async def _extract_post_page(self, page: Page, post_url: str) -> Post | None:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        await self._wait_for_post_ready(page)
        await self._try_play_video(page)
        await self._expand_comments(page)
        crawled_at = datetime.now(timezone.utc)
        target_post_id = extract_post_id(post_url)
        data = await page.evaluate(EXTRACT_POST_PAGE_JS, target_post_id)
        await hydrate_precise_comment_times(page, data.get("comments") or [])
        media = await page.evaluate(EXTRACT_MEDIA_JS, target_post_id)
        post = build_post_from_page_data(data, fallback_url=post_url, crawled_at=crawled_at)
        if post:
            post.images = media.get("images") or []
            post.videos = media.get("videos") or []
        if post and (post.topic or post.content or post.author):
            post.comments = post.comments[: self.max_comments]
            if not post.published_at:
                save_time_debug_html(await page.content(), post_url)
            return post
        await page.wait_for_timeout(1500)
        data = await page.evaluate(EXTRACT_POST_PAGE_JS, target_post_id)
        await hydrate_precise_comment_times(page, data.get("comments") or [])
        media = await page.evaluate(EXTRACT_MEDIA_JS, target_post_id)
        post = build_post_from_page_data(data, fallback_url=post_url, crawled_at=crawled_at)
        if post:
            post.images = media.get("images") or []
            post.videos = media.get("videos") or []
        if post:
            post.comments = post.comments[: self.max_comments]
            if not post.published_at:
                save_time_debug_html(await page.content(), post_url)
        return post

    async def fetch_single_post(self, post_url: str) -> Post | None:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        page = await self._context.new_page()
        try:
            return await self._extract_post_page(page, post_url)
        finally:
            await page.close()
