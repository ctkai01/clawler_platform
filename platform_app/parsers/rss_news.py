from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
from bs4 import BeautifulSoup

from platform_app.parsers.base import ParsedComment, ParsedDocument, SiteParser
from platform_app.parsers.http_client import RateLimitedFetcher
from platform_app.parsers.registry import register

# Ported from opencrawler's crawlers/news_rss.py — feedparser handles RSS/Atom
# edge cases (encodings, malformed feeds) far better than hand-rolled XML
# parsing, and this date-parsing logic specifically works around a real bug:
# tuoitre.vn's <pubDate> is plain "M/D/YYYY h:mm:ss AM/PM" with no timezone or
# weekday marker (not RFC822) — neither feedparser's own struct_time fields
# nor email.utils.parsedate_to_datetime can parse it, so every entry would
# silently fail date parsing and get skipped. Assumed Vietnam local time
# (+07:00), matching the feed's own <lastBuildDate> which does carry "GMT+7".
_TZ_OFFSET_RE = re.compile(r"GMT([+-])(\d{1,2})$")
_US_DATETIME_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*[AP]M$", re.IGNORECASE)
_VN_OFFSET = timezone(timedelta(hours=7))


def _domain(url: str) -> str:
    return urlparse(url).netloc


def _first_match(soup: BeautifulSoup, selector: str | None) -> Any:
    """`selector` may be a comma-separated fallback list, e.g.
    'article.fck_detail, article.content-detail' — return whichever matches
    first, mirroring how these sites vary the wrapper class per section."""
    if not selector:
        return None
    return soup.select_one(selector)


def _parse_published_at(entry: Any) -> datetime | None:
    """Best-effort UTC datetime from an RSS entry. Returns None if unparseable."""
    struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if struct is not None:
        return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)

    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if not raw:
        return None
    raw = raw.strip()

    if _US_DATETIME_RE.match(raw):
        try:
            dt = datetime.strptime(raw, "%m/%d/%Y %I:%M:%S %p")
        except ValueError:
            return None
        return dt.replace(tzinfo=_VN_OFFSET).astimezone(timezone.utc)

    m = _TZ_OFFSET_RE.search(raw)
    if m:
        sign, hours = m.group(1), int(m.group(2))
        raw = _TZ_OFFSET_RE.sub(f"{sign}{hours:02d}00", raw)

    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _content_value(entry: Any) -> str:
    contents = getattr(entry, "content", None)
    if not contents:
        return ""
    first = contents[0] if isinstance(contents, list) else contents
    if isinstance(first, dict):
        return first.get("value", "") or ""
    return str(first)


class RssNewsParser(SiteParser):
    """Config-driven parser for RSS-syndicated Vietnamese news sites — one
    crawl_targets row per site, url=the site's RSS feed. Ported from
    opencrawler's NewsRssCrawler; ~1:1 same selectors/date-parsing, adapted
    to this platform's discover_urls/fetch_and_parse split and async httpx.

    Expected `config` keys: body_selector (required, CSS, comma-separated
    fallbacks ok), title_selector (default 'h1'), max_articles_per_run
    (default 50), max_history_days (default 14), request_delay_seconds
    (default 1.0).
    """

    parser_key = "rss_news"

    async def discover_urls(self, target_url: str, config: dict) -> list[str]:
        feed = feedparser.parse(target_url)
        if feed.bozo and not feed.entries:
            raise RuntimeError(f"RSS fetch/parse failed for {target_url}: {getattr(feed, 'bozo_exception', 'unknown')}")

        max_history_days = config.get("max_history_days", 14)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_history_days)
        max_articles = config.get("max_articles_per_run", 50)

        candidates: list[tuple[datetime, str]] = []
        for entry in feed.entries:
            link = getattr(entry, "link", None)
            if not link:
                continue
            published_at = _parse_published_at(entry)
            if published_at is None or published_at < cutoff:
                continue
            candidates.append((published_at, link))

        candidates.sort(key=lambda c: c[0])  # oldest first
        if len(candidates) > max_articles:
            candidates = candidates[-max_articles:]  # keep newest N
        return [link for _, link in candidates]

    async def fetch_and_parse(self, url: str, config: dict) -> ParsedDocument | None:
        fetcher = RateLimitedFetcher(min_delay_seconds=config.get("request_delay_seconds", 1.0))
        html = await fetcher.fetch(url)
        soup = BeautifulSoup(html, "lxml")

        body_el = _first_match(soup, config.get("body_selector"))
        if body_el is None:
            return None
        for noise in body_el.select("script, style, figure, .ads, [class*=advert]"):
            noise.decompose()
        content = body_el.get_text("\n", strip=True)
        if not content:
            return None

        title_el = _first_match(soup, config.get("title_selector", "h1"))
        author_el = _first_match(soup, config.get("author_selector"))
        date_meta = soup.select_one('meta[name="pubdate"]') or soup.select_one('meta[property="article:published_time"]')
        published_at = _parse_iso(date_meta.get("content")) if date_meta else None

        comments: list[ParsedComment] = []
        comments_selector = config.get("comments_selector")
        if comments_selector:
            for i, el in enumerate(soup.select(comments_selector)[: config.get("max_top_comments", 10)]):
                text = el.get_text(" ", strip=True)
                if not text:
                    continue
                comments.append(ParsedComment(external_comment_id=f"{url}#c{i}", author=None, text=text))

        return ParsedDocument(
            external_doc_id=f"{_domain(url)}:{urlparse(url).path}",
            url=url,
            author=author_el.get_text(strip=True) if author_el else None,
            topic=title_el.get_text(strip=True) if title_el else None,
            content=content,
            published_at=published_at,
            comments=comments,
        )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


rss_news_parser = register(RssNewsParser())
