-- Facebook login session (Playwright storage_state: cookies + origins/
-- localStorage) moves from secrets/fb_sessions/{id}.json into this column —
-- shared automatically across every machine reading the same Postgres,
-- instead of each fb-celery-worker host needing its own synced copy of the
-- files. NULL means the account has no session yet and cannot be acquired
-- for crawling (see AccountPool._acquire).
ALTER TABLE fb_accounts ADD COLUMN session_data JSONB;
