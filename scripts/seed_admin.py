"""Create the first system_admin account. Not exposed via /auth/register on
purpose (register always creates an org_main) — run this once manually."""

from __future__ import annotations

import argparse
import getpass

from platform_app.api.security import hash_password
from platform_app.db.pool import get_pool


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a system_admin user")
    parser.add_argument("email")
    args = parser.parse_args()

    password = getpass.getpass("Mật khẩu cho tài khoản admin: ")
    if len(password) < 8:
        print("Mật khẩu phải từ 8 ký tự trở lên.")
        return 1

    with get_pool().connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = %s", (args.email,)).fetchone()
        if existing is not None:
            print(f"Email {args.email} đã tồn tại (id={existing['id']}).")
            return 1

        row = conn.execute(
            """
            INSERT INTO users (organization_id, email, password_hash, role)
            VALUES (NULL, %s, %s, 'system_admin')
            RETURNING id
            """,
            (args.email, hash_password(password)),
        ).fetchone()

    print(f"Đã tạo system_admin id={row['id']} email={args.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
