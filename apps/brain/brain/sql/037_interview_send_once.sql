-- Issue #604, plan Steps 1/5/8 (M6): every outgoing interview message is
-- recorded with a send-once key BEFORE it is sent; only the inserter sends.
-- A retried job, a self-heal or a concurrent tick finds the key and never
-- sends a duplicate. Idempotent.
ALTER TABLE cmap.interview_turn ADD COLUMN IF NOT EXISTS send_state text;
ALTER TABLE cmap.interview_turn ADD COLUMN IF NOT EXISTS send_key text;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'interview_turn_send_state_check'
  ) THEN
    ALTER TABLE cmap.interview_turn ADD CONSTRAINT interview_turn_send_state_check
      CHECK (send_state IS NULL OR send_state IN ('sending', 'sent', 'failed'));
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS interview_turn_send_key_uq
  ON cmap.interview_turn (send_key) WHERE send_key IS NOT NULL;
-- Messages already sent before this column existed.
UPDATE cmap.interview_turn SET send_state = 'sent'
 WHERE direction = 'out' AND send_state IS NULL AND teams_activity_id IS NOT NULL;
-- Owner ruling L9: there is no exchange limit; the old setting is unused.
ALTER TABLE cmap.interview_setting DROP COLUMN IF EXISTS max_exchanges_per_sitting;
