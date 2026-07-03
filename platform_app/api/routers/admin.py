from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from platform_app.api.deps import require_roles
from platform_app.api.schemas import (
    EntityGazetteerCreate,
    EntityGazetteerOut,
    EntityGazetteerUpdate,
    KeywordCatalogCreate,
    KeywordCatalogOut,
    KeywordCatalogUpdate,
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
