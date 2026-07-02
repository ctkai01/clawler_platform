from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from fb_crawl.filters import (
    NEW_POST_HOURS,
    RECENT_COMMENT_MINUTES,
    PostCrawlResult,
    _utcnow,
    classify_post,
)
from fb_crawl.parser import (
    dedupe_page_post_urls,
    extract_page_id,
    normalize_page_post_url,
    normalize_page_url,
)
from fb_crawl.playwright_page_crawler import PlaywrightPageCrawler
from fb_crawl.storage import Storage, _from_iso

logger = logging.getLogger(__name__)


@dataclass
class CrawlPageResult:
    page_id: str
    page_url: str
    page_name: str | None
    crawled_at: datetime
    posts: list[PostCrawlResult]


class PageCrawlService:
    def __init__(
        self,
        storage: Storage,
        crawler: PlaywrightPageCrawler,
        *,
        new_post_hours: float = NEW_POST_HOURS,
        recent_comment_minutes: float = RECENT_COMMENT_MINUTES,
    ) -> None:
        self.storage = storage
        self.crawler = crawler
        self.new_post_hours = new_post_hours
        self.recent_comment_minutes = recent_comment_minutes

    async def crawl_page(self, page_url: str, *, feed_only: bool = False) -> CrawlPageResult:
        crawled_at = _utcnow()
        page_id = extract_page_id(page_url)
        if not page_id:
            raise ValueError(f"URL Page không hợp lệ: {page_url}")

        canonical_url = normalize_page_url(page_url)
        page_name = await self.crawler.fetch_page_name(canonical_url)
        self.storage.upsert_page(page_id, canonical_url, name=page_name)
        if not page_name:
            stored = self.storage.get_page(page_id)
            page_name = (stored or {}).get("name")

        feed_urls = await self.crawler.discover_feed_post_urls(canonical_url)
        recheck_only: list[str] = []
        if not feed_only:
            recheck_rows = self.storage.list_posts_to_recheck(
                page_id,
                since_hours=max(self.new_post_hours, self.recent_comment_minutes / 60.0),
                source_type="page",
            )
            recheck_urls = [
                normalize_page_post_url(r["url"], page_id) or r["url"]
                for r in recheck_rows
                if r.get("url")
            ]
            feed_set = set(feed_urls)
            recheck_only = [u for u in recheck_urls if u not in feed_set]
        all_urls = dedupe_page_post_urls(feed_urls + recheck_only, page_id)
        logger.info(
            "Crawl %d URL (feed=%d, recheck=%d%s)",
            len(all_urls),
            len(feed_urls),
            len(recheck_only),
            ", feed-only" if feed_only else "",
        )

        crawled = await self.crawler.fetch_posts_from_urls(all_urls, page_id=page_id)

        results: list[PostCrawlResult] = []
        for post in crawled:
            post.page_id = page_id
            post.source_type = "page"
            post.group_id = page_id

            existing = self.storage.get_post(post.post_id)
            is_first_crawl = existing is None
            if existing and existing.get("first_seen_at"):
                first_crawled_at = _from_iso(existing["first_seen_at"]) or crawled_at
            else:
                first_crawled_at = crawled_at

            reason = classify_post(
                post,
                self.storage,
                new_post_hours=self.new_post_hours,
                recent_comment_minutes=self.recent_comment_minutes,
            )
            if not reason:
                self.storage.save_post(post)
                self.storage.upsert_comments(post.post_id, post.comments)
                continue

            self.storage.save_post(post)
            self.storage.upsert_comments(post.post_id, post.comments)
            results.append(
                PostCrawlResult(
                    post=post,
                    filter_reason=reason,
                    is_first_crawl=is_first_crawl,
                    first_crawled_at=first_crawled_at,
                    crawled_at=crawled_at,
                )
            )

        self.storage.mark_page_synced(page_id)
        return CrawlPageResult(
            page_id=page_id,
            page_url=canonical_url,
            page_name=page_name,
            crawled_at=crawled_at,
            posts=results,
        )
