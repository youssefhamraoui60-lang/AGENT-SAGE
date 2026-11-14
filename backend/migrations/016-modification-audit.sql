CREATE TABLE chat_modification_audit (
 id bigserial PRIMARY KEY,
 owner_id uuid NOT NULL,
 conversation_id uuid NOT NULL,
 draft_id uuid NOT NULL,
 operation_id uuid,
 event text NOT NULL CHECK(event IN ('prepared','blocked','approved','executing','succeeded','rollback','ambiguous','cancelled')),
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(conversation_id,owner_id) REFERENCES chat_conversations(id,owner_id) ON DELETE CASCADE
);
CREATE INDEX chat_modification_audit_owner ON chat_modification_audit(owner_id,conversation_id,created_at);
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON chat_modification_audit FOR EACH ROW EXECUTE FUNCTION chat_account_storage();
CREATE FUNCTION chat_modification_audit_no_update() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 RAISE EXCEPTION 'Modification audit events are immutable';
END $$;
CREATE TRIGGER immutable_event BEFORE UPDATE ON chat_modification_audit FOR EACH ROW EXECUTE FUNCTION chat_modification_audit_no_update();
