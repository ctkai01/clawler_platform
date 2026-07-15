from __future__ import annotations

import argparse
import json
import logging

from psycopg.types.json import Jsonb

from platform_app.crawlers.facebook_runner import FB_SESSION_DIR
from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)


def _import_one(conn, key: str, session_path) -> None:
    session_data = json.loads(session_path.read_text(encoding="utf-8"))
    conn.execute(
        """
        INSERT INTO fb_accounts (id, session_data)
        VALUES (%s, %s)
        ON CONFLICT (id) DO UPDATE SET session_data = EXCLUDED.session_data, updated_at = now()
        """,
        (key, Jsonb(session_data)),
    )
    logger.info("Đã import session cho account %s", key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import session FB (secrets/fb_sessions/*.json) vào fb_accounts.session_data. "
        "Chạy không tham số để import tất cả, hoặc truyền 1 key để import/refresh riêng account đó "
        "(vd sau khi chạy `fb-crawl login` lại)."
    )
    parser.add_argument("key", nargs="?", help="Session key, vd acc1 — bỏ trống để import tất cả")
    args = parser.parse_args(argv)

    if args.key:
        paths = [FB_SESSION_DIR / f"{args.key}.json"]
        if not paths[0].exists():
            parser.error(f"Không tìm thấy {paths[0]}")
    else:
        if not FB_SESSION_DIR.is_dir():
            parser.error(f"Thư mục {FB_SESSION_DIR} không tồn tại")
        paths = sorted(FB_SESSION_DIR.glob("*.json"))
        if not paths:
            logger.warning("Không có file .json nào trong %s", FB_SESSION_DIR)
            return 0

    with get_pool().connection() as conn:
        for path in paths:
            _import_one(conn, path.stem, path)

    logger.info("Xong — đã import %d session.", len(paths))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
