-- Runs once when the postgres container's data directory is first initialized.
-- Airflow's own metadata DB is created via POSTGRES_DB/POSTGRES_USER; this adds
-- the separate application database + role for the crawl platform.
CREATE USER crawler WITH PASSWORD 'crawler';
CREATE DATABASE crawl_platform OWNER crawler;
GRANT ALL PRIVILEGES ON DATABASE crawl_platform TO crawler;
