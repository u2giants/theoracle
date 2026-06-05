-- Raw Teams call transcripts (WebVTT), persisted at ingestion time.
--
-- Why: `messages` rows are a LOSSY transform of a call (consecutive same-speaker
-- cues merged, speakers resolved to employees, timing dropped). To keep the
-- whole pipeline (parsing → messages → extraction → synthesis) re-runnable from
-- true source — and because Microsoft expires ad-hoc transcripts after a while —
-- we store the original VTT here. The ingestion worker
-- (apps/workers/src/trigger/teams-transcript-ingestion.ts) inserts one row per
-- transcript, idempotent on transcript_id.
--
-- Not a Drizzle-generated table: kept as hand-written idempotent SQL (re-applies
-- safely on every boot). The worker reads/writes it via raw `sql`, so it is not
-- in packages/db/src/schema.ts.

CREATE TABLE IF NOT EXISTS raw_transcripts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_id     uuid REFERENCES channels(id) ON DELETE SET NULL,
  call_id        text,
  transcript_id  text NOT NULL,
  vtt            text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- One row per transcript; re-ingesting the same transcript is a no-op.
CREATE UNIQUE INDEX IF NOT EXISTS raw_transcripts_transcript_id_key
  ON raw_transcripts (transcript_id);

CREATE INDEX IF NOT EXISTS raw_transcripts_channel_idx
  ON raw_transcripts (channel_id);
