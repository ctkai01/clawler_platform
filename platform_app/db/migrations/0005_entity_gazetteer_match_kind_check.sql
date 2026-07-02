-- Match the opencrawler source schema's match_kind CHECK constraint exactly.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'entity_gazetteer_match_kind_check'
    ) THEN
        ALTER TABLE entity_gazetteer ADD CONSTRAINT entity_gazetteer_match_kind_check
            CHECK (match_kind = ANY (ARRAY['canonical', 'official', 'variant', 'abbrev', 'slang', 'typo']));
    END IF;
END $$;
