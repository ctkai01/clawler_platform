from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from fb_crawl.facebook_extract import (
    EXPAND_COMMENTS_JS,
    EXTRACT_MEDIA_JS,
    EXTRACT_POST_PAGE_JS,
    build_post_from_page_data,
    hydrate_precise_comment_times,
)
from fb_crawl.parser import (
    dedupe_page_post_urls,
    extract_page_id,
    extract_post_id,
    normalize_page_post_url,
    normalize_page_url,
)
from fb_crawl.types import Post

logger = logging.getLogger(__name__)

MAX_COMMENTS = 100

DISCOVER_PAGE_FEED_URLS_JS = """
(pageKey) => {
  const key = (pageKey || '').toLowerCase();
  const reserved = new Set([
    'groups', 'watch', 'photo', 'permalink.php', 'story.php', 'share',
    'login', 'recover', 'help', 'policies', 'privacy', 'marketplace',
    'gaming', 'reel', 'reels', 'events', 'friends', 'notifications',
    'messages', 'settings', 'pages', 'profile.php', 'people',
  ]);

  function matchesPage(href) {
    if (!key) return true;
    const h = href.toLowerCase();
    if (h.includes('/' + key + '/')) return true;
    if (h.endsWith('/' + key)) return true;
    const m = href.match(/[?&](?:id|page_id)=(\\d+)/i);
    return !!(m && m[1] === key);
  }

  const byPost = new Map();
  document.querySelectorAll('a[href]').forEach((a) => {
    const href = (a.href || '').split('#')[0];
    if (!href || !href.includes('facebook.com')) return;

    let m = href.match(/facebook\\.com\\/([^/?#]+)\\/(?:posts|videos|photos|reels?)\\/([^/?#]+)/i);
    if (m) {
      const slug = m[1];
      const postId = m[2];
      if (reserved.has(slug.toLowerCase())) return;
      if (!matchesPage(href)) return;
      const url = `https://www.facebook.com/${slug}/posts/${postId}`;
      byPost.set(postId, url);
      return;
    }

    if (/permalink\\.php|story\\.php|photo\\.php|watch\\/\\?v=/i.test(href)) {
      if (!matchesPage(href)) return;
      const pid = href.match(/story_fbid=(\\d+)/i)?.[1]
        || href.match(/[?&]fbid=(\\d+)/i)?.[1]
        || href.match(/[?&]v=(\\d+)/i)?.[1]
        || href;
      byPost.set(String(pid), href.split('#')[0]);
    }
  });
  return [...byPost.values()];
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

EXTRACT_PAGE_NAME_JS = """
() => {
  function cleanTitle(raw) {
    return (raw || '')
      .replace(/\\s*\\|\\s*Facebook.*$/i, '')
      .replace(/\\s*-\\s*Facebook.*$/i, '')
      .trim();
  }

  const og = document.querySelector('meta[property="og:title"]');
  if (og && og.content) {
    const t = cleanTitle(og.content);
    if (t && !/^facebook$/i.test(t)) return t;
  }

  for (const sel of [
    'h1[dir="auto"]',
    'h1',
    '[role="main"] h1',
    'a[aria-hidden="false"] span',
    'strong span',
  ]) {
    const el = document.querySelector(sel);
    const t = (el && el.innerText || '').trim();
    if (t && t.length < 200 && !/^(facebook|trang)$/i.test(t)) return t;
  }

  const title = cleanTitle(document.title);
  if (title && !/^facebook$/i.test(title)) return title;
  return '';
}
"""


class PlaywrightPageCrawler:
    def __init__(
        self,
        *,
        headless: bool = True,
        storage_state_path: str | Path | None = None,
        scroll_pause_ms: int = 1500,
        max_scrolls: int = 50,
        max_comments: int = MAX_COMMENTS,
        concurrency: int = 3,
    ) -> None:
        self.headless = headless
        self.storage_state_path = Path(storage_state_path) if storage_state_path else None
        self.scroll_pause_ms = scroll_pause_ms
        self.max_scrolls = max_scrolls
        self.max_comments = max_comments
        self.concurrency = max(1, concurrency)
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> PlaywrightPageCrawler:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            timeout=120_000,
        )
        context_kwargs: dict = {
            "viewport": {"width": 1280, "height": 900},
            "locale": "vi-VN",
        }
        if self.storage_state_path and self.storage_state_path.exists():
            context_kwargs["storage_state"] = str(self.storage_state_path)
        self._context = await self._browser.new_context(**context_kwargs)
        await self._context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type == "font"
            else route.continue_(),
        )
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

    async def fetch_page_name(self, page_url: str) -> str | None:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        page = await self._context.new_page()
        try:
            await page.goto(normalize_page_url(page_url), wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            name = await page.evaluate(EXTRACT_PAGE_NAME_JS)
            name = (name or "").strip()
            return name or None
        except Exception as exc:
            logger.warning("Không lấy được tên Page %s: %s", page_url, exc)
            return None
        finally:
            await page.close()

    async def discover_feed_post_urls(
        self,
        page_url: str,
        *,
        max_scrolls: int | None = None,
    ) -> list[str]:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")

        page_id = extract_page_id(page_url)
        if not page_id:
            raise ValueError(f"Không tìm thấy page_id: {page_url}")

        feed_url = normalize_page_url(page_url)
        scrolls = max_scrolls or self.max_scrolls
        page = await self._context.new_page()
        collected: set[str] = set()
        try:
            await page.goto(feed_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)

            stale_rounds = 0
            for _ in range(scrolls):
                found = await page.evaluate(DISCOVER_PAGE_FEED_URLS_JS, page_id)
                before = len(collected)
                collected.update(found)
                if len(collected) == before:
                    stale_rounds += 1
                    if stale_rounds >= 2:
                        break
                else:
                    stale_rounds = 0
                await page.evaluate(SCROLL_FEED_JS)
                await page.wait_for_timeout(self.scroll_pause_ms)

            urls = dedupe_page_post_urls(list(collected), page_id)
            logger.info("Discovered %d post URLs on page %s", len(urls), page_id)
            return urls
        finally:
            await page.close()

    async def fetch_posts_from_urls(
        self,
        urls: list[str],
        *,
        page_id: str | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[Post]:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        if not urls:
            return []

        urls = dedupe_page_post_urls(urls, page_id)
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
                    canonical = normalize_page_post_url(url, page_id) or url
                    post = await self._extract_post_page(page, canonical)
                    done += 1
                    if on_progress:
                        on_progress(done, total, canonical)
                    if post and (post.topic or post.content or post.author):
                        if page_id:
                            post.page_id = page_id
                            post.source_type = "page"
                            post.group_id = page_id
                        post.comments = post.comments[: self.max_comments]
                        return post
                except Exception as exc:
                    done += 1
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
        data = await page.evaluate(EXTRACT_POST_PAGE_JS)
        await hydrate_precise_comment_times(page, data.get("comments") or [])
        media = await page.evaluate(EXTRACT_MEDIA_JS)
        post = build_post_from_page_data(data, fallback_url=post_url, crawled_at=crawled_at)
        if post:
            post.images = media.get("images") or []
            post.videos = media.get("videos") or []
            post.source_type = "page"
        if post and (post.topic or post.content or post.author):
            post.comments = post.comments[: self.max_comments]
            return post
        await page.wait_for_timeout(1500)
        data = await page.evaluate(EXTRACT_POST_PAGE_JS)
        await hydrate_precise_comment_times(page, data.get("comments") or [])
        media = await page.evaluate(EXTRACT_MEDIA_JS)
        post = build_post_from_page_data(data, fallback_url=post_url, crawled_at=crawled_at)
        if post:
            post.images = media.get("images") or []
            post.videos = media.get("videos") or []
            post.source_type = "page"
            post.comments = post.comments[: self.max_comments]
        return post

    async def fetch_single_post(self, post_url: str) -> Post | None:
        if not self._context:
            raise RuntimeError("Crawler context is not initialized")
        page = await self._context.new_page()
        try:
            return await self._extract_post_page(page, post_url)
        finally:
            await page.close()
