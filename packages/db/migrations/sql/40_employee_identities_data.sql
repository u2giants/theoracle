-- DECISIONS.md D2.multi-identity — one-shot, idempotent data migration.
--
-- 1. Copy any existing (auth_provider, auth_user_id, email, last_login_at)
--    tuples from the employees table into employee_identities.
-- 2. Merge Albert's two rows: re-attach the popcre identity onto the gmail
--    employee, then delete the now-empty popcre employee row.
-- 3. NULL out the deprecated auth_* columns on employees so no consumer can
--    accidentally rely on stale data while the columns remain for compat.
--
-- Every step is guarded by existence checks so this file can be re-applied
-- safely on subsequent boots.

BEGIN;

-- (1) Backfill identities from employees that already had auth_user_id set.
--     ON CONFLICT (auth_user_id) DO NOTHING handles re-runs.
INSERT INTO employee_identities (
  employee_id, auth_provider, auth_user_id, auth_provider_subject,
  email, linked_at, last_login_at
)
SELECT
  e.id,
  e.auth_provider,
  e.auth_user_id,
  e.auth_provider_subject,
  e.email,
  COALESCE(e.last_login_at, e.created_at),
  e.last_login_at
FROM employees e
WHERE e.auth_user_id IS NOT NULL
  AND e.auth_provider IS NOT NULL
ON CONFLICT (auth_user_id) DO NOTHING;

-- (2) Albert merge — if both rows still exist, fold popcre into gmail.
DO $$
DECLARE
  gmail_emp uuid;
  popcre_emp uuid;
BEGIN
  SELECT id INTO gmail_emp  FROM employees WHERE email = 'u2giants@gmail.com'  LIMIT 1;
  SELECT id INTO popcre_emp FROM employees WHERE email = 'albert@popcre.com'   LIMIT 1;

  IF gmail_emp IS NOT NULL AND popcre_emp IS NOT NULL AND gmail_emp <> popcre_emp THEN
    -- Re-point any identities currently on the popcre row to the gmail row.
    -- ON CONFLICT guard: if gmail already has an identity for the same provider
    -- (it shouldn't, but be safe), keep the existing one and drop the dup.
    UPDATE employee_identities ei
       SET employee_id = gmail_emp
     WHERE ei.employee_id = popcre_emp
       AND NOT EXISTS (
         SELECT 1 FROM employee_identities other
          WHERE other.employee_id = gmail_emp
            AND other.auth_provider = ei.auth_provider
       );

    -- Any leftover dup identities (same provider already linked elsewhere): drop.
    DELETE FROM employee_identities WHERE employee_id = popcre_emp;

    -- Now the popcre employees row has no children — delete it.
    DELETE FROM employees WHERE id = popcre_emp;
  END IF;
END $$;

-- (3) Stop double-writing to the deprecated columns. NULLing them prevents the
--     linker / RLS from accidentally reading stale identity data while the
--     columns linger for compat. Idempotent.
UPDATE employees
   SET auth_user_id = NULL,
       auth_provider = NULL,
       auth_provider_subject = NULL
 WHERE auth_user_id IS NOT NULL
    OR auth_provider IS NOT NULL
    OR auth_provider_subject IS NOT NULL;

COMMIT;
