CREATE TABLE chat_accounts (
 id uuid PRIMARY KEY,email text NOT NULL UNIQUE CHECK(email=lower(email)),display_name text NOT NULL,
 password_hash text NOT NULL,active boolean NOT NULL DEFAULT true,created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE chat_web_sessions ADD COLUMN authenticated boolean NOT NULL DEFAULT false;
CREATE INDEX chat_session_owner ON chat_web_sessions(owner_id);
CREATE TABLE chat_auth_attempts (key text PRIMARY KEY,attempts integer NOT NULL DEFAULT 0,window_start timestamptz NOT NULL DEFAULT now());
CREATE TABLE chat_storage_usage (
 owner_id uuid PRIMARY KEY,used_bytes bigint NOT NULL DEFAULT 0 CHECK(used_bytes>=0),
 limit_bytes bigint NOT NULL DEFAULT 209715200 CHECK(limit_bytes BETWEEN 1 AND 209715200)
);
ALTER TABLE chat_conversations ADD COLUMN title_custom boolean NOT NULL DEFAULT false;
ALTER TABLE chat_conversations ADD CONSTRAINT chat_conversation_owner_unique UNIQUE(id,owner_id);
ALTER TABLE chat_messages ADD COLUMN owner_id uuid;
UPDATE chat_messages m SET owner_id=c.owner_id FROM chat_conversations c WHERE c.id=m.conversation_id;
ALTER TABLE chat_messages ALTER COLUMN owner_id SET NOT NULL;
CREATE FUNCTION chat_message_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.owner_id IS NULL THEN SELECT owner_id INTO NEW.owner_id FROM chat_conversations WHERE id=NEW.conversation_id; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER chat_message_owner BEFORE INSERT ON chat_messages FOR EACH ROW EXECUTE FUNCTION chat_message_owner();
CREATE TABLE chat_files (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,conversation_id uuid NOT NULL,
 filename text NOT NULL,media_type text NOT NULL,content bytea NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(conversation_id,owner_id) REFERENCES chat_conversations(id,owner_id) ON DELETE CASCADE
);
-- Make all conversation-derived data deletable together, including feedback.
DO $$ DECLARE r record; BEGIN
 FOR r IN SELECT conrelid::regclass AS tab,conname FROM pg_constraint
 WHERE contype='f' AND conrelid IN ('chat_messages'::regclass,'chat_business_examples'::regclass,'learning_turns'::regclass,'learning_feedback'::regclass)
 LOOP EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',r.tab,r.conname); END LOOP;
END $$;
ALTER TABLE chat_messages ADD FOREIGN KEY(conversation_id,owner_id) REFERENCES chat_conversations(id,owner_id) ON DELETE CASCADE;
ALTER TABLE chat_business_examples ADD FOREIGN KEY(conversation_id,owner_id) REFERENCES chat_conversations(id,owner_id) ON DELETE CASCADE;
ALTER TABLE learning_turns ADD CONSTRAINT learning_turn_owner_unique UNIQUE(id,owner_id);
ALTER TABLE learning_turns ADD FOREIGN KEY(conversation_id,owner_id) REFERENCES chat_conversations(id,owner_id) ON DELETE CASCADE;
ALTER TABLE learning_turns ADD FOREIGN KEY(message_id) REFERENCES chat_messages(id) ON DELETE CASCADE;
ALTER TABLE learning_feedback ADD FOREIGN KEY(turn_id,owner_id) REFERENCES learning_turns(id,owner_id) ON DELETE CASCADE;

CREATE FUNCTION chat_charge_storage(who uuid,amount bigint) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 IF amount=0 THEN RETURN; END IF;
 INSERT INTO chat_storage_usage(owner_id) VALUES(who) ON CONFLICT DO NOTHING;
 UPDATE chat_storage_usage SET used_bytes=greatest(0,used_bytes+amount)
 WHERE owner_id=who AND (amount<=0 OR used_bytes+amount<=limit_bytes);
 IF NOT FOUND THEN RAISE EXCEPTION 'storage_quota_exceeded' USING ERRCODE='P2001'; END IF;
END $$;
CREATE FUNCTION chat_account_storage() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE before_bytes bigint:=0;after_bytes bigint:=0;who uuid;
BEGIN
 IF TG_OP<>'INSERT' THEN
  who=OLD.owner_id;
  IF TG_TABLE_NAME='chat_files' THEN before_bytes=octet_length(OLD.content)+octet_length(OLD.filename)+octet_length(OLD.media_type)+128;
  ELSE before_bytes=octet_length(convert_to(to_jsonb(OLD)::text,'UTF8')); END IF;
 END IF;
 IF TG_OP<>'DELETE' THEN
  IF who IS NOT NULL AND who<>NEW.owner_id THEN RAISE EXCEPTION 'owner_immutable' USING ERRCODE='P2002'; END IF;
  who=NEW.owner_id;
  IF TG_TABLE_NAME='chat_files' THEN after_bytes=octet_length(NEW.content)+octet_length(NEW.filename)+octet_length(NEW.media_type)+128;
  ELSE after_bytes=octet_length(convert_to(to_jsonb(NEW)::text,'UTF8')); END IF;
 END IF;
 PERFORM chat_charge_storage(who,after_bytes-before_bytes);
 RETURN NULL;
END $$;
DO $$ DECLARE tab text; BEGIN
 FOREACH tab IN ARRAY ARRAY['chat_conversations','chat_messages','chat_business_examples','learning_items','learning_turns','learning_feedback','learning_jobs','learning_versions','learning_config'] LOOP
  EXECUTE format('INSERT INTO chat_storage_usage(owner_id,used_bytes) SELECT owner_id,sum(octet_length(convert_to(to_jsonb(t)::text,''UTF8''))) FROM %I t GROUP BY owner_id ON CONFLICT(owner_id) DO UPDATE SET used_bytes=chat_storage_usage.used_bytes+excluded.used_bytes',tab);
  EXECUTE format('CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION chat_account_storage()',tab);
 END LOOP;
END $$;
CREATE TRIGGER chat_storage_quota AFTER INSERT OR UPDATE OR DELETE ON chat_files FOR EACH ROW EXECUTE FUNCTION chat_account_storage();
