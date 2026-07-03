from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from platform_app.api.deps import get_current_user, require_roles
from platform_app.api.schemas import (
    OrgEntitySelectRequest,
    OrgEntitySelection,
    OrgKeywordSelection,
    SourceCreate,
    SourceImportResult,
    SourceOut,
)
from platform_app.db.pool import get_pool

VALID_PLATFORM_TYPES = {"facebook_group", "facebook_page", "forum", "news"}

router = APIRouter(prefix="/org", tags=["org"], dependencies=[Depends(require_roles("org_main", "org_sub"))])

# Configurator-only mutations: org_main always qualifies; org_sub needs the
# 'configurator' functional_role. Kept as its own dependency (not just a
# frontend guard) per the "enforce data-scope server-side" note in the
# architecture doc — an org_sub with report_viewer must not be able to
# write, even by calling the API directly.
def _require_configurator(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] == "org_main":
        return user
    if user["role"] == "org_sub" and user["functional_role"] == "configurator":
        return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Cần quyền configurator")


def _owns_target(conn, user: dict, target_id: int) -> bool:
    """A target is writable by this user iff it belongs to their org, and
    (for org_sub) is in their explicitly-granted access list."""
    row = conn.execute(
        "SELECT organization_id FROM crawl_targets WHERE id = %s", (target_id,)
    ).fetchone()
    if row is None or row["organization_id"] != user["organization_id"]:
        return False
    if user["role"] == "org_sub" and target_id not in (user["accessible_target_ids"] or []):
        return False
    return True


# ---------------------------------------------------------------------------
# Sources (crawl_targets scoped to the caller's organization)
# ---------------------------------------------------------------------------


@router.get("/sources", response_model=list[SourceOut])
def list_sources(user: dict = Depends(get_current_user)) -> list[dict]:
    with get_pool().connection() as conn:
        if user["role"] == "org_sub":
            ids = user["accessible_target_ids"] or []
            if not ids:
                return []
            return conn.execute(
                "SELECT * FROM crawl_targets WHERE organization_id = %s AND id = ANY(%s) ORDER BY created_at DESC",
                (user["organization_id"], ids),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM crawl_targets WHERE organization_id = %s ORDER BY created_at DESC",
            (user["organization_id"],),
        ).fetchall()


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(body: SourceCreate, user: dict = Depends(_require_configurator)) -> dict:
    with get_pool().connection() as conn:
        existing = conn.execute(
            "SELECT id FROM crawl_targets WHERE platform_type = %s AND url = %s",
            (body.platform_type, body.url),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Nguồn crawl đã tồn tại")
        return conn.execute(
            """
            INSERT INTO crawl_targets (platform_type, url, display_name, crawl_interval_sec, organization_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (body.platform_type, body.url, body.display_name, body.crawl_interval_sec, user["organization_id"]),
        ).fetchone()


@router.post("/sources/import", response_model=SourceImportResult)
def import_sources(file: UploadFile = File(...), user: dict = Depends(_require_configurator)) -> dict:
    """Bulk-add sources from a CSV with columns: platform_type,url,display_name
    (display_name optional). Bad/duplicate rows are skipped (not fatal) so
    one typo doesn't block the rest of the file — reasons are returned in
    `errors` keyed by row number so the user can fix and re-upload just
    those rows."""
    raw = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))

    if reader.fieldnames is None or "platform_type" not in reader.fieldnames or "url" not in reader.fieldnames:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "File CSV cần có cột 'platform_type' và 'url' (tuỳ chọn: 'display_name').",
        )

    inserted = 0
    errors: list[str] = []
    total_rows = 0

    with get_pool().connection() as conn:
        for i, row in enumerate(reader, start=2):  # start=2: row 1 is the header
            total_rows += 1
            platform_type = (row.get("platform_type") or "").strip()
            url = (row.get("url") or "").strip()
            display_name = (row.get("display_name") or "").strip() or None

            if platform_type not in VALID_PLATFORM_TYPES:
                errors.append(f"Dòng {i}: platform_type '{platform_type}' không hợp lệ")
                continue
            if not url:
                errors.append(f"Dòng {i}: thiếu url")
                continue

            result = conn.execute(
                """
                INSERT INTO crawl_targets (platform_type, url, display_name, organization_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (platform_type, url) DO NOTHING
                RETURNING id
                """,
                (platform_type, url, display_name, user["organization_id"]),
            ).fetchone()
            if result is not None:
                inserted += 1
            else:
                errors.append(f"Dòng {i}: nguồn đã tồn tại, bỏ qua")

    return {
        "total_rows": total_rows,
        "inserted": inserted,
        "skipped": total_rows - inserted,
        "errors": errors,
    }


@router.delete("/sources/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(target_id: int, user: dict = Depends(_require_configurator)) -> None:
    with get_pool().connection() as conn:
        if not _owns_target(conn, user, target_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nguồn crawl")
        conn.execute("DELETE FROM crawl_targets WHERE id = %s", (target_id,))


# ---------------------------------------------------------------------------
# Entity / keyword tracking selection
# ---------------------------------------------------------------------------


@router.get("/entities", response_model=list[OrgEntitySelection])
def list_org_entities(user: dict = Depends(get_current_user)) -> list[dict]:
    with get_pool().connection() as conn:
        return conn.execute(
            """
            SELECT eg.canonical_name AS canonical_name,
                   (oe.organization_id IS NOT NULL) AS is_selected
            FROM (SELECT DISTINCT canonical_name FROM entity_gazetteer WHERE is_active = true) eg
            LEFT JOIN organization_entities oe
                ON oe.canonical_name = eg.canonical_name AND oe.organization_id = %s
            ORDER BY eg.canonical_name
            """,
            (user["organization_id"],),
        ).fetchall()


@router.post("/entities/select", status_code=status.HTTP_204_NO_CONTENT)
def select_entity(body: OrgEntitySelectRequest, user: dict = Depends(_require_configurator)) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO organization_entities (organization_id, canonical_name)
            VALUES (%s, %s) ON CONFLICT DO NOTHING
            """,
            (user["organization_id"], body.canonical_name),
        )


@router.post("/entities/deselect", status_code=status.HTTP_204_NO_CONTENT)
def deselect_entity(body: OrgEntitySelectRequest, user: dict = Depends(_require_configurator)) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "DELETE FROM organization_entities WHERE organization_id = %s AND canonical_name = %s",
            (user["organization_id"], body.canonical_name),
        )


@router.get("/keywords", response_model=list[OrgKeywordSelection])
def list_org_keywords(user: dict = Depends(get_current_user)) -> list[dict]:
    with get_pool().connection() as conn:
        return conn.execute(
            """
            SELECT kc.id AS keyword_id, kc.category, kc.term,
                   (ok.organization_id IS NOT NULL) AS is_selected
            FROM keywords_catalog kc
            LEFT JOIN organization_keywords ok
                ON ok.keyword_id = kc.id AND ok.organization_id = %s
            WHERE kc.is_active = true
            ORDER BY kc.category, kc.term
            """,
            (user["organization_id"],),
        ).fetchall()


@router.post("/keywords/{keyword_id}/select", status_code=status.HTTP_204_NO_CONTENT)
def select_keyword(keyword_id: int, user: dict = Depends(_require_configurator)) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO organization_keywords (organization_id, keyword_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user["organization_id"], keyword_id),
        )


@router.delete("/keywords/{keyword_id}/select", status_code=status.HTTP_204_NO_CONTENT)
def deselect_keyword(keyword_id: int, user: dict = Depends(_require_configurator)) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "DELETE FROM organization_keywords WHERE organization_id = %s AND keyword_id = %s",
            (user["organization_id"], keyword_id),
        )


# ---------------------------------------------------------------------------
# Report — same shape of numbers as the internal /report dashboard page,
# but scoped to the caller's organization (and further to their granted
# targets if they're an org_sub) rather than a free-text entity filter.
# ---------------------------------------------------------------------------


@router.get("/report")
def org_report(days: int = Query(default=7, ge=1, le=365), user: dict = Depends(get_current_user)) -> dict:
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)

    target_filter = ""
    params: list = [user["organization_id"], period_start, period_end]
    if user["role"] == "org_sub":
        ids = user["accessible_target_ids"] or []
        if not ids:
            return {
                "total_posts": 0,
                "total_comments": 0,
                "total_reactions": 0,
                "total_shares": 0,
                "sentiment_positive": 0,
                "sentiment_negative": 0,
                "sentiment_neutral": 0,
            }
        target_filter = "AND d.target_id = ANY(%s)"
        params.append(ids)

    with get_pool().connection() as conn:
        kpis = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_posts,
                COALESCE(SUM(d.comment_count), 0) AS total_comments,
                COALESCE(SUM(d.reaction_count), 0) AS total_reactions,
                COALESCE(SUM(d.share_count), 0) AS total_shares
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            WHERE ct.organization_id = %s AND d.published_at >= %s AND d.published_at <= %s
            {target_filter}
            """,
            params,
        ).fetchone()

        sentiment_rows = conn.execute(
            f"""
            SELECT d.classification_sentiment AS sentiment, COUNT(*) AS count
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            WHERE ct.organization_id = %s AND d.published_at >= %s AND d.published_at <= %s
              AND d.classification_status = 'completed' AND d.classification_sentiment IS NOT NULL
            {target_filter}
            GROUP BY d.classification_sentiment
            """,
            params,
        ).fetchall()

    sentiment_map = {r["sentiment"]: r["count"] for r in sentiment_rows}
    return {
        **kpis,
        "sentiment_positive": sentiment_map.get("positive", 0),
        "sentiment_negative": sentiment_map.get("negative", 0),
        "sentiment_neutral": sentiment_map.get("neutral", 0),
    }
