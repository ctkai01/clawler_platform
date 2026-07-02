from __future__ import annotations

from platform_app.db.pool import get_pool

VALID_MODES = ("normal", "llm_text", "llm_image")


def get_classify_mode() -> str:
    with get_pool().connection() as conn:
        row = conn.execute("SELECT classify_mode FROM pipeline_settings WHERE id = 1").fetchone()
    return row["classify_mode"] if row else "llm_text"


def set_classify_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError(f"classify_mode không hợp lệ: {mode}")
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE pipeline_settings SET classify_mode = %s, updated_at = now() WHERE id = 1",
            (mode,),
        )
