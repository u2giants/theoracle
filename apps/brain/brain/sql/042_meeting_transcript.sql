-- Teams meeting transcripts staged for review (plan_meeting_triage_pipeline.md 0.2,
-- narrowed by Albert 2026-11-24: list + one-paragraph summary, no ingest). Idempotent.
CREATE TABLE IF NOT EXISTS cmap.transcript_candidate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_ref text NOT NULL UNIQUE,
  source_kind text NOT NULL CHECK (source_kind IN ('graph', 'recall', 'manual')),
  call_kind text,
  title text NOT NULL DEFAULT 'Meeting transcript',
  meeting_at timestamptz,
  ended_at timestamptz,
  organizer_id text,
  organizer_name text,
  participants jsonb NOT NULL DEFAULT '[]'::jsonb,
  raw_text text NOT NULL,
  summary text,
  summary_error text,
  summarized_at timestamptz,
  state text NOT NULL DEFAULT 'new'
    CHECK (state IN ('new', 'triaged', 'ingested', 'skipped', 'failed')),
  source_id uuid REFERENCES cmap.source (id) ON DELETE SET NULL,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS transcript_candidate_meeting_at_idx
  ON cmap.transcript_candidate (meeting_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS transcript_candidate_unsummarized_idx
  ON cmap.transcript_candidate (created_at) WHERE summary IS NULL;
