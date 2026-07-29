-- GAP-13: configurable, model-bounded oversized conversation windows.
INSERT INTO settings (key, value, description, updated_at)
VALUES
  (
    'extraction_window_overlap_messages',
    '2'::jsonb,
    'Complete active messages repeated across adjacent oversized-conversation extraction windows; original evidence IDs remain unchanged.',
    now()
  ),
  (
    'extraction_window_context_ratio',
    '0.7'::jsonb,
    'Share of the smallest configured extraction model context available to formatted conversation text; the rest is reserved for prompts, schema, and output.',
    now()
  )
ON CONFLICT (key) DO NOTHING;

UPDATE settings
SET description = 'Maximum formatted active-conversation characters per extraction window, further capped by the smallest configured model context.',
    updated_at = now()
WHERE key = 'extraction_char_budget'
  AND description IS DISTINCT FROM 'Maximum formatted active-conversation characters per extraction window, further capped by the smallest configured model context.';
