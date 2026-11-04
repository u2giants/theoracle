-- Teams build-out phase 1: knowledge an employee volunteers to the bot.
-- Idempotent. One row per conversation thread; turns are buffered here until
-- the thread closes (20 minutes of silence or "done"), then one transcript
-- source is ingested and its id recorded.
CREATE TABLE IF NOT EXISTS cmap.teams_intake (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL,           -- public.employees.id
  started_at timestamptz NOT NULL DEFAULT now(),
  last_at timestamptz NOT NULL DEFAULT now(),
  turns jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{speaker, text, at}]
  state text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'closing', 'closed', 'failed')),
  source_id uuid,                      -- cmap.source.id once ingested
  closed_at timestamptz,
  error text
);
CREATE UNIQUE INDEX IF NOT EXISTS teams_intake_one_open_idx
  ON cmap.teams_intake (employee_id) WHERE state = 'open';
CREATE INDEX IF NOT EXISTS teams_intake_state_idx ON cmap.teams_intake (state, last_at);
CREATE INDEX IF NOT EXISTS teams_intake_employee_idx ON cmap.teams_intake (employee_id, started_at DESC);
