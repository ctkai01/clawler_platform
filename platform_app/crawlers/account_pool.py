from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from platform_app.crawlers.facebook_runner import FB_SESSION_DIR
from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)


@dataclass
class Account:
    key: str
    session_path: Path
    user_agent: str | None = None


class AccountPool:
    """Postgres-backed health/cooldown tracking for the FB session pool.

    Cookies stay in secrets/fb_sessions/{key}.json exactly as before — this
    pool only tracks LIVE/CHECKPOINT status and a cooldown window, keyed by
    the same string used for crawl_targets.fb_session_key. No auto-login:
    a CHECKPOINT account stays isolated until release_checkpoint() is
    called by an operator who has manually verified it in a real browser
    (see docs/fb-session-pool.md).
    """

    def __init__(self) -> None:
        self.cooldown_minutes = int(os.environ.get("FB_ACCOUNT_COOLDOWN_MINUTES", "15"))

    def _sync_known_accounts(self) -> None:
        """Registers any secrets/fb_sessions/*.json not yet in fb_accounts
        as LIVE. Never touches an existing row's status — dropping a fresh
        session file next to an already-CHECKPOINT account doesn't silently
        un-isolate it; that still requires release_checkpoint()."""
        if not FB_SESSION_DIR.is_dir():
            return
        keys = sorted(p.stem for p in FB_SESSION_DIR.glob("*.json"))
        if not keys:
            return
        with get_pool().connection() as conn:
            for key in keys:
                conn.execute(
                    "INSERT INTO fb_accounts (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                    (key,),
                )

    def _acquire(self, *, key: str | None) -> Account | None:
        self._sync_known_accounts()
        with get_pool().connection() as conn:
            if key:
                row = conn.execute(
                    """
                    UPDATE fb_accounts SET last_used_at = now(), updated_at = now()
                    WHERE id = %s AND status = 'LIVE'
                      AND (last_used_at IS NULL OR last_used_at < now() - (%s * interval '1 minute'))
                    RETURNING id, user_agent
                    """,
                    (key, self.cooldown_minutes),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    UPDATE fb_accounts SET last_used_at = now(), updated_at = now()
                    WHERE id = (
                        SELECT id FROM fb_accounts
                        WHERE status = 'LIVE'
                          AND (last_used_at IS NULL OR last_used_at < now() - (%s * interval '1 minute'))
                        ORDER BY last_used_at ASC NULLS FIRST
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, user_agent
                    """,
                    (self.cooldown_minutes,),
                ).fetchone()
        if row is None:
            return None
        return Account(
            key=row["id"],
            session_path=FB_SESSION_DIR / f"{row['id']}.json",
            user_agent=row["user_agent"],
        )

    def acquire(self) -> Account | None:
        """Any LIVE account off cooldown, oldest-used first — for FB Pages
        that haven't been pinned to a specific account."""
        return self._acquire(key=None)

    def acquire_specific(self, key: str) -> Account | None:
        """That exact account — for FB Groups, which must use an account
        that's actually a member. Returns None if it's CHECKPOINT or still
        on cooldown; the caller should skip this batch rather than guess
        at a substitute."""
        return self._acquire(key=key)

    def release(self, key: str, *, success: bool) -> None:
        with get_pool().connection() as conn:
            if success:
                conn.execute(
                    "UPDATE fb_accounts SET fail_count = 0, updated_at = now() WHERE id = %s",
                    (key,),
                )
            else:
                # One CheckpointError is enough to know the account is
                # locked for every URL, not just this one — isolate
                # immediately rather than waiting for repeated failures.
                conn.execute(
                    """
                    UPDATE fb_accounts
                    SET status = 'CHECKPOINT', fail_count = fail_count + 1, updated_at = now()
                    WHERE id = %s
                    """,
                    (key,),
                )
                logger.error("Tài khoản %s bị checkpoint, đã cách ly khỏi pool.", key)

    def release_checkpoint(self, key: str) -> None:
        """Manual recovery, run after an operator has verified the account
        in a real browser and (if needed) re-exported its session file."""
        with get_pool().connection() as conn:
            conn.execute(
                """
                UPDATE fb_accounts
                SET status = 'LIVE', fail_count = 0, last_used_at = NULL, updated_at = now()
                WHERE id = %s
                """,
                (key,),
            )
        logger.info("Tài khoản %s đã được gỡ cách ly, sẵn sàng hoạt động lại.", key)


def _list_status() -> None:
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT id, status, fail_count, last_used_at FROM fb_accounts ORDER BY id"
        ).fetchall()
    if not rows:
        print("Chưa có account nào trong fb_accounts (chưa acquire() lần nào).")
        return
    for row in rows:
        print(f"{row['id']:<12} {row['status']:<10} fail_count={row['fail_count']:<3} last_used_at={row['last_used_at']}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Quản lý fb_accounts (FB session health pool)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Liệt kê trạng thái mọi account")
    release_parser = sub.add_parser("release-checkpoint", help="Gỡ cách ly 1 account sau khi đã tự xác minh thủ công")
    release_parser.add_argument("key", help="Session key, vd acc1")
    args = parser.parse_args(argv)

    if args.cmd == "status":
        _list_status()
    elif args.cmd == "release-checkpoint":
        AccountPool().release_checkpoint(args.key)
        print(f"Đã gỡ cách ly {args.key}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
