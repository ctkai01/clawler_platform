from __future__ import annotations

import re
from pathlib import Path

import yaml
from psycopg.types.json import Jsonb

from platform_app.db.pool import get_pool
from platform_app.pipeline.text_normalize import fold

DEFAULT_KEYWORDS_PATH = Path(__file__).resolve().parents[2] / "config" / "keywords.yaml"


def _load_yaml_keywords(path: Path) -> dict[str, list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): [str(v) for v in vs] for k, vs in data.items()}


def _compile_matchers(terms: list[str]) -> list[tuple[str, re.Pattern]]:
    return [(term, re.compile(r"\b" + re.escape(fold(term)) + r"\b", re.IGNORECASE)) for term in terms]


def run_keyword_filter(
    *,
    keywords_path: Path = DEFAULT_KEYWORDS_PATH,
    batch_size: int = 200,
    document_ids: list[int] | None = None,
) -> dict:
    """Cost gate before LLM classification: tag each pending document as
    'matched' (with which keywords hit) or 'no_match'. Only 'matched'
    documents proceed to classify().

    Each real organization uses ITS OWN keyword selection
    (organization_keywords -> keywords_catalog, managed via /admin/keywords
    + the org's own Entity/Keyword picker) — this used to be a UI-only
    preference with zero effect on the actual pipeline (every org silently
    shared one global config/keywords.yaml file instead); it's now
    load-bearing. An org with zero keywords selected gets zero matches
    (nothing proceeds to classify) rather than silently falling back to
    another org's — or an unrelated legacy domain's — keywords.

    Legacy/internal targets (crawl_targets.organization_id IS NULL — the
    separate internal ops dashboard, predates the multi-tenant org model and
    has no organization_keywords selection at all) keep using the global
    YAML file unchanged.

    `document_ids` narrows to a specific set (used by tests, and for
    on-demand re-filtering)."""
    legacy_matchers = _compile_matchers(
        [term for terms in _load_yaml_keywords(keywords_path).values() for term in terms]
    )

    with get_pool().connection() as conn:
        org_kw_rows = conn.execute(
            """
            SELECT ok.organization_id, kc.term
            FROM organization_keywords ok
            JOIN keywords_catalog kc ON kc.id = ok.keyword_id
            WHERE kc.is_active
            """
        ).fetchall()

    matchers_by_org: dict[int, list[tuple[str, re.Pattern]]] = {}
    for row in org_kw_rows:
        matchers_by_org.setdefault(row["organization_id"], []).append(
            (row["term"], re.compile(r"\b" + re.escape(fold(row["term"])) + r"\b", re.IGNORECASE))
        )

    matched = no_match = 0
    with get_pool().connection() as conn:
        base_query = """
            SELECT d.id, d.topic, d.content, ct.organization_id
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            WHERE d.keyword_status = 'pending'
        """
        if document_ids is not None:
            rows = conn.execute(base_query + " AND d.id = ANY(%s) LIMIT %s", (document_ids, batch_size)).fetchall()
        else:
            rows = conn.execute(base_query + " LIMIT %s", (batch_size,)).fetchall()

        for row in rows:
            org_id = row["organization_id"]
            matchers = legacy_matchers if org_id is None else matchers_by_org.get(org_id, [])
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
