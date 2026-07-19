from __future__ import annotations

import logging
import os

import redis

from platform_app.crawlers.celery_app import app
from platform_app.targets import repository

logger = logging.getLogger(__name__)

# Separate DB index from Airflow's own Celery broker (redis://redis:6379/0)
# — this is just an app-level lock namespace, not related to any queue.
REDIS_URL = os.environ.get("FB_INFLIGHT_REDIS_URL", "redis://redis:6379/2")

# Sources grouped into one crawl_batch_task — one browser session (one
# account + one proxy) is reused across the whole batch instead of
# opening/closing per source. See docs/dag-flow.md.
BATCH_SIZE = int(os.environ.get("FB_BATCH_SIZE", "10"))

# facebook_profile targets are crawled sequentially within a batch (one
# post's comments at a time) and any single target can burn up to ~15min
# (the scroll hard-cap in playwright_profile_crawler.py) — at BATCH_SIZE=10
# a worst-case batch can run past RabbitMQ's default 30-minute consumer
# ack timeout, which doesn't just fail the batch: it kills the whole
# Celery connection with an unrecoverable PreconditionFailed and crashes
# the worker process. Real incident: worker crash-looped repeatedly once
# profile targets scaled up via CSV import. Keep profile batches small
# enough that even the worst case stays well under that 30-minute ceiling.
PROFILE_BATCH_SIZE = int(os.environ.get("FB_PROFILE_BATCH_SIZE", "2"))

# Floor so a very-frequent target doesn't leave a near-zero-TTL inflight
# lock that could expire mid-crawl.
MIN_LOCK_TTL_SECONDS = 1800

_redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _inflight_key(platform_type: str, target_id: int) -> str:
    return f"fb:inflight:{platform_type}:{target_id}"


def dispatch_due_sources(platform_type: str) -> None:
    """Called directly by the Airflow DAG (not .delay()) — Airflow is just
    the clock here, this function itself publishes the actual crawl work
    onto RabbitMQ via app.send_task() for the fb-celery-worker to run.

    Takes platform_type explicitly (rather than looping over both types
    itself) because facebook_groups_crawl and facebook_pages_crawl are two
    separate DAGs — each dispatches only its own type, so one doesn't
    double-dispatch the other's due targets.

    Deliberately does NOT import platform_app.crawlers.batch_tasks (or
    anything from fb_crawl beyond the plain dataclasses) — that module
    pulls in Playwright/playwright-stealth at import time, which the
    Airflow http_crawler queue this runs on does not have installed.
    app.send_task() addresses the task by its registered string name
    instead of importing the function.
    """
    targets = repository.get_due_targets(platform_type, limit=200)
    # key = target.fb_session_key nếu đã gán cứng -> batch dùng
    # acquire_specific() ở crawl_batch_task, phải đúng account đó.
    # key = None (chưa gán, cả Group lẫn Page) -> gom chung 1 nhóm,
    # crawl_batch_task tự acquire() bất kỳ account LIVE nào khi chạy —
    # không tính trước 1 account cố định ở bước dispatch này, vì account
    # nào đang LIVE có thể đổi giữa lúc dispatch và lúc task thực sự chạy.
    batches: dict[str | None, list[int]] = {}
    for t in targets:
        lock_key = _inflight_key(platform_type, t.id)
        ttl = max(t.crawl_interval_sec, MIN_LOCK_TTL_SECONDS)
        if not _redis.set(lock_key, "1", nx=True, ex=ttl):
            continue  # batch trước vẫn đang xử lý target này
        batches.setdefault(t.fb_session_key, []).append(t.id)

    batch_size = PROFILE_BATCH_SIZE if platform_type == "facebook_profile" else BATCH_SIZE
    dispatched = 0
    for session_key, ids in batches.items():
        for i in range(0, len(ids), batch_size):
            app.send_task(
                "platform_app.crawlers.batch_tasks.crawl_batch_task",
                args=[platform_type, ids[i : i + batch_size], session_key],
                queue="fb_crawl",
            )
            dispatched += 1

    logger.info("Dispatch xong %s: %d batch", platform_type, dispatched)
