-- DesignFlow directory mirror — DECISIONS.md D-dflow-directory-source-of-truth.
--
-- DesignFlow role names per employee, written only by the brain
-- ``directory_sync`` job from the shared company directory
-- (``api.oracle_user_directory`` on the shared company Supabase). Oracle-only
-- fields stay on ``employees``; rows here are replace-only from the sync and
-- never hand-maintained.
--
-- DDL mirrors the 15_employee_identities.sql pattern; RLS policies live in
-- 21_employee_directory_roles_rls.sql because they call the 20_* helpers.

CREATE TABLE IF NOT EXISTS employee_directory_roles (
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  role_name text NOT NULL,
  PRIMARY KEY (employee_id, role_name)
);

ALTER TABLE employee_directory_roles ENABLE ROW LEVEL SECURITY;
