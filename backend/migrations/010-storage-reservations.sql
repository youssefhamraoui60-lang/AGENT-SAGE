ALTER TABLE chat_storage_usage ADD COLUMN reserved_bytes bigint NOT NULL DEFAULT 0 CHECK(reserved_bytes>=0);
CREATE TABLE chat_storage_reservations(id uuid PRIMARY KEY,owner_id uuid NOT NULL,bytes bigint NOT NULL CHECK(bytes>=0),created_at timestamptz NOT NULL DEFAULT now());
CREATE OR REPLACE FUNCTION chat_charge_storage(who uuid,amount bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE reservation uuid; available bigint:=0; consumed bigint:=0;
BEGIN
 IF amount=0 THEN RETURN; END IF;
 INSERT INTO chat_storage_usage(owner_id) VALUES(who) ON CONFLICT DO NOTHING;
 PERFORM 1 FROM chat_storage_usage WHERE owner_id=who FOR UPDATE;
 IF amount>0 THEN
  reservation=nullif(current_setting('chat.quota_reservation',true),'')::uuid;
  IF reservation IS NOT NULL THEN
   SELECT bytes INTO available FROM chat_storage_reservations WHERE id=reservation AND owner_id=who FOR UPDATE;
   consumed=least(amount,coalesce(available,0));
  END IF;
 END IF;
 UPDATE chat_storage_usage SET used_bytes=greatest(0,used_bytes+amount),reserved_bytes=reserved_bytes-consumed
 WHERE owner_id=who AND (amount<=0 OR used_bytes+reserved_bytes+amount-consumed<=limit_bytes);
 IF NOT FOUND THEN RAISE EXCEPTION 'storage_quota_exceeded' USING ERRCODE='P2001'; END IF;
 IF consumed>0 THEN UPDATE chat_storage_reservations SET bytes=bytes-consumed WHERE id=reservation AND owner_id=who; END IF;
END $$;
