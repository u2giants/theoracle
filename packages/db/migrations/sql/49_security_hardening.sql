-- Security hardening — closes Supabase advisor findings.
--
-- The SECURITY DEFINER helpers (`current_employee_id`,
-- `current_employee_is_admin`) must never be reachable via PostgREST RPC.
-- Revoke EXECUTE from anon / authenticated / PUBLIC and re-grant to
-- service_role so server code and trigger paths still work.
--
-- The rest of the original hardening pass (admin views forced to SECURITY
-- INVOKER, admin-only RLS over the R3/R3.5/R4 tables, and the
-- `provider_cached_content` trigger search_path) targeted Oracle 2 objects
-- that were dropped with that domain (issue #398) and is gone with them.
--
-- Idempotent: every statement is repeatable.

REVOKE EXECUTE ON FUNCTION public.current_employee_id()       FROM anon, authenticated, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.current_employee_is_admin() FROM anon, authenticated, PUBLIC;

GRANT EXECUTE ON FUNCTION public.current_employee_id()       TO service_role;
GRANT EXECUTE ON FUNCTION public.current_employee_is_admin() TO service_role;

-- Some Supabase projects have the optional rls_auto_enable helper, but no
-- repository migration creates it. Lock it down when present without making a
-- clean repository-built database depend on hidden project state.
DO $$
BEGIN
  IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM anon, authenticated, PUBLIC;
    GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO service_role;
  END IF;
END $$;
