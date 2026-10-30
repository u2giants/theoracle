-- Step 12: open-question queue and Teams interviews. Idempotent.

-- One stored Bot Framework conversation reference per employee; filled the
-- first time the employee messages the bot. No row = the bot may not write.
CREATE TABLE IF NOT EXISTS cmap.teams_conversation (
  employee_id uuid PRIMARY KEY,        -- public.employees.id
  conversation_ref jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- "stop" from the employee, or the admin page switch.
ALTER TABLE cmap.employee_flags ADD COLUMN IF NOT EXISTS interviews_paused boolean NOT NULL DEFAULT false;

-- Employees who replied "skip" are not asked the same question again.
ALTER TABLE cmap.open_question ADD COLUMN IF NOT EXISTS skipped_by uuid[] NOT NULL DEFAULT '{}';
ALTER TABLE cmap.open_question ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS open_question_asked_idx ON cmap.open_question (target_employee_id, asked_at);

-- Admin page global switch. Interviews run only when BRAIN_INTERVIEW_ENABLED
-- is true AND this row says enabled (the row defaults on, so the env flag
-- is the one switch to turn on; the page can pause everyone).
CREATE TABLE IF NOT EXISTS cmap.interview_setting (
  id boolean PRIMARY KEY DEFAULT true CHECK (id),
  enabled boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO cmap.interview_setting (id, enabled) VALUES (true, true) ON CONFLICT (id) DO NOTHING;

-- Every question actually sent, so the weekly cap counts skipped ones too.
CREATE TABLE IF NOT EXISTS cmap.interview_send (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL,           -- public.employees.id
  question_id uuid REFERENCES cmap.open_question(id) ON DELETE SET NULL,
  sent_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS interview_send_employee_idx ON cmap.interview_send (employee_id, sent_at);
