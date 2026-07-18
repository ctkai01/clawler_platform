-- New source type: facebook_profile (public posts on a personal FB
-- profile timeline, distinct from facebook_page). Same crawl_targets/
-- documents tables, just one more allowed platform_type value.
ALTER TABLE crawl_targets DROP CONSTRAINT crawl_targets_platform_type_check;
ALTER TABLE crawl_targets ADD CONSTRAINT crawl_targets_platform_type_check
    CHECK (platform_type IN ('facebook_group', 'facebook_page', 'facebook_profile', 'forum', 'news'));
