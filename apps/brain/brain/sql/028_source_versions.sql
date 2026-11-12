-- Repair plan D2: source supersession. Idempotent.
--
-- cmap.source_version records that one source is a newer version of another:
-- source_id is the NEWER document, supersedes_source_id the older one it
-- replaces. origin names how the supersession was decided (auto_title /
-- auto_similarity / admin); a row with decided_at IS NULL is a pending
-- proposal awaiting the one-click confirm on the sources page.
CREATE TABLE IF NOT EXISTS cmap.source_version (
  source_id uuid NOT NULL REFERENCES cmap.source(id) ON DELETE CASCADE,
  supersedes_source_id uuid NOT NULL REFERENCES cmap.source(id) ON DELETE CASCADE,
  origin text NOT NULL CHECK (origin IN ('auto_title', 'auto_similarity', 'admin')),
  decided_at timestamptz,
  PRIMARY KEY (source_id, supersedes_source_id),
  CHECK (source_id <> supersedes_source_id)
);
CREATE INDEX IF NOT EXISTS source_version_old_idx
  ON cmap.source_version (supersedes_source_id, decided_at);
CREATE INDEX IF NOT EXISTS source_version_new_idx
  ON cmap.source_version (source_id, decided_at);

-- relation.status is COMPUTED (brain.versions.recompute_relation_status):
-- 'superseded' when a fact's only sources are superseded, else 'current'.
-- It is never hand-set: the trigger below rejects any UPDATE that touches
-- status outside the recompute. Default 'current' covers fresh rows.
ALTER TABLE cmap.relation ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'current';
ALTER TABLE cmap.relation DROP CONSTRAINT IF EXISTS relation_status_check;
ALTER TABLE cmap.relation ADD CONSTRAINT relation_status_check
  CHECK (status IN ('current', 'superseded'));

CREATE OR REPLACE FUNCTION cmap.relation_status_guard() RETURNS trigger AS $$
BEGIN
  IF current_setting('cmap.status_recompute', true) IS DISTINCT FROM 'on' THEN
    RAISE EXCEPTION
      'cmap.relation.status is computed by brain.versions.recompute_relation_status and cannot be hand-set';
  END IF;
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS relation_status_guard ON cmap.relation;
CREATE TRIGGER relation_status_guard
  BEFORE UPDATE OF status ON cmap.relation
  FOR EACH ROW EXECUTE FUNCTION cmap.relation_status_guard();
