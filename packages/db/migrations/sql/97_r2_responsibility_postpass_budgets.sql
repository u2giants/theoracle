-- R2 responsibility post-pass budget is independent from the R0/R0.1 repair allowance.
INSERT INTO settings (key, value, description, updated_at)
VALUES
  (
    'responsibility_postpass_max_quote_repairs_per_source',
    '1'::jsonb,
    'Separate fail-loud R2 allowance for at most one strict responsibility quote-copy repair per source.',
    now()
  ),
  (
    'responsibility_postpass_max_omission_retries_per_source',
    '5'::jsonb,
    'Separate fail-loud R2 cap on source-driven responsibility omission retries across one source.',
    now()
  ),
  (
    'responsibility_postpass_max_omission_retries_per_chunk',
    '1'::jsonb,
    'Separate fail-loud R2 cap on source-driven responsibility omission retries for one chunk.',
    now()
  )
ON CONFLICT (key) DO NOTHING;
