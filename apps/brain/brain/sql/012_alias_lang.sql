-- Step 1.4: cross-lingual alias provenance on the existing alias table.
-- The table (entity_id, entity_type, normalized_name) has carried alias
-- matching since step 1; lang/source record how each alias was learned.
-- Idempotent.
ALTER TABLE cmap.entity_alias ADD COLUMN IF NOT EXISTS lang text;
ALTER TABLE cmap.entity_alias ADD COLUMN IF NOT EXISTS source text;
ALTER TABLE cmap.entity_alias ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
