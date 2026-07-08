-- Make the Teams transcript picker informative without ingesting transcripts.
-- This extends the discovery table with metadata and a cheap AI preview.

ALTER TABLE meeting_transcripts
  ADD COLUMN IF NOT EXISTS participants jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS duration_seconds integer,
  ADD COLUMN IF NOT EXISTS message_count integer,
  ADD COLUMN IF NOT EXISTS transcript_char_count integer,
  ADD COLUMN IF NOT EXISTS ai_summary text,
  ADD COLUMN IF NOT EXISTS ai_summary_model text,
  ADD COLUMN IF NOT EXISTS ai_summary_generated_at timestamptz;

CREATE INDEX IF NOT EXISTS meeting_transcripts_summary_missing_idx
  ON meeting_transcripts (status, ai_summary_generated_at)
  WHERE ai_summary_generated_at IS NULL;
