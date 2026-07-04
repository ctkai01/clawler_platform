#!/bin/bash
# Runs once when the postgres container's data directory is first initialized.
# Airflow's own metadata DB is created via POSTGRES_USER/POSTGRES_DB; this adds
# the separate application database + role for the crawl platform. A .sh
# (not .sql) so the password can come from the container's own environment
# (APP_DB_PASSWORD, set in docker-compose.yml) instead of being hardcoded —
# postgres:16-alpine only envsubst's docker-entrypoint-initdb.d/*.sh, not *.sql.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER crawler WITH PASSWORD '${APP_DB_PASSWORD}';
    CREATE DATABASE crawl_platform OWNER crawler;
    GRANT ALL PRIVILEGES ON DATABASE crawl_platform TO crawler;
EOSQL
