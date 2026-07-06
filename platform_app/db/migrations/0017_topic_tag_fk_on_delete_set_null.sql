-- documents.topic_tag_id had no ON DELETE behavior, so deleting a topic
-- that any document was already tagged with failed with a foreign key
-- violation (500). Deleting a topic should just untag those documents —
-- the report already treats topic_tag_id IS NULL as "KHÁC".
ALTER TABLE documents DROP CONSTRAINT documents_topic_tag_id_fkey;
ALTER TABLE documents
    ADD CONSTRAINT documents_topic_tag_id_fkey
    FOREIGN KEY (topic_tag_id) REFERENCES organization_topics(id) ON DELETE SET NULL;
