from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fb_crawl.storage import Storage
from fb_crawl.types import Comment, Post

NEW_POST_HOURS = 48.0
RECENT_COMMENT_MINUTES = 60.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class PostCrawlResult:
    post: Post
    filter_reason: str
    is_first_crawl: bool
    first_crawled_at: datetime
    crawled_at: datetime


def post_is_within_hours(post: Post, hours: float) -> bool:
    published = _ensure_utc(post.published_at)
    if not published:
        return True
    cutoff = _utcnow() - timedelta(hours=hours)
    return published >= cutoff


def comment_is_recent(comment: Comment, minutes: float) -> bool:
    created = _ensure_utc(comment.created_at)
    if not created:
        return False
    cutoff = _utcnow() - timedelta(minutes=minutes)
    return created >= cutoff


def post_has_recent_comments(post: Post, minutes: float = RECENT_COMMENT_MINUTES) -> bool:
    return any(comment_is_recent(c, minutes) for c in post.comments)


def post_has_new_comments_since_storage(
    post: Post,
    storage: Storage,
    minutes: float = RECENT_COMMENT_MINUTES,
) -> bool:
    if post_has_recent_comments(post, minutes):
        return True
    known = storage.known_comment_ids(post.post_id)
    if not known:
        return post_has_recent_comments(post, minutes)
    for comment in post.comments:
        if comment.comment_id not in known:
            if comment_is_recent(comment, minutes) or not comment.created_at:
                return True
    return False


def classify_post(
    post: Post,
    storage: Storage,
    *,
    new_post_hours: float = NEW_POST_HOURS,
    recent_comment_minutes: float = RECENT_COMMENT_MINUTES,
) -> str | None:
    if post_is_within_hours(post, new_post_hours):
        return "new_post"
    if post_has_new_comments_since_storage(post, storage, recent_comment_minutes):
        return "recent_comments"
    return None
