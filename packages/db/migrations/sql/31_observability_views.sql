-- R3 observability views.
--
-- One denormalized view that joins model_runs with its R3 detail tables.
-- Admin code reads from this view so cost dashboards don't have to repeat
-- the join in every query.

-- ---------------------------------------------------------------------------
-- model_runs_with_usage
--
-- Single row per model_run. Combines:
--   model_runs                  — taskType, model, provider, success, error
--   model_run_usage_details     — full token breakdown, fallback tracking
--   oracle_context_packs        — route, prompt version, cache hashes
--
-- Useful for: cost dashboards (cached_input_tokens / input_tokens hit rate),
-- fallback dashboards (which routes fell back and why), and per-route
-- success-rate reporting.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW model_runs_with_usage AS
SELECT
  mr.id                              AS model_run_id,
  mr.task_type,
  mr.model,
  mr.provider,
  mr.prompt_version,
  mr.dispatch_mode,
  mr.input_tokens                    AS legacy_input_tokens,
  mr.output_tokens                   AS legacy_output_tokens,
  mr.cost_usd,
  mr.latency_ms,
  mr.success,
  mr.error,
  mr.created_at                      AS run_created_at,

  mrud.id                            AS usage_detail_id,
  mrud.route_id,
  mrud.input_tokens,
  mrud.cached_input_tokens,
  mrud.cache_write_tokens,
  mrud.output_tokens,
  mrud.reasoning_tokens,
  mrud.provider_request_id,
  mrud.fell_back_from_route_id,
  mrud.fallback_reason,

  ocp.id                             AS context_pack_id,
  ocp.stable_prefix_hash,
  ocp.dynamic_input_hash,
  ocp.retrieval_plan_id,
  ocp.selected_domains,
  ocp.included_message_ids,
  ocp.included_document_chunk_ids,
  ocp.included_claim_ids,

  -- Derived: cache hit ratio if both numerator and denominator are present.
  CASE
    WHEN mrud.input_tokens IS NULL OR mrud.input_tokens = 0 THEN NULL
    WHEN mrud.cached_input_tokens IS NULL THEN NULL
    ELSE mrud.cached_input_tokens::float / mrud.input_tokens::float
  END AS cache_hit_ratio
FROM model_runs mr
LEFT JOIN model_run_usage_details mrud
  ON mrud.model_run_id = mr.id
LEFT JOIN oracle_context_packs ocp
  ON ocp.id = mrud.context_pack_id;
