from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from platform_app.parsers.base import ParsedComment, ParsedDocument, SiteParser
from platform_app.parsers.registry import register


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except (ValueError, OverflowError):
        return None


def _strip_html(html: str | None) -> str:
    return BeautifulSoup(html or "", "lxml").get_text(strip=True)


class DiscourseJsonParser(SiteParser):
    """Example bespoke plugin: Discourse-forum instances expose a public JSON
    API (no login, no JS rendering needed) that generic_css can't use since
    it isn't selector-driven HTML. Demonstrates that a new site type only
    needs a new file here + one `register()` call — nothing shared changes.
    """

    parser_key = "discourse_json"

    async def discover_urls(self, target_url: str, config: dict) -> list[str]:
        base = target_url.rstrip("/")
        listing_path = config.get("listing_path", "/latest.json")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{base}{listing_path}")
            resp.raise_for_status()
        topics = resp.json().get("topic_list", {}).get("topics", [])
        return [
            f"{base}/t/{topic['slug']}/{topic['id']}.json"
            for topic in topics
            if topic.get("slug") and topic.get("id")
        ]

    async def fetch_and_parse(self, url: str, config: dict) -> ParsedDocument | None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        data = resp.json()
        posts = data.get("post_stream", {}).get("posts", [])
        if not posts:
            return None

        domain = urlparse(url).netloc
        op = posts[0]
        by_number = {p["post_number"]: p["id"] for p in posts if p.get("post_number")}

        comments = [
            ParsedComment(
                external_comment_id=f"{domain}:post:{p['id']}",
                author=p.get("username"),
                text=_strip_html(p.get("cooked")),
                created_at=_parse_dt(p.get("created_at")),
                parent_comment_id=(
                    f"{domain}:post:{by_number[p['reply_to_post_number']]}"
                    if p.get("reply_to_post_number") in by_number
                    else None
                ),
            )
            for p in posts[1:]
        ]

        return ParsedDocument(
            external_doc_id=f"{domain}:topic:{data.get('id')}",
            url=url[: -len(".json")] if url.endswith(".json") else url,
            author=op.get("username"),
            topic=data.get("title"),
            content=_strip_html(op.get("cooked")),
            published_at=_parse_dt(op.get("created_at")),
            comments=comments,
        )


discourse_json_parser = register(DiscourseJsonParser())
