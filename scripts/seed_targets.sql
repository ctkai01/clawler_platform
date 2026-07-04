-- Manual helper for adding crawl targets (CRUD stays manual for now — no admin UI yet).
-- Run against the crawl_platform database, e.g.:
--   docker compose exec -T postgres psql -U crawler -d crawl_platform -f scripts/seed_targets.sql

-- Facebook group / page: no parser_key needed, crawler is fixed (crawling_facebook).
INSERT INTO crawl_targets (platform_type, url, display_name, crawl_interval_sec)
VALUES ('facebook_group', 'https://www.facebook.com/groups/REPLACE_ME', 'Ví dụ FB group', 3600)
ON CONFLICT (platform_type, url) WHERE organization_id IS NULL DO NOTHING;

INSERT INTO crawl_targets (platform_type, url, display_name, crawl_interval_sec)
VALUES ('facebook_page', 'https://www.facebook.com/REPLACE_ME', 'Ví dụ FB page', 3600)
ON CONFLICT (platform_type, url) WHERE organization_id IS NULL DO NOTHING;

-- Forum: generic_css parser, selectors describe the listing + thread page markup.
INSERT INTO crawl_targets (platform_type, url, parser_key, display_name, crawl_interval_sec, config)
VALUES (
    'forum',
    'https://forum.example.com/board',
    'generic_css',
    'Ví dụ forum (generic_css)',
    1800,
    '{
        "list_selector": "a.thread-link",
        "title_selector": "h1.thread-title",
        "author_selector": ".post-author",
        "content_selector": ".post-content",
        "date_selector": "time.post-date",
        "date_attr": "datetime",
        "comment_selector": ".comment",
        "comment_author_selector": ".comment-author",
        "comment_text_selector": ".comment-text"
    }'::jsonb
)
ON CONFLICT (platform_type, url) WHERE organization_id IS NULL DO NOTHING;

-- Forum running on Discourse: bespoke JSON-API parser, no selectors needed.
INSERT INTO crawl_targets (platform_type, url, parser_key, display_name, crawl_interval_sec)
VALUES ('forum', 'https://discuss.example.com', 'discourse_json', 'Ví dụ Discourse forum', 900)
ON CONFLICT (platform_type, url) WHERE organization_id IS NULL DO NOTHING;

-- News site: generic_css parser also covers most static article pages.
INSERT INTO crawl_targets (platform_type, url, parser_key, display_name, crawl_interval_sec, config)
VALUES (
    'news',
    'https://news.example.com/section/tech',
    'generic_css',
    'Ví dụ trang tin tức (generic_css)',
    900,
    '{
        "list_selector": "a.article-link",
        "title_selector": "h1.article-title",
        "author_selector": ".article-author",
        "content_selector": ".article-body",
        "date_selector": "time.article-date",
        "date_attr": "datetime"
    }'::jsonb
)
ON CONFLICT (platform_type, url) WHERE organization_id IS NULL DO NOTHING;
