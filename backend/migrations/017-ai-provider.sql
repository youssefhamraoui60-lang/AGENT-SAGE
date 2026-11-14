CREATE TABLE chat_ai_usage (
 id uuid PRIMARY KEY,
 owner_id uuid REFERENCES chat_accounts(id) ON DELETE CASCADE,
 conversation_id uuid REFERENCES chat_conversations(id) ON DELETE CASCADE,
 created_at timestamptz NOT NULL DEFAULT now(),
 provider text NOT NULL CHECK(provider IN ('deepseek','ollama')),
 model text NOT NULL,
 purpose text NOT NULL,
 status text NOT NULL,
 http_status integer,
 input_tokens integer,
 cached_tokens integer,
 output_tokens integer,
 estimated_cost_usd numeric(18,9),
 reserved_cost_usd numeric(18,9) NOT NULL DEFAULT 0,
 duration_ms integer,
 error_type text,
 price_source text NOT NULL DEFAULT 'https://api-docs.deepseek.com/quick_start/pricing/',
 price_date date NOT NULL DEFAULT '2026-11-05'
);
CREATE INDEX chat_ai_usage_owner ON chat_ai_usage(owner_id,created_at DESC);
CREATE INDEX chat_ai_usage_budget ON chat_ai_usage(created_at) WHERE provider='deepseek';
CREATE TABLE chat_ai_budget(day date PRIMARY KEY,used_usd numeric(18,9) NOT NULL DEFAULT 0 CHECK(used_usd>=0));
CREATE FUNCTION chat_ai_usage_quota() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE who uuid;before_bytes bigint:=0;after_bytes bigint:=0;
BEGIN
 IF TG_OP<>'INSERT' THEN who=OLD.owner_id;before_bytes=octet_length(convert_to(to_jsonb(OLD)::text,'UTF8')); END IF;
 IF TG_OP<>'DELETE' THEN
  IF who IS NOT NULL AND NEW.owner_id IS DISTINCT FROM who THEN RAISE EXCEPTION 'owner_immutable'; END IF;
  who=NEW.owner_id;after_bytes=octet_length(convert_to(to_jsonb(NEW)::text,'UTF8'));
 END IF;
 IF who IS NOT NULL THEN PERFORM chat_charge_storage(who,after_bytes-before_bytes); END IF;
 RETURN NULL;
END $$;
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON chat_ai_usage FOR EACH ROW EXECUTE FUNCTION chat_ai_usage_quota();
