CREATE TABLE IF NOT EXISTS soap_operations (
 id uuid PRIMARY KEY,resource text NOT NULL,action text NOT NULL CHECK(action IN ('create','update')),
 record_keys jsonb NOT NULL,payload jsonb NOT NULL,object_xml text NOT NULL,digest text NOT NULL,
 description_hash text NOT NULL,before_record jsonb,status text NOT NULL,
 checks jsonb NOT NULL,after_record jsonb,result jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS soap_operation_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,operation_id uuid NOT NULL REFERENCES soap_operations(id),
 event_type text NOT NULL,actor text NOT NULL,payload jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION reject_soap_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'SOAP operation events are append-only'; END $$;
DROP TRIGGER IF EXISTS soap_event_immutable ON soap_operation_events;
CREATE TRIGGER soap_event_immutable BEFORE UPDATE OR DELETE ON soap_operation_events FOR EACH ROW EXECUTE FUNCTION reject_soap_event_mutation();
CREATE TABLE IF NOT EXISTS soap_operation_approvals (
 operation_id uuid PRIMARY KEY REFERENCES soap_operations(id),digest text NOT NULL,token_sha256 text NOT NULL,
 actor text NOT NULL,reason text NOT NULL,expires_at timestamptz NOT NULL,consumed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
