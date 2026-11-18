-- Project-manager message intake staging (plan_pm_message_intake.md step 1.1,
-- issue #607). Idempotent. Raw message content lives only in these private
-- tables; dropped rows stay with their reason (plan L3).
CREATE TABLE IF NOT EXISTS cmap.intake_item (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  origin text NOT NULL CHECK (origin IN ('clickup', 'teams_chat', 'email')),
  external_id text NOT NULL,
  thread_key text NOT NULL,
  author_ref text,
  sent_at timestamptz,
  body_text text,
  raw jsonb,
  content_hash text,
  drop_reason text,
  collected_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (origin, external_id)
);
CREATE INDEX IF NOT EXISTS intake_item_thread_idx ON cmap.intake_item (origin, thread_key, sent_at);

CREATE TABLE IF NOT EXISTS cmap.intake_thread (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  origin text NOT NULL CHECK (origin IN ('clickup', 'teams_chat', 'email')),
  thread_key text NOT NULL,
  title text,
  started_at timestamptz,
  ended_at timestamptz,
  item_count integer NOT NULL DEFAULT 0,
  token_count integer NOT NULL DEFAULT 0,
  gate_scores jsonb,
  verdict text NOT NULL DEFAULT 'pending' CHECK (verdict IN ('pending', 'kept', 'dropped')),
  summary text,
  source_id uuid REFERENCES cmap.source(id) ON DELETE SET NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (origin, thread_key)
);
CREATE INDEX IF NOT EXISTS intake_thread_verdict_idx ON cmap.intake_thread (verdict);

ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS origin text;
ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS external_ref text;
