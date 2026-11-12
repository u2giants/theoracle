-- Repair plan D3: contradictions across sources. Idempotent.
--
-- cmap.contradiction holds one row per compared statement pair (and one per
-- PRECEDES cycle) — every classifier verdict is recorded here, and only the
-- conflict kinds are surfaced (page, entities, answers, reports) and queued
-- as gaps for F1:
--   kind:
--     'true_contradiction'  - the statements cannot both hold (open conflict)
--     'policy_vs_practice'  - written policy vs how practice is reported (gap)
--     'precedes_cycle'      - PRECEDES relations that form a cycle (conflict)
--     'changed_over_time'   - the same claim at different source dates; NOT a
--                             conflict (status 'explained'), kept as the feed
--                             D2's supersession work can consume
--     'same' | 'refinement' - record-only verdicts (status 'explained'); they
--                             are the incremental marker that keeps the job
--                             from re-classifying an unchanged pair
--   status: open | explained | resolved (the gap/interview flow moves rows;
--     D3 writes 'open' for conflicts and 'explained' for records)
-- relation_a / relation_b are the two compared relations (for a PRECEDES
--   cycle they are two edges of the cycle; the summary names the whole cycle).
--
-- NOTE on the extraction stage vocabulary: no row in cmap.extraction may use
-- stage 'contradiction' across a boot — 024_function_assignment.sql re-adds
-- the stage CHECK on every migrate and validates existing rows against its
-- 3-value list before this file runs. That is why the pair verdicts above
-- live in cmap.contradiction instead of as cmap.extraction markers. The
-- widened CHECK below is kept so the stage is available to a future pass
-- that writes its rows within a single boot only.
CREATE TABLE IF NOT EXISTS cmap.contradiction (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  relation_a uuid NOT NULL REFERENCES cmap.relation(id) ON DELETE CASCADE,
  relation_b uuid NOT NULL REFERENCES cmap.relation(id) ON DELETE CASCADE,
  kind text NOT NULL,
  summary text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  resolution text,
  resolved_by uuid
);
ALTER TABLE cmap.contradiction DROP CONSTRAINT IF EXISTS contradiction_kind_check;
ALTER TABLE cmap.contradiction ADD CONSTRAINT contradiction_kind_check
  CHECK (kind IN
    ('true_contradiction', 'policy_vs_practice', 'precedes_cycle',
     'changed_over_time', 'same', 'refinement'));
ALTER TABLE cmap.contradiction DROP CONSTRAINT IF EXISTS contradiction_status_check;
ALTER TABLE cmap.contradiction ADD CONSTRAINT contradiction_status_check
  CHECK (status IN ('open', 'explained', 'resolved'));
CREATE INDEX IF NOT EXISTS contradiction_relation_a_idx
  ON cmap.contradiction (relation_a);
CREATE INDEX IF NOT EXISTS contradiction_relation_b_idx
  ON cmap.contradiction (relation_b);
CREATE INDEX IF NOT EXISTS contradiction_status_idx
  ON cmap.contradiction (status, kind);

ALTER TABLE cmap.extraction DROP CONSTRAINT IF EXISTS extraction_stage_check;
ALTER TABLE cmap.extraction ADD CONSTRAINT extraction_stage_check
  CHECK (stage IN ('flat', 'relations', 'function', 'contradiction'));
