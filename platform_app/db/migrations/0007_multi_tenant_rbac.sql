-- Customer Portal RBAC: organizations / users / permissions, plus the
-- Admin-managed catalogs (entity_catalog, keywords_catalog) customers pick
-- from. Purely additive — crawl_targets/documents/entity_gazetteer/
-- pipeline_settings keep their existing structure and behavior unchanged;
-- crawl_targets only gains one nullable FK column.

CREATE TABLE organizations (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    tier            TEXT NOT NULL DEFAULT 'basic'
                    CHECK (tier IN ('basic', 'pro', 'enterprise')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- organization_id NULL => system_admin. parent_user_id set when role='org_sub',
-- points back to the org_main who created it.
CREATE TABLE users (
    id                  BIGSERIAL PRIMARY KEY,
    organization_id     BIGINT REFERENCES organizations(id),
    parent_user_id      BIGINT REFERENCES users(id),
    email               TEXT NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,
    role                TEXT NOT NULL
                        CHECK (role IN ('system_admin', 'org_main', 'org_sub')),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT org_required_unless_admin
        CHECK (role = 'system_admin' OR organization_id IS NOT NULL)
);
CREATE INDEX idx_users_organization ON users (organization_id);

-- Functional permission for sub-accounts: exactly one of the two roles.
CREATE TABLE user_permissions (
    user_id             BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    functional_role     TEXT NOT NULL
                        CHECK (functional_role IN ('report_viewer', 'configurator'))
);

-- Data-scope permission: sub-account only sees targets listed here.
-- No rows => sees nothing (default deny, not default allow).
CREATE TABLE user_target_access (
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_id           BIGINT NOT NULL REFERENCES crawl_targets(id) ON DELETE CASCADE,
    granted_by          BIGINT REFERENCES users(id),
    granted_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, target_id)
);

-- Admin-managed "trackable brand" catalog — separate from the granular
-- entity_gazetteer (surface-form matching data for the pipeline); this is
-- the short list customers pick from in the UI.
CREATE TABLE entity_catalog (
    id                      BIGSERIAL PRIMARY KEY,
    display_name            TEXT NOT NULL UNIQUE,
    concept_id_prefix       TEXT NOT NULL,
    industry_code           TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Admin-managed keyword catalog (separate from config/keywords.yaml, which
-- keyword_filter.py keeps reading unchanged for the running pipeline).
CREATE TABLE keywords_catalog (
    id              BIGSERIAL PRIMARY KEY,
    category        TEXT NOT NULL
                    CHECK (category IN ('brand', 'competitor', 'industry', 'custom')),
    term            TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (category, term)
);

-- Per-organization selections from the catalogs above.
CREATE TABLE organization_entities (
    organization_id     BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    entity_catalog_id   BIGINT NOT NULL REFERENCES entity_catalog(id) ON DELETE CASCADE,
    PRIMARY KEY (organization_id, entity_catalog_id)
);

CREATE TABLE organization_keywords (
    organization_id     BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    keyword_id          BIGINT NOT NULL REFERENCES keywords_catalog(id) ON DELETE CASCADE,
    PRIMARY KEY (organization_id, keyword_id)
);

-- NULL = internal/unassigned target (backward-compatible with existing rows).
ALTER TABLE crawl_targets ADD COLUMN organization_id BIGINT REFERENCES organizations(id);
CREATE INDEX idx_crawl_targets_organization ON crawl_targets (organization_id);
