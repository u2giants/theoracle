-- Admin review flags for the Map review gate (issue #255).
-- One open flag per item: entity/community item_id is the uuid, a relation
-- item_id is "from_uuid:to_uuid:rel_type" (the projected edge triple).
-- Idempotent.
CREATE TABLE IF NOT EXISTS cmap.review_flag (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_type text NOT NULL CHECK (item_type IN ('entity','relation','community')),
  item_id text NOT NULL,
  note text,
  created_by uuid,                    -- auth.users id
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by uuid                    -- auth.users id
);
CREATE UNIQUE INDEX IF NOT EXISTS review_flag_open_idx
  ON cmap.review_flag (item_type, item_id) WHERE resolved_at IS NULL;
