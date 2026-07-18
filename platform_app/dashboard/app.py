from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from platform_app.dashboard import report_data
from platform_app.db.pool import get_pool
from platform_app.pipeline.settings import VALID_MODES, get_classify_mode, set_classify_mode

app = FastAPI(title="Reputation Management Platform Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

PAGE_SIZE = 30

AIRFLOW_API_BASE = os.environ.get("AIRFLOW_API_BASE", "http://airflow-webserver:8080")
AIRFLOW_API_USER = os.environ.get("AIRFLOW_API_USER", "admin")
AIRFLOW_API_PASSWORD = os.environ.get("AIRFLOW_API_PASSWORD", "admin")

CRAWL_DAGS = [
    "facebook_groups_crawl",
    "facebook_pages_crawl",
    "facebook_profiles_crawl",
    "forums_crawl",
    "news_crawl",
    "content_pipeline",
]


@app.get("/", response_class=HTMLResponse)
def list_documents(
    request: Request,
    platform_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    triggered: str | None = Query(default=None),
    trigger_error: str | None = Query(default=None),
) -> HTMLResponse:
    offset = (page - 1) * PAGE_SIZE
    where = "WHERE d.platform_type = %(platform_type)s" if platform_type else ""
    params = {"platform_type": platform_type, "limit": PAGE_SIZE, "offset": offset}

    with get_pool().connection() as conn:
        rows = conn.execute(
            f"""
            SELECT d.id, d.platform_type, d.source_type, d.author, d.topic, d.content,
                   d.like_count, d.comment_count, d.reaction_count, d.reactions,
                   d.images, d.videos, d.published_at, d.url, ct.display_name AS target_name,
                   d.keyword_status, d.classification_status, d.classification_category,
                   d.classification_sentiment, d.classification_sentiment_source, d.classification_severity,
                   COALESCE(
                       (SELECT array_agg(DISTINCT de.canonical_name)
                        FROM document_entities de WHERE de.document_id = d.id AND de.concept_id != '__none__'),
                       ARRAY[]::text[]
                   ) AS entities
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            {where}
            ORDER BY d.last_seen_at DESC
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        ).fetchall()
        total = conn.execute(
            f"SELECT count(*) AS n FROM documents d {where}", params
        ).fetchone()["n"]
        platforms = conn.execute(
            "SELECT DISTINCT platform_type FROM documents ORDER BY platform_type"
        ).fetchall()

    return templates.TemplateResponse(
        request,
        "documents_list.html",
        {
            "documents": rows,
            "platforms": [p["platform_type"] for p in platforms],
            "selected_platform": platform_type,
            "page": page,
            "has_next": offset + PAGE_SIZE < total,
            "has_prev": page > 1,
            "total": total,
            "crawl_dags": CRAWL_DAGS,
            "triggered": triggered,
            "trigger_error": trigger_error,
            "classify_mode": get_classify_mode(),
            "classify_modes": VALID_MODES,
        },
    )


@app.post("/settings/classify-mode")
def update_classify_mode(mode: str = Form(...)) -> RedirectResponse:
    try:
        set_classify_mode(mode)
    except ValueError as exc:
        return RedirectResponse(f"/?trigger_error={exc}", status_code=303)
    return RedirectResponse(f"/?triggered=classify_mode:{mode}", status_code=303)


@app.post("/trigger")
def trigger_dag(dag_id: str = Form(...), next: str = Form(default="/")) -> RedirectResponse:
    if dag_id not in CRAWL_DAGS:
        return RedirectResponse(f"{next}?trigger_error=DAG không hợp lệ: {dag_id}", status_code=303)
    auth = (AIRFLOW_API_USER, AIRFLOW_API_PASSWORD)
    try:
        with httpx.Client(auth=auth, timeout=15.0) as client:
            # A paused DAG's manually-triggered run stays stuck in "queued" forever,
            # so unpause it first — the button should just work regardless of state.
            client.patch(
                f"{AIRFLOW_API_BASE}/api/v1/dags/{dag_id}",
                json={"is_paused": False},
            ).raise_for_status()
            client.post(
                f"{AIRFLOW_API_BASE}/api/v1/dags/{dag_id}/dagRuns",
                json={},
            ).raise_for_status()
    except httpx.HTTPError as exc:
        return RedirectResponse(f"{next}?trigger_error=Trigger {dag_id} thất bại: {exc}", status_code=303)
    return RedirectResponse(f"{next}?triggered={dag_id}", status_code=303)


FB_DAG_IDS = ("facebook_groups_crawl", "facebook_pages_crawl", "facebook_profiles_crawl")


@app.get("/fb-crawl", response_class=HTMLResponse)
def fb_crawl_status(
    request: Request,
    triggered: str | None = Query(default=None),
    trigger_error: str | None = Query(default=None),
    released: str | None = Query(default=None),
) -> HTMLResponse:
    """Gộp mọi tín hiệu sức khoẻ của flow crawl FB (DAG dispatch, worker
    Celery, hàng đợi RabbitMQ, account pool, trạng thái crawl_targets) vào
    1 trang — thay cho việc kiểm tra tay qua nhiều lệnh `docker compose
    exec`/`psql`/`celery inspect` mỗi lần. Mỗi nguồn dữ liệu bọc try/except
    riêng để 1 nguồn tạm thời lỗi không làm vỡ cả trang."""
    auth = (AIRFLOW_API_USER, AIRFLOW_API_PASSWORD)
    dag_status = []
    for dag_id in FB_DAG_IDS:
        entry: dict = {"dag_id": dag_id, "is_paused": None, "last_run_state": None, "last_run_at": None, "error": None}
        try:
            with httpx.Client(auth=auth, timeout=10.0) as client:
                dag_resp = client.get(f"{AIRFLOW_API_BASE}/api/v1/dags/{dag_id}")
                dag_resp.raise_for_status()
                entry["is_paused"] = dag_resp.json()["is_paused"]
                runs_resp = client.get(
                    f"{AIRFLOW_API_BASE}/api/v1/dags/{dag_id}/dagRuns",
                    params={"limit": 1, "order_by": "-start_date"},
                )
                runs_resp.raise_for_status()
                runs = runs_resp.json().get("dag_runs", [])
                if runs:
                    entry["last_run_state"] = runs[0]["state"]
                    entry["last_run_at"] = runs[0]["start_date"]
        except httpx.HTTPError as exc:
            entry["error"] = str(exc)
        dag_status.append(entry)

    worker_alive = False
    worker_error: str | None = None
    try:
        from platform_app.crawlers.celery_app import app as fb_celery_app

        worker_alive = bool(fb_celery_app.control.ping(timeout=2.0))
    except Exception as exc:  # noqa: BLE001 - trạng thái hiển thị, không cần phân loại lỗi
        worker_error = str(exc)

    queue_info: dict | None = None
    queue_error: str | None = None
    try:
        resp = httpx.get(
            "http://rabbitmq:15672/api/queues/%2f/fb_crawl",
            auth=("fbcrawl", "fbcrawl"),
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        queue_info = {
            "messages_ready": data.get("messages_ready", 0),
            "messages_unacknowledged": data.get("messages_unacknowledged", 0),
            "consumers": data.get("consumers", 0),
        }
    except httpx.HTTPError as exc:
        queue_error = str(exc)

    with get_pool().connection() as conn:
        accounts = conn.execute(
            "SELECT id, status, fail_count, last_used_at FROM fb_accounts ORDER BY status, id"
        ).fetchall()
        target_breakdown = conn.execute(
            """
            SELECT platform_type, last_status, count(*) AS n
            FROM crawl_targets
            WHERE platform_type IN ('facebook_group', 'facebook_page', 'facebook_profile') AND enabled
            GROUP BY platform_type, last_status
            ORDER BY platform_type, last_status
            """
        ).fetchall()
        recent_activity = conn.execute(
            """
            SELECT id, platform_type, display_name, last_status, last_crawled_at, last_error
            FROM crawl_targets
            WHERE platform_type IN ('facebook_group', 'facebook_page', 'facebook_profile')
            ORDER BY last_crawled_at DESC NULLS LAST
            LIMIT 20
            """
        ).fetchall()

    return templates.TemplateResponse(
        request,
        "fb_crawl_status.html",
        {
            "dag_status": dag_status,
            "worker_alive": worker_alive,
            "worker_error": worker_error,
            "queue_info": queue_info,
            "queue_error": queue_error,
            "accounts": accounts,
            "target_breakdown": target_breakdown,
            "recent_activity": recent_activity,
            "triggered": triggered,
            "trigger_error": trigger_error,
            "released": released,
        },
    )


@app.post("/fb-crawl/release-checkpoint")
def fb_crawl_release_checkpoint(account_key: str = Form(...)) -> RedirectResponse:
    from platform_app.crawlers.account_pool import AccountPool

    try:
        AccountPool().release_checkpoint(account_key)
    except Exception as exc:  # noqa: BLE001 - hiển thị lỗi cho người vận hành, không cần phân loại
        return RedirectResponse(f"/fb-crawl?trigger_error=Gỡ cách ly {account_key} thất bại: {exc}", status_code=303)
    return RedirectResponse(f"/fb-crawl?released={account_key}", status_code=303)


@app.get("/documents/{document_id}", response_class=HTMLResponse)
def document_detail(request: Request, document_id: int) -> HTMLResponse:
    with get_pool().connection() as conn:
        doc = conn.execute(
            """
            SELECT d.*, ct.display_name AS target_name
            FROM documents d
            JOIN crawl_targets ct ON ct.id = d.target_id
            WHERE d.id = %s
            """,
            (document_id,),
        ).fetchone()
        comments = conn.execute(
            """
            SELECT author, text, created_at, depth
            FROM document_comments
            WHERE document_id = %s
            ORDER BY created_at NULLS LAST, id
            """,
            (document_id,),
        ).fetchall()
        entities = conn.execute(
            "SELECT canonical_name FROM document_entities WHERE document_id = %s AND concept_id != '__none__'",
            (document_id,),
        ).fetchall()

    return templates.TemplateResponse(
        request,
        "document_detail.html",
        {"doc": doc, "comments": comments, "entities": [e["canonical_name"] for e in entities]},
    )


@app.get("/report", response_class=HTMLResponse)
def report(
    request: Request,
    entity: str = Query(default="mobifone"),
    days: int = Query(default=7, ge=1, le=365),
) -> HTMLResponse:
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(days=days)

    kpis = report_data.get_kpis(entity, period_start, period_end)
    sentiment_dist = report_data.get_sentiment_distribution(entity, period_start, period_end)
    topic_detail = report_data.get_topic_detail(entity, period_start, period_end)
    topic_by_sentiment = report_data.get_topic_by_sentiment(entity, period_start, period_end)
    negative_count = report_data.count_by_sentiment(entity, period_start, period_end, "negative")
    positive_count = report_data.count_by_sentiment(entity, period_start, period_end, "positive")
    negative_posts = report_data.get_top_posts(entity, period_start, period_end, sentiment="negative")
    positive_posts = report_data.get_top_posts(entity, period_start, period_end, sentiment="positive")

    sentiment_map = {row["sentiment"]: row["count"] for row in sentiment_dist}
    # Preserve topic_detail's post-count ranking for the bar chart's topic order.
    topics = [row["topic"] for row in topic_detail]
    topic_sentiment_map: dict[str, dict[str, int]] = {t: {"positive": 0, "negative": 0, "neutral": 0} for t in topics}
    for row in topic_by_sentiment:
        if row["topic"] in topic_sentiment_map:
            topic_sentiment_map[row["topic"]][row["sentiment"]] = row["count"]
    topic_positive_counts = [topic_sentiment_map[t]["positive"] for t in topics]
    topic_neutral_counts = [topic_sentiment_map[t]["neutral"] for t in topics]
    topic_negative_counts = [topic_sentiment_map[t]["negative"] for t in topics]

    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "entity": entity,
            "days": days,
            "period_start": period_start,
            "period_end": period_end,
            "kpis": kpis,
            "sentiment_positive": sentiment_map.get("positive", 0),
            "sentiment_negative": sentiment_map.get("negative", 0),
            "sentiment_neutral": sentiment_map.get("neutral", 0),
            "topic_detail": topic_detail,
            "topics": topics,
            "topic_positive_counts": topic_positive_counts,
            "topic_neutral_counts": topic_neutral_counts,
            "topic_negative_counts": topic_negative_counts,
            "negative_count": negative_count,
            "positive_count": positive_count,
            "negative_posts": negative_posts,
            "positive_posts": positive_posts,
        },
    )
