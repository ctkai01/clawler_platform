from __future__ import annotations

import logging
import sys
from pathlib import Path

from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations() -> None:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            logger.info("Applying migration %s", path.name)
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    sys.exit(0)
