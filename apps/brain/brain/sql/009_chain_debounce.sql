-- Debounce gate for the resolve→project→communities chain (issue #415).
-- A job whose run_after is in the future is invisible to the worker claim,
-- so a burst of sources can share one chain run. Idempotent.
ALTER TABLE cmap.job ADD COLUMN IF NOT EXISTS run_after timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS job_run_after_idx ON cmap.job (state, run_after);
