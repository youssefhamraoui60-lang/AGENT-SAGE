-- Local project data only. No Sage database access.
CREATE TABLE IF NOT EXISTS soap_article_preparations (
 id uuid PRIMARY KEY,
 reference text NOT NULL,
 payload jsonb NOT NULL,
 object_xml text NOT NULL,
 object_sha256 text NOT NULL,
 checks jsonb NOT NULL,
 status text NOT NULL CHECK(status IN ('blocked_existing','blocked_unknown','awaiting_human_review')),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS soap_article_observations (
 id uuid PRIMARY KEY,
 reference text NOT NULL,
 source text NOT NULL,
 result jsonb NOT NULL,
 observed_at timestamptz NOT NULL DEFAULT now()
);
