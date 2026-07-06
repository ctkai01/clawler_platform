-- Per-organization "chủ đề" (topic) taxonomy, admin-managed (manual entry or
-- CSV import), used to auto-tag each document with the one topic whose
-- keywords it matches most (NULL = no match = "KHÁC" in reports). Distinct
-- from keywords_catalog (a global Stage-1 cost-gate, boolean matched/not)
-- and entity_gazetteer (brand/company NLP matching) — this is a simpler
-- literal-keyword-per-org classification purely for topic reporting.
CREATE TABLE organization_topics (
    id              BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organization_id, name)
);

CREATE TABLE organization_topic_keywords (
    id          BIGSERIAL PRIMARY KEY,
    topic_id    BIGINT NOT NULL REFERENCES organization_topics(id) ON DELETE CASCADE,
    keyword     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (topic_id, keyword)
);
CREATE INDEX idx_org_topic_keywords_topic ON organization_topic_keywords (topic_id);

-- topic_tag_status follows the same pending/done idiom as keyword_status /
-- classification_status — needed because topic_tag_id alone can't tell "not
-- yet checked" apart from "checked, zero topic keywords matched" (both NULL).
ALTER TABLE documents ADD COLUMN topic_tag_id BIGINT REFERENCES organization_topics(id);
ALTER TABLE documents ADD COLUMN topic_tag_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (topic_tag_status IN ('pending', 'tagged', 'none'));
CREATE INDEX idx_documents_topic_tag ON documents (topic_tag_id);
CREATE INDEX idx_documents_topic_tag_status ON documents (topic_tag_status);
