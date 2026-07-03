-- Seed entity_catalog / keywords_catalog with a starting set so the Admin
-- CRUD screens aren't empty. Admin can add/edit/remove freely afterward —
-- this is a convenience seed, not authoritative data (entity_gazetteer
-- stays the source of truth for the crawl/classify pipeline's matching).

INSERT INTO entity_catalog (display_name, concept_id_prefix, industry_code) VALUES
    ('MobiFone', 'mobifone', 'TELECOM'),
    ('Viettel', 'viettel', 'TELECOM'),
    ('VinaPhone', 'vinaphone', 'TELECOM'),
    ('Vietnamobile', 'vietnamobile', 'TELECOM'),
    ('Gmobile', 'gmobile', 'TELECOM'),
    ('Petrovietnam', 'petrovietnam', 'ENERGY'),
    ('PVOIL', 'pvoil', 'ENERGY'),
    ('Vietsovpetro', 'vietsovpetro', 'ENERGY')
ON CONFLICT (display_name) DO NOTHING;

INSERT INTO keywords_catalog (category, term) VALUES
    ('brand', 'mobifone'),
    ('brand', 'mobi fone'),
    ('brand', 'saymee'),
    ('competitor', 'viettel'),
    ('competitor', 'vinaphone'),
    ('competitor', 'vietnamobile'),
    ('competitor', 'gmobile'),
    ('industry', 'nhà mạng'),
    ('industry', 'gói cước'),
    ('industry', 'esim'),
    ('industry', 'chuyển mạng giữ số')
ON CONFLICT (category, term) DO NOTHING;
