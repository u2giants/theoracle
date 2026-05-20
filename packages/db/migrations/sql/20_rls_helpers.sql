-- Spec 7.1 — RLS identity helpers.
-- These functions are SECURITY DEFINER so they can read employees while RLS
-- is enabled on that table. They are STABLE so the planner can call once per
-- statement.

CREATE OR REPLACE FUNCTION public.current_employee_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id
  FROM employees
  WHERE auth_user_id = auth.uid()
    AND disabled_at IS NULL
  LIMIT 1
$$;

CREATE OR REPLACE FUNCTION public.current_employee_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE(is_admin, false)
  FROM employees
  WHERE auth_user_id = auth.uid()
    AND disabled_at IS NULL
  LIMIT 1
$$;

-- Lock down the helpers so only the application roles can call them.
REVOKE ALL ON FUNCTION public.current_employee_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.current_employee_is_admin() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_employee_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.current_employee_is_admin() TO authenticated, service_role;
