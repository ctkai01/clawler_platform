from __future__ import annotations

import argparse
import getpass
import logging

from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Điền password + 2FA secret cho 1 account FB, để bật tính năng tự động "
        "refresh session khi hết hạn (batch_tasks.py's refresh_login). Account không có "
        "credentials thì đơn giản không tự refresh, giữ hành vi cũ. Đọc qua stdin ẩn "
        "(getpass) — không lộ qua lịch sử shell/log."
    )
    parser.add_argument("key", help="Session key, vd acc1")
    args = parser.parse_args(argv)

    with get_pool().connection() as conn:
        exists = conn.execute("SELECT 1 FROM fb_accounts WHERE id = %s", (args.key,)).fetchone()
        if not exists:
            parser.error(f"Không tìm thấy account '{args.key}' trong fb_accounts — import session trước bằng scripts/import_fb_sessions_to_db.py")

        password = getpass.getpass(f"Password cho {args.key}: ")
        if not password:
            parser.error("Password không được để trống")
        two_fa_secret = getpass.getpass(f"2FA secret cho {args.key} (Enter nếu account không bật 2FA): ")

        conn.execute(
            "UPDATE fb_accounts SET password = %s, two_fa_secret = %s, updated_at = now() WHERE id = %s",
            (password, two_fa_secret or None, args.key),
        )

    logger.info("Đã lưu credentials cho account %s.", args.key)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
