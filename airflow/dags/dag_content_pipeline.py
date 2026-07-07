from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="content_pipeline",
    schedule=None,  # triggered directly by each crawl DAG (facebook_groups/pages, forums, news) once it finishes
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["pipeline"],
)
def content_pipeline():
    """Post-crawl processing, modeled after the opencrawler reference
    project: keyword_filter (free cost gate) -> classify (LLM, only on
    keyword matches) -> entity_match (free, runs on everything, independent
    of the keyword gate) -> topic_tag (free, admin-defined per-org topic
    keywords, also independent of the keyword gate)."""

    @task(queue="http_crawler")
    def keyword_filter() -> dict:
        from platform_app.pipeline.keyword_filter import run_keyword_filter

        return run_keyword_filter()

    @task(queue="http_crawler")
    def classify() -> dict:
        from platform_app.pipeline.classify import run_classify

        return run_classify()

    @task(queue="http_crawler")
    def entity_match() -> dict:
        from platform_app.pipeline.entity_match import run_entity_match

        return run_entity_match()

    @task(queue="http_crawler")
    def topic_tag() -> dict:
        from platform_app.pipeline.topic_tag import run_topic_tag

        return run_topic_tag()

    keyword_filter() >> classify()
    entity_match()
    topic_tag()


content_pipeline()
