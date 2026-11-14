-- Membership is provisioned by a database administrator, never by chat input.
CREATE TABLE learning_memberships (
 company_id uuid NOT NULL,owner_id uuid NOT NULL REFERENCES chat_accounts(id),
 folder text NOT NULL CHECK(folder='TEST'),role text NOT NULL CHECK(role IN ('member','reviewer')),
 PRIMARY KEY(company_id,owner_id,folder)
);
CREATE TABLE learning_methods (
 id uuid PRIMARY KEY,company_id uuid NOT NULL,folder text NOT NULL CHECK(folder='TEST'),
 owner_id uuid NOT NULL,title text NOT NULL,content text NOT NULL,version integer NOT NULL CHECK(version>0),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','disabled')),
 source text NOT NULL DEFAULT 'human_authored_anonymized_method',
 created_at timestamptz NOT NULL DEFAULT now(),reviewed_by uuid,reviewed_at timestamptz,
 evaluation jsonb NOT NULL DEFAULT '{}',UNIQUE(company_id,folder,title,version),
 FOREIGN KEY(company_id,owner_id,folder) REFERENCES learning_memberships(company_id,owner_id,folder)
);
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON learning_methods FOR EACH ROW EXECUTE FUNCTION chat_account_storage();
