-- pipeline_settings was a hardcoded singleton (id=1, one classify_mode for
-- every organization). Add an optional organization_id so each org can
-- override the mode for itself; the id=1 row (organization_id IS NULL)
-- becomes the fallback default for orgs that haven't set their own.
ALTER TABLE pipeline_settings DROP CONSTRAINT IF EXISTS pipeline_settings_id_check;
ALTER TABLE pipeline_settings ALTER COLUMN id DROP DEFAULT;
ALTER TABLE pipeline_settings ALTER COLUMN id TYPE BIGINT;
CREATE SEQUENCE IF NOT EXISTS pipeline_settings_id_seq OWNED BY pipeline_settings.id;
SELECT setval('pipeline_settings_id_seq', GREATEST((SELECT max(id) FROM pipeline_settings), 1), true);
ALTER TABLE pipeline_settings ALTER COLUMN id SET DEFAULT nextval('pipeline_settings_id_seq');

ALTER TABLE pipeline_settings
    ADD COLUMN IF NOT EXISTS organization_id BIGINT REFERENCES organizations(id) ON DELETE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS pipeline_settings_org_unique_idx
    ON pipeline_settings (organization_id) WHERE organization_id IS NOT NULL;
