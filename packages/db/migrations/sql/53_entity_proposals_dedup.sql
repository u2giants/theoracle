-- 53_entity_proposals_dedup.sql
--
-- Write-time fuzzy-deduplication for entity_proposals.
--
-- When the extraction workers surface the same unknown entity multiple times
-- (e.g. "Disney", "Walt Disney", "Disney approvals") before an admin reviews
-- it, we want to group them into one proposal row instead of flooding the
-- queue with near-duplicates.
--
-- Strategy:
--   1. Enable pg_trgm (safe to call on an existing extension).
--   2. Add proposal_count (how many times this entity surface has been seen).
--   3. Add a GIN trgm index on proposed_canonical_value so the similarity
--      query in stageEntityProposal() can use the index.
--
-- The application-level helper (packages/oracle-engines/src/extraction/
-- stage-entity-proposal.ts) does:
--   SELECT id FROM entity_proposals
--   WHERE proposed_entity_type = $1
--     AND status IN ('pending', 'approved')
--     AND similarity(proposed_canonical_value, $2) >= 0.85
--   ORDER BY similarity(proposed_canonical_value, $2) DESC
--   LIMIT 1
--
-- If a match is found → UPDATE proposal_count + 1 and append to raw_strings_observed.
-- If no match → INSERT new row.
--
-- Idempotent.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE entity_proposals
  ADD COLUMN IF NOT EXISTS proposal_count integer NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS entity_proposals_canonical_value_trgm_idx
  ON entity_proposals
  USING GIN (proposed_canonical_value gin_trgm_ops);
