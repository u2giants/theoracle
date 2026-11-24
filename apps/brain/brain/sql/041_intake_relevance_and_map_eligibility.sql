-- Intake relevance gate, RAG-only routing, and Map eligibility (#607 phase 1).
-- Idempotent. Keeps drop reasons untouched (L3 audit trail) and widens
-- cmap.model_seat.stage safely alongside sql/040_message_relations_seat.sql.

ALTER TABLE cmap.intake_thread ADD COLUMN IF NOT EXISTS tier text;
ALTER TABLE cmap.intake_thread ADD COLUMN IF NOT EXISTS gate_prompt_hash text;
ALTER TABLE cmap.intake_thread ADD COLUMN IF NOT EXISTS gate_reason text;
ALTER TABLE cmap.intake_thread ADD COLUMN IF NOT EXISTS gate_model text;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cmap.intake_thread'::regclass
      AND conname = 'intake_thread_tier_check'
  ) THEN
    ALTER TABLE cmap.intake_thread ADD CONSTRAINT intake_thread_tier_check
      CHECK (tier IS NULL OR tier IN (
        'knowledge',
        'transactional_routine',
        'drop_marketing_auto',
        'drop_irrelevant_internal'
      ));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS intake_thread_tier_idx
  ON cmap.intake_thread (tier) WHERE tier IS NOT NULL;

ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS ingest_tier text NOT NULL DEFAULT 'full';
ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS map_eligible boolean NOT NULL DEFAULT true;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cmap.source'::regclass
      AND conname = 'source_ingest_tier_check'
  ) THEN
    ALTER TABLE cmap.source ADD CONSTRAINT source_ingest_tier_check
      CHECK (ingest_tier IN ('full', 'rag_only'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS source_map_eligible_idx
  ON cmap.source (map_eligible) WHERE map_eligible = true;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cmap.model_seat'::regclass
      AND conname = 'model_seat_stage_check'
      AND pg_get_constraintdef(oid) LIKE '%intake_gate%'
  ) THEN
    ALTER TABLE cmap.model_seat DROP CONSTRAINT IF EXISTS model_seat_stage_check;
    ALTER TABLE cmap.model_seat ADD CONSTRAINT model_seat_stage_check
      CHECK (stage IN (
        'vision',
        'embed',
        'flat',
        'relations',
        'relations_messages',
        'resolve',
        'process',
        'reports',
        'answer',
        'recommend',
        'grade',
        'contradictions',
        'converse',
        'intake_gate'
      ));
  END IF;
END $$;
