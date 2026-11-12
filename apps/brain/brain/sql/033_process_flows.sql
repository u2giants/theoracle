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

-- D3 seam (plan D3 / E2): cmap.contradiction is D3's table
-- (B/sql/032_contradictions.sql, "relation_a, relation_b, kind, summary,
-- status open|explained|resolved, resolution, resolved_by"). D3 had not landed
-- when E2 needed to record cross-source flow disagreements, so E2 provisions
-- the documented shape here; when 032 lands it must stay idempotent
-- (CREATE TABLE IF NOT EXISTS) and owns the shape from then on.
CREATE TABLE IF NOT EXISTS cmap.contradiction (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  relation_a uuid NOT NULL,
  relation_b uuid NOT NULL,
  kind text NOT NULL,
  summary text NOT NULL,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','explained','resolved')),
  resolution text,
  resolved_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);
