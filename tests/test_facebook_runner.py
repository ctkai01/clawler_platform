from __future__ import annotations

from pathlib import Path

import pytest

from platform_app.crawlers import facebook_runner
from platform_app.targets.repository import CrawlTarget


def _target(id: int, platform_type: str, fb_session_key: str | None = None) -> CrawlTarget:
    return CrawlTarget(
        id=id,
        platform_type=platform_type,
        url=f"https://facebook.com/{platform_type}/{id}",
        parser_key=None,
        external_id=None,
        display_name=None,
        config={},
        crawl_interval_sec=900,
        fb_session_key=fb_session_key,
    )


def test_no_session_dir_falls_back_to_legacy_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(facebook_runner, "FB_SESSION_DIR", tmp_path / "does_not_exist")
    monkeypatch.setattr(facebook_runner, "DEFAULT_SESSION", tmp_path / "legacy.json")

    result = facebook_runner._resolve_session_path(_target(1, "facebook_page"))

    assert result == tmp_path / "legacy.json"


def test_single_session_used_for_pages_and_groups(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "fb_sessions"
    session_dir.mkdir()
    (session_dir / "acc1.json").write_text("{}")
    monkeypatch.setattr(facebook_runner, "FB_SESSION_DIR", session_dir)

    for platform_type in ("facebook_page", "facebook_group"):
        result = facebook_runner._resolve_session_path(_target(1, platform_type))
        assert result == session_dir / "acc1.json"


def test_multiple_sessions_round_robin_pages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "fb_sessions"
    session_dir.mkdir()
    (session_dir / "acc1.json").write_text("{}")
    (session_dir / "acc2.json").write_text("{}")
    monkeypatch.setattr(facebook_runner, "FB_SESSION_DIR", session_dir)

    # id % 2 == 0 -> acc1, id % 2 == 1 -> acc2 (keys sorted alphabetically)
    assert facebook_runner._resolve_session_path(_target(10, "facebook_page")) == session_dir / "acc1.json"
    assert facebook_runner._resolve_session_path(_target(11, "facebook_page")) == session_dir / "acc2.json"


def test_multiple_sessions_round_robin_unassigned_group(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Unassigned groups round-robin same as pages now — requiring manual
    # fb_session_key for every group was pure friction, since many "Public"
    # groups' feeds are readable without joining. Groups that actually need
    # a member account still get one via fetch_group_name's join-wall check
    # raising NotGroupMemberError (see fb_crawl.playwright_crawler).
    session_dir = tmp_path / "fb_sessions"
    session_dir.mkdir()
    (session_dir / "acc1.json").write_text("{}")
    (session_dir / "acc2.json").write_text("{}")
    monkeypatch.setattr(facebook_runner, "FB_SESSION_DIR", session_dir)

    assert facebook_runner._resolve_session_path(_target(10, "facebook_group")) == session_dir / "acc1.json"
    assert facebook_runner._resolve_session_path(_target(11, "facebook_group")) == session_dir / "acc2.json"


def test_explicit_fb_session_key_is_honored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "fb_sessions"
    session_dir.mkdir()
    (session_dir / "acc1.json").write_text("{}")
    (session_dir / "acc2.json").write_text("{}")
    monkeypatch.setattr(facebook_runner, "FB_SESSION_DIR", session_dir)

    result = facebook_runner._resolve_session_path(_target(1, "facebook_group", fb_session_key="acc2"))

    assert result == session_dir / "acc2.json"


def test_explicit_fb_session_key_not_found_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "fb_sessions"
    session_dir.mkdir()
    (session_dir / "acc1.json").write_text("{}")
    monkeypatch.setattr(facebook_runner, "FB_SESSION_DIR", session_dir)

    with pytest.raises(ValueError, match="không tồn tại"):
        facebook_runner._resolve_session_path(_target(1, "facebook_page", fb_session_key="ghost"))
