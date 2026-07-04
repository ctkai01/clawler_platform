-- documents was uniqued globally on (platform_type, external_doc_id), so the
-- SAME real-world Facebook post could only ever be stored ONCE across the
-- whole platform. When an organization added a crawl_target whose URL
-- happened to already be tracked by another target (e.g. the legacy
-- organization_id IS NULL internal targets), their crawls "succeeded" but
-- every post that already existed got silently claimed by whichever target
-- inserted it first (target_id is not touched on ON CONFLICT UPDATE) —
-- confirmed against real data: 98 posts belonging to Mobifone's own sources
-- were invisible to them, permanently attributed to unrelated internal
-- targets. Rescoping uniqueness to (target_id, external_doc_id) gives each
-- target (and therefore each organization) its own row for the same
-- content going forward. Existing misattributed rows are NOT retroactively
-- reassigned here — they'll get a fresh, correctly-owned row the next time
-- that target's crawl encounters the same post again.
ALTER TABLE documents DROP CONSTRAINT documents_platform_type_external_doc_id_key;
ALTER TABLE documents ADD CONSTRAINT documents_target_id_external_doc_id_key UNIQUE (target_id, external_doc_id);
