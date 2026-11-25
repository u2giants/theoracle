-- 044: Add AI triage summary, suggested action, and reason columns to cmap.correction_note.
-- Keeps human admins in control (Apply / Dismiss) while surfacing a short plain-English
-- AI summary and suggested action first.

ALTER TABLE cmap.correction_note
  ADD COLUMN IF NOT EXISTS ai_summary text;

ALTER TABLE cmap.correction_note
  ADD COLUMN IF NOT EXISTS ai_suggested_action text;

ALTER TABLE cmap.correction_note
  ADD COLUMN IF NOT EXISTS ai_reason text;

ALTER TABLE cmap.correction_note
  ADD COLUMN IF NOT EXISTS ai_triaged_at timestamptz;

ALTER TABLE cmap.correction_note
  ADD COLUMN IF NOT EXISTS ai_triage_error text;

ALTER TABLE cmap.correction_note
  DROP CONSTRAINT IF EXISTS correction_note_ai_suggested_action_check;

ALTER TABLE cmap.correction_note
  ADD CONSTRAINT correction_note_ai_suggested_action_check
  CHECK (
    ai_suggested_action IS NULL
    OR ai_suggested_action IN (
      'apply_ideal_policy',
      'apply_observed_practice',
      'needs_clarification',
      'dismiss'
    )
  );
