from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedComment:
    external_comment_id: str
    author: str | None
    text: str
    created_at: datetime | None = None
    parent_comment_id: str | None = None
    depth: int = 0


@dataclass
class ParsedDocument:
    external_doc_id: str  # "{domain}:{native_id}" — must stay unique across all forum/news targets
    url: str
    author: str | None
    topic: str | None
    content: str
    published_at: datetime | None = None
    edited_at: datetime | None = None
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    comments: list[ParsedComment] = field(default_factory=list)


class SiteParser(ABC):
    """One implementation per distinct site/domain, not per URL.

    A parser_key is chosen per-domain (crawl_targets.parser_key); adding a new
    URL on an already-supported domain is just a DB row, not code.
    """

    parser_key: str

    @abstractmethod
    async def discover_urls(self, target_url: str, config: dict) -> list[str]:
        """List thread/article URLs to fetch, given a listing/board/section page."""

    @abstractmethod
    async def fetch_and_parse(self, url: str, config: dict) -> ParsedDocument | None:
        """Fetch raw content and parse it into a ParsedDocument."""
