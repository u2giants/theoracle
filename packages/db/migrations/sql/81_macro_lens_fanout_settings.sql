BEGIN;

INSERT INTO settings (key, value, description)
VALUES
  (
    'macro_lenses_enabled',
    'true'::jsonb,
    'Enable source-outline completion to dispatch budgeted document lens extraction workers.'
  ),
  (
    'macro_max_lenses_per_document',
    '4'::jsonb,
    'Maximum document lens extraction tasks selected per document outline.'
  ),
  (
    'macro_max_lens_groups_per_document',
    '8'::jsonb,
    'Maximum source groups considered for automatic document lens extraction.'
  ),
  (
    'macro_max_lens_model_calls_per_document',
    '4'::jsonb,
    'Maximum model calls allowed for automatic document lens fan-out per document.'
  ),
  (
    'macro_max_lens_estimated_input_tokens',
    '32000'::jsonb,
    'Estimated input-token ceiling for automatic document lens fan-out per document.'
  )
ON CONFLICT (key) DO NOTHING;

COMMIT;

