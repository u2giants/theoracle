-- Historical generated migrations still create Oracle 2 tables on fresh databases.
-- Keep their data, but deny client access. Missing tables on production are skipped.
-- Explicit allowlist: never change permissions on Company Map or future app tables.
DO $$
DECLARE
  retired_table text;
BEGIN
  FOREACH retired_table IN ARRAY ARRAY[
    'brain_section_versions',
    'brain_sections',
    'business_conversation_details',
    'business_element_claims',
    'business_element_systems',
    'business_elements',
    'business_narrative_macro_details',
    'business_object_top_domains',
    'business_object_versions',
    'business_objects',
    'business_paths',
    'business_process_details',
    'business_reference_details',
    'business_relations',
    'business_responsibility_details',
    'business_rule_details',
    'channel_participants',
    'channels',
    'claim_domains',
    'claim_entities',
    'claim_evidence',
    'claim_metadata',
    'claim_sub_topics',
    'claim_top_domains',
    'claim_translation_events',
    'claim_translations',
    'claims',
    'contradictions',
    'document_chunk_entities',
    'document_chunk_top_domains',
    'document_chunks',
    'document_top_domains',
    'documents',
    'employee_invites',
    'entities',
    'entity_proposals',
    'extraction_batches',
    'extraction_candidate_evidence',
    'extraction_candidates',
    'extraction_validation_results',
    'gaps',
    'job_runs',
    'knowledge_sub_topics',
    'knowledge_top_domains',
    'message_attachments',
    'message_entities',
    'message_top_domains',
    'messages',
    'model_capabilities',
    'model_run_usage_details',
    'model_runs',
    'oracle_context_packs',
    'oracle_interventions',
    'provider_cached_content',
    'section_claims',
    'settings',
    'taxonomy_change_log',
    'taxonomy_proposals',
    'typing_indicators'
  ] LOOP
    IF to_regclass(format('public.%I', retired_table)) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', retired_table);
      EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC, anon, authenticated', retired_table);
    END IF;
  END LOOP;
END $$;
