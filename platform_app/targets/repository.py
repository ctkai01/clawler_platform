from __future__ import annotations

import json
from dataclasses import dataclass

from platform_app.db.pool import get_pool


@dataclass
class CrawlTarget:
    id: int
    platform_type: str
    url: str
    parser_key: str | None
    external_id: str | None
    display_name: str | None
    config: dict
    crawl_interval_sec: int
    fb_session_key: str | None = None


def _row_to_target(row: dict) -> CrawlTarget:
    return CrawlTarget(
        id=row["id"],
        platform_type=row["platform_type"],
        url=row["url"],
        parser_key=row["parser_key"],
        external_id=row["external_id"],
        display_name=row["display_name"],
        config=row["config"] or {},
        crawl_interval_sec=row["crawl_interval_sec"],
        fb_session_key=row.get("fb_session_key"),
    )


def get_target(target_id: int) -> CrawlTarget | None:
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT id, platform_type, url, parser_key, external_id, display_name, config, crawl_interval_sec,
                   fb_session_key
            FROM crawl_targets WHERE id = %s
            """,
            (target_id,),
        ).fetchone()
    return _row_to_target(row) if row else None


def get_due_targets(platform_type: str, *, limit: int = 50) -> list[CrawlTarget]:
    pool = get_pool()
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT id, platform_type, url, parser_key, external_id, display_name, config, crawl_interval_sec,
                   fb_session_key
            FROM crawl_targets
            WHERE platform_type = %s AND enabled
              AND (
                  last_crawled_at IS NULL
                  OR last_crawled_at < now() - (crawl_interval_sec * interval '1 second')
              )
            ORDER BY priority, last_crawled_at NULLS FIRST
            LIMIT %s
            """,
            (platform_type, limit),
        ).fetchall()
    return [_row_to_target(r) for r in rows]


def mark_running(target_id: int) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE crawl_targets SET last_status = 'running', updated_at = now() WHERE id = %s",
            (target_id,),
        )


def mark_success(target_id: int) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE crawl_targets
            SET last_status = 'ok',
                last_error = NULL,
                last_crawled_at = now(),
                last_success_at = now(),
                consecutive_failures = 0,
                updated_at = now()
            WHERE id = %s
            """,
            (target_id,),
        )


def mark_failed(target_id: int, error: str, *, status: str = "error") -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE crawl_targets
            SET last_status = %s,
                last_error = %s,
                last_crawled_at = now(),
                consecutive_failures = consecutive_failures + 1,
                updated_at = now()
            WHERE id = %s
            """,
            (status, error, target_id),
        )


def seed_target(
    platform_type: str,
    url: str,
    *,
    parser_key: str | None = None,
    display_name: str | None = None,
    crawl_interval_sec: int = 3600,
    config: dict | None = None,
    enabled: bool = True,
) -> int:
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO crawl_targets (platform_type, url, parser_key, display_name, crawl_interval_sec, config, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (platform_type, url) WHERE organization_id IS NULL DO UPDATE SET
                parser_key = EXCLUDED.parser_key,
                display_name = COALESCE(EXCLUDED.display_name, crawl_targets.display_name),
                crawl_interval_sec = EXCLUDED.crawl_interval_sec,
                config = EXCLUDED.config,
                enabled = EXCLUDED.enabled,
                updated_at = now()
            RETURNING id
            """,
            (platform_type, url, parser_key, display_name, crawl_interval_sec, json.dumps(config or {}), enabled),
        ).fetchone()
    return row["id"]
