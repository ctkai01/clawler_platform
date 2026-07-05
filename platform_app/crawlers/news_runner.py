from __future__ import annotations

import argparse
import asyncio
import logging

from platform_app.adapters.document_store import save_document
from platform_app.parsers.registry import get_parser
from platform_app.targets import repository

logger = logging.getLogger(__name__)


async def crawl_target(target_id: int) -> None:
    target = repository.get_target(target_id)
    if target is None:
        raise ValueError(f"Không tìm thấy crawl_target id={target_id}")
    if target.platform_type != "news":
        raise ValueError(f"news_runner không xử lý platform_type={target.platform_type}")
    if not target.parser_key:
        raise ValueError(f"Target {target_id} thiếu parser_key")

    repository.mark_running(target_id)
    parser = get_parser(target.parser_key)

    try:
        urls = await parser.discover_urls(target.url, target.config)
    except Exception as exc:  # noqa: BLE001 - must reach Airflow as a failed task
        repository.mark_failed(target_id, str(exc))
        raise

    saved = 0
    failed = 0
    for url in urls:
        try:
            doc = await parser.fetch_and_parse(url, target.config)
        except Exception:
            # One article failing to fetch (flaky network, transient block, ...)
            # must not discard every other article already fetched in this run
            # or mark the whole source 'error' — only discover_urls failing is
            # a real source-level problem.
            logger.exception("Bỏ qua bài lỗi khi crawl news target %s: %s", target_id, url)
            failed += 1
            continue
        if doc is None:
            continue
        save_document(target_id, "news", "news_article", target.external_id, doc)
        saved += 1

    repository.mark_success(target_id)
    logger.info(
        "Crawled news target %s (%s): %d bài lưu, %d bài lỗi (bỏ qua)", target_id, target.url, saved, failed
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl một news target theo id trong crawl_targets")
    parser.add_argument("target_id", type=int)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(crawl_target(args.target_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
