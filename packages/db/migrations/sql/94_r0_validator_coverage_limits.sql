-- R0: validator/reference integrity, deterministic coverage, and reader budgets.
-- The gaps.gap_type column is intentionally free text; model_coverage needs no
-- enum/schema change. Stable idempotency uses a deterministic gaps.id UUID.

INSERT INTO settings (key, value, description)
VALUES
  ('source_reader_max_read_calls_per_source', '40'::jsonb,
   'Fail-loud cap on segmentation and detailed source-reader model calls per immutable source.'),
  ('source_reader_max_input_tokens_per_source', '500000'::jsonb,
   'Fail-loud cap on estimated source-reader input tokens per immutable source.'),
  ('source_reader_max_estimated_cost_usd_per_source', '10'::jsonb,
   'Fail-loud cap on estimated source-reader input cost in USD per immutable source.'),
  ('source_reader_estimated_input_cost_per_million_tokens_usd', '5'::jsonb,
   'Conservative configurable input-token rate used only for source-reader pre-dispatch budget estimates.'),
  ('source_reader_max_repair_attempts_per_source', '1'::jsonb,
   'Maximum bounded segmentation repair attempts per immutable source.'),
  ('source_reader_max_concurrency_per_source', '4'::jsonb,
   'Maximum concurrent detailed segment reads for one immutable source.')
ON CONFLICT (key) DO NOTHING;

ALTER TABLE extraction_validation_results
  DROP CONSTRAINT IF EXISTS extraction_validation_results_check_name_check;
ALTER TABLE extraction_validation_results
  ADD CONSTRAINT extraction_validation_results_check_name_check
  CHECK (check_name IN (
    'source_exists','quote_exact_match','quote_offsets_match','source_type_valid',
    'not_duplicate','domain_valid','score_range_valid','sensitivity_gate',
    'promotion_transaction','duplicate_promotion_lock','validation_loop_circuit_breaker',
    'map_element_ref_membership'
  ));

COMMENT ON COLUMN gaps.gap_type IS
  'Free-text gap discriminator. model_coverage rows are administrative quality findings and must be excluded from employee-facing consumers.';
