from __future__ import annotations

import re

from psycopg.types.json import Jsonb

from platform_app.db.pool import get_pool
from platform_app.pipeline.text_normalize import fold


def run_keyword_filter(
    *,
    batch_size: int = 200,
    document_ids: list[int] | None = None,
) -> dict:
    """Cost gate before LLM classification: tag each pending document as
    'matched' (with which keywords hit) or 'no_match'. Only 'matched'
    documents proceed to classify().

    Each organization uses ITS OWN keyword selection (organization_keywords
    -> keywords_catalog, managed via /admin/keywords + the org's own
    Entity/Keyword picker) — an org with zero keywords selected gets zero
    matches (nothing proceeds to classify) rather than falling back to
    another org's keywords. Targets with no organization_id (or an
    organization with no keywords configured) never match anything.

    A document only counts as 'matched' if at least one hit is a 'brand'
    (the org's own name) or 'competitor' keyword — a pure 'industry' match
    (generic telecom term, no brand name at all) is too ambiguous ("about
    whom?") to be worth classifying. `brand_focus` records WHICH kind of
    match it was: 'own' (mentions this org) or 'competitor' (mentions a
    competitor but not this org) — both get classified, but the org's main
    dashboard only aggregates 'own' by default; 'competitor' is a separate
    view (see brand_focus filtering in api/routers/org.py).

    `document_ids` narrows to a specific set (used by tests, and for
    on-demand re-filtering)."""
    with get_pool().connection() as conn:
        org_kw_rows = conn.execute(
            """
            SELECT ok.organization_id, kc.term, kc.category
            FROM organization_keywords ok
            JOIN keywords_catalog kc ON kc.id = ok.keyword_id
            WHERE kc.is_active
            """
        ).fetchall()

    matchers_by_org: dict[int, list[tuple[str, str, re.Pattern]]] = {}
    for row in org_kw_rows:
        matchers_by_org.setdefault(row["organization_id"], []).append(
            (row["term"], row["category"], re.compile(r"\b" + re.escape(fold(row["term"])) + r"\b", re.IGNORECASE))
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
            matchers = matchers_by_org.get(row["organization_id"], [])
            text = fold(f"{row['topic'] or ''} {row['content'] or ''}")
            hits = [(term, category) for term, category, pattern in matchers if pattern.search(text)]
            has_brand_hit = any(category == "brand" for _, category in hits)
            has_competitor_hit = any(category == "competitor" for _, category in hits)
            if has_brand_hit or has_competitor_hit:
                brand_focus = "own" if has_brand_hit else "competitor"
                conn.execute(
                    """
                    UPDATE documents SET keyword_status = 'matched', matched_keywords = %s, brand_focus = %s
                    WHERE id = %s
                    """,
                    (Jsonb([term for term, _ in hits]), brand_focus, row["id"]),
                )
                matched += 1
            else:
                conn.execute(
                    "UPDATE documents SET keyword_status = 'no_match', brand_focus = NULL WHERE id = %s",
                    (row["id"],),
                )
                no_match += 1

    return {"matched": matched, "no_match": no_match}
