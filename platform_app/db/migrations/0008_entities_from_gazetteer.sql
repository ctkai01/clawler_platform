-- Retire entity_catalog — the Admin "Entity" screen and the customer
-- entity picker now read/write entity_gazetteer directly (grouped by
-- canonical_name) instead of a separately curated short list. No rows in
-- organization_entities reference entity_catalog yet, so this is safe.
DROP TABLE organization_entities;
DROP TABLE entity_catalog;

-- Keyed on canonical_name (text) rather than a catalog row id, since a
-- "selectable entity" is now a canonical_name group in entity_gazetteer
-- (which can span many concept_id/surface_form rows).
CREATE TABLE organization_entities (
    organization_id  BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    canonical_name   TEXT NOT NULL,
    PRIMARY KEY (organization_id, canonical_name)
);
