-- Multi-identity support — DECISIONS.md D2.multi-identity.
--
-- One employee can have many identities (Google + Microsoft + future Authentik).
-- The linker resolves an authenticated Supabase user by looking up an identity
-- row keyed on (auth_provider, auth_user_id). If none matches it falls back to
-- email-based linking against employees.email (the first-login bootstrap path).
--
-- This file is run ahead of 20_rls_helpers.sql so the helper functions can join
-- through this table. The data migration that copies existing
-- employees.auth_* values into here lives in 40_employee_identities_data.sql.

CREATE TABLE IF NOT EXISTS employee_identities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  auth_provider auth_provider NOT NULL,
  -- Supabase auth.users.id — globally unique across providers in Supabase.
  auth_user_id uuid NOT NULL UNIQUE,
  -- Provider-stable subject (Google `sub`, Microsoft `oid`).
  auth_provider_subject varchar(255),
  -- Provider email captured at link time. Denormalized so we can show "you can
  -- sign in via X or Y" even if a future email change drifts.
  email varchar(320) NOT NULL,
  linked_at timestamp NOT NULL DEFAULT now(),
  last_login_at timestamp
);

CREATE INDEX IF NOT EXISTS employee_identities_provider_employee_idx
  ON employee_identities (auth_provider, employee_id);
CREATE INDEX IF NOT EXISTS employee_identities_employee_idx
  ON employee_identities (employee_id);
CREATE INDEX IF NOT EXISTS employee_identities_email_idx
  ON employee_identities (email);

-- One identity per provider per employee — prevents an Albert from accidentally
-- holding two Google rows.
CREATE UNIQUE INDEX IF NOT EXISTS employee_identities_provider_employee_unique
  ON employee_identities (auth_provider, employee_id);

ALTER TABLE employee_identities ENABLE ROW LEVEL SECURITY;
