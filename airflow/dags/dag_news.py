from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task

BATCH_CAP = 100


@dag(
    dag_id="news_crawl",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["news", "crawl"],
)
def news_crawl():
    @task(queue="http_crawler")
    def get_due_targets() -> list[dict]:
        from platform_app.targets.repository import get_due_targets

        return [{"id": t.id, "url": t.url} for t in get_due_targets("news", limit=BATCH_CAP)]

    @task(pool="http_pool", queue="http_crawler", retries=1)
    def crawl_one(target: dict) -> None:
        import asyncio

        from platform_app.crawlers.news_runner import crawl_target

        asyncio.run(crawl_target(target["id"]))

    crawl_one.expand(target=get_due_targets())


news_crawl()
