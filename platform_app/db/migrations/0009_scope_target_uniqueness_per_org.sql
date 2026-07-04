-- crawl_targets had a GLOBAL UNIQUE(platform_type, url), so two different
-- organizations (or an org vs. the pre-multi-tenant NULL-org rows) could
-- never track the same URL — a CSV import of already-crawled URLs got
-- silently rejected as "already exists" even for orgs that had never added
-- them.
--
-- Two partial unique indexes instead of one constraint, because NULL never
-- equals NULL in a unique index (Postgres), so a plain
-- UNIQUE(organization_id, platform_type, url) would stop deduplicating the
-- internal/ops-managed rows that have organization_id IS NULL (used by
-- platform_app/targets/repository.py's seed_target(), still relied on for
-- non-multi-tenant seeding):
--   - internal/ops rows (organization_id IS NULL): dedupe on (platform_type, url) as before
--   - customer-portal rows (organization_id IS NOT NULL): dedupe per organization
ALTER TABLE crawl_targets DROP CONSTRAINT crawl_targets_platform_type_url_key;

CREATE UNIQUE INDEX crawl_targets_url_key_internal ON crawl_targets (platform_type, url)
    WHERE organization_id IS NULL;
CREATE UNIQUE INDEX crawl_targets_url_key_per_org ON crawl_targets (organization_id, platform_type, url)
    WHERE organization_id IS NOT NULL;
