from __future__ import annotations

from platform_app.db.pool import get_pool

VALID_MODES = ("normal", "llm_text", "llm_image")


def get_classify_mode(organization_id: int | None = None) -> str:
    """Each org can override the classify mode for itself; the id=1 row
    (organization_id IS NULL) is the fallback default for orgs that haven't."""
    with get_pool().connection() as conn:
        if organization_id is not None:
            row = conn.execute(
                "SELECT classify_mode FROM pipeline_settings WHERE organization_id = %s",
                (organization_id,),
            ).fetchone()
            if row:
                return row["classify_mode"]
        row = conn.execute("SELECT classify_mode FROM pipeline_settings WHERE id = 1").fetchone()
    return row["classify_mode"] if row else "llm_text"


def set_classify_mode(mode: str, organization_id: int | None = None) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"classify_mode không hợp lệ: {mode}")
    with get_pool().connection() as conn:
        if organization_id is None:
            conn.execute(
                "UPDATE pipeline_settings SET classify_mode = %s, updated_at = now() WHERE id = 1",
                (mode,),
            )
        else:
            conn.execute(
                """
                INSERT INTO pipeline_settings (organization_id, classify_mode)
                VALUES (%s, %s)
                ON CONFLICT (organization_id) WHERE organization_id IS NOT NULL
                DO UPDATE SET classify_mode = EXCLUDED.classify_mode, updated_at = now()
                """,
                (organization_id, mode),
            )
