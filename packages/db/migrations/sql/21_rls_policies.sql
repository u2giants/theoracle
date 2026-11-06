-- Spec 7.2 — Row Level Security policies.
--
-- Conventions:
-- * service_role bypasses RLS automatically in Supabase, but we add explicit
--   USING (true) policies for clarity where needed.
-- * `authenticated` is the role Supabase clients run as after sign-in.
-- * Both live tables are gated through current_employee_id(), which joins
--   through employee_identities.
--
-- Employee and identity policies live here. Directory roles are secured in
-- 21_employee_directory_roles_rls.sql; departments in 63_departments_rls.sql.
-- 22_retired_oracle2_lockdown.sql denies client access to any retired tables
-- recreated by historical generated migrations, skipping absent tables.

-- ===========================================================================
-- Employees
-- ===========================================================================
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS employees_self_select   ON employees;
DROP POLICY IF EXISTS employees_admin_all     ON employees;

-- After DECISIONS.md D2.multi-identity, auth_user_id no longer lives on the
-- employees row — it lives in employee_identities. Use the helper which joins
-- through the identities table.
CREATE POLICY employees_self_select ON employees
  FOR SELECT
  TO authenticated
  USING (id = public.current_employee_id() OR public.current_employee_is_admin());

CREATE POLICY employees_admin_all ON employees
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Employee identities — admin all, employee can read own identities
-- ===========================================================================
ALTER TABLE employee_identities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS employee_identities_self_select ON employee_identities;
DROP POLICY IF EXISTS employee_identities_admin_all   ON employee_identities;

CREATE POLICY employee_identities_self_select ON employee_identities
  FOR SELECT
  TO authenticated
  USING (
    employee_id = public.current_employee_id()
    OR public.current_employee_is_admin()
  );

CREATE POLICY employee_identities_admin_all ON employee_identities
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());
