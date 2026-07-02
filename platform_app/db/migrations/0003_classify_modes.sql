-- Sentiment field + a single-row settings table so the classify mode
-- (normal / llm_text / llm_image) is switchable from the dashboard UI
-- without redeploying.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_sentiment TEXT;

CREATE TABLE IF NOT EXISTS pipeline_settings (
    id            SMALLINT PRIMARY KEY DEFAULT 1,
    classify_mode TEXT NOT NULL DEFAULT 'llm_text' CHECK (classify_mode IN ('normal', 'llm_text', 'llm_image')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (id = 1)
);
INSERT INTO pipeline_settings (id, classify_mode) VALUES (1, 'llm_text') ON CONFLICT (id) DO NOTHING;
