from __future__ import annotations

import asyncio
import logging

from fb_crawl.page_service import PageCrawlService
from fb_crawl.service import GroupCrawlService
from fb_crawl.types import CheckpointError, NotGroupMemberError

from platform_app.adapters.fb_pg_storage import PgStorage
from platform_app.crawlers.account_pool import AccountPool
from platform_app.crawlers.celery_app import app
from platform_app.crawlers.dispatch_tasks import _inflight_key, _redis
from platform_app.crawlers.facebook_runner import SessionExpiredError
from platform_app.crawlers.proxy_pool import ProxyPool
from platform_app.targets import repository

logger = logging.getLogger(__name__)

_account_pool = AccountPool()
_proxy_pool = ProxyPool()


async def _run_batch(platform_type: str, target_ids: list[int], session_path, proxy, user_agent: str | None) -> bool:
    """Crawls every target_id in one browser session. Returns True if the
    account got checkpointed partway through (caller uses this to decide
    what to tell AccountPool.release)."""
    # Imported here, not at module level: this whole module already
    # requires Playwright transitively via fb_crawl.page_service/service
    # above, so there's no lazy-loading benefit left to gain — kept local
    # only to mirror _extract_post_page-style call sites elsewhere. Safe
    # either way since only the Playwright-equipped fb-celery-worker ever
    # imports platform_app.crawlers.batch_tasks in the first place.
    from fb_crawl.playwright_crawler import PlaywrightGroupCrawler
    from fb_crawl.playwright_page_crawler import PlaywrightPageCrawler

    crawler_cls = PlaywrightGroupCrawler if platform_type == "facebook_group" else PlaywrightPageCrawler
    account_checkpointed = False

    async with crawler_cls(
        headless=True,
        storage_state_path=session_path,
        proxy_server=proxy.server,
        proxy_username=proxy.username,
        proxy_password=proxy.password,
        user_agent=user_agent,
    ) as crawler:
        for i, target_id in enumerate(target_ids):
            target = repository.get_target(target_id)
            if target is None:
                continue
            storage = PgStorage(target_id=target_id, platform_type=platform_type)
            repository.mark_running(target_id)
            try:
                if platform_type == "facebook_group":
                    service = GroupCrawlService(storage, crawler)
                    result = await service.crawl_group(target.url)
                    name = result.group_name
                else:
                    service = PageCrawlService(storage, crawler)
                    result = await service.crawl_page(target.url)
                    name = result.page_name
                if name is None:
                    raise SessionExpiredError(
                        f"Không lấy được tên {'group' if platform_type == 'facebook_group' else 'page'} "
                        f"{target.url} — có thể session đã hết hạn"
                    )
                repository.mark_success(target_id)
                for item in result.posts:
                    storage.update_extra(
                        item.post.post_id,
                        {"filter_reason": item.filter_reason, "is_first_crawl": item.is_first_crawl},
                    )
            except CheckpointError as exc:
                account_checkpointed = True
                # Account-level failure, not per-target — every remaining
                # target in this batch would hit the same dead session, so
                # stop instead of burning time re-discovering the same
                # checkpoint over and over.
                for remaining_id in target_ids[i:]:
                    repository.mark_failed(remaining_id, str(exc), status="checkpoint")
                    _redis.delete(_inflight_key(platform_type, remaining_id))
                break
            except SessionExpiredError as exc:
                repository.mark_failed(target_id, str(exc), status="session_expired")
            except NotGroupMemberError as exc:
                repository.mark_failed(target_id, str(exc), status="not_a_member")
            except Exception as exc:  # noqa: BLE001 - isolate per-target failure
                repository.mark_failed(target_id, str(exc))
                logger.warning("Crawl lỗi target %s (%s): %s", target_id, platform_type, exc)
            finally:
                _redis.delete(_inflight_key(platform_type, target_id))

    return account_checkpointed


@app.task(name="platform_app.crawlers.batch_tasks.crawl_batch_task", bind=True, max_retries=0)
def crawl_batch_task(self, platform_type: str, target_ids: list[int], session_key: str | None) -> None:
    account = _account_pool.acquire_specific(session_key) if session_key else _account_pool.acquire()
    if account is None:
        # Assigned account is CHECKPOINT/cooldown, or no LIVE account left
        # at all — drop this batch, next dispatch tick will retry. Not an
        # immediate Celery retry: piling attempts onto a just-checkpointed
        # account helps nothing.
        logger.warning(
            "Không có account khả dụng cho batch %s session_key=%s (%d target) — bỏ qua, đợi tick sau.",
            platform_type, session_key, len(target_ids),
        )
        for target_id in target_ids:
            _redis.delete(_inflight_key(platform_type, target_id))
        return

    proxy = _proxy_pool.acquire()
    try:
        checkpointed = asyncio.run(
            _run_batch(platform_type, target_ids, account.session_path, proxy, account.user_agent)
        )
    except Exception:
        logger.exception("Batch %s session_key=%s thất bại toàn bộ", platform_type, session_key)
        checkpointed = True
        for target_id in target_ids:
            _redis.delete(_inflight_key(platform_type, target_id))
    finally:
        _account_pool.release(account.key, success=not checkpointed)
