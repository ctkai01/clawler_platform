"""Data queries for the social-listening report page (/report).

Modeled on opencrawler's daily-report queries (opencrawler/reports/daily_data.py)
but adapted to this project's schema and to the user's explicit choice that
"chủ đề" (topic) rows in the report ARE entities (from document_entities),
not a separately-classified topic taxonomy — so there's no new classification
stage here, just grouping by already-tagged entities.

Every query is scoped to `entity_text`: free text the user types (e.g.
"mobifone"), matched against document_entities.canonical_name / concept_id
via ILIKE. Empty entity_text means "no entity filter, all documents".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from platform_app.db.pool import get_pool

_CHANNEL_PREFIX = {
    "facebook_group": "FB Group",
    "facebook_page": "FB Page",
    "facebook_profile": "FB Profile",
    "forum": "Forum",
    "news": "News",
}


def _entity_pattern(entity_text: str) -> str | None:
    text = entity_text.strip()
    if not text:
        return None
    # Escape user-typed % / _ so they can't accidentally widen the match.
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _entity_exists_clause(pattern: str | None) -> tuple[str, tuple]:
    if pattern is None:
        return "", ()
    return (
        """
        AND EXISTS (
            SELECT 1 FROM document_entities de
            WHERE de.document_id = d.id AND de.concept_id != '__none__'
              AND (de.canonical_name ILIKE %s OR de.concept_id ILIKE %s)
        )
        """,
        (pattern, pattern),
    )


def get_kpis(entity_text: str, period_start: datetime, period_end: datetime) -> dict[str, int]:
    pattern = _entity_pattern(entity_text)
    entity_clause, entity_params = _entity_exists_clause(pattern)
    with get_pool().connection() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_posts,
                COALESCE(SUM(comment_count), 0) AS total_comments,
                COALESCE(SUM(reaction_count), 0) AS total_reactions,
                COALESCE(SUM(share_count), 0) AS total_shares
            FROM documents d
            WHERE published_at >= %s AND published_at <= %s
            {entity_clause}
            """,
            (period_start, period_end, *entity_params),
        ).fetchone()
    return dict(row)


def get_sentiment_distribution(entity_text: str, period_start: datetime, period_end: datetime) -> list[dict[str, Any]]:
    pattern = _entity_pattern(entity_text)
    entity_clause, entity_params = _entity_exists_clause(pattern)
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT classification_sentiment AS sentiment, COUNT(*) AS count
            FROM documents d
            WHERE classification_status = 'completed'
              AND classification_sentiment IS NOT NULL
              AND published_at >= %s AND published_at <= %s
            {entity_clause}
            GROUP BY classification_sentiment
            """,
            (period_start, period_end, *entity_params),
        ).fetchall()
    return list(rows)


def get_topic_detail(entity_text: str, period_start: datetime, period_end: datetime, limit: int = 15) -> list[dict[str, Any]]:
    """'Chủ đề' rows = entity canonical_name (per the user's explicit
    direction — topics are entities, not a separate classified taxonomy).
    A document tagged with N entities contributes to N topic rows."""
    pattern = _entity_pattern(entity_text)
    entity_clause, entity_params = _entity_exists_clause(pattern)
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT de.canonical_name AS topic,
                   COUNT(DISTINCT d.id) AS posts,
                   COALESCE(SUM(d.comment_count), 0) AS comments,
                   COALESCE(SUM(d.reaction_count) + SUM(d.comment_count), 0) AS total_engagement
            FROM documents d
            JOIN document_entities de ON de.document_id = d.id AND de.concept_id != '__none__'
            WHERE d.published_at >= %s AND d.published_at <= %s
            {entity_clause}
            GROUP BY de.canonical_name
            ORDER BY posts DESC
            LIMIT %s
            """,
            (period_start, period_end, *entity_params, limit),
        ).fetchall()
    return list(rows)


def get_topic_by_sentiment(entity_text: str, period_start: datetime, period_end: datetime, limit: int = 15) -> list[dict[str, Any]]:
    pattern = _entity_pattern(entity_text)
    entity_clause, entity_params = _entity_exists_clause(pattern)
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            WITH top_topics AS (
                SELECT de.canonical_name AS topic, COUNT(DISTINCT d.id) AS posts
                FROM documents d
                JOIN document_entities de ON de.document_id = d.id AND de.concept_id != '__none__'
                WHERE d.published_at >= %s AND d.published_at <= %s
                {entity_clause}
                GROUP BY de.canonical_name
                ORDER BY posts DESC
                LIMIT %s
            )
            SELECT de.canonical_name AS topic, d.classification_sentiment AS sentiment, COUNT(DISTINCT d.id) AS count
            FROM documents d
            JOIN document_entities de ON de.document_id = d.id AND de.concept_id != '__none__'
            JOIN top_topics tt ON tt.topic = de.canonical_name
            WHERE d.published_at >= %s AND d.published_at <= %s
              AND d.classification_status = 'completed'
              AND d.classification_sentiment IS NOT NULL
            {entity_clause}
            GROUP BY de.canonical_name, d.classification_sentiment
            """,
            (period_start, period_end, *entity_params, limit, period_start, period_end, *entity_params),
        ).fetchall()
    return list(rows)


def count_by_sentiment(entity_text: str, period_start: datetime, period_end: datetime, sentiment: str) -> int:
    pattern = _entity_pattern(entity_text)
    entity_clause, entity_params = _entity_exists_clause(pattern)
    with get_pool().connection() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM documents d
            WHERE classification_status = 'completed'
              AND classification_sentiment = %s
              AND published_at >= %s AND published_at <= %s
            {entity_clause}
            """,
            (sentiment, period_start, period_end, *entity_params),
        ).fetchone()
    return row["n"]


def get_top_posts(
    entity_text: str, period_start: datetime, period_end: datetime, *, sentiment: str, limit: int = 5
) -> list[dict[str, Any]]:
    pattern = _entity_pattern(entity_text)
    entity_clause, entity_params = _entity_exists_clause(pattern)
    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT d.id, d.topic, d.content, d.url, d.author, d.platform_type,
                   ct.display_name AS target_name,
                   (COALESCE(d.reaction_count, 0) + COALESCE(d.comment_count, 0)) AS engagement_total
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            WHERE d.classification_sentiment = %s
              AND d.published_at >= %s AND d.published_at <= %s
            {entity_clause}
            ORDER BY engagement_total DESC, d.published_at DESC
            LIMIT %s
            """,
            (sentiment, period_start, period_end, *entity_params, limit),
        ).fetchall()

    posts = []
    for row in rows:
        title = row["topic"] or (row["content"][:80] + "…" if len(row["content"]) > 80 else row["content"])
        channel_prefix = _CHANNEL_PREFIX.get(row["platform_type"], row["platform_type"])
        channel_label = f"{channel_prefix}: {row['author'] or row['target_name']}"
        posts.append(
            {
                "id": row["id"],
                "title": title,
                "url": row["url"],
                "channel_label": channel_label,
                "engagement_total": row["engagement_total"],
            }
        )
    return posts
