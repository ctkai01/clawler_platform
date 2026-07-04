from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
from bs4 import BeautifulSoup

from platform_app.parsers.base import ParsedComment, ParsedDocument, SiteParser
from platform_app.parsers.http_client import RateLimitedFetcher
from platform_app.parsers.registry import register

# Ported from opencrawler's crawlers/forum_xenforo.py (confirmed live against
# voz.vn, otofun.net, tuoitreit.vn, kenhsinhvien.vn — same XenForo 2.x theme
# markup). Simplified from the original: no multi-page backward reply walk
# (that needs a DB lookup of "largest comment_id already persisted for this
# thread" mid-parse, which doesn't fit this platform's discover_urls/
# fetch_and_parse split) — replies are page-1 only, capped at
# max_top_comments. Quote-stripping/reaction/view-count extraction is
# otherwise unchanged from the reference implementation.
_REACTIONS_NUMBER_RE = re.compile(r"(\d[\d.,]*)")


def _domain(url: str) -> str:
    return urlparse(url).netloc


def _parse_published_at(entry: Any) -> datetime | None:
    struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if struct is not None:
        return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    # XenForo emits "2025-11-26T11:44:14+0700" (no colon in offset) which
    # fromisoformat can't take pre-3.11. Insert the colon defensively.
    v = value
    m = re.match(r"^(.*[T\s].*)([+-])(\d{2})(\d{2})$", v)
    if m:
        v = f"{m.group(1)}{m.group(2)}{m.group(3)}:{m.group(4)}"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_body_variant(body_html: str, *, include_quotes: bool) -> str | None:
    """Return the post's own text. `include_quotes=True` keeps quoted text
    rendered as "[trích dẫn <author>]: <text>" for readability;
    `include_quotes=False` strips quote blocks entirely (used to avoid
    double-counting a brand mention that's only present because it was
    quoted from another post)."""
    soup = BeautifulSoup(body_html, "lxml")
    root = soup.find("div", class_="bbWrapper") or soup.body or soup

    if include_quotes:
        for q in root.select(".bbCodeBlock--quote"):
            author_el = q.select_one(".bbCodeBlock-sourceJump")
            author = (author_el.get_text(strip=True) if author_el else "").strip()
            if author.endswith(" said:"):
                author = author[: -len(" said:")]
            inner = q.select_one(".bbCodeBlock-expandContent") or q.select_one(".bbCodeBlock-content")
            if inner is not None:
                for chrome in inner.select(".bbCodeBlock-expandLink, .bbCodeBlock-title"):
                    chrome.decompose()
                quote_text = inner.get_text(" ", strip=True)
            else:
                quote_text = ""
            marker = f"\n[trích dẫn {author}]: {quote_text}\n" if author else f"\n[trích dẫn]: {quote_text}\n"
            q.replace_with(marker)
        for noise in root.select("script, style, .js-attachments"):
            noise.decompose()
    else:
        for noise in root.select("blockquote, script, style, .bbCodeBlock--quote, .js-attachments"):
            noise.decompose()

    text = root.get_text(separator="\n", strip=True)
    return text or None


def _extract_body(article_el: Any) -> str | None:
    body = article_el.select_one("div.bbWrapper")
    if body is None:
        return None
    return _extract_body_variant(str(body), include_quotes=True)


def _extract_reply(article_el: Any) -> ParsedComment | None:
    post_id_attr = article_el.get("data-content") or ""
    comment_id = post_id_attr.removeprefix("post-")
    if not comment_id:
        return None
    body = _extract_body(article_el)
    if not body:
        return None
    time_el = article_el.select_one("time[datetime]")
    return ParsedComment(
        external_comment_id=comment_id,
        author=article_el.get("data-author"),
        text=body,
        created_at=_parse_iso(time_el.get("datetime")) if time_el is not None else None,
    )


class XenforoParser(SiteParser):
    """Shared parser for forums running XenForo 2.x — one crawl_targets row
    per subforum, url = the subforum's base URL (e.g.
    https://voz.vn/f/diem-bao.33/); discovery via that subforum's built-in
    RSS feed (`{url}index.rss`). NOT for tinhte.vn — see tinhte.py, a
    different (Next.js frontend) engine on the same XenForo backend.

    Expected `config` keys: max_threads_per_run (default 30), max_top_comments
    (default 20), max_history_days (default 14), request_delay_seconds
    (default 1.5).
    """

    parser_key = "xenforo"

    async def discover_urls(self, target_url: str, config: dict) -> list[str]:
        rss_url = urljoin(target_url.rstrip("/") + "/", "index.rss")
        feed = feedparser.parse(rss_url)
        if feed.bozo and not feed.entries:
            raise RuntimeError(f"RSS fetch/parse failed for {rss_url}: {getattr(feed, 'bozo_exception', 'unknown')}")

        max_history_days = config.get("max_history_days", 14)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_history_days)
        max_threads = config.get("max_threads_per_run", 30)

        candidates: list[tuple[datetime, str]] = []
        for entry in feed.entries:
            link = getattr(entry, "link", None)
            if not link:
                continue
            published_at = _parse_published_at(entry)
            if published_at is None or published_at < cutoff:
                continue
            candidates.append((published_at, link.split("?")[0]))

        candidates.sort(key=lambda c: c[0])
        if len(candidates) > max_threads:
            candidates = candidates[-max_threads:]
        return [link for _, link in candidates]

    async def fetch_and_parse(self, url: str, config: dict) -> ParsedDocument | None:
        fetcher = RateLimitedFetcher(min_delay_seconds=config.get("request_delay_seconds", 1.5))
        html = await fetcher.fetch(url)
        soup = BeautifulSoup(html, "lxml")

        posts = soup.select("article.message")
        if not posts:
            return None

        op = posts[0]
        op_body = _extract_body(op)
        if not op_body:
            return None

        title_el = soup.select_one("h1.p-title-value")
        op_time_el = op.select_one("time.u-dt")

        max_top_comments = config.get("max_top_comments", 20)
        comments: list[ParsedComment] = []
        for post in posts[1 : 1 + max_top_comments]:
            reply = _extract_reply(post)
            if reply is not None:
                comments.append(reply)

        return ParsedDocument(
            external_doc_id=f"{_domain(url)}:{urlparse(url).path}",
            url=url,
            author=op.get("data-author"),
            topic=title_el.get_text(strip=True) if title_el else None,
            content=op_body,
            published_at=_parse_iso(op_time_el.get("datetime")) if op_time_el is not None else None,
            comments=comments,
        )


xenforo_parser = register(XenforoParser())
