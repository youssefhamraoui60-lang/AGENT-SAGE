-- Existing documents are preserved. No implicit grant to every registered user.
ALTER TABLE learning_memberships ADD COLUMN active boolean NOT NULL DEFAULT true;
CREATE TABLE learning_document_access (
 id uuid PRIMARY KEY,document_id uuid NOT NULL REFERENCES knowledge_documents(id),
 owner_id uuid REFERENCES chat_accounts(id),company_id uuid,
 folder text NOT NULL CHECK(folder='TEST'),
 CHECK((owner_id IS NOT NULL)::integer+(company_id IS NOT NULL)::integer=1)
);
CREATE INDEX learning_document_owner ON learning_document_access(owner_id,document_id);
CREATE INDEX learning_document_company ON learning_document_access(company_id,document_id);
