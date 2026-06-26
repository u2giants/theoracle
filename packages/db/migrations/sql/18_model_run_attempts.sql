-- Durable per-candidate model attempt log.
--
-- model_run_usage_details is intentionally 1:1 with model_runs. Pool-as-chain
-- dispatch needs a separate append-only table so failed/skipped candidates are
-- visible even when no provider usage row exists.

CREATE TABLE IF NOT EXISTS model_run_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_run_id uuid REFERENCES model_runs(id),
  context_pack_id uuid REFERENCES oracle_context_packs(id),
  task_type varchar(100) NOT NULL,
  slot varchar(50) NOT NULL,
  attempt_index integer NOT NULL,
  route_id varchar(100) NOT NULL,
  provider varchar(100) NOT NULL,
  model_id varchar(100) NOT NULL,
  is_primary boolean NOT NULL,
  status varchar(50) NOT NULL,
  error text,
  latency_ms integer,
  provider_request_id varchar(255),
  created_at timestamp NOT NULL DEFAULT now()
);

ALTER TABLE model_run_attempts
  DROP CONSTRAINT IF EXISTS model_run_attempts_status_check;
ALTER TABLE model_run_attempts
  ADD CONSTRAINT model_run_attempts_status_check
  CHECK (status IN ('success', 'failed', 'skipped_capability', 'skipped_unapproved'));

ALTER TABLE model_run_attempts
  DROP CONSTRAINT IF EXISTS model_run_attempts_attempt_index_nonnegative_check;
ALTER TABLE model_run_attempts
  ADD CONSTRAINT model_run_attempts_attempt_index_nonnegative_check
  CHECK (attempt_index >= 0);

ALTER TABLE model_run_attempts
  DROP CONSTRAINT IF EXISTS model_run_attempts_latency_nonnegative_check;
ALTER TABLE model_run_attempts
  ADD CONSTRAINT model_run_attempts_latency_nonnegative_check
  CHECK (latency_ms IS NULL OR latency_ms >= 0);

CREATE INDEX IF NOT EXISTS model_run_attempts_task_created_idx
  ON model_run_attempts (task_type, created_at);
CREATE INDEX IF NOT EXISTS model_run_attempts_slot_created_idx
  ON model_run_attempts (slot, created_at);
CREATE INDEX IF NOT EXISTS model_run_attempts_route_created_idx
  ON model_run_attempts (route_id, created_at);
CREATE INDEX IF NOT EXISTS model_run_attempts_model_run_idx
  ON model_run_attempts (model_run_id);
CREATE INDEX IF NOT EXISTS model_run_attempts_context_pack_idx
  ON model_run_attempts (context_pack_id);
