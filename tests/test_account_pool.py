from __future__ import annotations

from pathlib import Path

import pytest

from platform_app.crawlers import account_pool as account_pool_module
from platform_app.crawlers.account_pool import AccountPool
from platform_app.db.pool import get_pool


@pytest.fixture
def session_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    d = tmp_path / "fb_sessions"
    d.mkdir()
    monkeypatch.setattr(account_pool_module, "FB_SESSION_DIR", d)
    return d


@pytest.fixture
def pool() -> AccountPool:
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM fb_accounts WHERE id LIKE 'test_%'")
    yield AccountPool()
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM fb_accounts WHERE id LIKE 'test_%'")


def _touch(session_dir: Path, key: str) -> None:
    (session_dir / f"{key}.json").write_text("{}")


def test_sync_registers_new_session_files_as_live(session_dir: Path, pool: AccountPool) -> None:
    _touch(session_dir, "test_acc1")

    account = pool.acquire_specific("test_acc1")

    assert account is not None
    assert account.key == "test_acc1"
    assert account.session_path == session_dir / "test_acc1.json"


def test_acquire_specific_returns_none_for_unknown_key(session_dir: Path, pool: AccountPool) -> None:
    assert pool.acquire_specific("test_ghost") is None


def test_acquire_any_picks_oldest_used_first(session_dir: Path, pool: AccountPool) -> None:
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
        _touch(session_dir, "test_acc1")
        _touch(session_dir, "test_acc2")
        pool._sync_known_accounts()

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


def test_acquire_specific_respects_cooldown(session_dir: Path, pool: AccountPool) -> None:
    _touch(session_dir, "test_acc1")
    pool.acquire_specific("test_acc1")

    assert pool.acquire_specific("test_acc1") is None


def test_release_failure_moves_account_to_checkpoint(session_dir: Path, pool: AccountPool) -> None:
    _touch(session_dir, "test_acc1")
    pool.acquire_specific("test_acc1")

    pool.release("test_acc1", success=False)

    assert pool.acquire_specific("test_acc1") is None
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT status, fail_count FROM fb_accounts WHERE id = %s", ("test_acc1",)
        ).fetchone()
    assert row["status"] == "CHECKPOINT"
    assert row["fail_count"] == 1


def test_release_checkpoint_restores_availability(session_dir: Path, pool: AccountPool) -> None:
    _touch(session_dir, "test_acc1")
    pool.acquire_specific("test_acc1")
    pool.release("test_acc1", success=False)
    assert pool.acquire_specific("test_acc1") is None

    pool.release_checkpoint("test_acc1")

    assert pool.acquire_specific("test_acc1") is not None


def test_release_success_resets_fail_count(session_dir: Path, pool: AccountPool) -> None:
    _touch(session_dir, "test_acc1")
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
