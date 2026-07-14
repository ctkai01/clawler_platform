-- Tracks health/cooldown state for each Facebook crawling account (session
-- pool). Cookies stay in secrets/fb_sessions/{id}.json as before — this
-- table only stores status, not credentials. `id` matches both the session
-- filename (without .json) and crawl_targets.fb_session_key.
CREATE TABLE fb_accounts (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'LIVE' CHECK (status IN ('LIVE', 'CHECKPOINT')),
    fail_count INT NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
