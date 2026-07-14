-- Real accounts (imported from the fb-distributed-scraper reference
-- project's Mongo account_pool) each carry a fixed user_agent that matches
-- the browser the cookie was originally issued to — crawling with a
-- different UA than the one the cookie was born under is itself a
-- detectable anomaly.
ALTER TABLE fb_accounts ADD COLUMN user_agent TEXT;
