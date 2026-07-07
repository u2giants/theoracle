BEGIN;

INSERT INTO settings (key, value, description, updated_at)
VALUES (
  'require_workflow_map_for_ingestion',
  'false'::jsonb,
  'When false, document ingestion falls back to blind extraction if source workflow read exhausts its model pool; when true, reader failure fails the document.',
  now()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
