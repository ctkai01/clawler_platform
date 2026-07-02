-- Entity gazetteer seed: canonical company names + surface forms to match
-- against document text (entity_match pipeline stage). Not present in the
-- opencrawler CSVs (01a-01g), which only cover Petrovietnam-side entities.
INSERT INTO entity_gazetteer (concept_id, canonical_name, canonical_display_name, surface_form, surface_form_folded, entity_type, industry_code, source_file) VALUES
    ('mobifone', 'MobiFone', 'MobiFone', 'mobifone', 'mobifone', 'company', 'TELECOM', 'seed_entities.sql'),
    ('mobifone', 'MobiFone', 'MobiFone', 'mobi fone', 'mobi fone', 'company', 'TELECOM', 'seed_entities.sql'),
    ('viettel', 'Viettel', 'Viettel', 'viettel', 'viettel', 'company', 'TELECOM', 'seed_entities.sql'),
    ('vinaphone', 'VinaPhone', 'VinaPhone', 'vinaphone', 'vinaphone', 'company', 'TELECOM', 'seed_entities.sql'),
    ('vinaphone', 'VinaPhone', 'VinaPhone', 'vina phone', 'vina phone', 'company', 'TELECOM', 'seed_entities.sql'),
    ('vietnamobile', 'Vietnamobile', 'Vietnamobile', 'vietnamobile', 'vietnamobile', 'company', 'TELECOM', 'seed_entities.sql'),
    ('gmobile', 'Gmobile', 'Gmobile', 'gmobile', 'gmobile', 'company', 'TELECOM', 'seed_entities.sql'),
    ('petrovietnam', 'Petrovietnam', 'Petrovietnam', 'petrovietnam', 'petrovietnam', 'company', 'ENERGY', 'seed_entities.sql'),
    ('petrovietnam', 'Petrovietnam', 'Petrovietnam', 'pvn', 'pvn', 'company', 'ENERGY', 'seed_entities.sql'),
    ('pvoil', 'PVOIL', 'PVOIL', 'pvoil', 'pvoil', 'company', 'ENERGY', 'seed_entities.sql'),
    ('vietsovpetro', 'Vietsovpetro', 'Vietsovpetro', 'vietsovpetro', 'vietsovpetro', 'company', 'ENERGY', 'seed_entities.sql')
ON CONFLICT (concept_id, surface_form) DO NOTHING;
