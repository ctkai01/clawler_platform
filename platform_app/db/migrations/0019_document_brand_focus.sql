-- Distinguishes documents matched because they mention THIS org's own brand
-- ('own') from ones matched only because they mention a competitor
-- ('competitor') — both now proceed to classify() (sentiment is still
-- useful for competitor content), but the org's main dashboard/report only
-- aggregates 'own' by default; 'competitor' content is meant for a separate
-- view. NULL for documents with keyword_status IN ('pending', 'no_match').
ALTER TABLE documents ADD COLUMN brand_focus TEXT CHECK (brand_focus IN ('own', 'competitor'));
CREATE INDEX idx_documents_brand_focus ON documents (brand_focus);
