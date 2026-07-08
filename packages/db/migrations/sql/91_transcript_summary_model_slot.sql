-- Dedicated model slot for Teams transcript picker summaries.
-- Values are single-encoded jsonb: route is a JSON string, pool is a JSON array.

INSERT INTO settings (key, value, description, updated_at)
VALUES
  (
    'default_transcript_summary_route',
    '"qwen/qwen3.6-flash"'::jsonb,
    'Auxiliary model route for Teams transcript picker preview summaries.',
    now()
  ),
  (
    'model_pool_transcript_summary',
    '["qwen/qwen3.6-flash","qwen/qwen3.7-plus"]'::jsonb,
    'Ordered fallback chain for Teams transcript picker preview summaries.',
    now()
  )
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = EXCLUDED.description,
    updated_at = now();
