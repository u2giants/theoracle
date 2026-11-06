-- Runs after 61_departments.sql creates both tables. Direct server access is
-- unchanged; signed-in employees can read the directory, admins can maintain it.
ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employee_departments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS departments_employee_read ON public.departments;
CREATE POLICY departments_employee_read ON public.departments
  FOR SELECT TO authenticated
  USING (public.current_employee_id() IS NOT NULL);
DROP POLICY IF EXISTS departments_admin_all ON public.departments;
CREATE POLICY departments_admin_all ON public.departments
  FOR ALL TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

DROP POLICY IF EXISTS employee_departments_employee_read ON public.employee_departments;
CREATE POLICY employee_departments_employee_read ON public.employee_departments
  FOR SELECT TO authenticated
  USING (public.current_employee_id() IS NOT NULL);
DROP POLICY IF EXISTS employee_departments_admin_all ON public.employee_departments;
CREATE POLICY employee_departments_admin_all ON public.employee_departments
  FOR ALL TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());
