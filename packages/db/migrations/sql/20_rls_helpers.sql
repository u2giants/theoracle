-- Spec 7.1 — RLS identity helpers.
-- These functions are SECURITY DEFINER so they can read employees + identities
-- while RLS is enabled on those tables. They are STABLE so the planner can call
-- once per statement.
--
-- After DECISIONS.md D2.multi-identity, the lookup goes through
-- employee_identities (the authoritative source) and joins to employees for the
-- disabled / is_admin check.

CREATE OR REPLACE FUNCTION public.current_employee_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT e.id
  FROM employees e
  JOIN employee_identities ei ON ei.employee_id = e.id
  WHERE ei.auth_user_id = auth.uid()
    AND e.disabled_at IS NULL
  LIMIT 1
$$;

CREATE OR REPLACE FUNCTION public.current_employee_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE(e.is_admin, false)
  FROM employees e
  JOIN employee_identities ei ON ei.employee_id = e.id
  WHERE ei.auth_user_id = auth.uid()
    AND e.disabled_at IS NULL
  LIMIT 1
$$;

-- Lock down the helpers so only the application roles can call them.
REVOKE ALL ON FUNCTION public.current_employee_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.current_employee_is_admin() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_employee_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.current_employee_is_admin() TO authenticated, service_role;
