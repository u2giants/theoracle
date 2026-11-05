-- RLS for employee_directory_roles — same shape as the employees and
-- employee_identities policies in 21_rls_policies.sql: admins manage, any
-- signed-in employee can read.

ALTER TABLE employee_directory_roles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS employee_directory_roles_self_select ON employee_directory_roles;
DROP POLICY IF EXISTS employee_directory_roles_admin_all   ON employee_directory_roles;

CREATE POLICY employee_directory_roles_self_select ON employee_directory_roles
  FOR SELECT
  TO authenticated
  USING (
    employee_id = public.current_employee_id()
    OR public.current_employee_is_admin()
  );

CREATE POLICY employee_directory_roles_admin_all ON employee_directory_roles
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());
