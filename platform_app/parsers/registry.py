from __future__ import annotations

from platform_app.parsers.base import SiteParser

_REGISTRY: dict[str, SiteParser] = {}


def register(parser: SiteParser) -> SiteParser:
    if parser.parser_key in _REGISTRY:
        raise ValueError(f"parser_key đã tồn tại: {parser.parser_key}")
    _REGISTRY[parser.parser_key] = parser
    return parser


def get_parser(parser_key: str) -> SiteParser:
    try:
        return _REGISTRY[parser_key]
    except KeyError:
        raise ValueError(f"Không tìm thấy parser cho parser_key={parser_key!r}") from None
