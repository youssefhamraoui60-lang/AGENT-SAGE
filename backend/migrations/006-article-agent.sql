CREATE TABLE article_agent_drafts (
 id uuid PRIMARY KEY REFERENCES requests(id),
 draft jsonb NOT NULL,
 revision integer NOT NULL DEFAULT 1,
 validation jsonb NOT NULL DEFAULT '{}',
 validated boolean NOT NULL DEFAULT false,
 operation_id uuid REFERENCES soap_operations(id),
 outcome jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE article_agent_events (
 id bigserial PRIMARY KEY,
 draft_id uuid NOT NULL REFERENCES article_agent_drafts(id),
 kind text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
