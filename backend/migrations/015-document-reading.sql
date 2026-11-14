ALTER TABLE chat_files ADD CONSTRAINT chat_file_owner_conversation_unique UNIQUE(id,owner_id,conversation_id);
CREATE TABLE chat_document_reads (
 file_id uuid PRIMARY KEY,owner_id uuid NOT NULL,conversation_id uuid NOT NULL,
 report jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(file_id,owner_id,conversation_id) REFERENCES chat_files(id,owner_id,conversation_id) ON DELETE CASCADE
);
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON chat_document_reads FOR EACH ROW EXECUTE FUNCTION chat_account_storage();
