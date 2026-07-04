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

# Ported from opencrawler's crawlers/forum_tinhte.py. tinhte.vn runs XenForo
# 2.x on the backend but a custom Next.js frontend — NOTHING like vanilla
# XenForo markup (no article.message, no div.bbWrapper, no <time datetime>),
# hence its own module rather than reusing xenforo.py. Confirmed live: RSS
# discovery works fine at https://tinhte.vn/forums/<slug>/index.rss (an
# earlier attempt to scrape the forum's HTML listing page directly found
# nothing because that page is client-rendered — RSS sidesteps that
# entirely, same as every other forum here).
#
# Simplified from the reference implementation: no multi-page backward reply
# walk (needs a DB lookup mid-parse that doesn't fit discover_urls/
# fetch_and_parse) — replies are page-1 only, capped at max_top_comments.
_QUOTE_AUTHOR_LABEL_RE = re.compile(r"^\s*[^\n\r]*?\s+(?:đã nói|said):\s*↑?\s*", re.UNICODE)


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


def _extract_body_variant(body_html: str, *, include_quotes: bool) -> str | None:
    """Quote handling differs from voz/xenforo.py: quote selector is
    `.bbCodeBlock.bbCodeQuote`, the quoted author lives in `data-author` on
    the quote element itself, and the inline "<author> đã nói: ↑" label is
    stripped since the wrapper marker already names the author."""
    soup = BeautifulSoup(body_html, "lxml")
    root = soup.find("div", class_="xfBody") or soup.body or soup

    if include_quotes:
        for q in root.select(".bbCodeBlock.bbCodeQuote"):
            author = (q.get("data-author") or "").strip()
            inner_text = q.get_text(" ", strip=True)
            inner_text = _QUOTE_AUTHOR_LABEL_RE.sub("", inner_text, count=1)
            inner_text = re.sub(r"\s*Xem thêm\s*$", "", inner_text).strip()
            marker = f"\n[trích dẫn {author}]: {inner_text}\n" if author else f"\n[trích dẫn]: {inner_text}\n"
            q.replace_with(marker)
        for noise in root.select("script, style"):
            noise.decompose()
    else:
        for noise in root.select(".bbCodeBlock.bbCodeQuote, blockquote, script, style"):
            noise.decompose()

    text = root.get_text(separator="\n", strip=True)
    return text or None


_POST_ID_RE = re.compile(r"post-(\d+)")
_REPLY_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _extract_post_id(container_el: Any) -> str | None:
    for a in container_el.select('a[href*="post-"]'):
        m = _POST_ID_RE.search(a.get("href", ""))
        if m:
            return m.group(1)
    return None


def _extract_reply_date(container_el: Any) -> datetime | None:
    """"<author> [<badge>] DD/MM/YYYY" → UTC midnight. Day resolution only —
    tinhte's frontend strips time-of-day for replies."""
    hdr = container_el.select_one(".thread-comment__author")
    if hdr is None:
        return None
    m = _REPLY_DATE_RE.search(hdr.get_text(" ", strip=True))
    if m is None:
        return None
    d, mo, y = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d, tzinfo=timezone.utc)
    except ValueError:
        return None


def _extract_reply(container_el: Any) -> ParsedComment | None:
    comment_id = _extract_post_id(container_el)
    if not comment_id:
        return None
    body_el = container_el.select_one("div.xfBody[data-author]:not(.big)")
    if body_el is None:
        return None
    body = _extract_body_variant(str(body_el), include_quotes=True)
    if not body:
        return None
    return ParsedComment(
        external_comment_id=comment_id,
        author=body_el.get("data-author"),
        text=body,
        created_at=_extract_reply_date(container_el),
    )


class TinhteParser(SiteParser):
    """tinhte.vn — XenForo 2.x backend, custom Next.js frontend. One
    crawl_targets row per subforum, url = the subforum's base URL (e.g.
    https://tinhte.vn/forums/smartphone-tablet.796/); discovery via that
    subforum's RSS feed (`{url}index.rss`) — the forum's HTML listing page
    is client-rendered and has no server-rendered thread links, but
    individual thread pages ARE server-rendered and scrapable.

    Expected `config` keys: max_threads_per_run (default 30), max_top_comments
    (default 20), max_history_days (default 14), request_delay_seconds
    (default 1.5).
    """

    parser_key = "tinhte"

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

        # OP body lives in xfBody[data-author] blocks that are NOT nested
        # inside a reply container; long OPs split into multiple such blocks
        # (editorial section-breaks), concatenated in document order.
        op_blocks = [
            b for b in soup.select("div.xfBody[data-author]") if not b.find_parent(class_="thread-comment__container")
        ]
        if not op_blocks:
            return None

        full_parts = []
        for block in op_blocks:
            text = _extract_body_variant(str(block), include_quotes=True)
            if text and text not in full_parts:
                full_parts.append(text)
        content = "\n\n".join(full_parts)
        if not content:
            return None

        title_el = soup.select_one("h1")
        author = op_blocks[0].get("data-author")

        max_top_comments = config.get("max_top_comments", 20)
        comments: list[ParsedComment] = []
        for container in soup.select(".thread-comment__container")[:max_top_comments]:
            reply = _extract_reply(container)
            if reply is not None:
                comments.append(reply)

        return ParsedDocument(
            external_doc_id=f"{_domain(url)}:{urlparse(url).path}",
            url=url,
            author=author,
            topic=title_el.get_text(strip=True) if title_el else None,
            content=content,
            comments=comments,
        )


tinhte_parser = register(TinhteParser())
