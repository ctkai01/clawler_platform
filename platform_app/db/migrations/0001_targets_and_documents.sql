-- Crawl targets: the link list, stored as data (not config files).
CREATE TABLE IF NOT EXISTS crawl_targets (
    id                    BIGSERIAL PRIMARY KEY,
    platform_type         TEXT NOT NULL CHECK (platform_type IN ('facebook_group', 'facebook_page', 'forum', 'news')),
    parser_key            TEXT,                 -- selects plugin/config for forum/news; NULL for FB
    url                   TEXT NOT NULL,
    external_id           TEXT,                 -- group_id/page_id, resolved on first crawl
    display_name          TEXT,
    enabled               BOOLEAN NOT NULL DEFAULT TRUE,
    crawl_interval_sec    INTEGER NOT NULL DEFAULT 3600,
    priority              SMALLINT NOT NULL DEFAULT 100,
    config                JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_crawled_at       TIMESTAMPTZ,
    last_success_at       TIMESTAMPTZ,
    last_status           TEXT,
    last_error            TEXT,
    consecutive_failures  INTEGER NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (platform_type, url)
);
CREATE INDEX IF NOT EXISTS idx_targets_due ON crawl_targets (platform_type, enabled, last_crawled_at);

-- Unified content table across FB posts, forum threads, news articles.
CREATE TABLE IF NOT EXISTS documents (
    id                  BIGSERIAL PRIMARY KEY,
    target_id           BIGINT NOT NULL REFERENCES crawl_targets(id),
    platform_type       TEXT NOT NULL,
    source_type         TEXT NOT NULL,          -- 'group' | 'page' | 'forum_thread' | 'news_article'
    external_doc_id     TEXT NOT NULL,           -- FB: post_id. forum/news: "{domain}:{native_id}"
    owner_external_id   TEXT,                    -- group_id / page_id / forum board id
    url                 TEXT NOT NULL,
    author               TEXT,
    author_id            TEXT,
    topic                TEXT,
    content              TEXT NOT NULL,
    content_hash         TEXT NOT NULL,
    published_at         TIMESTAMPTZ,
    edited_at            TIMESTAMPTZ,
    is_edited            BOOLEAN NOT NULL DEFAULT FALSE,
    images               JSONB NOT NULL DEFAULT '[]'::jsonb,
    videos               JSONB NOT NULL DEFAULT '[]'::jsonb,
    like_count           INTEGER NOT NULL DEFAULT 0,
    comment_count        INTEGER NOT NULL DEFAULT 0,
    reaction_count       INTEGER NOT NULL DEFAULT 0,
    share_count          INTEGER NOT NULL DEFAULT 0,
    reactions            JSONB NOT NULL DEFAULT '{}'::jsonb,
    extra                JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (platform_type, external_doc_id)
);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents (platform_type, owner_external_id, source_type);
CREATE INDEX IF NOT EXISTS idx_documents_recheck ON documents (owner_external_id, source_type, comment_count, published_at);
CREATE INDEX IF NOT EXISTS idx_documents_target ON documents (target_id);

CREATE TABLE IF NOT EXISTS document_comments (
    id                    BIGSERIAL PRIMARY KEY,
    document_id           BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    external_comment_id   TEXT NOT NULL,
    author                 TEXT,
    author_id              TEXT,
    text                   TEXT NOT NULL,
    content_hash           TEXT NOT NULL,
    parent_comment_id      TEXT,
    depth                  INTEGER NOT NULL DEFAULT 0,
    match_key              TEXT NOT NULL,
    is_edited               BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ,
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, external_comment_id)
);
CREATE INDEX IF NOT EXISTS idx_comments_document ON document_comments (document_id);
CREATE INDEX IF NOT EXISTS idx_comments_match ON document_comments (document_id, match_key);
