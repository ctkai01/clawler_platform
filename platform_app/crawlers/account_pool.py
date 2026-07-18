from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)


@dataclass
class Account:
    key: str
    session_data: dict
    user_agent: str | None = None
    # Optional — only set for accounts an operator has explicitly opted
    # into auto-refresh (scripts/set_fb_account_credentials.py). None means
    # batch_tasks.py never attempts refresh_login for this account.
    password: str | None = None
    two_fa_secret: str | None = None


class AccountPool:
    """Postgres-backed health/cooldown tracking AND session storage for the
    FB session pool — fb_accounts.session_data (Playwright storage_state:
    cookies + origins/localStorage) is the source of truth, keyed by the
    same string used for crawl_targets.fb_session_key. An account with no
    session_data yet is never handed out. Registering a new account or
    refreshing a session is done via scripts/import_fb_sessions_to_db.py,
    not by dropping a file — there is no filesystem involved here anymore.
    No auto-login: a CHECKPOINT account stays isolated until
    release_checkpoint() is called by an operator who has manually verified
    it in a real browser (see docs/fb-session-pool.md).
    """

    def __init__(self) -> None:
        self.cooldown_minutes = int(os.environ.get("FB_ACCOUNT_COOLDOWN_MINUTES", "15"))

    def _acquire(self, *, key: str | None, require_profile: bool = False) -> Account | None:
        with get_pool().connection() as conn:
            if key:
                row = conn.execute(
                    """
                    UPDATE fb_accounts SET last_used_at = now(), updated_at = now()
                    WHERE id = %s AND status = 'LIVE' AND session_data IS NOT NULL
                      AND (NOT %s OR supports_profile)
                      AND (last_used_at IS NULL OR last_used_at < now() - (%s * interval '1 minute'))
                    RETURNING id, session_data, user_agent, password, two_fa_secret
                    """,
                    (key, require_profile, self.cooldown_minutes),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    UPDATE fb_accounts SET last_used_at = now(), updated_at = now()
                    WHERE id = (
                        SELECT id FROM fb_accounts
                        WHERE status = 'LIVE' AND session_data IS NOT NULL
                          AND (NOT %s OR supports_profile)
                          AND (last_used_at IS NULL OR last_used_at < now() - (%s * interval '1 minute'))
                        ORDER BY last_used_at ASC NULLS FIRST
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING id, session_data, user_agent, password, two_fa_secret
                    """,
                    (require_profile, self.cooldown_minutes),
                ).fetchone()
        if row is None:
            return None
        return Account(
            key=row["id"],
            session_data=row["session_data"],
            user_agent=row["user_agent"],
            password=row["password"],
            two_fa_secret=row["two_fa_secret"],
        )

    def acquire(self, *, require_profile: bool = False) -> Account | None:
        """Any LIVE account off cooldown, oldest-used first — for FB Pages
        that haven't been pinned to a specific account. require_profile
        restricts to accounts an operator has confirmed have a full
        browser-login session (real localStorage) — facebook_profile's
        GraphQL/payload-based crawler needs that; facebook_group/page's
        DOM-scraping doesn't, so they leave this False and can use any
        LIVE account, including ones flagged supports_profile."""
        return self._acquire(key=None, require_profile=require_profile)

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

    def update_session(self, key: str, session_data: dict) -> None:
        """Called by batch_tasks.py after a successful refresh_login() —
        persists the freshly re-authenticated storage_state and clears the
        account back to LIVE, so the very next acquire() (in this batch or
        the next) picks up the new cookies instead of the dead ones."""
        with get_pool().connection() as conn:
            conn.execute(
                """
                UPDATE fb_accounts
                SET session_data = %s, status = 'LIVE', fail_count = 0, updated_at = now()
                WHERE id = %s
                """,
                (Jsonb(session_data), key),
            )
        logger.info("Đã tự động refresh session cho account %s", key)


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
