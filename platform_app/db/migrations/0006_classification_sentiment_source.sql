-- Track whether classification_sentiment came from the LLM ('ai') or the
-- rule-based/keyword path ('default': curated word list or the sentiment
-- lexicon CSV fallback), so the dashboard can show the user which is which.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS classification_sentiment_source TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documents_classification_sentiment_source_check'
    ) THEN
        ALTER TABLE documents ADD CONSTRAINT documents_classification_sentiment_source_check
            CHECK (classification_sentiment_source IS NULL OR classification_sentiment_source = ANY (ARRAY['ai', 'default']));
    END IF;
END $$;

-- Backfill already-classified rows: normal mode always costs $0, LLM modes
-- always incur nonzero token cost, so cost is a reliable retroactive signal
-- since we didn't persist per-document mode before this column existed.
UPDATE documents
SET classification_sentiment_source = CASE WHEN classification_cost_usd > 0 THEN 'ai' ELSE 'default' END
WHERE classification_status = 'completed' AND classification_sentiment_source IS NULL;
