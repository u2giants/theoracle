-- DECISIONS.md D2.multi-identity — post-merge identity reconciliation for Albert.
--
-- When the data migration ran, Albert's M365 employees row had already been
-- created via a manual SQL insert that did NOT carry an auth_user_id; the
-- subsequent M365 login set it on that row but state churn between then and
-- migration time meant the data migration only captured Albert's gmail
-- identity (stored as 'magic_link_dev' because Supabase's app_metadata.provider
-- reflected the first-used provider 'email', not the most recent OAuth one).
--
-- Albert's actual Supabase auth.users state (from inspection at migration time):
--   * u2giants@gmail.com → e0968007-7276-46fb-8abd-25baa108f112 (email + google)
--   * albert@popcre.com  → 751efc6f-b030-43cf-9f22-8e82ac389771 (email + azure)
--
-- This file:
--   1. Updates the existing gmail identity from 'magic_link_dev' to 'google'.
--   2. Inserts the missing microsoft identity for Albert pointing at the gmail
--      employee row, using his real M365 auth.users.id.
--
-- Idempotent — ON CONFLICT guards both statements. Safe to re-run.

BEGIN;

-- (1) Re-label the existing gmail identity as 'google' (Supabase will return
-- the same auth_user_id for email + google sign-ins on this user, so future
-- magic-link logins also resolve via Path 1).
UPDATE employee_identities
   SET auth_provider = 'google'
 WHERE auth_user_id = 'e0968007-7276-46fb-8abd-25baa108f112'::uuid
   AND auth_provider = 'magic_link_dev';

-- (2) Attach Albert's M365 identity to his gmail employee row.
INSERT INTO employee_identities (
  employee_id, auth_provider, auth_user_id, email, linked_at, last_login_at
)
SELECT
  e.id,
  'microsoft'::auth_provider,
  '751efc6f-b030-43cf-9f22-8e82ac389771'::uuid,
  'albert@popcre.com',
  now(),
  now()
FROM employees e
WHERE e.email = 'u2giants@gmail.com'
ON CONFLICT (auth_user_id) DO NOTHING;

COMMIT;
