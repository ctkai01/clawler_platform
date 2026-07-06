from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from platform_app.api.deps import require_roles
from platform_app.api.schemas import (
    EntityGazetteerCreate,
    EntityGazetteerOut,
    EntityGazetteerUpdate,
    KeywordCatalogCreate,
    KeywordCatalogOut,
    KeywordCatalogUpdate,
    OrganizationOut,
    TopicCreate,
    TopicImportResult,
    TopicKeywordCreate,
    TopicKeywordOut,
    TopicOut,
)
from platform_app.db.pool import get_pool
from platform_app.pipeline.text_normalize import fold

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles("system_admin"))])


# ---------------------------------------------------------------------------
# Entities — read/write entity_gazetteer directly (grouped by canonical_name)
# rather than a separately curated entity_catalog, so the Admin screen and
# the crawl/classify pipeline share one source of truth. `entity_gazetteer`
# has many rows per brand (one per surface form); this groups them into the
# "one row per brand" shape the Admin table shows.
# ---------------------------------------------------------------------------


@router.get("/entities", response_model=list[EntityGazetteerOut])
def list_entities() -> list[dict]:
    with get_pool().connection() as conn:
        return conn.execute(
            """
            SELECT canonical_name,
                   MAX(canonical_display_name) AS canonical_display_name,
                   MAX(industry_code) AS industry_code,
                   COUNT(*) AS surface_form_count,
                   BOOL_OR(is_active) AS is_active
            FROM entity_gazetteer
            GROUP BY canonical_name
            ORDER BY canonical_name
            """
        ).fetchall()


@router.post("/entities", response_model=EntityGazetteerOut, status_code=status.HTTP_201_CREATED)
def create_entity(body: EntityGazetteerCreate) -> dict:
    with get_pool().connection() as conn:
        existing = conn.execute(
            "SELECT id FROM entity_gazetteer WHERE concept_id = %s AND surface_form = %s",
            (body.concept_id, body.surface_form),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Surface form này đã tồn tại cho concept_id đó")
        conn.execute(
            """
            INSERT INTO entity_gazetteer
                (concept_id, canonical_name, canonical_display_name, surface_form, surface_form_folded,
                 industry_code, entity_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                body.concept_id,
                body.canonical_name,
                body.canonical_name,
                body.surface_form,
                fold(body.surface_form),
                body.industry_code,
                body.entity_type,
            ),
        )
        return conn.execute(
            """
            SELECT canonical_name,
                   MAX(canonical_display_name) AS canonical_display_name,
                   MAX(industry_code) AS industry_code,
                   COUNT(*) AS surface_form_count,
                   BOOL_OR(is_active) AS is_active
            FROM entity_gazetteer WHERE canonical_name = %s
            GROUP BY canonical_name
            """,
            (body.canonical_name,),
        ).fetchone()


@router.patch("/entities/{canonical_name}", response_model=EntityGazetteerOut)
def update_entity(canonical_name: str, body: EntityGazetteerUpdate) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có trường nào để cập nhật")
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_pool().connection() as conn:
        updated = conn.execute(
            f"UPDATE entity_gazetteer SET {set_clause} WHERE canonical_name = %s RETURNING id",
            (*fields.values(), canonical_name),
        ).fetchall()
        if not updated:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy entity")
        return conn.execute(
            """
            SELECT canonical_name,
                   MAX(canonical_display_name) AS canonical_display_name,
                   MAX(industry_code) AS industry_code,
                   COUNT(*) AS surface_form_count,
                   BOOL_OR(is_active) AS is_active
            FROM entity_gazetteer WHERE canonical_name = %s
            GROUP BY canonical_name
            """,
            (canonical_name,),
        ).fetchone()


@router.delete("/entities/{canonical_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(canonical_name: str) -> None:
    with get_pool().connection() as conn:
        result = conn.execute(
            "DELETE FROM entity_gazetteer WHERE canonical_name = %s RETURNING id", (canonical_name,)
        ).fetchall()
        if not result:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy entity")


@router.get("/keywords", response_model=list[KeywordCatalogOut])
def list_keywords() -> list[dict]:
    with get_pool().connection() as conn:
        return conn.execute("SELECT * FROM keywords_catalog ORDER BY category, term").fetchall()


@router.post("/keywords", response_model=KeywordCatalogOut, status_code=status.HTTP_201_CREATED)
def create_keyword(body: KeywordCatalogCreate) -> dict:
    with get_pool().connection() as conn:
        existing = conn.execute(
            "SELECT id FROM keywords_catalog WHERE category = %s AND term = %s", (body.category, body.term)
        ).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Từ khóa đã tồn tại trong nhóm này")
        return conn.execute(
            "INSERT INTO keywords_catalog (category, term) VALUES (%s, %s) RETURNING *",
            (body.category, body.term),
        ).fetchone()


@router.patch("/keywords/{keyword_id}", response_model=KeywordCatalogOut)
def update_keyword(keyword_id: int, body: KeywordCatalogUpdate) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có trường nào để cập nhật")
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    with get_pool().connection() as conn:
        row = conn.execute(
            f"UPDATE keywords_catalog SET {set_clause} WHERE id = %s RETURNING *",
            (*fields.values(), keyword_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy từ khóa")
        return row


@router.delete("/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(keyword_id: int) -> None:
    with get_pool().connection() as conn:
        result = conn.execute(
            "DELETE FROM keywords_catalog WHERE id = %s RETURNING id", (keyword_id,)
        ).fetchone()
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy từ khóa")


# ---------------------------------------------------------------------------
# Topics — per-organization "chủ đề" + keyword lists, admin-managed (manual
# entry or CSV import). platform_app.pipeline.topic_tag tags each document
# with whichever topic's keywords it matches most. Distinct from
# keywords_catalog (global Stage-1 cost gate) and entity_gazetteer
# (brand/company NLP matching) — this is literal per-org keyword grouping
# purely for the "báo cáo theo chủ đề" report section.
# ---------------------------------------------------------------------------


def _reset_topic_tags(conn, organization_id: int) -> None:
    """Whenever an org's topic/keyword set changes, previously-tagged (or
    previously-'none') documents must be re-evaluated against the new rules
    — otherwise edits after the first tagging pass would silently never
    apply."""
    conn.execute(
        """
        UPDATE documents SET topic_tag_id = NULL, topic_tag_status = 'pending'
        WHERE target_id IN (SELECT id FROM crawl_targets WHERE organization_id = %s)
        """,
        (organization_id,),
    )


@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations() -> list[dict]:
    with get_pool().connection() as conn:
        return conn.execute("SELECT id, name FROM organizations ORDER BY name").fetchall()


@router.get("/organizations/{organization_id}/topics", response_model=list[TopicOut])
def list_topics(organization_id: int) -> list[dict]:
    with get_pool().connection() as conn:
        topics = conn.execute(
            "SELECT id, name FROM organization_topics WHERE organization_id = %s ORDER BY name",
            (organization_id,),
        ).fetchall()
        keywords = conn.execute(
            """
            SELECT otk.id, otk.topic_id, otk.keyword
            FROM organization_topic_keywords otk
            JOIN organization_topics ot ON ot.id = otk.topic_id
            WHERE ot.organization_id = %s
            ORDER BY otk.keyword
            """,
            (organization_id,),
        ).fetchall()
    keywords_by_topic: dict[int, list[dict]] = {}
    for kw in keywords:
        keywords_by_topic.setdefault(kw["topic_id"], []).append({"id": kw["id"], "keyword": kw["keyword"]})
    return [{"id": t["id"], "name": t["name"], "keywords": keywords_by_topic.get(t["id"], [])} for t in topics]


@router.post("/organizations/{organization_id}/topics", response_model=TopicOut, status_code=status.HTTP_201_CREATED)
def create_topic(organization_id: int, body: TopicCreate) -> dict:
    with get_pool().connection() as conn:
        existing = conn.execute(
            "SELECT id FROM organization_topics WHERE organization_id = %s AND name = %s",
            (organization_id, body.name),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Chủ đề này đã tồn tại cho tổ chức")
        row = conn.execute(
            "INSERT INTO organization_topics (organization_id, name) VALUES (%s, %s) RETURNING id, name",
            (organization_id, body.name),
        ).fetchone()
    return {"id": row["id"], "name": row["name"], "keywords": []}


@router.delete("/organizations/{organization_id}/topics/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(organization_id: int, topic_id: int) -> None:
    with get_pool().connection() as conn:
        result = conn.execute(
            "DELETE FROM organization_topics WHERE id = %s AND organization_id = %s RETURNING id",
            (topic_id, organization_id),
        ).fetchone()
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy chủ đề")
        _reset_topic_tags(conn, organization_id)


@router.post(
    "/organizations/{organization_id}/topics/{topic_id}/keywords",
    response_model=TopicKeywordOut,
    status_code=status.HTTP_201_CREATED,
)
def create_topic_keyword(organization_id: int, topic_id: int, body: TopicKeywordCreate) -> dict:
    with get_pool().connection() as conn:
        topic = conn.execute(
            "SELECT id FROM organization_topics WHERE id = %s AND organization_id = %s",
            (topic_id, organization_id),
        ).fetchone()
        if topic is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy chủ đề")
        existing = conn.execute(
            "SELECT id FROM organization_topic_keywords WHERE topic_id = %s AND keyword = %s",
            (topic_id, body.keyword),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Từ khóa này đã có trong chủ đề")
        row = conn.execute(
            "INSERT INTO organization_topic_keywords (topic_id, keyword) VALUES (%s, %s) RETURNING id, keyword",
            (topic_id, body.keyword),
        ).fetchone()
        _reset_topic_tags(conn, organization_id)
    return row


@router.delete(
    "/organizations/{organization_id}/topics/{topic_id}/keywords/{keyword_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_topic_keyword(organization_id: int, topic_id: int, keyword_id: int) -> None:
    with get_pool().connection() as conn:
        result = conn.execute(
            """
            DELETE FROM organization_topic_keywords otk
            USING organization_topics ot
            WHERE otk.topic_id = ot.id AND ot.id = %s AND ot.organization_id = %s AND otk.id = %s
            RETURNING otk.id
            """,
            (topic_id, organization_id, keyword_id),
        ).fetchone()
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy từ khóa")
        _reset_topic_tags(conn, organization_id)


@router.post("/organizations/{organization_id}/topics/import", response_model=TopicImportResult)
def import_topics(organization_id: int, file: UploadFile = File(...)) -> dict:
    """Bulk-replace CSV with columns: chu_de,tu_khoa (one row per topic+keyword
    pair — see scripts/mau_import_chu_de_tu_khoa.csv). Replaces the org's
    ENTIRE topic set, not a merge — re-exporting/re-importing the source
    spreadsheet is the intended update workflow, so a deleted row in the
    sheet must actually disappear here too."""
    raw = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames is None or "chu_de" not in reader.fieldnames or "tu_khoa" not in reader.fieldnames:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File CSV cần có cột 'chu_de' và 'tu_khoa'.")

    rows = list(reader)
    errors: list[str] = []
    pairs: list[tuple[str, str]] = []
    for i, row in enumerate(rows, start=2):
        topic = (row.get("chu_de") or "").strip()
        keyword = (row.get("tu_khoa") or "").strip()
        if not topic or not keyword:
            errors.append(f"Dòng {i}: thiếu chu_de hoặc tu_khoa")
            continue
        pairs.append((topic, keyword))

    with get_pool().connection() as conn:
        conn.execute("DELETE FROM organization_topics WHERE organization_id = %s", (organization_id,))
        topic_ids: dict[str, int] = {}
        keyword_count = 0
        for topic, keyword in pairs:
            if topic not in topic_ids:
                topic_row = conn.execute(
                    "INSERT INTO organization_topics (organization_id, name) VALUES (%s, %s) RETURNING id",
                    (organization_id, topic),
                ).fetchone()
                topic_ids[topic] = topic_row["id"]
            conn.execute(
                """
                INSERT INTO organization_topic_keywords (topic_id, keyword)
                VALUES (%s, %s) ON CONFLICT (topic_id, keyword) DO NOTHING
                """,
                (topic_ids[topic], keyword),
            )
            keyword_count += 1
        _reset_topic_tags(conn, organization_id)

    return {
        "total_rows": len(rows),
        "topics": len(topic_ids),
        "keywords": keyword_count,
        "errors": errors,
    }
