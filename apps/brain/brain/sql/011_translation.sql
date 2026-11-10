-- Step 1.3: translation sidecar for stored map prose. Idempotent.
-- One row per (artifact, field, language); English canonical text stays in
-- the existing columns and the sidecar carries the companions (plan L6).
CREATE TABLE IF NOT EXISTS cmap.translation (
  kind text NOT NULL CHECK (kind IN ('entity', 'community', 'edge')),
  ref_id uuid NOT NULL,
  field text NOT NULL,
  lang text NOT NULL CHECK (lang IN ('en', 'zh-CN')),
  text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (kind, ref_id, field, lang)
);
