from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from fb_crawl.page_service import PageCrawlService
from fb_crawl.playwright_crawler import PlaywrightGroupCrawler
from fb_crawl.playwright_page_crawler import PlaywrightPageCrawler
from fb_crawl.service import GroupCrawlService
from fb_crawl.types import CheckpointError, NotGroupMemberError

from platform_app.adapters.fb_pg_storage import PgStorage
from platform_app.crawlers.proxy_pool import ProxyPool
from platform_app.targets import repository
from platform_app.targets.repository import CrawlTarget

logger = logging.getLogger(__name__)

# Module-level so the round-robin cycle (and any future reset-cooldown
# state) is shared across every crawl_target() call in this process,
# rather than restarting from the first proxy each time.
_proxy_pool = ProxyPool()

# Legacy single-session path — kept as the final fallback so a VPS that
# hasn't set up FB_SESSION_DIR yet (no `fb_sessions/` directory) keeps
# working exactly as before this change.
DEFAULT_SESSION = Path(
    os.environ.get("FB_SESSION_PATH", str(Path.home() / ".fb_crawl" / "fb_session.json"))
)
FB_SESSION_DIR = Path(
    os.environ.get("FB_SESSION_DIR", str(Path.home() / ".fb_crawl" / "sessions"))
)


def _resolve_session_key(target: CrawlTarget) -> str | None:
    """Picks which FB account (by session key, e.g. "acc1") should crawl
    `target` — the string half of session resolution, split out from
    _resolve_session_path so callers that need to GROUP targets by account
    (batch dispatch) don't have to reverse-engineer a key back out of a Path.

    Both pages and unassigned groups round-robin across whatever session
    files exist. Groups ideally use an account that's actually a member
    (set fb_session_key explicitly for those), but requiring that up front
    for every group was pure friction: many "Public" groups' feeds are
    readable without joining, so most auto-assigned groups just work. For
    the ones that don't, fetch_group_name's join-wall check raises
    NotGroupMemberError with a specific, actionable status instead of
    silently reporting a 0-document "success" — see crawl_target below.

    Returns None only when there's no session pool directory at all (the
    legacy single-DEFAULT_SESSION setup) — callers resolving to a Path
    fall back to DEFAULT_SESSION in that case.
    """
    keys = sorted(p.stem for p in FB_SESSION_DIR.glob("*.json")) if FB_SESSION_DIR.is_dir() else []

    if target.fb_session_key:
        if target.fb_session_key not in keys:
            raise ValueError(
                f"fb_session_key={target.fb_session_key!r} không tồn tại trong {FB_SESSION_DIR}"
            )
        return target.fb_session_key

    if not keys:
        return None
    if len(keys) == 1:
        # Single-account setup (today's default everywhere) — no pool to
        # choose from, behave exactly like the old single-file DEFAULT_SESSION.
        return keys[0]

    return keys[target.id % len(keys)]


def _resolve_session_path(target: CrawlTarget) -> Path:
    """Picks which FB account's session file to crawl `target` with — see
    _resolve_session_key for the selection logic."""
    key = _resolve_session_key(target)
    return FB_SESSION_DIR / f"{key}.json" if key else DEFAULT_SESSION


class SessionExpiredError(RuntimeError):
    """Raised when the FB crawl looks like it hit a login wall.

    Best-effort heuristic only (fb_crawl doesn't expose a login-redirect
    signal without internal changes we're avoiding) — see plan's open risks.
    """


async def crawl_target(target_id: int, *, show_browser: bool = False) -> None:
    target = repository.get_target(target_id)
    if target is None:
        raise ValueError(f"Không tìm thấy crawl_target id={target_id}")
    if target.platform_type not in ("facebook_group", "facebook_page"):
        raise ValueError(f"facebook_runner không xử lý platform_type={target.platform_type}")

    repository.mark_running(target_id)
    storage = PgStorage(target_id=target_id, platform_type=target.platform_type)
    cfg = target.config or {}

    try:
        session_path = _resolve_session_path(target)
        proxy = _proxy_pool.acquire()
        if target.platform_type == "facebook_group":
            async with PlaywrightGroupCrawler(
                headless=not show_browser,
                storage_state_path=session_path,
                proxy_server=proxy.server,
                proxy_username=proxy.username,
                proxy_password=proxy.password,
                max_scrolls=cfg.get("max_scrolls", 50),
                max_comments=cfg.get("max_comments", 100),
                concurrency=cfg.get("concurrency", 3),
            ) as crawler:
                service = GroupCrawlService(storage, crawler)
                result = await service.crawl_group(target.url, feed_only=cfg.get("feed_only", False))
            if result.group_name is None:
                raise SessionExpiredError(
                    f"Không lấy được tên group {target.url} — có thể session đã hết hạn"
                )
        else:
            async with PlaywrightPageCrawler(
                headless=not show_browser,
                storage_state_path=session_path,
                proxy_server=proxy.server,
                proxy_username=proxy.username,
                proxy_password=proxy.password,
                max_scrolls=cfg.get("max_scrolls", 50),
                max_comments=cfg.get("max_comments", 100),
                concurrency=cfg.get("concurrency", 3),
            ) as crawler:
                service = PageCrawlService(storage, crawler)
                result = await service.crawl_page(target.url, feed_only=cfg.get("feed_only", False))
            if result.page_name is None:
                raise SessionExpiredError(
                    f"Không lấy được tên page {target.url} — có thể session đã hết hạn"
                )
    except SessionExpiredError as exc:
        repository.mark_failed(target_id, str(exc), status="session_expired")
        raise
    except NotGroupMemberError as exc:
        repository.mark_failed(target_id, str(exc), status="not_a_member")
        raise
    except CheckpointError as exc:
        repository.mark_failed(target_id, str(exc), status="checkpoint")
        raise
    except Exception as exc:  # noqa: BLE001 - must reach Airflow as a failed task
        repository.mark_failed(target_id, str(exc))
        raise

    for item in result.posts:
        storage.update_extra(
            item.post.post_id,
            {"filter_reason": item.filter_reason, "is_first_crawl": item.is_first_crawl},
        )

    logger.info("Crawled target %s (%s): %d thay đổi", target_id, target.url, len(result.posts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl một FB group/page target theo id trong crawl_targets")
    parser.add_argument("target_id", type=int)
    parser.add_argument("--show-browser", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(crawl_target(args.target_id, show_browser=args.show_browser))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
