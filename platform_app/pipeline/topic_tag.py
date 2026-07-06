from __future__ import annotations

import re

from platform_app.db.pool import get_pool
from platform_app.pipeline.text_normalize import fold


def run_topic_tag(*, batch_size: int = 200, document_ids: list[int] | None = None) -> dict:
    """Tags each not-yet-checked document with the organization_topics row
    whose keywords it matches the most (ties broken by lowest topic id);
    'none' when zero topics match — reported as "KHÁC". Runs independently
    of keyword_filter's match gate, same as entity_match — topic
    classification isn't about LLM-spend gating, it's "which product/service
    does this post concern" for reporting. Only orgs with at least one
    topic+keyword defined are considered; documents in orgs with none
    defined are left at topic_tag_status='pending' indefinitely (harmless —
    the report treats "no topics defined for this org" as "everything is
    KHÁC" without needing a DB scan)."""
    with get_pool().connection() as conn:
        topic_rows = conn.execute(
            """
            SELECT ot.id AS topic_id, ot.organization_id, otk.keyword
            FROM organization_topics ot
            JOIN organization_topic_keywords otk ON otk.topic_id = ot.id
            """
        ).fetchall()

    matchers_by_org: dict[int, list[tuple[int, re.Pattern]]] = {}
    for row in topic_rows:
        matchers_by_org.setdefault(row["organization_id"], []).append(
            (row["topic_id"], re.compile(r"\b" + re.escape(fold(row["keyword"])) + r"\b", re.IGNORECASE))
        )

    if not matchers_by_org:
        return {"tagged": 0, "none": 0}

    org_ids = list(matchers_by_org.keys())
    tagged = untagged = 0
    with get_pool().connection() as conn:
        base_query = """
            SELECT d.id, d.topic, d.content, ct.organization_id
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            WHERE d.topic_tag_status = 'pending' AND ct.organization_id = ANY(%s)
        """
        if document_ids is not None:
            rows = conn.execute(
                base_query + " AND d.id = ANY(%s) LIMIT %s",
                (org_ids, document_ids, batch_size),
            ).fetchall()
        else:
            rows = conn.execute(base_query + " LIMIT %s", (org_ids, batch_size)).fetchall()

        for row in rows:
            matchers = matchers_by_org[row["organization_id"]]
            text = fold(f"{row['topic'] or ''} {row['content'] or ''}")
            counts: dict[int, int] = {}
            for topic_id, pattern in matchers:
                n = len(pattern.findall(text))
                if n:
                    counts[topic_id] = counts.get(topic_id, 0) + n

            if counts:
                best_topic_id = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]
                conn.execute(
                    "UPDATE documents SET topic_tag_id = %s, topic_tag_status = 'tagged' WHERE id = %s",
                    (best_topic_id, row["id"]),
                )
                tagged += 1
            else:
                conn.execute(
                    "UPDATE documents SET topic_tag_status = 'none' WHERE id = %s",
                    (row["id"],),
                )
                untagged += 1

    return {"tagged": tagged, "none": untagged}
