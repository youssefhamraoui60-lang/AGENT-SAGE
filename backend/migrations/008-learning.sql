CREATE TABLE learning_items (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,folder text NOT NULL DEFAULT 'TEST' CHECK(folder='TEST'),
 kind text NOT NULL CHECK(kind IN ('preference','rule','correction','document','example')),
 title text NOT NULL,content text NOT NULL,source text NOT NULL,source_date timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','validated','rejected','superseded')),
 payload jsonb NOT NULL DEFAULT '{}',sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 validated_at timestamptz,validated_by uuid,UNIQUE(owner_id,kind,sha256)
);
CREATE INDEX learning_items_search ON learning_items USING gin(to_tsvector('french',content));
CREATE INDEX learning_owner ON learning_items(owner_id,status,kind);
CREATE TABLE learning_turns (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,conversation_id uuid NOT NULL REFERENCES chat_conversations(id),
 message_id bigint NOT NULL UNIQUE REFERENCES chat_messages(id),user_text text NOT NULL,answer text NOT NULL,
 proposal jsonb NOT NULL DEFAULT '{}',eligible boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE learning_feedback (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,turn_id uuid NOT NULL REFERENCES learning_turns(id),
 verdict text NOT NULL CHECK(verdict IN ('correct','incorrect')),expected text NOT NULL,
 confirmed boolean NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(owner_id,turn_id)
);
CREATE TABLE learning_jobs (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,dataset_sha text NOT NULL,manifest jsonb NOT NULL,
 status text NOT NULL,training_performed boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE learning_config (
 owner_id uuid PRIMARY KEY,enabled boolean NOT NULL DEFAULT true,
 min_examples integer NOT NULL DEFAULT 50 CHECK(min_examples BETWEEN 5 AND 100000),
 interval_hours integer NOT NULL DEFAULT 168 CHECK(interval_hours BETWEEN 1 AND 8760),
 last_job_at timestamptz
);
CREATE TABLE learning_versions (
 id uuid PRIMARY KEY,owner_id uuid NOT NULL,model_name text NOT NULL,digest text NOT NULL,
 status text NOT NULL CHECK(status IN ('baseline','candidate','evaluated','active','retired','rejected')),
 training_performed boolean NOT NULL DEFAULT false,metadata jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(owner_id,model_name,digest)
);
