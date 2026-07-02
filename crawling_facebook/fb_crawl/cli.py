from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import sys
from pathlib import Path

from fb_crawl.filters import NEW_POST_HOURS, RECENT_COMMENT_MINUTES
from fb_crawl.output import crawl_page_result_to_dict, crawl_result_to_dict
from fb_crawl.page_service import PageCrawlService
from fb_crawl.playwright_crawler import PlaywrightGroupCrawler
from fb_crawl.playwright_page_crawler import PlaywrightPageCrawler
from fb_crawl.service import GroupCrawlService
from fb_crawl.storage import Storage

DEFAULT_DB = Path.home() / ".fb_crawl" / "facebook.db"
DEFAULT_SESSION = Path.home() / ".fb_crawl" / "fb_session.json"


def _normalize_target_url(url: str) -> str:
    url = url.strip()
    if len(url) >= 2 and url[0] == url[-1] and url[0] in "'\"":
        url = url[1:-1].strip()
    return url


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _write_output(payload: dict, output: str | None) -> None:
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã lưu {payload['post_count']} bài viết → {out_path}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


async def _cmd_login(args: argparse.Namespace) -> int:
    session_path = Path(args.session)
    async with PlaywrightGroupCrawler(headless=False, storage_state_path=session_path) as crawler:
        ok = await crawler.login_interactive(timeout_sec=args.timeout)
        if not ok:
            print("Đăng nhập thất bại hoặc hết thời gian chờ.", file=sys.stderr)
            return 1
        await crawler.save_session(session_path)
    print(f"Đã lưu session tại {session_path}")
    return 0


async def _cmd_crawl_group(args: argparse.Namespace) -> int:
    storage = Storage(args.db)
    async with PlaywrightGroupCrawler(
        headless=not args.show_browser,
        storage_state_path=args.session,
        max_scrolls=args.max_scrolls,
        max_comments=args.max_comments,
        concurrency=args.concurrency,
    ) as crawler:
        service = GroupCrawlService(
            storage,
            crawler,
            new_post_hours=args.new_post_hours,
            recent_comment_minutes=args.recent_comment_minutes,
        )
        result = await service.crawl_group(args.target_url, feed_only=args.feed_only)

    _write_output(crawl_result_to_dict(result), args.output)
    return 0


async def _cmd_crawl_page(args: argparse.Namespace) -> int:
    storage = Storage(args.db)
    async with PlaywrightPageCrawler(
        headless=not args.show_browser,
        storage_state_path=args.session,
        max_scrolls=args.max_scrolls,
        max_comments=args.max_comments,
        concurrency=args.concurrency,
    ) as crawler:
        service = PageCrawlService(
            storage,
            crawler,
            new_post_hours=args.new_post_hours,
            recent_comment_minutes=args.recent_comment_minutes,
        )
        result = await service.crawl_page(args.target_url, feed_only=args.feed_only)

    _write_output(crawl_page_result_to_dict(result), args.output)
    return 0


def _add_crawl_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target_url",
        type=_normalize_target_url,
        help="URL Facebook Group hoặc Page",
    )
    parser.add_argument(
        "--new-post-hours",
        type=float,
        default=NEW_POST_HOURS,
        help=f"Bài viết mới trong N giờ (mặc định {NEW_POST_HOURS})",
    )
    parser.add_argument(
        "--recent-comment-minutes",
        type=float,
        default=RECENT_COMMENT_MINUTES,
        help=f"Comment mới trong N phút (mặc định {RECENT_COMMENT_MINUTES})",
    )
    parser.add_argument("--max-scrolls", type=int, default=50, help="Số lần scroll feed")
    parser.add_argument("--max-comments", type=int, default=100, help="Số comment tối đa mỗi bài")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Số tab song song khi crawl từng bài (mặc định 3)",
    )
    parser.add_argument(
        "--feed-only",
        action="store_true",
        help="Chỉ crawl bài trên feed, bỏ qua recheck từ DB (nhanh hơn)",
    )
    parser.add_argument("--show-browser", action="store_true", help="Hiện trình duyệt khi crawl")
    parser.add_argument("-o", "--output", help="Ghi kết quả JSON ra file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fb-crawl",
        description="Crawl bài viết Facebook Group và Page",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Đường dẫn SQLite DB")
    parser.add_argument("--session", default=str(DEFAULT_SESSION), help="File session Playwright")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Đăng nhập Facebook và lưu session")
    login.add_argument("--timeout", type=int, default=300)
    login.set_defaults(func=_cmd_login)

    crawl_group = sub.add_parser(
        "crawl-group",
        help="Crawl nhóm Facebook (bài mới 48h hoặc comment mới ~60 phút)",
    )
    _add_crawl_args(crawl_group)
    crawl_group.set_defaults(func=_cmd_crawl_group)

    crawl_page = sub.add_parser(
        "crawl-page",
        help="Crawl Facebook Page (bài mới 48h hoặc comment mới ~60 phút)",
    )
    _add_crawl_args(crawl_page)
    crawl_page.set_defaults(func=_cmd_crawl_page)

    # Giữ alias `crawl` cho group (tương thích ngược)
    crawl = sub.add_parser("crawl", help="Alias của crawl-group")
    _add_crawl_args(crawl)
    crawl.set_defaults(func=_cmd_crawl_group)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    if inspect.iscoroutinefunction(args.func):
        return asyncio.run(args.func(args))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
