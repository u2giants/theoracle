-- Macro understanding first slice: provisional source outlines and source groups.
-- Outlines are guidance only. They are not claim evidence and are server-only
-- until explicit RLS policies are added for any browser/anon-client access.

CREATE TABLE IF NOT EXISTS source_outlines (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_type varchar(50) NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'provisional',
  outline_version varchar(50) NOT NULL,
  model_run_id uuid REFERENCES model_runs(id),
  context_pack_id uuid REFERENCES oracle_context_packs(id),
  source_hash varchar(64) NOT NULL,
  outline_json jsonb NOT NULL,
  summary text,
  budget_json jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_outline_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_outline_id uuid NOT NULL REFERENCES source_outlines(id) ON DELETE CASCADE,
  source_type varchar(50) NOT NULL,
  document_id uuid REFERENCES documents(id),
  channel_id uuid REFERENCES channels(id),
  meeting_transcript_id uuid,
  start_message_id uuid REFERENCES messages(id),
  end_message_id uuid REFERENCES messages(id),
  source_hash varchar(64),
  metadata_json jsonb
);

CREATE TABLE IF NOT EXISTS source_outline_source_refs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_outline_id uuid NOT NULL REFERENCES source_outlines(id) ON DELETE CASCADE,
  outline_element_id varchar(100),
  ref_type varchar(50) NOT NULL,
  document_chunk_id uuid REFERENCES document_chunks(id),
  message_id uuid REFERENCES messages(id),
  claim_id uuid REFERENCES claims(id),
  ref_role varchar(50),
  metadata_json jsonb
);

CREATE TABLE IF NOT EXISTS source_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_outline_id uuid NOT NULL REFERENCES source_outlines(id) ON DELETE CASCADE,
  group_type varchar(50) NOT NULL,
  title text NOT NULL,
  description text,
  embedding vector(1536),
  sort_order integer,
  metadata_json jsonb
);

CREATE TABLE IF NOT EXISTS source_group_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_group_id uuid NOT NULL REFERENCES source_groups(id) ON DELETE CASCADE,
  item_type varchar(50) NOT NULL,
  document_chunk_id uuid REFERENCES document_chunks(id),
  message_id uuid REFERENCES messages(id),
  sort_order integer NOT NULL DEFAULT 0,
  metadata_json jsonb
);

ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_kind varchar(50);
ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_kind_confidence integer;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_kind_review_status varchar(50);
ALTER TABLE claims ALTER COLUMN claim_kind SET DEFAULT 'uncertain';
ALTER TABLE claims ALTER COLUMN claim_kind_review_status SET DEFAULT 'model_labeled';
UPDATE claims
SET claim_kind = 'uncertain'
WHERE claim_kind IS NULL;
UPDATE claims
SET claim_kind_review_status = 'model_labeled'
WHERE claim_kind_review_status IS NULL;

ALTER TABLE extraction_candidates ADD COLUMN IF NOT EXISTS claim_kind varchar(50);
ALTER TABLE extraction_candidates ADD COLUMN IF NOT EXISTS claim_kind_confidence integer;
ALTER TABLE extraction_candidates ALTER COLUMN claim_kind SET DEFAULT 'uncertain';

CREATE TABLE IF NOT EXISTS macro_relationships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  relationship_type varchar(100) NOT NULL,
  summary text NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'pending_review',
  staleness_reason text,
  stale_since timestamptz,
  source_outline_id uuid REFERENCES source_outlines(id),
  confidence_score integer NOT NULL,
  impact_score integer NOT NULL,
  triage_score numeric,
  embedding vector(1536),
  metadata_json jsonb,
  model_run_id uuid REFERENCES model_runs(id),
  context_pack_id uuid REFERENCES oracle_context_packs(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS macro_relationship_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  macro_relationship_id uuid NOT NULL REFERENCES macro_relationships(id) ON DELETE CASCADE,
  source_type varchar(50) NOT NULL,
  document_id uuid REFERENCES documents(id),
  channel_id uuid REFERENCES channels(id),
  meeting_transcript_id uuid,
  metadata_json jsonb
);

CREATE TABLE IF NOT EXISTS macro_relationship_claims (
  macro_relationship_id uuid NOT NULL REFERENCES macro_relationships(id) ON DELETE CASCADE,
  claim_id uuid NOT NULL REFERENCES claims(id) ON DELETE RESTRICT,
  support_role varchar(50) NOT NULL,
  claim_status_at_link varchar(50) NOT NULL,
  claim_version_hash varchar(64),
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (macro_relationship_id, claim_id, support_role)
);

CREATE TABLE IF NOT EXISTS macro_relationship_review_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  macro_relationship_id uuid NOT NULL REFERENCES macro_relationships(id) ON DELETE CASCADE,
  action varchar(50) NOT NULL,
  reviewed_by_employee_id uuid REFERENCES employees(id),
  reviewer_note text,
  before_state jsonb NOT NULL,
  after_state jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_coverage_findings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_outline_id uuid REFERENCES source_outlines(id),
  finding_type varchar(100) NOT NULL,
  summary text NOT NULL,
  suggested_question text,
  related_claim_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  related_source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  severity integer NOT NULL DEFAULT 5,
  triage_score numeric,
  status varchar(50) NOT NULL DEFAULT 'open',
  created_gap_id uuid REFERENCES gaps(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS source_outlines_source_status_created_idx
  ON source_outlines(source_type, status, created_at);
CREATE INDEX IF NOT EXISTS source_outlines_source_hash_idx
  ON source_outlines(source_hash);
CREATE INDEX IF NOT EXISTS source_outlines_model_run_idx
  ON source_outlines(model_run_id);
CREATE INDEX IF NOT EXISTS source_outlines_context_pack_idx
  ON source_outlines(context_pack_id);

CREATE INDEX IF NOT EXISTS source_outline_sources_outline_idx
  ON source_outline_sources(source_outline_id);
CREATE INDEX IF NOT EXISTS source_outline_sources_document_idx
  ON source_outline_sources(document_id);
CREATE INDEX IF NOT EXISTS source_outline_sources_channel_idx
  ON source_outline_sources(channel_id);

CREATE INDEX IF NOT EXISTS source_outline_source_refs_outline_idx
  ON source_outline_source_refs(source_outline_id);
CREATE INDEX IF NOT EXISTS source_outline_source_refs_chunk_idx
  ON source_outline_source_refs(document_chunk_id);
CREATE INDEX IF NOT EXISTS source_outline_source_refs_message_idx
  ON source_outline_source_refs(message_id);
CREATE INDEX IF NOT EXISTS source_outline_source_refs_claim_idx
  ON source_outline_source_refs(claim_id);

CREATE INDEX IF NOT EXISTS source_groups_outline_idx
  ON source_groups(source_outline_id);
CREATE INDEX IF NOT EXISTS source_groups_type_idx
  ON source_groups(group_type);

CREATE INDEX IF NOT EXISTS source_group_items_group_idx
  ON source_group_items(source_group_id);
CREATE INDEX IF NOT EXISTS source_group_items_chunk_idx
  ON source_group_items(document_chunk_id);
CREATE INDEX IF NOT EXISTS source_group_items_message_idx
  ON source_group_items(message_id);

CREATE INDEX IF NOT EXISTS claims_claim_kind_idx
  ON claims(claim_kind);
CREATE INDEX IF NOT EXISTS extraction_candidates_claim_kind_idx
  ON extraction_candidates(claim_kind);

CREATE INDEX IF NOT EXISTS macro_relationships_status_created_idx
  ON macro_relationships(status, created_at);
CREATE INDEX IF NOT EXISTS macro_relationships_type_status_idx
  ON macro_relationships(relationship_type, status);
CREATE INDEX IF NOT EXISTS macro_relationships_source_outline_idx
  ON macro_relationships(source_outline_id);
CREATE INDEX IF NOT EXISTS macro_relationships_triage_idx
  ON macro_relationships(triage_score);

CREATE INDEX IF NOT EXISTS macro_relationship_sources_relationship_idx
  ON macro_relationship_sources(macro_relationship_id);
CREATE INDEX IF NOT EXISTS macro_relationship_sources_document_idx
  ON macro_relationship_sources(document_id);
CREATE INDEX IF NOT EXISTS macro_relationship_sources_channel_idx
  ON macro_relationship_sources(channel_id);

CREATE INDEX IF NOT EXISTS macro_relationship_claims_relationship_idx
  ON macro_relationship_claims(macro_relationship_id);
CREATE INDEX IF NOT EXISTS macro_relationship_claims_claim_idx
  ON macro_relationship_claims(claim_id);

CREATE INDEX IF NOT EXISTS macro_relationship_review_events_relationship_idx
  ON macro_relationship_review_events(macro_relationship_id);
CREATE INDEX IF NOT EXISTS macro_relationship_review_events_action_created_idx
  ON macro_relationship_review_events(action, created_at);

CREATE INDEX IF NOT EXISTS source_coverage_findings_outline_idx
  ON source_coverage_findings(source_outline_id);
CREATE INDEX IF NOT EXISTS source_coverage_findings_status_created_idx
  ON source_coverage_findings(status, created_at);
CREATE INDEX IF NOT EXISTS source_coverage_findings_type_status_idx
  ON source_coverage_findings(finding_type, status);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_outlines_source_type_check'
  ) THEN
    ALTER TABLE source_outlines
      ADD CONSTRAINT source_outlines_source_type_check
      CHECK (source_type IN ('document', 'channel_thread', 'meeting_transcript', 'cross_source_set')) NOT VALID;
    ALTER TABLE source_outlines VALIDATE CONSTRAINT source_outlines_source_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_outlines_status_check'
  ) THEN
    ALTER TABLE source_outlines
      ADD CONSTRAINT source_outlines_status_check
      CHECK (status IN ('provisional', 'superseded', 'failed')) NOT VALID;
    ALTER TABLE source_outlines VALIDATE CONSTRAINT source_outlines_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_outline_sources_source_type_check'
  ) THEN
    ALTER TABLE source_outline_sources
      ADD CONSTRAINT source_outline_sources_source_type_check
      CHECK (source_type IN ('document', 'channel', 'meeting_transcript', 'message_range', 'manual_collection')) NOT VALID;
    ALTER TABLE source_outline_sources VALIDATE CONSTRAINT source_outline_sources_source_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_outline_source_refs_ref_type_check'
  ) THEN
    ALTER TABLE source_outline_source_refs
      ADD CONSTRAINT source_outline_source_refs_ref_type_check
      CHECK (ref_type IN ('document_chunk', 'message', 'claim')) NOT VALID;
    ALTER TABLE source_outline_source_refs VALIDATE CONSTRAINT source_outline_source_refs_ref_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_groups_group_type_check'
  ) THEN
    ALTER TABLE source_groups
      ADD CONSTRAINT source_groups_group_type_check
      CHECK (group_type IN ('workflow_stage', 'handoff', 'exception_branch', 'incident_thread', 'entity_context', 'open_question')) NOT VALID;
    ALTER TABLE source_groups VALIDATE CONSTRAINT source_groups_group_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_group_items_item_type_check'
  ) THEN
    ALTER TABLE source_group_items
      ADD CONSTRAINT source_group_items_item_type_check
      CHECK (item_type IN ('document_chunk', 'message')) NOT VALID;
    ALTER TABLE source_group_items VALIDATE CONSTRAINT source_group_items_item_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'claims_claim_kind_check'
  ) THEN
    ALTER TABLE claims
      ADD CONSTRAINT claims_claim_kind_check
      CHECK (claim_kind IS NULL OR claim_kind IN ('policy', 'observed_practice', 'workaround', 'exception', 'historical', 'uncertain', 'proposed_future_state')) NOT VALID;
    ALTER TABLE claims VALIDATE CONSTRAINT claims_claim_kind_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'claims_claim_kind_confidence_check'
  ) THEN
    ALTER TABLE claims
      ADD CONSTRAINT claims_claim_kind_confidence_check
      CHECK (claim_kind_confidence IS NULL OR claim_kind_confidence BETWEEN 1 AND 10) NOT VALID;
    ALTER TABLE claims VALIDATE CONSTRAINT claims_claim_kind_confidence_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'claims_claim_kind_review_status_check'
  ) THEN
    ALTER TABLE claims
      ADD CONSTRAINT claims_claim_kind_review_status_check
      CHECK (claim_kind_review_status IS NULL OR claim_kind_review_status IN ('model_labeled', 'reviewed', 'uncertain')) NOT VALID;
    ALTER TABLE claims VALIDATE CONSTRAINT claims_claim_kind_review_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'extraction_candidates_claim_kind_check'
  ) THEN
    ALTER TABLE extraction_candidates
      ADD CONSTRAINT extraction_candidates_claim_kind_check
      CHECK (claim_kind IS NULL OR claim_kind IN ('policy', 'observed_practice', 'workaround', 'exception', 'historical', 'uncertain', 'proposed_future_state')) NOT VALID;
    ALTER TABLE extraction_candidates VALIDATE CONSTRAINT extraction_candidates_claim_kind_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'extraction_candidates_claim_kind_confidence_check'
  ) THEN
    ALTER TABLE extraction_candidates
      ADD CONSTRAINT extraction_candidates_claim_kind_confidence_check
      CHECK (claim_kind_confidence IS NULL OR claim_kind_confidence BETWEEN 1 AND 10) NOT VALID;
    ALTER TABLE extraction_candidates VALIDATE CONSTRAINT extraction_candidates_claim_kind_confidence_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'macro_relationships_type_check'
  ) THEN
    ALTER TABLE macro_relationships
      ADD CONSTRAINT macro_relationships_type_check
      CHECK (relationship_type IN ('dependency', 'handoff', 'sequence', 'exception_path', 'policy_vs_practice_tension', 'workaround_to_system_limitation', 'definition_resolution', 'coverage_gap', 'contradiction_or_tension')) NOT VALID;
    ALTER TABLE macro_relationships VALIDATE CONSTRAINT macro_relationships_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'macro_relationships_status_check'
  ) THEN
    ALTER TABLE macro_relationships
      ADD CONSTRAINT macro_relationships_status_check
      CHECK (status IN ('pending_review', 'blocked_pending_support', 'approved', 'needs_review', 'stale_support', 'rejected', 'superseded')) NOT VALID;
    ALTER TABLE macro_relationships VALIDATE CONSTRAINT macro_relationships_status_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'macro_relationships_scores_check'
  ) THEN
    ALTER TABLE macro_relationships
      ADD CONSTRAINT macro_relationships_scores_check
      CHECK (confidence_score BETWEEN 1 AND 10 AND impact_score BETWEEN 1 AND 10) NOT VALID;
    ALTER TABLE macro_relationships VALIDATE CONSTRAINT macro_relationships_scores_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'macro_relationship_claims_support_role_check'
  ) THEN
    ALTER TABLE macro_relationship_claims
      ADD CONSTRAINT macro_relationship_claims_support_role_check
      CHECK (support_role IN ('premise', 'enables', 'blocks', 'contrasts', 'defines', 'resolves', 'policy_anchor', 'practice_anchor', 'workaround_anchor')) NOT VALID;
    ALTER TABLE macro_relationship_claims VALIDATE CONSTRAINT macro_relationship_claims_support_role_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'macro_relationship_review_events_action_check'
  ) THEN
    ALTER TABLE macro_relationship_review_events
      ADD CONSTRAINT macro_relationship_review_events_action_check
      CHECK (action IN ('approve', 'reject', 'revise', 'mark_stale', 'revalidate', 'drop_support', 'manual_create')) NOT VALID;
    ALTER TABLE macro_relationship_review_events VALIDATE CONSTRAINT macro_relationship_review_events_action_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_coverage_findings_type_check'
  ) THEN
    ALTER TABLE source_coverage_findings
      ADD CONSTRAINT source_coverage_findings_type_check
      CHECK (finding_type IN ('missing_stage', 'missing_owner', 'missing_branch', 'unresolved_reference', 'unrepresented_exception', 'low_claim_density', 'macro_only_source', 'conflict_without_contradiction')) NOT VALID;
    ALTER TABLE source_coverage_findings VALIDATE CONSTRAINT source_coverage_findings_type_check;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_coverage_findings_status_check'
  ) THEN
    ALTER TABLE source_coverage_findings
      ADD CONSTRAINT source_coverage_findings_status_check
      CHECK (status IN ('open', 'converted_to_gap', 'dismissed', 'resolved')) NOT VALID;
    ALTER TABLE source_coverage_findings VALIDATE CONSTRAINT source_coverage_findings_status_check;
  END IF;
END $$;

-- Server-only boundary for round 1: service-role code can use these tables,
-- but anon/authenticated clients cannot query them directly.
ALTER TABLE source_outlines ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_outline_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_outline_source_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_group_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE macro_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE macro_relationship_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE macro_relationship_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE macro_relationship_review_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_coverage_findings ENABLE ROW LEVEL SECURITY;

INSERT INTO settings (key, value, description, updated_at)
VALUES (
  'macro_outline_injection_enabled',
  'false'::jsonb,
  'When true, document ingestion injects the latest provisional source outline as non-quotable guidance before atomic extraction.',
  now()
)
ON CONFLICT (key) DO NOTHING;
