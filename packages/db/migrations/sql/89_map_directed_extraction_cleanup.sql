-- Macro-first Stage 3: map-directed extraction cleanup.
--
-- Removes dead lens fan-out / outline-injection settings and adds the runtime
-- switch that keeps the old blind document extraction path callable until the
-- Stage 5 gate retires it.

BEGIN;

DELETE FROM settings
WHERE key IN (
  'macro_lenses_enabled',
  'macro_max_lenses_per_document',
  'macro_max_lens_groups_per_document',
  'macro_max_lens_model_calls_per_document',
  'macro_max_lens_estimated_input_tokens',
  'macro_outline_injection_enabled'
);

INSERT INTO settings (key, value, description)
VALUES (
  'map_directed_extraction_enabled',
  'true'::jsonb,
  'When true, document ingestion reads and injects the source workflow map before extraction and dedups map-referenced candidates by document + map element. When false, extraction uses the old blind document path.'
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
