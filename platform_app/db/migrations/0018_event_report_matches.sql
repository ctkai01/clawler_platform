-- Per-"sự vụ" (topic-event, e.g. "5G") match results: which documents are
-- about this event AND which brand (MobiFone or a competitor) they concern.
-- Distinct from organization_topics (mutually-exclusive per-org product/
-- service categories) — an event match is many-per-document (a comparison
-- article can mention both MobiFone and Viettel) and always paired with a
-- brand. LLM-derived fields (sentiment/impact_level/reasoning) are cached
-- here so regenerating the same day's report doesn't re-call the LLM.
CREATE TABLE event_report_matches (
    id               BIGSERIAL PRIMARY KEY,
    document_id      BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    event_key        TEXT NOT NULL,
    brand            TEXT NOT NULL,
    sentiment        TEXT,
    impact_level     TEXT,
    reasoning        TEXT,
    -- Reflects real-world CSKH follow-up the system has no visibility into —
    -- always defaults to "chưa xử lý" on insert; only a human editing it later
    -- (no editor UI yet) can change it. Never set by the LLM.
    handling_status  TEXT NOT NULL DEFAULT 'chua_xu_ly',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, event_key, brand)
);
CREATE INDEX idx_event_report_matches_event ON event_report_matches (event_key, brand);
