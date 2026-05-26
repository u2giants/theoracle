-- R11.3 — Flip `enable_live_contradiction_interjections` ON.
--
-- Per spec Part 5.1 Rule 1 the default was conservative (false): contradictions
-- were queued silently rather than surfaced live. After R11 lands the full
-- gating stack (decideContradictionInterjection requires severity=high AND
-- detectionConfidence>=80 AND cooldown elapsed AND under per-hour rate cap
-- AND a model-suggested question), live interjection is opt-in via this
-- single setting. The HANDOFF decision (2026-05-26) was to flip it on by
-- default; if it turns out misfires happen in practice, the admin can flip
-- it back via /admin/settings or:
--   UPDATE settings SET value = 'false'::jsonb WHERE key = 'enable_live_contradiction_interjections';
--
-- Idempotent: UPDATE on an existing key. The row was created by the seed.
-- If somehow missing, the worker uses default=false (silent), so this
-- migration just makes the intended ON state explicit.

UPDATE settings
SET value = 'true'::jsonb, updated_at = now()
WHERE key = 'enable_live_contradiction_interjections';

-- Insert it if it doesn't exist yet (defensive — the seed should have created it).
INSERT INTO settings (key, value, description)
SELECT 'enable_live_contradiction_interjections', 'true'::jsonb,
       'If true (R11 default), the contradiction-watcher posts a live message in chat when a high-severity high-confidence contradiction is detected (subject to cooldown + rate cap). If false, contradictions are queued silently for synthesis.'
WHERE NOT EXISTS (SELECT 1 FROM settings WHERE key = 'enable_live_contradiction_interjections');
