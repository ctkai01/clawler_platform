-- Post-crawl processing pipeline: keyword filter (cost gate) -> classify (LLM)
-- -> entity match (gazetteer). Modeled after the opencrawler reference project.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS keyword_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS matched_keywords JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_category TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_reasoning TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_severity SMALLINT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_documents_keyword_pending ON documents (keyword_status) WHERE keyword_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_documents_classify_pending ON documents (classification_status) WHERE classification_status = 'pending';

CREATE TABLE IF NOT EXISTS entity_gazetteer (
    id             BIGSERIAL PRIMARY KEY,
    concept_id     TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    surface_form   TEXT NOT NULL,
    entity_type    TEXT NOT NULL DEFAULT 'company',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (concept_id, surface_form)
);

CREATE TABLE IF NOT EXISTS document_entities (
    id            BIGSERIAL PRIMARY KEY,
    document_id   BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    concept_id    TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, concept_id)
);
CREATE INDEX IF NOT EXISTS idx_document_entities_document ON document_entities (document_id);
CREATE INDEX IF NOT EXISTS idx_document_entities_concept ON document_entities (concept_id);
