-- Additive migration, executed inside the dedicated project schema and transaction.
CREATE TABLE IF NOT EXISTS reference_entries (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 kind text NOT NULL CHECK(kind IN ('unit','category','supplier','article','site','family')),
 code text NOT NULL, label text NOT NULL,
 aliases jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(aliases)='array'),
 metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
 validated boolean NOT NULL DEFAULT false,
 provenance text NOT NULL, synthetic boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(kind,code)
);
CREATE TABLE IF NOT EXISTS knowledge_documents (
 id uuid PRIMARY KEY, source_path text NOT NULL UNIQUE, sha256 text NOT NULL,
 source_kind text NOT NULL, reviewed boolean NOT NULL DEFAULT false,
 synthetic boolean NOT NULL DEFAULT false, indexed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS knowledge_passages (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id uuid NOT NULL REFERENCES knowledge_documents(id), ordinal integer NOT NULL,
 content text NOT NULL, UNIQUE(document_id,ordinal)
);
CREATE TABLE IF NOT EXISTS requests (
 id uuid PRIMARY KEY, original_text text NOT NULL,
 initial_extraction jsonb, current_extraction jsonb, evaluated_result jsonb,
 provenance jsonb NOT NULL, status text NOT NULL CHECK(status IN
 ('processing','pending_approval','needs_clarification','analysis_failed','approved_locally','rejected')),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS request_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 request_id uuid NOT NULL REFERENCES requests(id), event_type text NOT NULL,
 actor text NOT NULL, revision integer NOT NULL,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS request_events_request_idx ON request_events(request_id,id);
CREATE OR REPLACE FUNCTION preserve_request_events() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Audit events are append-only'; END;
$$;
DROP TRIGGER IF EXISTS request_events_immutable ON request_events;
CREATE TRIGGER request_events_immutable BEFORE UPDATE OR DELETE ON request_events
 FOR EACH ROW EXECUTE FUNCTION preserve_request_events();
