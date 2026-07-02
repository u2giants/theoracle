BEGIN;

INSERT INTO settings (key, value, description)
VALUES
  (
    'macro_auto_followups_enabled',
    'true'::jsonb,
    'Enable source-outline completion to trigger macro relationship extraction and source coverage audit follow-up workers.'
  ),
  (
    'macro_auto_max_outline_groups',
    '12'::jsonb,
    'Maximum source groups on an outline that can run automatic macro follow-up workers without manual review.'
  ),
  (
    'macro_auto_max_support_claims',
    '40'::jsonb,
    'Maximum support claims included in one automatic macro relationship extraction pass.'
  )
ON CONFLICT (key) DO NOTHING;

COMMIT;
