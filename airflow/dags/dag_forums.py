from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task

BATCH_CAP = 100


@dag(
    dag_id="forums_crawl",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["forum", "crawl"],
)
def forums_crawl():
    @task(queue="http_crawler")
    def get_due_targets() -> list[dict]:
        from platform_app.targets.repository import get_due_targets

        return [{"id": t.id, "url": t.url} for t in get_due_targets("forum", limit=BATCH_CAP)]

    @task(pool="http_pool", queue="http_crawler", retries=1)
    def crawl_one(target: dict) -> None:
        import asyncio

        from platform_app.crawlers.forum_runner import crawl_target

        asyncio.run(crawl_target(target["id"]))

    @task(queue="http_crawler", trigger_rule="all_done")
    def trigger_content_pipeline() -> None:
        from datetime import datetime, timezone

        from airflow.api.common.trigger_dag import DagRunAlreadyExists, trigger_dag

        now = datetime.now(timezone.utc)
        try:
            # replace_microseconds=False: the default (True) zeroes the
            # execution_date down to whole seconds, which collides on the
            # dag_run (dag_id, execution_date) unique constraint whenever
            # another crawl DAG's trigger_content_pipeline fires in the
            # same second (frequent — several crawl DAGs share overlapping
            # schedule ticks).
            trigger_dag(
                dag_id="content_pipeline",
                run_id=f"forums_crawl__{now.isoformat()}",
                execution_date=now,
                replace_microseconds=False,
            )
        except DagRunAlreadyExists:
            # Another crawl DAG already triggered content_pipeline for this
            # instant — the goal (content_pipeline runs) is satisfied either way.
            pass

    crawl_one.expand(target=get_due_targets()) >> trigger_content_pipeline()


forums_crawl()
