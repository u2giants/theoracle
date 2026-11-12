-- Repair plan E2: whole-document process pass.
-- One flow per Process entity (process_flow), its ordered branching steps
-- (flow_step). Every step carries the relation/mention ids that ground it
-- (plan E2: "every step must cite an existing relation or mention"); the pass
-- drops and logs anything it cannot ground, so this table never holds invented
-- grounding. branch_of is the ordinal of the decision step a branch continues.
-- Idempotent.

CREATE TABLE IF NOT EXISTS cmap.process_flow (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  process_entity_id uuid NOT NULL REFERENCES cmap.entity(id) ON DELETE CASCADE,
  function_id uuid REFERENCES cmap.function(id) ON DELETE SET NULL,
  title text NOT NULL,
  trigger text,
  outcome text,
  version int NOT NULL DEFAULT 1,
  sources uuid[] NOT NULL DEFAULT '{}'    -- contributing sources, merge order
);

CREATE TABLE IF NOT EXISTS cmap.flow_step (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_id uuid NOT NULL REFERENCES cmap.process_flow(id) ON DELETE CASCADE,
  ordinal int NOT NULL,
  step_entity_id uuid REFERENCES cmap.entity(id) ON DELETE SET NULL,
  performer_entity_id uuid REFERENCES cmap.entity(id) ON DELETE SET NULL,
  system_entity_id uuid REFERENCES cmap.entity(id) ON DELETE SET NULL,
  input text,
  output text,
  decision text,
  branch_of int,                          -- ordinal of the step this branch continues
  typical_duration text,
  evidence_relation_ids uuid[] NOT NULL DEFAULT '{}',  -- grounding: cmap.relation and/or cmap.mention ids
  UNIQUE (flow_id, ordinal)
);

-- Cross-source flow disagreements are recorded as rows in cmap.contradiction,
-- owned by D3's B/sql/032_contradictions.sql (which has landed and owns the
-- shape). 033 creates no copy of that table.
