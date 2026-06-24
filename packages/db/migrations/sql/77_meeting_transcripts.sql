-- Meeting-transcript DISCOVERY table — the "list of meetings to choose from".
--
-- The Oracle does NOT auto-ingest meetings. Instead, available transcripts are
-- discovered as metadata only (no content pulled) from two sources:
--   - the Graph change-notification webhook (real-time, discovered_via='subscription')
--   - the on-demand teams-transcript-discovery-scan task (past meetings, 'scan')
-- An admin then picks meetings to ingest on /admin/transcripts; ingesting pulls
-- the VTT and flows into normal extraction. See:
--   apps/web/app/api/teams/notifications/route.ts (webhook → upsert here)
--   apps/workers/src/trigger/teams-transcript-discovery-scan.ts (scan → upsert here)
--   apps/workers/src/trigger/teams-transcript-ingestion.ts (ingest → marks row 'ingested')
--   apps/web/app/admin/transcripts/* (the picker UI + actions)
--
-- Not in the Drizzle schema (mirrors raw_transcripts): hand-written idempotent
-- SQL, re-applies safely on every boot. transcript_id is the full Graph id
-- (text, no length cap — online-meeting ids are ~230 chars).

CREATE TABLE IF NOT EXISTS meeting_transcripts (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  transcript_id          text NOT NULL,
  meeting_id             text,
  call_id                text,
  organizer_id           text,
  organizer_name         text,
  subject                text,
  transcript_content_url text,
  meeting_time           timestamptz,
  status                 text NOT NULL DEFAULT 'available'
                           CHECK (status IN ('available', 'ingested', 'dismissed')),
  ingested_channel_id    uuid REFERENCES channels(id) ON DELETE SET NULL,
  ingested_at            timestamptz,
  discovered_via         text,
  discovered_at          timestamptz NOT NULL DEFAULT now()
);

-- One row per transcript; discovery from either source upserts on this key.
CREATE UNIQUE INDEX IF NOT EXISTS meeting_transcripts_transcript_id_key
  ON meeting_transcripts (transcript_id);

-- The picker lists by status, newest meeting first.
CREATE INDEX IF NOT EXISTS meeting_transcripts_status_time_idx
  ON meeting_transcripts (status, meeting_time DESC);
