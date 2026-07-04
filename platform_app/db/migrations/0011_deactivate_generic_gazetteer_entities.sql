-- entity_gazetteer was originally seeded from a Petrovietnam-oriented CSV
-- that, alongside real PVN business entities, also carried plain reference
-- data: provinces/countries (entity_type='geo') and government/party bodies
-- (entity_type='organization'). Those match on ANY mention of a place name
-- or ministry in unrelated content (e.g. a weather post naming "Quảng
-- Ninh"), showing up as noise entities/relationship-graph nodes for every
-- organization on the platform regardless of industry — reported directly
-- against real MobiFone (telecom) data, which never selected these for
-- tracking. Deactivating (not deleting) so the rows and any historical
-- document_entities tagging stay intact; entity_match.py only tags
-- is_active rows going forward.
UPDATE entity_gazetteer
SET is_active = false
WHERE industry_code = 'ENERGY' AND entity_type IN ('geo', 'organization');

-- Also purge the already-tagged rows on already-crawled documents (entity_match
-- only re-tags is_active rows going FORWARD; without this, noise already
-- written to document_entities would keep showing up in the network graph).
DELETE FROM document_entities
WHERE concept_id IN (
    SELECT DISTINCT concept_id FROM entity_gazetteer
    WHERE industry_code = 'ENERGY' AND entity_type IN ('geo', 'organization')
);
