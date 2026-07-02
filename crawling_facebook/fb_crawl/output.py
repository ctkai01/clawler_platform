from __future__ import annotations

from datetime import datetime

from fb_crawl.filters import PostCrawlResult
from fb_crawl.page_service import CrawlPageResult
from fb_crawl.parser import engagement_to_api_dict, normalize_post_engagement
from fb_crawl.service import CrawlGroupResult


def _dt_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt.isoformat()


def comment_to_dict(comment) -> dict:
    return {
        "author": comment.author,
        "author_id": comment.author_id,
        "text": comment.text,
        "created_at": _dt_iso(comment.created_at),
        "is_edited": comment.is_edited,
    }


def _post_content(post) -> str:
    full_content = post.content
    if post.topic and post.topic not in (post.content or ""):
        full_content = f"{post.topic}\n\n{post.content}".strip() if post.content else post.topic
    return full_content


def _post_reactions(post) -> dict:
    eng = normalize_post_engagement(post.engagement)
    engagement = engagement_to_api_dict(eng)
    reactions = engagement.get("reactions") or {}
    return {
        "like": engagement.get("like_count", 0),
        "love": reactions.get("love", 0),
        "haha": reactions.get("haha", 0),
        "wow": reactions.get("wow", 0),
        "sad": reactions.get("sad", 0),
        "angry": reactions.get("angry", 0),
        "care": reactions.get("care", 0),
        "other": reactions.get("other", 0),
        "total": engagement.get("reaction_count", 0),
    }, engagement


def _post_common_fields(item: PostCrawlResult) -> dict:
    post = item.post
    reactions, engagement = _post_reactions(post)
    return {
        "post_id": post.post_id,
        "url": post.url,
        "author": post.author,
        "author_id": post.author_id,
        "published_at": _dt_iso(post.published_at),
        "edited_at": _dt_iso(post.edited_at),
        "is_edited": post.is_edited,
        "content": _post_content(post),
        "images": list(post.images),
        "videos": list(post.videos),
        "reactions": reactions,
        "comment_count": engagement.get("comment_count", len(post.comments)),
        "comments": [comment_to_dict(c) for c in post.comments[:100]],
        "filter_reason": item.filter_reason,
        "is_first_crawl": item.is_first_crawl,
        "first_crawled_at": _dt_iso(item.first_crawled_at),
        "crawled_at": _dt_iso(item.crawled_at),
    }


def group_post_to_dict(item: PostCrawlResult, *, group_name: str | None = None) -> dict:
    post = item.post
    return {
        **_post_common_fields(item),
        "group_id": post.group_id,
        "group_name": group_name,
        "source_type": "group",
    }


def page_post_to_dict(item: PostCrawlResult, *, page_name: str | None = None) -> dict:
    post = item.post
    return {
        **_post_common_fields(item),
        "page_id": post.page_id or post.group_id,
        "page_name": page_name,
        "source_type": "page",
    }


def crawl_result_to_dict(result: CrawlGroupResult) -> dict:
    return {
        "source_type": "group",
        "group_id": result.group_id,
        "group_url": result.group_url,
        "group_name": result.group_name,
        "crawled_at": _dt_iso(result.crawled_at),
        "post_count": len(result.posts),
        "posts": [
            group_post_to_dict(item, group_name=result.group_name)
            for item in result.posts
        ],
    }


def crawl_page_result_to_dict(result: CrawlPageResult) -> dict:
    return {
        "source_type": "page",
        "page_id": result.page_id,
        "page_url": result.page_url,
        "page_name": result.page_name,
        "crawled_at": _dt_iso(result.crawled_at),
        "post_count": len(result.posts),
        "posts": [
            page_post_to_dict(item, page_name=result.page_name)
            for item in result.posts
        ],
    }
