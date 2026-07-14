from __future__ import annotations

import os

from celery import Celery

BROKER_URL = os.environ.get("FB_BROKER_URL", "amqp://fbcrawl:fbcrawl@rabbitmq:5672//")

app = Celery(
    "fb_crawl_worker",
    broker=BROKER_URL,
    task_ignore_result=True,
    include=["platform_app.crawlers.batch_tasks"],
)
app.conf.timezone = "UTC"
app.conf.task_default_queue = "fb_crawl"
