-- SUPERSEDED / DEAD MIGRATION ARTIFACT.
--
-- This is preserved for audit only and is deliberately outside migrations/sql,
-- so the raw migration runner never executes it. The final source_workflow_maps
-- schema is owned by migrations/sql/86_macro_first_schema.sql and later amended
-- by 93_source_structure_maps.sql.
--
-- Historical failure mode: both active files began with 86_. The runner sorts
-- filenames lexicographically, so 86_macro_first_schema.sql created the current
-- table first and this older file then attempted indexes/constraints against its
-- retired source_outline_id/workflow_version shape. A fresh database therefore
-- failed even though already-upgraded production had the correct surviving table.

-- First-class workflow-map artifact for structured sources/diagrams.
-- Source outlines remain guidance-only; this table preserves the graph shape
-- (nodes/edges/paths/swimlanes) once so extraction, dedup, macro derivation,
-- and coverage can point at stable graph IDs instead of rediscovering topology
-- from prose claims.

CREATE TABLE IF NOT EXISTS source_workflow_maps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_outline_id uuid NOT NULL REFERENCES source_outlines(id) ON DELETE CASCADE,
  document_id uuid REFERENCES documents(id),
  workflow_version varchar(50) NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'provisional',
  summary text,
  nodes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  edges_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  paths_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  model_run_id uuid REFERENCES model_runs(id),
  context_pack_id uuid REFERENCES oracle_context_packs(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS source_workflow_maps_outline_idx
  ON source_workflow_maps(source_outline_id);
CREATE INDEX IF NOT EXISTS source_workflow_maps_document_idx
  ON source_workflow_maps(document_id);
CREATE INDEX IF NOT EXISTS source_workflow_maps_status_created_idx
  ON source_workflow_maps(status, created_at);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_workflow_maps_status_check'
  ) THEN
    ALTER TABLE source_workflow_maps
      ADD CONSTRAINT source_workflow_maps_status_check
      CHECK (status IN ('provisional', 'superseded', 'failed')) NOT VALID;
    ALTER TABLE source_workflow_maps VALIDATE CONSTRAINT source_workflow_maps_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_workflow_maps_nodes_array_check'
  ) THEN
    ALTER TABLE source_workflow_maps
      ADD CONSTRAINT source_workflow_maps_nodes_array_check
      CHECK (jsonb_typeof(nodes_json) = 'array') NOT VALID;
    ALTER TABLE source_workflow_maps VALIDATE CONSTRAINT source_workflow_maps_nodes_array_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_workflow_maps_edges_array_check'
  ) THEN
    ALTER TABLE source_workflow_maps
      ADD CONSTRAINT source_workflow_maps_edges_array_check
      CHECK (jsonb_typeof(edges_json) = 'array') NOT VALID;
    ALTER TABLE source_workflow_maps VALIDATE CONSTRAINT source_workflow_maps_edges_array_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_workflow_maps_paths_array_check'
  ) THEN
    ALTER TABLE source_workflow_maps
      ADD CONSTRAINT source_workflow_maps_paths_array_check
      CHECK (jsonb_typeof(paths_json) = 'array') NOT VALID;
    ALTER TABLE source_workflow_maps VALIDATE CONSTRAINT source_workflow_maps_paths_array_check;
  END IF;
END $$;

ALTER TABLE source_workflow_maps ENABLE ROW LEVEL SECURITY;
