-- GAP-10: employee_identities has been the only owned runtime identity source
-- for one rollback-compatible release. The production read-only audit found
-- zero values and no external dependencies on these legacy employees columns.
-- Rerun-safe because raw SQL migrations are replayed by the current runner.

BEGIN;

ALTER TABLE public.employees
  DROP CONSTRAINT IF EXISTS employees_auth_user_id_unique;

DROP INDEX IF EXISTS public.employees_auth_user_id_unique;

ALTER TABLE public.employees
  DROP COLUMN IF EXISTS auth_user_id,
  DROP COLUMN IF EXISTS auth_provider,
  DROP COLUMN IF EXISTS auth_provider_subject;

COMMIT;
