-- Optional credentials for automatic session refresh (AccountPool /
-- batch_tasks.py's refresh_login flow) when a session has genuinely
-- expired (SessionExpiredError) — NOT used for CheckpointError, which
-- usually needs real identity verification that an automated re-login
-- can't pass. Both nullable: an account with no password simply never
-- attempts auto-refresh, keeping today's behavior (mark target failed,
-- leave account status untouched).
ALTER TABLE fb_accounts ADD COLUMN password TEXT;
ALTER TABLE fb_accounts ADD COLUMN two_fa_secret TEXT;
