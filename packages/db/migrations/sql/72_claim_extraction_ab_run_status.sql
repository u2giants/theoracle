ALTER TABLE claim_extraction_ab_tests
ADD COLUMN IF NOT EXISTS run_status varchar(20) NOT NULL DEFAULT 'idle',
ADD COLUMN IF NOT EXISTS run_requested_at timestamp,
ADD COLUMN IF NOT EXISTS run_started_at timestamp,
ADD COLUMN IF NOT EXISTS run_completed_at timestamp,
ADD COLUMN IF NOT EXISTS last_run_error text;

ALTER TABLE claim_extraction_ab_tests
DROP CONSTRAINT IF EXISTS claim_extraction_ab_tests_run_status_check;

ALTER TABLE claim_extraction_ab_tests
ADD CONSTRAINT claim_extraction_ab_tests_run_status_check
CHECK (run_status IN ('idle', 'queued', 'running', 'complete', 'failed'));

CREATE INDEX IF NOT EXISTS claim_extraction_ab_tests_run_status_idx
  ON claim_extraction_ab_tests (run_status, run_requested_at);
