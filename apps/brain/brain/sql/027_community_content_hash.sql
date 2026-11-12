-- Repair plan C3: stable community identities, content-hash regeneration and
-- incomplete propagation.
--
-- * cmap.relation.updated_at: a report's content hash covers its sorted entity
--   ids and relation ids with their updated-at, so relations need the same
--   timestamp column cmap.entity already carries.
-- * cmap.community.content_hash: a report is regenerated when this hash
--   changes, not only when its entity set changes (audit C2). A legacy row
--   (NULL hash) is always regenerated — migrate or regenerate, never reuse a
--   stale key.
-- * cmap.community.incomplete: a report written while a child report was
--   missing is flagged so the next run regenerates it instead of caching it
--   without the child.
-- * cmap.community.function_id: the business function one level-0 cluster
--   belongs to (level-1 rows take the function's own id as their row id and
--   repeat it here; the company row leaves it NULL). Jaccard matching of
--   level-0 identities is scoped to one function. Rows are updated in place
--   under their stable id, so cmap.recommendation / cmap.review_flag
--   references survive every rebuild without re-pointing.
-- Idempotent.
ALTER TABLE cmap.relation
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE cmap.community
  ADD COLUMN IF NOT EXISTS content_hash text;

ALTER TABLE cmap.community
  ADD COLUMN IF NOT EXISTS incomplete boolean NOT NULL DEFAULT false;

ALTER TABLE cmap.community
  ADD COLUMN IF NOT EXISTS function_id uuid REFERENCES cmap.function(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS community_function_idx ON cmap.community (function_id);
