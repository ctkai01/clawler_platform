-- News + forum sources for Mobifone (organization_id=14), sourced from the
-- opencrawler reference config's "news"/"forums" sections the user pasted.
-- Parsers (platform_app/parsers/rss_news.py, xenforo.py, tinhte.py) are
-- ports of opencrawler's own crawlers/news_rss.py, forum_xenforo.py,
-- forum_tinhte.py — verified live against each real site.
-- forum.gamevn.com is intentionally NOT included here: it refused the
-- connection when checked (site unreachable at the time) — add it with the
-- xenforo parser (same shape as voz.vn's rows below) once it's back up.
-- Run: docker compose exec -T postgres psql -U crawler -d crawl_platform -f scripts/seed_mobifone_news_forums.sql

-- ---------------------------------------------------------------------
-- News (rss_news parser)
-- ---------------------------------------------------------------------

INSERT INTO crawl_targets (organization_id, platform_type, url, parser_key, display_name, crawl_interval_sec, config)
VALUES (
    14, 'news', 'https://vnexpress.net/rss/tin-moi-nhat.rss', 'rss_news', 'VnExpress', 900,
    '{"body_selector": "article.fck_detail, article.content-detail", "title_selector": "h1.title-detail", "max_articles_per_run": 300, "max_history_days": 14}'::jsonb
)
ON CONFLICT (organization_id, platform_type, url) WHERE organization_id IS NOT NULL DO NOTHING;

INSERT INTO crawl_targets (organization_id, platform_type, url, parser_key, display_name, crawl_interval_sec, config)
VALUES (
    14, 'news', 'https://thanhnien.vn/rss/home.rss', 'rss_news', 'Thanh Nien', 900,
    '{"body_selector": "div.detail-content, div#abody", "title_selector": "h1", "max_articles_per_run": 300, "max_history_days": 14}'::jsonb
)
ON CONFLICT (organization_id, platform_type, url) WHERE organization_id IS NOT NULL DO NOTHING;

INSERT INTO crawl_targets (organization_id, platform_type, url, parser_key, display_name, crawl_interval_sec, config)
VALUES (
    14, 'news', 'https://tuoitre.vn/rss/tin-moi-nhat.rss', 'rss_news', 'Tuoi Tre', 900,
    '{"body_selector": "div#main-detail-body, div.detail-content", "title_selector": "h1", "max_articles_per_run": 300, "max_history_days": 14}'::jsonb
)
ON CONFLICT (organization_id, platform_type, url) WHERE organization_id IS NOT NULL DO NOTHING;

-- ---------------------------------------------------------------------
-- Forums (xenforo parser) — one crawl_target per subforum
-- ---------------------------------------------------------------------

INSERT INTO crawl_targets (organization_id, platform_type, url, parser_key, display_name, crawl_interval_sec, config) VALUES
(14, 'forum', 'https://voz.vn/f/diem-bao.33/', 'xenforo', 'VOZ - Điểm báo', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://voz.vn/f/chuyen-tro-linh-tinh.17/', 'xenforo', 'VOZ - Chuyện trò linh tinh', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://voz.vn/f/dien-thoai.71/', 'xenforo', 'VOZ - Điện thoại', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://voz.vn/f/internet-mang.144/', 'xenforo', 'VOZ - Internet / Mạng', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://voz.vn/f/cong-nghe.42/', 'xenforo', 'VOZ - Công nghệ', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://www.otofun.net/forums/tai-chinh-ngan-hang.285/', 'xenforo', 'Otofun - Tài chính - Ngân hàng', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://www.otofun.net/forums/quan-cafe-otofun.77/', 'xenforo', 'Otofun - Quán cafe Otofun', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://tuoitreit.vn/forums/tro-chuyen-linh-tinh.64/', 'xenforo', 'TuoiTreIT - Trò chuyện linh tinh', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://tuoitreit.vn/forums/tin-khoa-hoc-san-pham-moi.10/', 'xenforo', 'TuoiTreIT - Tin khoa học, sản phẩm mới', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://kenhsinhvien.vn/forums/tin-360.308/', 'xenforo', 'Kenh Sinh Vien - Tin 360°', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://kenhsinhvien.vn/forums/kham-pha.231/', 'xenforo', 'Kenh Sinh Vien - Khám phá', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb)
ON CONFLICT (organization_id, platform_type, url) WHERE organization_id IS NOT NULL DO NOTHING;

-- ---------------------------------------------------------------------
-- Forums (tinhte parser) — XenForo backend, custom Next.js frontend
-- ---------------------------------------------------------------------

INSERT INTO crawl_targets (organization_id, platform_type, url, parser_key, display_name, crawl_interval_sec, config) VALUES
(14, 'forum', 'https://tinhte.vn/forums/smartphone-tablet.796/', 'tinhte', 'Tinhte - Smartphone - Tablet', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb),
(14, 'forum', 'https://tinhte.vn/forums/dich-vu.777/', 'tinhte', 'Tinhte - Dịch vụ', 900, '{"max_threads_per_run": 30, "max_top_comments": 20, "max_history_days": 14}'::jsonb)
ON CONFLICT (organization_id, platform_type, url) WHERE organization_id IS NOT NULL DO NOTHING;
