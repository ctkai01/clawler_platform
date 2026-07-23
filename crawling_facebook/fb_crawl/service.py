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
    post_is_within_hours,
)
from fb_crawl.parser import (
    dedupe_post_urls,
    extract_group_id,
    extract_post_id,
    normalize_group_post_url,
)
from fb_crawl.playwright_crawler import PlaywrightGroupCrawler
from fb_crawl.storage import Storage, _from_iso

logger = logging.getLogger(__name__)


@dataclass
class CrawlGroupResult:
    group_id: str
    group_url: str
    group_name: str | None
    crawled_at: datetime
    posts: list[PostCrawlResult]


class GroupCrawlService:
    def __init__(
        self,
        storage: Storage,
        crawler: PlaywrightGroupCrawler,
        *,
        new_post_hours: float = NEW_POST_HOURS,
        recent_comment_minutes: float = RECENT_COMMENT_MINUTES,
        max_posts_per_crawl: int = 40,
    ) -> None:
        self.storage = storage
        self.crawler = crawler
        self.new_post_hours = new_post_hours
        self.recent_comment_minutes = recent_comment_minutes
        # See PageCrawlService's identical field — same real incident
        # (unbounded post-fetch count blowing past RabbitMQ's 30-min ack
        # timeout and killing the whole worker), same fix, Group side.
        self.max_posts_per_crawl = max_posts_per_crawl

    async def crawl_group(self, group_url: str, *, feed_only: bool = False) -> CrawlGroupResult:
        crawled_at = _utcnow()
        group_id = extract_group_id(group_url)
        if not group_id:
            raise ValueError(f"URL nhóm không hợp lệ: {group_url}")

        group_name = await self.crawler.fetch_group_name(group_url)
        self.storage.upsert_group(group_id, group_url, name=group_name)
        if not group_name:
            stored = self.storage.get_group(group_id)
            group_name = (stored or {}).get("name")

        feed_urls = await self.crawler.discover_feed_post_urls(group_url)
        recheck_only: list[str] = []
        recheck_post_ids: set[str] = set()
        if not feed_only:
            recheck_rows = self.storage.list_posts_to_recheck(
                group_id,
                since_hours=max(self.new_post_hours, self.recent_comment_minutes / 60.0),
                source_type="group",
            )
            recheck_post_ids = {r["post_id"] for r in recheck_rows}
            recheck_urls = [
                normalize_group_post_url(r["url"], group_id) or r["url"]
                for r in recheck_rows
                if r.get("url")
            ]
            feed_set = set(feed_urls)
            recheck_only = [u for u in recheck_urls if u not in feed_set]

        # Every post still visible in the feed used to get fully re-fetched
        # (page load + comment expansion) on every crawl, even ones we
        # already have and that aren't due a recheck — most of the cost for
        # an active group, since the feed rarely shrinks. Skip those; keep
        # anything brand new or explicitly due for a recheck.
        known_ids = self.storage.known_post_ids(group_id, source_type="group")
        new_feed_urls = [
            u for u in feed_urls
            if (extract_post_id(u) or u) not in known_ids or (extract_post_id(u) or u) in recheck_post_ids
        ]

        all_urls = dedupe_post_urls(new_feed_urls + recheck_only, group_id)
        capped = len(all_urls) > self.max_posts_per_crawl
        if capped:
            room = max(0, self.max_posts_per_crawl - len(recheck_only))
            all_urls = dedupe_post_urls(new_feed_urls[:room] + recheck_only, group_id)
        logger.info(
            "Crawl %d URL (feed=%d bo qua %d bai da biet, recheck=%d%s%s)",
            len(all_urls),
            len(feed_urls),
            len(feed_urls) - len(new_feed_urls),
            len(recheck_only),
            ", feed-only" if feed_only else "",
            f", cắt bớt (giới hạn {self.max_posts_per_crawl})" if capped else "",
        )

        crawled = await self.crawler.fetch_posts_from_urls(all_urls, group_id=group_id)

        results: list[PostCrawlResult] = []
        for post in crawled:
            if post.group_id in ("unknown", ""):
                post.group_id = group_id
            post.source_type = "group"

            existing = self.storage.get_post(post.post_id)
            is_first_crawl = existing is None
            if existing and existing.get("first_seen_at"):
                first_crawled_at = _from_iso(existing["first_seen_at"]) or crawled_at
            else:
                first_crawled_at = crawled_at

            if is_first_crawl and not post_is_within_hours(post, self.new_post_hours):
                # Discovered for the first time but published long ago (e.g.
                # an old post still sitting in a feed we just started
                # crawling) — only posts that were actually new when we saw
                # them get a permanent record; already-known posts still get
                # updated below regardless of age via the recheck path.
                continue

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

        self.storage.mark_group_synced(group_id)
        return CrawlGroupResult(
            group_id=group_id,
            group_url=group_url,
            group_name=group_name,
            crawled_at=crawled_at,
            posts=results,
        )
