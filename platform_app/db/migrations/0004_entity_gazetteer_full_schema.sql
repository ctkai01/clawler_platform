-- Bring entity_gazetteer to full parity with the opencrawler source schema
-- (surface_form_folded, match_kind, canonical_display_name vs canonical_name,
-- stakeholder_role, parent_display_name, org_level, industry_code,
-- match_mode, is_active, source_file, imported_at).
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS surface_form_folded TEXT;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS match_kind TEXT;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS canonical_display_name TEXT;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS stakeholder_role TEXT;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS parent_display_name TEXT;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS org_level TEXT;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS industry_code TEXT;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS match_mode TEXT NOT NULL DEFAULT 'contains';
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE entity_gazetteer ADD COLUMN IF NOT EXISTS source_file TEXT;

-- Backfill for any pre-existing rows (manually-seeded ones) so the new
-- NOT NULL-ish "display" column isn't empty for data imported before this
-- migration.
UPDATE entity_gazetteer SET canonical_display_name = canonical_name WHERE canonical_display_name IS NULL;
UPDATE entity_gazetteer SET surface_form_folded = lower(surface_form) WHERE surface_form_folded IS NULL;

CREATE INDEX IF NOT EXISTS idx_entity_gazetteer_active ON entity_gazetteer (is_active);
CREATE INDEX IF NOT EXISTS idx_entity_gazetteer_industry ON entity_gazetteer (industry_code);
