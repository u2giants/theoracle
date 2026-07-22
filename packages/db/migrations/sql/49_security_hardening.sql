-- Security hardening — closes Supabase advisor findings raised after R3 / R3.5
-- / R4 tables and views landed.
--
-- Four things:
--   1. Admin views default to SECURITY DEFINER under the postgres superuser
--      that runs migrations. Force INVOKER so RLS on the underlying tables
--      actually applies to view consumers.
--   2. The new R3 / R3.5 / R4 tables had RLS auto-enabled but no explicit
--      policies. Add the admin-only policy uniformly across all of them —
--      they're service-role-only in practice, but the explicit policy closes
--      the linter gap and documents intent.
--   3. SECURITY DEFINER helpers (`current_employee_id`, `current_employee_is_admin`,
--      `rls_auto_enable`) must never be reachable via PostgREST RPC. Revoke
--      EXECUTE from anon / authenticated / PUBLIC and re-grant to service_role
--      so server code and trigger paths still work.
--   4. Trigger function `provider_cached_content_touch_updated_at` had a
--      mutable search_path — pin it.
--
-- Idempotent: every statement is repeatable.

-- ── 1. Admin views → SECURITY INVOKER ────────────────────────────────────────
ALTER VIEW claims_with_primary_evidence           SET (security_invoker = on);
ALTER VIEW employee_claims                        SET (security_invoker = on);
ALTER VIEW section_claims_with_evidence           SET (security_invoker = on);
ALTER VIEW open_gaps_by_employee                  SET (security_invoker = on);
ALTER VIEW claims_pending_review_with_evidence    SET (security_invoker = on);
ALTER VIEW latest_brain_sections                  SET (security_invoker = on);
ALTER VIEW contradictions_with_claim_summaries    SET (security_invoker = on);
ALTER VIEW model_runs_with_usage                  SET (security_invoker = on);

-- ── 2. New R3 / R3.5 / R4 tables → admin-only RLS policies ───────────────────
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    -- R3 observability
    'model_run_usage_details','oracle_context_packs','provider_cached_content',
    -- R3.5 taxonomy
    'claim_entities','claim_metadata','claim_sub_topics','claim_top_domains',
    'document_chunk_entities','document_chunk_top_domains','document_top_domains',
    'entities','entity_proposals','knowledge_sub_topics','knowledge_top_domains',
    'message_entities','message_top_domains','taxonomy_change_log','taxonomy_proposals',
    -- R4 extraction staging
    'extraction_batches','extraction_candidates','extraction_candidate_evidence','extraction_validation_results'
  ])
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I_admin_all ON %I', t, t);
    EXECUTE format(
      'CREATE POLICY %I_admin_all ON %I FOR ALL TO authenticated ' ||
      'USING (public.current_employee_is_admin()) ' ||
      'WITH CHECK (public.current_employee_is_admin())',
      t, t
    );
  END LOOP;
END $$;

-- ── 3. SECURITY DEFINER helpers must NOT be callable via REST RPC ────────────
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

-- ── 4. Trigger function search_path pinned ───────────────────────────────────
ALTER FUNCTION public.provider_cached_content_touch_updated_at()
  SET search_path = pg_catalog, public;
