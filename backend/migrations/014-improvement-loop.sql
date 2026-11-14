CREATE TABLE learning_corrections (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,conversation_id uuid NOT NULL,
 family text NOT NULL,lesson jsonb NOT NULL,fingerprint text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(owner_id,fingerprint),
 FOREIGN KEY(conversation_id,owner_id) REFERENCES chat_conversations(id,owner_id) ON DELETE CASCADE
);
CREATE TABLE learning_auto_methods (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,company_id uuid,folder text NOT NULL CHECK(folder='TEST'),
 family text NOT NULL,version integer NOT NULL,recipe jsonb NOT NULL,
 status text NOT NULL CHECK(status IN ('candidate','active','rejected','disabled')),
 evidence jsonb NOT NULL,evaluation jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(owner_id,family,version)
);
CREATE TABLE learning_auto_runs (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,report jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE learning_memberships ADD COLUMN auto_share boolean NOT NULL DEFAULT false;
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON learning_corrections FOR EACH ROW EXECUTE FUNCTION chat_account_storage();
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON learning_auto_methods FOR EACH ROW EXECUTE FUNCTION chat_account_storage();
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON learning_auto_runs FOR EACH ROW EXECUTE FUNCTION chat_account_storage();
