from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="facebook_pages_crawl",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["facebook", "crawl"],
)
def facebook_pages_crawl():
    @task(queue="http_crawler")
    def dispatch() -> None:
        # Called directly, not via .delay() — this task itself just queries
        # Postgres and publishes crawl_batch_task onto RabbitMQ. The actual
        # Playwright crawling happens out-of-band on fb-celery-worker, which
        # Airflow has no visibility into (no more crawl_one/.expand() here).
        from platform_app.crawlers.dispatch_tasks import dispatch_due_sources

        dispatch_due_sources("facebook_page")

    @task(queue="http_crawler")
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
                run_id=f"facebook_pages_crawl__{now.isoformat()}",
                execution_date=now,
                replace_microseconds=False,
            )
        except DagRunAlreadyExists:
            # Another crawl DAG already triggered content_pipeline for this
            # instant — the goal (content_pipeline runs) is satisfied either way.
            pass

    dispatch() >> trigger_content_pipeline()


facebook_pages_crawl()
