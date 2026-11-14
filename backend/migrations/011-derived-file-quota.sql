ALTER TABLE learning_jobs ADD COLUMN artifact_bytes bigint NOT NULL DEFAULT 0 CHECK(artifact_bytes>=0);
CREATE OR REPLACE FUNCTION chat_account_storage() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE before_bytes bigint:=0;after_bytes bigint:=0;who uuid;
BEGIN
 IF TG_OP<>'INSERT' THEN
  who=OLD.owner_id;
  IF TG_TABLE_NAME='chat_files' THEN before_bytes=octet_length(OLD.content)+octet_length(OLD.filename)+octet_length(OLD.media_type)+128;
  ELSE
   before_bytes=octet_length(convert_to(to_jsonb(OLD)::text,'UTF8'));
   IF TG_TABLE_NAME='learning_jobs' THEN before_bytes=before_bytes+OLD.artifact_bytes; END IF;
  END IF;
 END IF;
 IF TG_OP<>'DELETE' THEN
  IF who IS NOT NULL AND who<>NEW.owner_id THEN RAISE EXCEPTION 'owner_immutable' USING ERRCODE='P2002'; END IF;
  who=NEW.owner_id;
  IF TG_TABLE_NAME='chat_files' THEN after_bytes=octet_length(NEW.content)+octet_length(NEW.filename)+octet_length(NEW.media_type)+128;
  ELSE
   after_bytes=octet_length(convert_to(to_jsonb(NEW)::text,'UTF8'));
   IF TG_TABLE_NAME='learning_jobs' THEN after_bytes=after_bytes+NEW.artifact_bytes; END IF;
  END IF;
 END IF;
 PERFORM chat_charge_storage(who,after_bytes-before_bytes);
 RETURN NULL;
END $$;
