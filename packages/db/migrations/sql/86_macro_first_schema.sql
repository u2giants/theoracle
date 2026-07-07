-- Macro-first business model foundation (Stage 1).
--
-- Additive only: source workflow maps, durable business-process graph tables,
-- model-change proposals, recommendations, extraction linkage, and settings.
-- These tables are server/service-role only until explicit RLS policies are
-- added for a browser-facing read path.

BEGIN;

-- Reconcile a stale prod-only 'source_workflow_maps' left by a pre-Stage-1
-- experiment (shape from fix_enhancement.md §7: source_outline_id,
-- workflow_version, coverage_json; recorded in no migration). CREATE IF NOT
-- EXISTS would silently keep it and the index below would fail (42703).
-- Guarded: drops ONLY the legacy shape, ONLY when empty; errors loudly if it
-- somehow holds rows. No-op on fresh databases and on re-runs.
DO $$
BEGIN
  IF to_regclass('public.source_workflow_maps') IS NOT NULL
     AND EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'source_workflow_maps'
         AND column_name = 'source_outline_id'
     )
     AND NOT EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'source_workflow_maps'
         AND column_name = 'source_content_hash'
     ) THEN
    IF EXISTS (SELECT 1 FROM source_workflow_maps LIMIT 1) THEN
      RAISE EXCEPTION
        'source_workflow_maps has the legacy pre-Stage-1 shape AND contains rows — manual reconciliation required before migration 86';
    END IF;
    DROP TABLE source_workflow_maps CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS source_workflow_maps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type varchar(50) NOT NULL,
  document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
  channel_id uuid REFERENCES channels(id) ON DELETE SET NULL,
  segment_ref text,
  source_content_hash varchar(64) NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'pending',
  map_kind varchar(50) NOT NULL DEFAULT 'workflow',
  summary text,
  nodes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  edges_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  lanes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  paths_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  validation_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  model_run_id uuid REFERENCES model_runs(id) ON DELETE SET NULL,
  context_pack_id uuid REFERENCES oracle_context_packs(id) ON DELETE SET NULL,
  superseded_by_map_id uuid REFERENCES source_workflow_maps(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  finalized_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS source_workflow_maps_active_source_hash_unique
  ON source_workflow_maps (
    source_type,
    COALESCE(document_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(channel_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(segment_ref, ''),
    source_content_hash
  )
  WHERE status <> 'superseded';

CREATE INDEX IF NOT EXISTS source_workflow_maps_status_created_idx
  ON source_workflow_maps(status, created_at);
CREATE INDEX IF NOT EXISTS source_workflow_maps_document_idx
  ON source_workflow_maps(document_id);
CREATE INDEX IF NOT EXISTS source_workflow_maps_channel_idx
  ON source_workflow_maps(channel_id);
CREATE INDEX IF NOT EXISTS source_workflow_maps_model_run_idx
  ON source_workflow_maps(model_run_id);
CREATE INDEX IF NOT EXISTS source_workflow_maps_context_pack_idx
  ON source_workflow_maps(context_pack_id);

CREATE TABLE IF NOT EXISTS business_processes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug varchar(160) NOT NULL UNIQUE,
  status varchar(50) NOT NULL DEFAULT 'draft',
  current_version_id uuid,
  summary text,
  embedding vector(1536),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_process_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  process_id uuid NOT NULL REFERENCES business_processes(id) ON DELETE CASCADE,
  version_number integer NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'pending_review',
  narrative text,
  created_from_change_id uuid,
  model_run_id uuid REFERENCES model_runs(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  UNIQUE (process_id, version_number)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_processes_current_version_fk'
  ) THEN
    ALTER TABLE business_processes
      ADD CONSTRAINT business_processes_current_version_fk
      FOREIGN KEY (current_version_id)
      REFERENCES business_process_versions(id)
      ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS business_processes_status_idx
  ON business_processes(status);
CREATE INDEX IF NOT EXISTS business_processes_current_version_idx
  ON business_processes(current_version_id);
CREATE INDEX IF NOT EXISTS business_process_versions_process_status_idx
  ON business_process_versions(process_id, status);

CREATE TABLE IF NOT EXISTS process_nodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES business_process_versions(id) ON DELETE CASCADE,
  node_key varchar(120) NOT NULL,
  label text NOT NULL,
  node_type varchar(50) NOT NULL,
  lane_label text,
  owner_department_id department REFERENCES departments(id) ON DELETE SET NULL,
  owner_entity_id uuid REFERENCES entities(id) ON DELETE SET NULL,
  owner_raw text,
  sort_order integer,
  provisional boolean NOT NULL DEFAULT true,
  confidence_score integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (version_id, node_key)
);

CREATE TABLE IF NOT EXISTS process_edges (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES business_process_versions(id) ON DELETE CASCADE,
  edge_key varchar(120) NOT NULL,
  from_node_key varchar(120) NOT NULL,
  to_node_key varchar(120) NOT NULL,
  condition text,
  edge_type varchar(50) NOT NULL,
  provisional boolean NOT NULL DEFAULT true,
  confidence_score integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (version_id, edge_key)
);

CREATE TABLE IF NOT EXISTS process_node_systems (
  node_id uuid NOT NULL REFERENCES process_nodes(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (node_id, entity_id)
);

CREATE TABLE IF NOT EXISTS process_paths (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES business_process_versions(id) ON DELETE CASCADE,
  path_key varchar(120) NOT NULL,
  name text NOT NULL,
  path_type varchar(50) NOT NULL,
  node_keys_ordered jsonb NOT NULL DEFAULT '[]'::jsonb,
  terminal_outcome text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (version_id, path_key)
);

CREATE TABLE IF NOT EXISTS process_element_claims (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES business_process_versions(id) ON DELETE CASCADE,
  element_kind varchar(20) NOT NULL,
  element_key varchar(120) NOT NULL,
  claim_id uuid NOT NULL REFERENCES claims(id) ON DELETE RESTRICT,
  support_role varchar(50) NOT NULL DEFAULT 'primary',
  claim_status_at_link varchar(50) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (version_id, element_kind, element_key, claim_id, support_role)
);

CREATE UNIQUE INDEX IF NOT EXISTS process_element_claims_primary_unique
  ON process_element_claims(version_id, element_kind, element_key)
  WHERE support_role = 'primary';
CREATE INDEX IF NOT EXISTS process_element_claims_claim_idx
  ON process_element_claims(claim_id);

CREATE TABLE IF NOT EXISTS process_top_domains (
  process_id uuid NOT NULL REFERENCES business_processes(id) ON DELETE CASCADE,
  top_domain_id varchar(100) NOT NULL REFERENCES knowledge_top_domains(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (process_id, top_domain_id)
);

CREATE INDEX IF NOT EXISTS process_top_domains_domain_idx
  ON process_top_domains(top_domain_id);

CREATE TABLE IF NOT EXISTS business_model_changes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  process_id uuid REFERENCES business_processes(id) ON DELETE SET NULL,
  base_version_id uuid REFERENCES business_process_versions(id) ON DELETE SET NULL,
  change_type varchar(50) NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'pending_review',
  superseded_by_change_id uuid REFERENCES business_model_changes(id) ON DELETE SET NULL,
  source_workflow_map_id uuid NOT NULL REFERENCES source_workflow_maps(id) ON DELETE RESTRICT,
  operations_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  summary text,
  contradiction_id uuid REFERENCES contradictions(id) ON DELETE SET NULL,
  reviewed_by uuid REFERENCES employees(id) ON DELETE SET NULL,
  model_run_id uuid REFERENCES model_runs(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  applied_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS business_model_changes_active_idempotency_unique
  ON business_model_changes(
    source_workflow_map_id,
    COALESCE(base_version_id, '00000000-0000-0000-0000-000000000000'::uuid)
  )
  WHERE status <> 'superseded';

CREATE INDEX IF NOT EXISTS business_model_changes_status_created_idx
  ON business_model_changes(status, created_at);
CREATE INDEX IF NOT EXISTS business_model_changes_process_status_idx
  ON business_model_changes(process_id, status);
CREATE INDEX IF NOT EXISTS business_model_changes_source_map_idx
  ON business_model_changes(source_workflow_map_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_process_versions_change_fk'
  ) THEN
    ALTER TABLE business_process_versions
      ADD CONSTRAINT business_process_versions_change_fk
      FOREIGN KEY (created_from_change_id)
      REFERENCES business_model_changes(id)
      ON DELETE SET NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS business_model_change_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_model_change_id uuid NOT NULL REFERENCES business_model_changes(id) ON DELETE CASCADE,
  action varchar(50) NOT NULL,
  reviewed_by_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  reviewer_note text,
  before_state jsonb NOT NULL,
  after_state jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS business_model_change_events_change_idx
  ON business_model_change_events(business_model_change_id, created_at);
CREATE INDEX IF NOT EXISTS business_model_change_events_action_created_idx
  ON business_model_change_events(action, created_at);

CREATE TABLE IF NOT EXISTS recommendations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  process_id uuid NOT NULL REFERENCES business_processes(id) ON DELETE CASCADE,
  version_id uuid NOT NULL REFERENCES business_process_versions(id) ON DELETE CASCADE,
  origin varchar(50) NOT NULL,
  analyzer_key varchar(120),
  title text NOT NULL,
  severity varchar(50) NOT NULL DEFAULT 'info',
  narrative text NOT NULL,
  element_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  support_claim_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(50) NOT NULL DEFAULT 'open',
  model_run_id uuid REFERENCES model_runs(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS recommendations_deterministic_unique
  ON recommendations(version_id, analyzer_key, md5(element_keys::text))
  WHERE origin = 'deterministic' AND analyzer_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS recommendations_process_status_idx
  ON recommendations(process_id, status);
CREATE INDEX IF NOT EXISTS recommendations_version_idx
  ON recommendations(version_id);

ALTER TABLE extraction_candidates ADD COLUMN IF NOT EXISTS map_element_ref text;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS map_element_ref text;

CREATE INDEX IF NOT EXISTS extraction_candidates_map_element_ref_idx
  ON extraction_candidates(map_element_ref);
CREATE INDEX IF NOT EXISTS claims_map_element_ref_idx
  ON claims(map_element_ref);

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_macro_health_check;
ALTER TABLE documents
  ADD CONSTRAINT documents_macro_health_check
  CHECK (macro_health IN (
    'not_applicable',
    'pending',
    'map_failed',
    'map_degraded',
    'merge_pending_review',
    'complete',
    'degraded',
    'failed'
  ));

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_workflow_maps_source_type_check'
  ) THEN
    ALTER TABLE source_workflow_maps
      ADD CONSTRAINT source_workflow_maps_source_type_check
      CHECK (source_type IN ('document', 'meeting', 'conversation_segment')) NOT VALID;
    ALTER TABLE source_workflow_maps VALIDATE CONSTRAINT source_workflow_maps_source_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_workflow_maps_status_check'
  ) THEN
    ALTER TABLE source_workflow_maps
      ADD CONSTRAINT source_workflow_maps_status_check
      CHECK (status IN ('pending', 'validated', 'degraded', 'failed', 'superseded')) NOT VALID;
    ALTER TABLE source_workflow_maps VALIDATE CONSTRAINT source_workflow_maps_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_workflow_maps_map_kind_check'
  ) THEN
    ALTER TABLE source_workflow_maps
      ADD CONSTRAINT source_workflow_maps_map_kind_check
      CHECK (map_kind IN ('workflow', 'reference')) NOT VALID;
    ALTER TABLE source_workflow_maps VALIDATE CONSTRAINT source_workflow_maps_map_kind_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_processes_status_check'
  ) THEN
    ALTER TABLE business_processes
      ADD CONSTRAINT business_processes_status_check
      CHECK (status IN ('draft', 'active', 'archived')) NOT VALID;
    ALTER TABLE business_processes VALIDATE CONSTRAINT business_processes_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_process_versions_status_check'
  ) THEN
    ALTER TABLE business_process_versions
      ADD CONSTRAINT business_process_versions_status_check
      CHECK (status IN ('pending_review', 'approved', 'superseded', 'rejected')) NOT VALID;
    ALTER TABLE business_process_versions VALIDATE CONSTRAINT business_process_versions_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'process_nodes_type_check'
  ) THEN
    ALTER TABLE process_nodes
      ADD CONSTRAINT process_nodes_type_check
      CHECK (node_type IN ('step', 'decision', 'approval_gate', 'system_entry', 'artifact', 'terminal')) NOT VALID;
    ALTER TABLE process_nodes VALIDATE CONSTRAINT process_nodes_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'process_edges_type_check'
  ) THEN
    ALTER TABLE process_edges
      ADD CONSTRAINT process_edges_type_check
      CHECK (edge_type IN ('sequence', 'handoff', 'branch', 'loop', 'exception')) NOT VALID;
    ALTER TABLE process_edges VALIDATE CONSTRAINT process_edges_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'process_paths_type_check'
  ) THEN
    ALTER TABLE process_paths
      ADD CONSTRAINT process_paths_type_check
      CHECK (path_type IN ('main', 'alternate', 'exception', 'loop')) NOT VALID;
    ALTER TABLE process_paths VALIDATE CONSTRAINT process_paths_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'process_element_claims_kind_check'
  ) THEN
    ALTER TABLE process_element_claims
      ADD CONSTRAINT process_element_claims_kind_check
      CHECK (element_kind IN ('node', 'edge')) NOT VALID;
    ALTER TABLE process_element_claims VALIDATE CONSTRAINT process_element_claims_kind_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'process_element_claims_support_role_check'
  ) THEN
    ALTER TABLE process_element_claims
      ADD CONSTRAINT process_element_claims_support_role_check
      CHECK (support_role IN ('primary', 'corroborating')) NOT VALID;
    ALTER TABLE process_element_claims VALIDATE CONSTRAINT process_element_claims_support_role_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_model_changes_type_check'
  ) THEN
    ALTER TABLE business_model_changes
      ADD CONSTRAINT business_model_changes_type_check
      CHECK (change_type IN ('create_process', 'refine_process', 'confirm', 'contradict')) NOT VALID;
    ALTER TABLE business_model_changes VALIDATE CONSTRAINT business_model_changes_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_model_changes_status_check'
  ) THEN
    ALTER TABLE business_model_changes
      ADD CONSTRAINT business_model_changes_status_check
      CHECK (status IN ('pending_review', 'approved', 'rejected', 'auto_applied', 'needs_rebase', 'superseded', 'failed_apply')) NOT VALID;
    ALTER TABLE business_model_changes VALIDATE CONSTRAINT business_model_changes_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_model_changes_base_required_check'
  ) THEN
    ALTER TABLE business_model_changes
      ADD CONSTRAINT business_model_changes_base_required_check
      CHECK (
        (change_type = 'create_process' AND base_version_id IS NULL)
        OR (change_type IN ('refine_process', 'confirm', 'contradict') AND base_version_id IS NOT NULL)
      ) NOT VALID;
    ALTER TABLE business_model_changes VALIDATE CONSTRAINT business_model_changes_base_required_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'business_model_change_events_action_check'
  ) THEN
    ALTER TABLE business_model_change_events
      ADD CONSTRAINT business_model_change_events_action_check
      CHECK (action IN ('create', 'approve', 'reject', 'auto_apply', 'needs_rebase', 'supersede', 'fail_apply', 'veto_claim', 'rebase')) NOT VALID;
    ALTER TABLE business_model_change_events VALIDATE CONSTRAINT business_model_change_events_action_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'recommendations_origin_check'
  ) THEN
    ALTER TABLE recommendations
      ADD CONSTRAINT recommendations_origin_check
      CHECK (origin IN ('deterministic', 'llm')) NOT VALID;
    ALTER TABLE recommendations VALIDATE CONSTRAINT recommendations_origin_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'recommendations_severity_check'
  ) THEN
    ALTER TABLE recommendations
      ADD CONSTRAINT recommendations_severity_check
      CHECK (severity IN ('info', 'warning', 'critical')) NOT VALID;
    ALTER TABLE recommendations VALIDATE CONSTRAINT recommendations_severity_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'recommendations_status_check'
  ) THEN
    ALTER TABLE recommendations
      ADD CONSTRAINT recommendations_status_check
      CHECK (status IN ('open', 'accepted', 'dismissed', 'done')) NOT VALID;
    ALTER TABLE recommendations VALIDATE CONSTRAINT recommendations_status_check;
  END IF;
END $$;

ALTER TABLE source_workflow_maps ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_processes ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_process_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE process_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE process_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE process_node_systems ENABLE ROW LEVEL SECURITY;
ALTER TABLE process_paths ENABLE ROW LEVEL SECURITY;
ALTER TABLE process_element_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE process_top_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_model_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_model_change_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;

INSERT INTO settings (key, value, description, updated_at)
VALUES
  ('serve_provisional_process_elements', 'true'::jsonb, 'When true, chat may serve process elements with unapproved support as explicitly provisional.', now()),
  ('workflow_map_max_dropped_ratio', '0.2'::jsonb, 'Maximum dropped workflow-map element ratio before a validated map is marked degraded.', now()),
  ('model_merge_min_alignment_confidence', '70'::jsonb, 'Minimum confidence score for accepting a source-map to business-model alignment.', now()),
  ('merge_candidate_top_k', '5'::jsonb, 'Internal domain-scoped process shortlist width for business-model merge.', now()),
  ('process_match_top_k', '2'::jsonb, 'Number of business processes to render into chat context.', now()),
  ('workflow_read_max_estimated_input_tokens', '150000'::jsonb, 'Estimated-token threshold above which workflow read uses sequential windows instead of one call.', now()),
  ('model_pool_vision', '["qwen/qwen3-vl-235b-a22b-thinking","google/gemini-2.5-flash","anthropic/claude-sonnet-5"]'::jsonb, 'Ordered fallback chain for image vision transcription.', now()),
  ('default_workflow_read_route', '"anthropic/claude-sonnet-5"'::jsonb, 'Model route for source workflow read.', now()),
  ('model_pool_workflow_read', '["anthropic/claude-sonnet-5","google/gemini-2.5-pro","openai/gpt-4.1"]'::jsonb, 'Ordered fallback chain for source workflow read.', now()),
  ('default_model_merge_route', '"openai/gpt-4.1-mini"'::jsonb, 'Model route for business-model merge alignment.', now()),
  ('model_pool_model_merge', '["openai/gpt-4.1-mini","google/gemini-2.5-flash","anthropic/claude-haiku-4-5-20251001"]'::jsonb, 'Ordered fallback chain for business-model merge alignment.', now()),
  ('model_pool_translation', '["qwen/qwen-mt-plus","qwen/qwen3.7-max","google/gemini-2.5-flash"]'::jsonb, 'Ordered fallback chain for translation.', now()),
  ('model_pool_general', '["qwen/qwen3.7-max","anthropic/claude-haiku-4-5-20251001","google/gemini-2.5-flash"]'::jsonb, 'Ordered fallback chain for general utility tasks.', now())
ON CONFLICT (key) DO NOTHING;

ALTER TABLE claim_review_events ADD COLUMN IF NOT EXISTS review_source varchar(100);
ALTER TABLE claim_review_events ADD COLUMN IF NOT EXISTS business_model_change_id uuid REFERENCES business_model_changes(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS claim_review_events_business_model_change_idx
  ON claim_review_events(business_model_change_id);

COMMIT;
