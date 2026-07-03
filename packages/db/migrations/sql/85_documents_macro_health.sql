-- documents.macro_health (2026-07-03).
--
-- Document-level health of the macro (holistic) layer, so a document whose macro
-- layer failed can never read as a green `status = complete`. Written by the
-- source-outline / macro-relationship-extraction / source-coverage-audit workers
-- (apps/workers/src/lib/macro-health.ts). Added via hand-written SQL (like
-- documents.context / domain_hints, migration 65) plus schema.ts; a generated
-- Drizzle migration does not accompany it, so db:check-drift may flag it.
--
-- Values: not_applicable | pending | complete | degraded | failed.
--   not_applicable — no macro layer attempted (e.g. non-document sources).
--   pending        — outline dispatched the followups; awaiting their outcome.
--   complete       — a followup succeeded and nothing failed.
--   degraded       — a macro/coverage followup failed (partial holistic layer).
--   failed         — the outline itself failed (no holistic layer at all).

BEGIN;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS macro_health varchar(20) NOT NULL DEFAULT 'not_applicable';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'documents_macro_health_check'
  ) THEN
    ALTER TABLE documents
      ADD CONSTRAINT documents_macro_health_check
      CHECK (macro_health IN ('not_applicable', 'pending', 'complete', 'degraded', 'failed'));
  END IF;
END$$;

COMMIT;
