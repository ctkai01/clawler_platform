from __future__ import annotations

import asyncio
import logging
import os

from fb_crawl.filters import NEW_POST_HOURS
from fb_crawl.page_service import PageCrawlService
from fb_crawl.profile_service import ProfileCrawlService
from fb_crawl.service import GroupCrawlService
from fb_crawl.types import CheckpointError, NotGroupMemberError

from platform_app.adapters.fb_pg_storage import PgStorage
from platform_app.crawlers.account_pool import Account, AccountPool
from platform_app.crawlers.celery_app import app
from platform_app.crawlers.dispatch_tasks import _inflight_key, _redis
from platform_app.crawlers.facebook_runner import SessionExpiredError
from platform_app.crawlers.proxy_pool import ProxyPool
from platform_app.targets import repository

logger = logging.getLogger(__name__)

_account_pool = AccountPool()
_proxy_pool = ProxyPool()
# How far back a post's published_at can be and still count as "new" on
# first discovery (crawling_facebook/fb_crawl/filters.py's default is 48h).
# Configurable here so widening it (e.g. to backfill a reporting window)
# is just an env var + worker restart, not a code change/rebuild.
_NEW_POST_HOURS = float(os.environ.get("FB_NEW_POST_HOURS", NEW_POST_HOURS))
# facebook_profile has its own knob, deliberately NOT tied to
# FB_NEW_POST_HOURS above — that one is set to 96h right now to backfill a
# specific weekly report window for Group/Page, unrelated to how far back a
# profile crawl should scroll. Defaults to 48h for the initial rollout/test.
_PROFILE_NEW_POST_HOURS = float(os.environ.get("FB_PROFILE_NEW_POST_HOURS", "48"))


async def _run_batch(platform_type: str, target_ids: list[int], account: Account, proxy) -> bool:
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
    from fb_crawl.playwright_profile_crawler import PlaywrightProfileCrawler

    crawler_cls = {
        "facebook_group": PlaywrightGroupCrawler,
        "facebook_page": PlaywrightPageCrawler,
        "facebook_profile": PlaywrightProfileCrawler,
    }[platform_type]
    account_checkpointed = False
    # Only ever try refresh_login() once per batch — an account whose
    # password/2FA don't actually work anymore shouldn't get retried on
    # every remaining target, just checkpointed once and moved on.
    session_refresh_attempted = False

    # Profile-only knobs: PlaywrightGroupCrawler/PlaywrightPageCrawler don't
    # accept these kwargs, so only pass them for facebook_profile. Scroll
    # depth is tied to _PROFILE_NEW_POST_HOURS instead of the reference
    # project's fixed 365-day default — everything older than that window is
    # outside what classify_post would ever report as new/recent anyway, so
    # scrolling further just burns time. Comments capped at 100/post.
    extra_kwargs: dict = {}
    if platform_type == "facebook_profile":
        extra_kwargs = {
            "days_back": max(_PROFILE_NEW_POST_HOURS / 24.0, 1.0),
            "max_comments": 100,
            "top_comment_limit": 100,
            # Sequential for now (was 3) — concurrent tabs opening/sorting/
            # scrolling comments simultaneously on the same logged-in
            # session is a much stronger automation signal to Facebook than
            # one-at-a-time, and is the leading suspect for 2 accounts
            # getting checkpointed right after this was turned on. Revisit
            # once checkpoint-safety (now added — see CheckpointError checks
            # in playwright_profile_crawler.py) has been proven live.
            "concurrency": 1,
        }

    async with crawler_cls(
        headless=True,
        storage_state_path=account.session_data,
        proxy_server=proxy.server,
        proxy_username=proxy.username,
        proxy_password=proxy.password,
        user_agent=account.user_agent,
        **extra_kwargs,
    ) as crawler:
        for i, target_id in enumerate(target_ids):
            target = repository.get_target(target_id)
            if target is None:
                continue
            storage = PgStorage(target_id=target_id, platform_type=platform_type)
            repository.mark_running(target_id)
            try:
                if platform_type == "facebook_group":
                    service = GroupCrawlService(storage, crawler, new_post_hours=_NEW_POST_HOURS)
                    result = await service.crawl_group(target.url)
                    name = result.group_name
                elif platform_type == "facebook_page":
                    service = PageCrawlService(storage, crawler, new_post_hours=_NEW_POST_HOURS)
                    result = await service.crawl_page(target.url)
                    name = result.page_name
                else:
                    service = ProfileCrawlService(storage, crawler, new_post_hours=_PROFILE_NEW_POST_HOURS)
                    result = await service.crawl_profile(target.url)
                    name = result.profile_name
                if name is None:
                    kind = {"facebook_group": "group", "facebook_page": "page"}.get(platform_type, "profile")
                    raise SessionExpiredError(
                        f"Không lấy được tên {kind} {target.url} — có thể session đã hết hạn"
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
                if account.password and not session_refresh_attempted:
                    session_refresh_attempted = True
                    logger.info("Session hết hạn cho %s, thử tự động đăng nhập lại...", account.key)
                    new_session = await crawler.refresh_login(account.key, account.password, account.two_fa_secret)
                    if new_session:
                        _account_pool.update_session(account.key, new_session)
                        repository.mark_failed(target_id, str(exc), status="session_expired")
                    else:
                        # Auto-refresh failed — same account-level dead-end
                        # as a real checkpoint, no point retrying the rest
                        # of the batch against the same broken session.
                        account_checkpointed = True
                        for remaining_id in target_ids[i:]:
                            repository.mark_failed(remaining_id, "Tự động refresh session thất bại", status="checkpoint")
                            _redis.delete(_inflight_key(platform_type, remaining_id))
                        break
                else:
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
        checkpointed = asyncio.run(_run_batch(platform_type, target_ids, account, proxy))
    except Exception:
        logger.exception("Batch %s session_key=%s thất bại toàn bộ", platform_type, session_key)
        checkpointed = True
        for target_id in target_ids:
            _redis.delete(_inflight_key(platform_type, target_id))
    finally:
        _account_pool.release(account.key, success=not checkpointed)
