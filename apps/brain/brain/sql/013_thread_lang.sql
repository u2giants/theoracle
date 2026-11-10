-- Step 2.1: per-thread language pin for Teams intake threads. Idempotent.
-- Set when the thread's first message is Chinese for an English-locale
-- employee; replies to that thread stay Chinese. NULL means "use the
-- employee locale / message detection" (plan step 2.1).
ALTER TABLE cmap.teams_intake ADD COLUMN IF NOT EXISTS lang text;
