-- Retry bookkeeping for Teams intake threads whose ingest failed with a
-- transient error (owner direction 2026-11-04). Idempotent.
ALTER TABLE cmap.teams_intake ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0;
ALTER TABLE cmap.teams_intake ADD COLUMN IF NOT EXISTS next_retry_at timestamptz;
