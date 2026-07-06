from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="report_email",
    schedule="0 1 * * *",  # 01:00 UTC = 08:00 Vietnam time
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["report", "email"],
)
def report_email():
    @task(queue="http_crawler")
    def send_reports() -> dict:
        from platform_app.pipeline.report_email import send_daily_reports

        return send_daily_reports(days=1)

    send_reports()


report_email()
