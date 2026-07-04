-- One row per crawl pass that touches a document, capturing its engagement
-- counters at that moment. documents.* only ever holds the LATEST values
-- (each crawl UPSERTs in place), so this is the only place growth-over-time
-- can be read from. Starts empty for already-crawled documents; accumulates
-- going forward as fb_pg_storage.save_post / document_store.save_document
-- insert a snapshot alongside every upsert.
CREATE TABLE document_engagement_snapshots (
    id             BIGSERIAL PRIMARY KEY,
    document_id    BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    crawled_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    like_count     INTEGER NOT NULL DEFAULT 0,
    comment_count  INTEGER NOT NULL DEFAULT 0,
    reaction_count INTEGER NOT NULL DEFAULT 0,
    share_count    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_engagement_snapshots_document ON document_engagement_snapshots (document_id, crawled_at);
