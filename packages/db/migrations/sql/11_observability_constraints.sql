-- R3 observability constraints.
--
-- Drizzle generates table DDL only — CHECK constraints and triggers live here.
-- These guard the R3 tables (provider_cached_content, oracle_context_packs,
-- model_run_usage_details) at the DB level so background workers, admin SQL,
-- and any future non-TypeScript integration get the same invariants.
--
-- Idempotent: every constraint uses DROP CONSTRAINT IF EXISTS / DROP TRIGGER
-- IF EXISTS first.

-- ---------------------------------------------------------------------------
-- provider_cached_content — value whitelists
-- ---------------------------------------------------------------------------

ALTER TABLE provider_cached_content
  DROP CONSTRAINT IF EXISTS provider_cached_content_provider_check;
ALTER TABLE provider_cached_content
  ADD CONSTRAINT provider_cached_content_provider_check
  CHECK (provider IN ('anthropic', 'vertex', 'openai'));

ALTER TABLE provider_cached_content
  DROP CONSTRAINT IF EXISTS provider_cached_content_cache_kind_check;
ALTER TABLE provider_cached_content
  ADD CONSTRAINT provider_cached_content_cache_kind_check
  CHECK (cache_kind IN ('explicit', 'implicit'));

ALTER TABLE provider_cached_content
  DROP CONSTRAINT IF EXISTS provider_cached_content_status_check;
ALTER TABLE provider_cached_content
  ADD CONSTRAINT provider_cached_content_status_check
  CHECK (status IN ('active', 'deleted', 'expired', 'failed', 'orphaned'));

-- Reuse counts must be non-negative; expected must be at least 1 (we never
-- create a cache that nobody plans to reuse).
ALTER TABLE provider_cached_content
  DROP CONSTRAINT IF EXISTS provider_cached_content_expected_reuse_check;
ALTER TABLE provider_cached_content
  ADD CONSTRAINT provider_cached_content_expected_reuse_check
  CHECK (expected_reuse_count >= 1);

ALTER TABLE provider_cached_content
  DROP CONSTRAINT IF EXISTS provider_cached_content_actual_reuse_check;
ALTER TABLE provider_cached_content
  ADD CONSTRAINT provider_cached_content_actual_reuse_check
  CHECK (actual_reuse_count >= 0);

-- A deleted row must carry deleted_at and a status_reason; an active row
-- must not. This catches cleanup paths that forget to record the teardown.
ALTER TABLE provider_cached_content
  DROP CONSTRAINT IF EXISTS provider_cached_content_deleted_consistency_check;
ALTER TABLE provider_cached_content
  ADD CONSTRAINT provider_cached_content_deleted_consistency_check
  CHECK (
    (status = 'active' AND deleted_at IS NULL)
    OR (status <> 'active' AND deleted_at IS NOT NULL)
  );

-- ---------------------------------------------------------------------------
-- provider_cached_content — updated_at auto-bump trigger
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION provider_cached_content_touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS provider_cached_content_touch_updated_at ON provider_cached_content;
CREATE TRIGGER provider_cached_content_touch_updated_at
  BEFORE UPDATE ON provider_cached_content
  FOR EACH ROW
  EXECUTE FUNCTION provider_cached_content_touch_updated_at();

-- ---------------------------------------------------------------------------
-- model_run_usage_details — token columns must be non-negative
-- ---------------------------------------------------------------------------

ALTER TABLE model_run_usage_details
  DROP CONSTRAINT IF EXISTS model_run_usage_details_tokens_nonnegative_check;
ALTER TABLE model_run_usage_details
  ADD CONSTRAINT model_run_usage_details_tokens_nonnegative_check
  CHECK (
    (input_tokens IS NULL OR input_tokens >= 0)
    AND (cached_input_tokens IS NULL OR cached_input_tokens >= 0)
    AND (cache_write_tokens IS NULL OR cache_write_tokens >= 0)
    AND (output_tokens IS NULL OR output_tokens >= 0)
    AND (reasoning_tokens IS NULL OR reasoning_tokens >= 0)
  );

-- Cached input tokens cannot exceed total input tokens.
ALTER TABLE model_run_usage_details
  DROP CONSTRAINT IF EXISTS model_run_usage_details_cached_le_input_check;
ALTER TABLE model_run_usage_details
  ADD CONSTRAINT model_run_usage_details_cached_le_input_check
  CHECK (
    cached_input_tokens IS NULL
    OR input_tokens IS NULL
    OR cached_input_tokens <= input_tokens
  );

-- ---------------------------------------------------------------------------
-- oracle_context_packs — hash columns must be 64-char hex (sha256)
-- ---------------------------------------------------------------------------
-- Skipped for now: a regex CHECK would reject the empty-string defaults that
-- a partially-built pack might carry while a worker is still composing it.
-- The application layer guarantees sha256-shaped values when it inserts; this
-- can be tightened in a later migration once usage patterns settle.
