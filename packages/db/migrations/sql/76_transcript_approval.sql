-- Approval gate for ingested Teams meeting transcripts.
--
-- Adds review/approval state to raw_transcripts (one row per ad-hoc Teams
-- transcript; see 62_raw_transcripts.sql). The transcript-ingestion worker now
-- writes utterances as extraction_status='awaiting_approval' (held); an admin
-- approves/rejects each transcript on /admin/transcripts. Approval flips that
-- channel's held messages to 'pending' so the existing extraction cron picks
-- them up; rejection flips them to 'skipped'.
--
-- raw_transcripts is not in the Drizzle schema (the worker reads/writes it via
-- raw `sql`), so these columns are hand-written idempotent DDL.
--
-- The column-add + one-time backfill run together inside a single guard so the
-- backfill (mark pre-gate transcripts 'approved' — they already flowed to
-- extraction) happens exactly once and never re-clobbers later human decisions
-- on re-boot.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'raw_transcripts' AND column_name = 'approval_status'
  ) THEN
    ALTER TABLE raw_transcripts
      ADD COLUMN approval_status text NOT NULL DEFAULT 'pending_approval',
      ADD COLUMN reviewed_by_employee_id uuid REFERENCES employees(id),
      ADD COLUMN reviewed_at timestamptz,
      ADD COLUMN review_note text;

    -- Transcripts ingested before the gate already flowed to extraction; don't
    -- retroactively surface them in the pending-approval queue.
    UPDATE raw_transcripts SET approval_status = 'approved';
  END IF;
END $$;

-- Constrain the status values (idempotent: drop + recreate).
ALTER TABLE raw_transcripts DROP CONSTRAINT IF EXISTS raw_transcripts_approval_status_check;
ALTER TABLE raw_transcripts
  ADD CONSTRAINT raw_transcripts_approval_status_check
  CHECK (approval_status IN ('pending_approval', 'approved', 'rejected'));

CREATE INDEX IF NOT EXISTS raw_transcripts_approval_status_idx
  ON raw_transcripts (approval_status);
