-- Repair plan G1 (Phase G, issue #520): corrections that stick.
-- A human correction wins over extraction and survives every rebuild: its
-- target_key is content-based (see brain/corrections.py for the scheme), never
-- a row id. Applied at resolution, projection and answer/report assembly.
-- The existing cmap.review_flag rows gain the action chosen at resolve time.
-- Idempotent.

CREATE TABLE IF NOT EXISTS cmap.correction (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  target_kind text NOT NULL CHECK (target_kind IN ('entity','relation','flow_step','assignment','source')),
  target_key text NOT NULL,
  action text NOT NULL CHECK (action IN ('reject','edit','confirm','merge','split','rename','reassign')),
  payload jsonb NOT NULL DEFAULT '{}',
  reason text,
  by text,                            -- actor identifier
  at timestamptz NOT NULL DEFAULT now(),
  active boolean NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS correction_active_idx
  ON cmap.correction (target_kind, target_key) WHERE active;

-- review_flag rows gain the action the admin chose when resolving (G1).
ALTER TABLE cmap.review_flag ADD COLUMN IF NOT EXISTS action text;

-- Existing review_flag rows that name a concrete target are copied into
-- cmap.correction by brain/corrections.py:migrate_review_flags (called from
-- brain.migrate after this file): the copy computes content keys with the one
-- shared Python normaliser, which SQL cannot reproduce without drifting.
