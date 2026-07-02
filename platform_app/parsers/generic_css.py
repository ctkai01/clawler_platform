from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from platform_app.parsers.base import ParsedComment, ParsedDocument, SiteParser
from platform_app.parsers.registry import register


def _domain(url: str) -> str:
    return urlparse(url).netloc


def _text_or_none(soup: BeautifulSoup, selector: str | None) -> str | None:
    if not selector:
        return None
    el = soup.select_one(selector)
    return el.get_text(strip=True) if el else None


def _date_or_none(soup: BeautifulSoup, selector: str | None, attr: str | None) -> datetime | None:
    if not selector:
        return None
    el = soup.select_one(selector)
    if not el:
        return None
    raw = el.get(attr) if attr else el.get_text(strip=True)
    if not raw:
        return None
    try:
        return date_parser.parse(str(raw))
    except (ValueError, OverflowError):
        return None


class GenericCssParser(SiteParser):
    """Config-driven parser for simple static-HTML forum/news sites.

    No Python code needed to add a new site of this kind — just a
    crawl_targets row with parser_key='generic_css' and CSS selectors in
    `config`. Sites that need JS rendering or unusual markup get a bespoke
    SiteParser under platform_app/parsers/sites/ instead.
    """

    parser_key = "generic_css"

    async def discover_urls(self, target_url: str, config: dict) -> list[str]:
        list_selector = config.get("list_selector")
        if not list_selector:
            return [target_url]

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(target_url)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        urls = []
        for el in soup.select(list_selector):
            href = el.get("href")
            if href:
                urls.append(urljoin(target_url, href))
        return list(dict.fromkeys(urls))  # dedupe, keep order

    async def fetch_and_parse(self, url: str, config: dict) -> ParsedDocument | None:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        content = _text_or_none(soup, config.get("content_selector"))
        if not content:
            return None

        comments: list[ParsedComment] = []
        comment_selector = config.get("comment_selector")
        if comment_selector:
            for i, el in enumerate(soup.select(comment_selector)):
                author = _text_or_none(el, config.get("comment_author_selector"))
                text = _text_or_none(el, config.get("comment_text_selector")) or el.get_text(strip=True)
                if not text:
                    continue
                comments.append(
                    ParsedComment(
                        external_comment_id=f"{url}#comment-{i}",
                        author=author,
                        text=text,
                    )
                )

        return ParsedDocument(
            external_doc_id=f"{_domain(url)}:{urlparse(url).path}",
            url=url,
            author=_text_or_none(soup, config.get("author_selector")),
            topic=_text_or_none(soup, config.get("title_selector")),
            content=content,
            published_at=_date_or_none(soup, config.get("date_selector"), config.get("date_attr")),
            comments=comments,
        )


generic_css_parser = register(GenericCssParser())
