-- Issue #604: the interview bot holds one serial conversation per employee.
-- Idempotent. The partial unique index on interview_conversation is the
-- serial guarantee: at most one conversation that is not closed per person.

CREATE TABLE IF NOT EXISTS cmap.interview_conversation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL,           -- public.employees.id
  state text NOT NULL DEFAULT 'awaiting_answer'
    CHECK (state IN ('awaiting_answer','processing','closed')),
  opened_at timestamptz NOT NULL DEFAULT now(),
  last_activity_at timestamptz NOT NULL DEFAULT now(),
  processing_since timestamptz,
  closed_at timestamptz,
  close_reason text,
  exchanges int NOT NULL DEFAULT 0,
  lang text
);
CREATE UNIQUE INDEX IF NOT EXISTS interview_conversation_one_open
  ON cmap.interview_conversation (employee_id) WHERE state <> 'closed';
CREATE INDEX IF NOT EXISTS interview_conversation_employee_idx
  ON cmap.interview_conversation (employee_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS cmap.interview_turn (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL REFERENCES cmap.interview_conversation(id) ON DELETE CASCADE,
  seq int NOT NULL,
  direction text NOT NULL CHECK (direction IN ('out','in')),
  -- out: question | followup | clarify | close | request
  -- in:  answer | dont_know | unclear | request | other
  kind text NOT NULL,
  text text NOT NULL DEFAULT '',
  teams_activity_id text,
  quoted_activity_id text,
  question_id uuid REFERENCES cmap.open_question(id) ON DELETE SET NULL,
  source_id uuid REFERENCES cmap.source(id) ON DELETE SET NULL,
  in_reply_to uuid REFERENCES cmap.interview_turn(id) ON DELETE SET NULL,
  processed boolean NOT NULL DEFAULT false,
  meta jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (conversation_id, seq)
);
CREATE UNIQUE INDEX IF NOT EXISTS interview_turn_in_activity_uniq
  ON cmap.interview_turn (teams_activity_id)
  WHERE teams_activity_id IS NOT NULL AND direction = 'in';
CREATE INDEX IF NOT EXISTS interview_turn_activity_idx
  ON cmap.interview_turn (teams_activity_id);
CREATE INDEX IF NOT EXISTS interview_turn_source_idx
  ON cmap.interview_turn (source_id) WHERE source_id IS NOT NULL;

-- Interview fast lane: answer processing never queues behind global rebuilds.
ALTER TABLE cmap.job ADD COLUMN IF NOT EXISTS lane text NOT NULL DEFAULT 'main';
CREATE INDEX IF NOT EXISTS job_lane_idx ON cmap.job (lane, state, created_at);

-- Sitting length and answer wait (plan O1, O2) live in settings, not code.
ALTER TABLE cmap.interview_setting
  ADD COLUMN IF NOT EXISTS max_exchanges_per_sitting int NOT NULL DEFAULT 5;
ALTER TABLE cmap.interview_setting
  ADD COLUMN IF NOT EXISTS answer_wait_hours int NOT NULL DEFAULT 24;
