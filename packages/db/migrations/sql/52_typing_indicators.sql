-- 52_typing_indicators.sql
--
-- Lightweight typing-presence heartbeat table.
--
-- The channel-chat client upserts a row when a user starts typing and deletes
-- it when they stop (or when the 2-second idle timer fires). `expires_at` is
-- set to NOW() + 5s on every keystroke so stale rows from disconnected clients
-- are naturally excluded by server-side queries.
--
-- The lull-interjection worker queries:
--   EXISTS (SELECT 1 FROM typing_indicators WHERE channel_id = $1 AND expires_at > NOW())
-- instead of the round-1 hardcoded `isAnyoneTyping = false`.
--
-- Idempotent.

CREATE TABLE IF NOT EXISTS typing_indicators (
  channel_id  uuid NOT NULL REFERENCES channels(id)   ON DELETE CASCADE,
  employee_id uuid NOT NULL REFERENCES employees(id)  ON DELETE CASCADE,
  expires_at  timestamptz NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (channel_id, employee_id)
);

CREATE INDEX IF NOT EXISTS typing_indicators_expires_at_idx
  ON typing_indicators (expires_at);

-- RLS: employees may manage their own indicator; service-role can read all.
ALTER TABLE typing_indicators ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'typing_indicators'
      AND policyname = 'typing_indicators_self_manage'
  ) THEN
    CREATE POLICY typing_indicators_self_manage ON typing_indicators
      FOR ALL
      USING   (employee_id = current_employee_id())
      WITH CHECK (employee_id = current_employee_id());
  END IF;
END $$;
