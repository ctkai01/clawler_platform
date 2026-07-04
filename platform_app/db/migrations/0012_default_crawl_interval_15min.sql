-- Customer request: re-crawl every 15 minutes instead of the previous 1-hour
-- default. Scoped to real customer orgs only — the 196 legacy/internal
-- targets (organization_id IS NULL, used by the separate internal ops
-- dashboard) keep their existing interval untouched.
ALTER TABLE crawl_targets ALTER COLUMN crawl_interval_sec SET DEFAULT 900;

UPDATE crawl_targets
SET crawl_interval_sec = 900
WHERE organization_id IS NOT NULL;
