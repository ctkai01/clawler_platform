from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

from platform_app.crawlers.account_pool import AccountPool
from platform_app.db.pool import get_pool


@pytest.fixture
def pool() -> AccountPool:
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM fb_accounts WHERE id LIKE 'test_%'")
    yield AccountPool()
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM fb_accounts WHERE id LIKE 'test_%'")


def _seed(key: str, *, has_session: bool = True, password: str | None = None, two_fa_secret: str | None = None) -> None:
    session_data = {"cookies": []} if has_session else None
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO fb_accounts (id, session_data, password, two_fa_secret) VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                session_data = EXCLUDED.session_data,
                password = EXCLUDED.password,
                two_fa_secret = EXCLUDED.two_fa_secret
            """,
            (key, Jsonb(session_data) if session_data is not None else None, password, two_fa_secret),
        )


def test_acquire_specific_returns_account_with_session_data(pool: AccountPool) -> None:
    _seed("test_acc1")

    account = pool.acquire_specific("test_acc1")

    assert account is not None
    assert account.key == "test_acc1"
    assert account.session_data == {"cookies": []}


def test_acquire_specific_returns_none_for_unknown_key(pool: AccountPool) -> None:
    assert pool.acquire_specific("test_ghost") is None


def test_acquire_specific_skips_account_without_session_data(pool: AccountPool) -> None:
    _seed("test_acc1", has_session=False)

    assert pool.acquire_specific("test_acc1") is None


def test_acquire_any_picks_oldest_used_first(pool: AccountPool) -> None:
    # acquire() (no key) considers every LIVE row in fb_accounts, including
    # real accounts outside this test's "test_%" namespace — bump their
    # last_used_at to "now" for the duration of this test so they can't
    # out-rank test_acc1/test_acc2 on recency, then restore it exactly.
    with get_pool().connection() as conn:
        others = conn.execute(
            "SELECT id, last_used_at FROM fb_accounts WHERE id NOT LIKE 'test_%' AND status = 'LIVE'"
        ).fetchall()
        conn.execute("UPDATE fb_accounts SET last_used_at = now() WHERE id NOT LIKE 'test_%' AND status = 'LIVE'")

    try:
        _seed("test_acc1")
        _seed("test_acc2")

        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE fb_accounts SET last_used_at = now() - interval '30 minutes' WHERE id = %s",
                ("test_acc1",),
            )
            conn.execute(
                "UPDATE fb_accounts SET last_used_at = now() - interval '1 hour' WHERE id = %s",
                ("test_acc2",),
            )

        account = pool.acquire()
    finally:
        with get_pool().connection() as conn:
            for row in others:
                conn.execute(
                    "UPDATE fb_accounts SET last_used_at = %s WHERE id = %s",
                    (row["last_used_at"], row["id"]),
                )

    assert account is not None
    assert account.key == "test_acc2"


def test_acquire_specific_respects_cooldown(pool: AccountPool) -> None:
    _seed("test_acc1")
    pool.acquire_specific("test_acc1")

    assert pool.acquire_specific("test_acc1") is None


def test_release_failure_moves_account_to_checkpoint(pool: AccountPool) -> None:
    _seed("test_acc1")
    pool.acquire_specific("test_acc1")

    pool.release("test_acc1", success=False)

    assert pool.acquire_specific("test_acc1") is None
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT status, fail_count FROM fb_accounts WHERE id = %s", ("test_acc1",)
        ).fetchone()
    assert row["status"] == "CHECKPOINT"
    assert row["fail_count"] == 1


def test_release_checkpoint_restores_availability(pool: AccountPool) -> None:
    _seed("test_acc1")
    pool.acquire_specific("test_acc1")
    pool.release("test_acc1", success=False)
    assert pool.acquire_specific("test_acc1") is None

    pool.release_checkpoint("test_acc1")

    assert pool.acquire_specific("test_acc1") is not None


def test_release_success_resets_fail_count(pool: AccountPool) -> None:
    _seed("test_acc1")
    pool.acquire_specific("test_acc1")
    pool.release("test_acc1", success=False)
    pool.release_checkpoint("test_acc1")

    pool.acquire_specific("test_acc1")
    pool.release("test_acc1", success=True)

    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT fail_count FROM fb_accounts WHERE id = %s", ("test_acc1",)
        ).fetchone()
    assert row["fail_count"] == 0


def test_acquire_returns_credentials_when_set(pool: AccountPool) -> None:
    _seed("test_acc1", password="hunter2", two_fa_secret="JBSWY3DPEHPK3PXP")

    account = pool.acquire_specific("test_acc1")

    assert account is not None
    assert account.password == "hunter2"
    assert account.two_fa_secret == "JBSWY3DPEHPK3PXP"


def test_acquire_returns_none_credentials_when_unset(pool: AccountPool) -> None:
    _seed("test_acc1")

    account = pool.acquire_specific("test_acc1")

    assert account is not None
    assert account.password is None
    assert account.two_fa_secret is None


def test_update_session_replaces_data_and_restores_live(pool: AccountPool) -> None:
    _seed("test_acc1")
    pool.acquire_specific("test_acc1")
    pool.release("test_acc1", success=False)  # -> CHECKPOINT, fail_count=1

    pool.update_session("test_acc1", {"cookies": [{"name": "c_user", "value": "123"}]})

    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT status, fail_count, session_data FROM fb_accounts WHERE id = %s", ("test_acc1",)
        ).fetchone()
    assert row["status"] == "LIVE"
    assert row["fail_count"] == 0
    assert row["session_data"] == {"cookies": [{"name": "c_user", "value": "123"}]}
