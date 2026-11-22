-- Message intake step 2.3 (plan_pm_message_intake.md, #607). Idempotent.
-- Widens cmap.model_seat.stage so message-origin relation extraction
-- ('relations_messages') and all stages in brain.seats.STAGES can be seated
-- independently of document/meeting 'relations' without altering cmap.extraction.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'cmap.model_seat'::regclass
      AND conname = 'model_seat_stage_check'
      AND pg_get_constraintdef(oid) LIKE '%relations_messages%'
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
        'converse'
      ));
  END IF;
END $$;
