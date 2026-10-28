-- Step 6: entity resolution bookkeeping. Idempotent.

CREATE TABLE IF NOT EXISTS cmap.resolve_decision (   -- every judge verdict, so a pair is asked once
  mention_id uuid NOT NULL REFERENCES cmap.mention(id) ON DELETE CASCADE,
  candidate_entity_id uuid NOT NULL REFERENCES cmap.entity(id) ON DELETE CASCADE,
  decided_same boolean NOT NULL,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (mention_id, candidate_entity_id)
);

-- mention_count at the last description rewrite ("never rewritten for this count").
ALTER TABLE cmap.entity ADD COLUMN IF NOT EXISTS described_at_count int;

CREATE INDEX IF NOT EXISTS mention_unresolved_idx ON cmap.mention (entity_type) WHERE entity_id IS NULL;
CREATE INDEX IF NOT EXISTS mention_entity_idx ON cmap.mention (entity_id);
