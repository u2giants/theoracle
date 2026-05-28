-- R12 — provider response session state
--
-- Persists provider-native conversation/session handles such as Qwen
-- Responses API `previous_response_id` so chat channels can reuse session
-- cache across requests and processes.

CREATE TABLE IF NOT EXISTS provider_response_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider varchar(50) NOT NULL,
  session_key varchar(255) NOT NULL,
  scope_kind varchar(50) NOT NULL,
  scope_id varchar(255) NOT NULL,
  model_id varchar(255) NOT NULL,
  latest_response_id varchar(255) NOT NULL,
  last_context_pack_id uuid REFERENCES oracle_context_packs(id) ON DELETE SET NULL,
  last_model_run_id uuid REFERENCES model_runs(id) ON DELETE SET NULL,
  expires_at timestamptz,
  metadata_json jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS provider_response_sessions_provider_session_key_unique
  ON provider_response_sessions (provider, session_key);

CREATE INDEX IF NOT EXISTS provider_response_sessions_scope_idx
  ON provider_response_sessions (scope_kind, scope_id);

CREATE INDEX IF NOT EXISTS provider_response_sessions_expires_idx
  ON provider_response_sessions (expires_at);

CREATE OR REPLACE FUNCTION provider_response_sessions_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS provider_response_sessions_touch_updated_at
  ON provider_response_sessions;

CREATE TRIGGER provider_response_sessions_touch_updated_at
  BEFORE UPDATE ON provider_response_sessions
  FOR EACH ROW
  EXECUTE FUNCTION provider_response_sessions_touch_updated_at();
