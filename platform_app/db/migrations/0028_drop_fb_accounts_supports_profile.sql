-- Every fb_accounts row is now expected to have a full browser-login
-- session (real localStorage) — the pool has grown past the small subset
-- that used to need this flag, so distinguishing "profile-capable" accounts
-- is no longer meaningful. AccountPool.acquire() no longer filters on it
-- (see platform_app/crawlers/account_pool.py).
ALTER TABLE fb_accounts DROP COLUMN supports_profile;
