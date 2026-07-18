-- Not every LIVE account is safe to use for facebook_profile crawling: that
-- crawler needs a session with real localStorage (established via a full
-- browser login), while facebook_group/facebook_page's DOM-scraping works
-- fine even with a "thin" cookie-only session. Accounts default to FALSE —
-- an operator opts an account in only after confirming its session has the
-- full browser-login state (see docs/fb-session-pool.md).
ALTER TABLE fb_accounts ADD COLUMN supports_profile BOOLEAN NOT NULL DEFAULT FALSE;
