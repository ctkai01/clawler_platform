from __future__ import annotations

import re
from pathlib import Path

import yaml
from psycopg.types.json import Jsonb

from platform_app.db.pool import get_pool
from platform_app.pipeline.text_normalize import fold

DEFAULT_KEYWORDS_PATH = Path(__file__).resolve().parents[2] / "config" / "keywords.yaml"


def _load_keywords(path: Path) -> dict[str, list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): [str(v) for v in vs] for k, vs in data.items()}


def _compile_matchers(keywords: dict[str, list[str]]) -> list[tuple[str, re.Pattern]]:
    matchers = []
    for terms in keywords.values():
        for term in terms:
            matchers.append((term, re.compile(r"\b" + re.escape(fold(term)) + r"\b", re.IGNORECASE)))
    return matchers


def run_keyword_filter(
    *,
    keywords_path: Path = DEFAULT_KEYWORDS_PATH,
    batch_size: int = 200,
    document_ids: list[int] | None = None,
) -> dict:
    """Cost gate before LLM classification: tag each pending document as
    'matched' (with which keywords hit) or 'no_match'. Only 'matched'
    documents proceed to classify(). `document_ids` narrows to a specific
    set (used by tests, and for on-demand re-filtering)."""
    matchers = _compile_matchers(_load_keywords(keywords_path))
    matched = no_match = 0
    with get_pool().connection() as conn:
        if document_ids is not None:
            rows = conn.execute(
                "SELECT id, topic, content FROM documents WHERE keyword_status = 'pending' AND id = ANY(%s) LIMIT %s",
                (document_ids, batch_size),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, topic, content FROM documents WHERE keyword_status = 'pending' LIMIT %s",
                (batch_size,),
            ).fetchall()
        for row in rows:
            text = fold(f"{row['topic'] or ''} {row['content'] or ''}")
            hits = [term for term, pattern in matchers if pattern.search(text)]
            if hits:
                conn.execute(
                    "UPDATE documents SET keyword_status = 'matched', matched_keywords = %s WHERE id = %s",
                    (Jsonb(hits), row["id"]),
                )
                matched += 1
            else:
                conn.execute(
                    "UPDATE documents SET keyword_status = 'no_match' WHERE id = %s",
                    (row["id"],),
                )
                no_match += 1
    return {"matched": matched, "no_match": no_match}
