-- Repair plan A6: what a reader could not read stays visible. Idempotent.
-- read_notes: per-source reading notes. Key 'unreadable_regions' holds a list
--   of {"locator": {...}, "note": "..."} objects reported by the vision
--   reader (empty object = nothing to report).
ALTER TABLE cmap.source ADD COLUMN IF NOT EXISTS read_notes jsonb NOT NULL DEFAULT '{}';
