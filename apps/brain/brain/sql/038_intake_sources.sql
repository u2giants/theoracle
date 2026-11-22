-- Message intake step 1.6 (plan_pm_message_intake.md, #607). Idempotent.
-- A message-thread source's date comes from its first record ('message_record').
-- A thread that gained messages is re-ingested as a new source that supersedes
-- the old one ('intake_update').
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cmap.source'::regclass
      AND conname = 'source_date_origin_check'
      AND pg_get_constraintdef(oid) LIKE '%message_record%'
  ) THEN
    ALTER TABLE cmap.source DROP CONSTRAINT IF EXISTS source_date_origin_check;
    ALTER TABLE cmap.source ADD CONSTRAINT source_date_origin_check
      CHECK (date_origin IS NULL OR date_origin IN
        ('admin','meeting_start','interview_answer','document_text','file_metadata',
         'upload_time','message_record'));
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cmap.source_version'::regclass
      AND conname = 'source_version_origin_check'
      AND pg_get_constraintdef(oid) LIKE '%intake_update%'
  ) THEN
    ALTER TABLE cmap.source_version DROP CONSTRAINT IF EXISTS source_version_origin_check;
    ALTER TABLE cmap.source_version ADD CONSTRAINT source_version_origin_check
      CHECK (origin IN ('auto_title', 'auto_similarity', 'admin', 'intake_update'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS source_origin_ref_idx ON cmap.source (origin, external_ref)
  WHERE origin IS NOT NULL;
