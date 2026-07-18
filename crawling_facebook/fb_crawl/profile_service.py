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
from fb_crawl.parser import extract_page_id, normalize_page_url
from fb_crawl.playwright_profile_crawler import PlaywrightProfileCrawler
from fb_crawl.storage import Storage, _from_iso

logger = logging.getLogger(__name__)


@dataclass
class CrawlProfileResult:
    profile_id: str
    profile_url: str
    profile_name: str | None
    crawled_at: datetime
    posts: list[PostCrawlResult]


class ProfileCrawlService:
    def __init__(
        self,
        storage: Storage,
        crawler: PlaywrightProfileCrawler,
        *,
        new_post_hours: float = NEW_POST_HOURS,
        recent_comment_minutes: float = RECENT_COMMENT_MINUTES,
    ) -> None:
        self.storage = storage
        self.crawler = crawler
        self.new_post_hours = new_post_hours
        self.recent_comment_minutes = recent_comment_minutes

    async def crawl_profile(self, profile_url: str) -> CrawlProfileResult:
        crawled_at = _utcnow()
        # extract_page_id/normalize_page_url (fb_crawl.parser) already
        # handle profile.php?id=, /people/<slug>/<id>, and plain vanity-slug
        # URLs identically to how they handle a Page — a personal profile
        # and a Page share the same facebook.com/<slug> URL shape.
        profile_id = extract_page_id(profile_url)
        if not profile_id:
            raise ValueError(f"URL Profile không hợp lệ: {profile_url}")
        canonical_url = normalize_page_url(profile_url)

        # discover_posts does the full scroll+scrape+comment pass in one
        # shot (GraphQL/embedded-JSON sniffing, unlike the Page crawler's
        # separate discover-URLs / fetch-each-post phases) — everything
        # within crawler.days_back gets re-walked and re-saved every crawl
        # (fresh engagement numbers), same as Group/Page; new_post_hours
        # below only decides what's worth reporting as "new"/"recent
        # comments" this cycle, not what gets discovered/saved.
        profile_name, discovered = await self.crawler.discover_posts(canonical_url, profile_id=profile_id)

        self.storage.upsert_page(profile_id, canonical_url, name=profile_name)
        if not profile_name:
            stored = self.storage.get_page(profile_id)
            profile_name = (stored or {}).get("name")

        results: list[PostCrawlResult] = []
        for post in discovered:
            existing = self.storage.get_post(post.post_id)
            is_first_crawl = existing is None
            if existing and existing.get("first_seen_at"):
                first_crawled_at = _from_iso(existing["first_seen_at"]) or crawled_at
            else:
                first_crawled_at = crawled_at

            if is_first_crawl and not post_is_within_hours(post, self.new_post_hours):
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

        self.storage.mark_page_synced(profile_id)
        return CrawlProfileResult(
            profile_id=profile_id,
            profile_url=canonical_url,
            profile_name=profile_name,
            crawled_at=crawled_at,
            posts=results,
        )
