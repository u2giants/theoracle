-- Repair plan C2: function assignment for sources, chunks and entities.
-- Each row pairs one source / chunk / entity with one curated function
-- (cmap.function, repair C1) and carries the assignment's weight and origin:
-- 'auto' rows are computed by the function_assign job and are replaced on
-- every re-run; 'admin' rows are set on the source and entity pages and are
-- never overwritten by the job. A pair has exactly one row, so an admin row
-- for a pair the job also computes wins outright.
--
-- A chunk is classified once per prompt (cmap.extraction stage='function'
-- marks it, like stage='relations' does for the relations pass), then a
-- source's functions are the weighted union of its chunks' rows and an
-- entity's functions are the weighted union of the chunks that mention it —
-- so a hand-off step mentioned in two functions' passages carries both.
-- Idempotent.
CREATE TABLE IF NOT EXISTS cmap.source_function (
  source_id uuid NOT NULL REFERENCES cmap.source(id) ON DELETE CASCADE,
  function_id uuid NOT NULL REFERENCES cmap.function(id) ON DELETE CASCADE,
  weight real NOT NULL CHECK (weight BETWEEN 0 AND 1),
  origin text NOT NULL DEFAULT 'auto' CHECK (origin IN ('auto','admin')),
  PRIMARY KEY (source_id, function_id)
);

CREATE TABLE IF NOT EXISTS cmap.chunk_function (
  chunk_id uuid NOT NULL REFERENCES cmap.chunk(id) ON DELETE CASCADE,
  function_id uuid NOT NULL REFERENCES cmap.function(id) ON DELETE CASCADE,
  weight real NOT NULL CHECK (weight BETWEEN 0 AND 1),
  origin text NOT NULL DEFAULT 'auto' CHECK (origin IN ('auto','admin')),
  PRIMARY KEY (chunk_id, function_id)
);

CREATE TABLE IF NOT EXISTS cmap.entity_function (
  entity_id uuid NOT NULL REFERENCES cmap.entity(id) ON DELETE CASCADE,
  function_id uuid NOT NULL REFERENCES cmap.function(id) ON DELETE CASCADE,
  weight real NOT NULL CHECK (weight BETWEEN 0 AND 1),
  origin text NOT NULL DEFAULT 'auto' CHECK (origin IN ('auto','admin')),
  PRIMARY KEY (entity_id, function_id)
);

-- The function_assign classifier records its raw model output per chunk in
-- cmap.extraction, stage 'function' (the same incremental marker the
-- relations pass uses). Extend the stage vocabulary to hold it.
ALTER TABLE cmap.extraction DROP CONSTRAINT IF EXISTS extraction_stage_check;
ALTER TABLE cmap.extraction ADD CONSTRAINT extraction_stage_check
  CHECK (stage IN ('flat','relations','function'));
