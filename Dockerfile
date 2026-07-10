# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12
ARG AIRFLOW_VERSION=2.10.5

# ---------------------------------------------------------------------------
# base: platform code + Airflow, no browser binaries (small, fast to rebuild)
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS base
ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

ENV AIRFLOW_HOME=/opt/airflow \
    PYTHONUNBUFFERED=1
WORKDIR /opt/app

RUN pip install --no-cache-dir "apache-airflow[celery,postgres,redis]==${AIRFLOW_VERSION}" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

# ---------------------------------------------------------------------------
# fb-worker: branches off `base` BEFORE the app-source COPY below, so editing
# crawling_facebook/ or platform_app/ (which happens constantly) never
# invalidates this layer and forces a ~180MB Chromium re-download — only
# bumping the pinned playwright version here does.
# ---------------------------------------------------------------------------
FROM base AS fb-worker
RUN pip install --no-cache-dir playwright>=1.40.0 \
    && playwright install --with-deps chromium

COPY crawling_facebook/ ./crawling_facebook/
COPY platform_app/ ./platform_app/
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ./crawling_facebook -e .

COPY config/ ./config/
COPY csv/ ./csv/
COPY airflow/dags/ ${AIRFLOW_HOME}/dags/

# ---------------------------------------------------------------------------
# http-worker / webserver / scheduler: base + app source, no browser binaries
# ---------------------------------------------------------------------------
FROM base AS http-worker

COPY crawling_facebook/ ./crawling_facebook/
COPY platform_app/ ./platform_app/
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ./crawling_facebook -e .

COPY config/ ./config/
COPY csv/ ./csv/
COPY airflow/dags/ ${AIRFLOW_HOME}/dags/
