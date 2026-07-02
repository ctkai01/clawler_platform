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

from platform_app.adapters.fb_pg_storage import PgStorage
from platform_app.targets import repository

logger = logging.getLogger(__name__)

DEFAULT_SESSION = Path(
    os.environ.get("FB_SESSION_PATH", str(Path.home() / ".fb_crawl" / "fb_session.json"))
)


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
        if target.platform_type == "facebook_group":
            async with PlaywrightGroupCrawler(
                headless=not show_browser,
                storage_state_path=DEFAULT_SESSION,
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
                storage_state_path=DEFAULT_SESSION,
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
