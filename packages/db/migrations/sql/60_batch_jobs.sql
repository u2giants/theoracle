-- D14 — provider Batch API job tracking
--
-- Adds support for the provider Batch APIs (OpenAI Batch, Vertex Batch
-- Prediction, Anthropic Message Batches) that run async at ~50% off vs
-- the sync endpoints with a 24-hour SLA. See DECISIONS.md D14.
--
-- Tables:
--   provider_batch_jobs                — one row per submitted batch
--   extraction_batches.provider_batch_job_id — link to the owning batch job
--   model_runs.dispatch_mode           — 'sync' | 'batch' for cost analytics
--
-- Idempotent: IF NOT EXISTS / DROP CONSTRAINT IF EXISTS throughout.

-- ---------------------------------------------------------------------------
-- provider_batch_jobs — top-level batch tracking row
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS provider_batch_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider varchar(50) NOT NULL,
  provider_batch_id varchar(255) NOT NULL,
  status varchar(50) NOT NULL DEFAULT 'submitted',
  task_type varchar(100) NOT NULL,
  route_id varchar(255) NOT NULL,
  model_id varchar(255) NOT NULL,
  request_count integer NOT NULL,
  completed_count integer NOT NULL DEFAULT 0,
  failed_count integer NOT NULL DEFAULT 0,
  provider_metadata_json jsonb,
  error_json jsonb,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  poll_last_at timestamptz,
  completed_at timestamptz,
  results_retrieved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS provider_batch_jobs_status_idx
  ON provider_batch_jobs (status);

CREATE UNIQUE INDEX IF NOT EXISTS provider_batch_jobs_provider_batch_unique
  ON provider_batch_jobs (provider, provider_batch_id);

CREATE INDEX IF NOT EXISTS provider_batch_jobs_task_idx
  ON provider_batch_jobs (task_type);

CREATE INDEX IF NOT EXISTS provider_batch_jobs_submitted_idx
  ON provider_batch_jobs (submitted_at);

-- status whitelist
ALTER TABLE provider_batch_jobs
  DROP CONSTRAINT IF EXISTS provider_batch_jobs_status_check;
ALTER TABLE provider_batch_jobs
  ADD CONSTRAINT provider_batch_jobs_status_check
  CHECK (status IN ('submitted','in_progress','completed','failed','expired','canceled'));

-- provider whitelist — keep in sync with OracleProvider type union
ALTER TABLE provider_batch_jobs
  DROP CONSTRAINT IF EXISTS provider_batch_jobs_provider_check;
ALTER TABLE provider_batch_jobs
  ADD CONSTRAINT provider_batch_jobs_provider_check
  CHECK (provider IN ('anthropic','openai','vertex','deepseek','qwen'));

-- counters non-negative + bounded by request_count
ALTER TABLE provider_batch_jobs
  DROP CONSTRAINT IF EXISTS provider_batch_jobs_counter_range_check;
ALTER TABLE provider_batch_jobs
  ADD CONSTRAINT provider_batch_jobs_counter_range_check
  CHECK (
    request_count >= 0
    AND completed_count >= 0
    AND failed_count >= 0
    AND completed_count <= request_count
    AND failed_count <= request_count
  );

-- a non-pending batch must have a completed_at
ALTER TABLE provider_batch_jobs
  DROP CONSTRAINT IF EXISTS provider_batch_jobs_completed_at_check;
ALTER TABLE provider_batch_jobs
  ADD CONSTRAINT provider_batch_jobs_completed_at_check
  CHECK (
    status IN ('submitted','in_progress')
    OR completed_at IS NOT NULL
  );

-- ---------------------------------------------------------------------------
-- extraction_batches.provider_batch_job_id — link per-input rows to the batch
-- ---------------------------------------------------------------------------

ALTER TABLE extraction_batches
  ADD COLUMN IF NOT EXISTS provider_batch_job_id uuid
  REFERENCES provider_batch_jobs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS extraction_batches_provider_batch_job_idx
  ON extraction_batches (provider_batch_job_id);

-- ---------------------------------------------------------------------------
-- model_runs.dispatch_mode — 'sync' | 'batch' for cost dashboards.
-- NULL on legacy rows. New writes set it explicitly per code path.
-- ---------------------------------------------------------------------------

ALTER TABLE model_runs
  ADD COLUMN IF NOT EXISTS dispatch_mode varchar(20);

ALTER TABLE model_runs
  DROP CONSTRAINT IF EXISTS model_runs_dispatch_mode_check;
ALTER TABLE model_runs
  ADD CONSTRAINT model_runs_dispatch_mode_check
  CHECK (dispatch_mode IS NULL OR dispatch_mode IN ('sync','batch'));

CREATE INDEX IF NOT EXISTS model_runs_dispatch_mode_idx
  ON model_runs (dispatch_mode);
