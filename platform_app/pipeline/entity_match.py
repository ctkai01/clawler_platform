from __future__ import annotations

import re

from platform_app.db.pool import get_pool
from platform_app.pipeline.text_normalize import fold


def run_entity_match(*, batch_size: int = 200, document_ids: list[int] | None = None) -> dict:
    """Rule-based, no LLM: tag every not-yet-checked document with any
    entity_gazetteer surface forms found in its text. Runs independently of
    keyword_filter — every document gets checked, not just keyword matches.
    `document_ids` narrows to a specific set (used by tests, and for
    on-demand re-tagging)."""
    with get_pool().connection() as conn:
        gazetteer_rows = conn.execute(
            "SELECT concept_id, canonical_name, surface_form_folded FROM entity_gazetteer WHERE is_active = true"
        ).fetchall()
        if not gazetteer_rows:
            return {"tagged": 0, "processed": 0}
        gazetteer = [
            (r["concept_id"], r["canonical_name"], re.compile(r"\b" + re.escape(r["surface_form_folded"]) + r"\b", re.IGNORECASE))
            for r in gazetteer_rows
        ]

        if document_ids is not None:
            rows = conn.execute(
                """
                SELECT d.id, d.topic, d.content
                FROM documents d
                WHERE NOT EXISTS (SELECT 1 FROM document_entities de WHERE de.document_id = d.id)
                  AND d.id = ANY(%s)
                LIMIT %s
                """,
                (document_ids, batch_size),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT d.id, d.topic, d.content
                FROM documents d
                WHERE NOT EXISTS (SELECT 1 FROM document_entities de WHERE de.document_id = d.id)
                LIMIT %s
                """,
                (batch_size,),
            ).fetchall()

        tagged = 0
        for row in rows:
            text = fold(f"{row['topic'] or ''} {row['content'] or ''}")
            seen_concepts: set[str] = set()
            for concept_id, canonical_name, pattern in gazetteer:
                if concept_id in seen_concepts or not pattern.search(text):
                    continue
                conn.execute(
                    """
                    INSERT INTO document_entities (document_id, concept_id, canonical_name)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (row["id"], concept_id, canonical_name),
                )
                seen_concepts.add(concept_id)
                tagged += 1
            if not seen_concepts:
                # Sentinel row so a document with zero entity matches is
                # still recognized as "already checked" by the NOT EXISTS
                # query above, instead of being re-scanned every run.
                conn.execute(
                    """
                    INSERT INTO document_entities (document_id, concept_id, canonical_name)
                    VALUES (%s, '__none__', '__none__') ON CONFLICT DO NOTHING
                    """,
                    (row["id"],),
                )

    return {"tagged": tagged, "processed": len(rows)}
