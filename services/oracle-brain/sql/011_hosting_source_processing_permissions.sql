-- Dedicated Oracle ledger only. Source implementation; no admission rows are issued.
-- The installer must independently pin this existing trusted owner before applying.
DO $owner$
DECLARE owner_oid oid; helper_owner oid;
BEGIN
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 SELECT proowner INTO helper_owner FROM pg_proc WHERE oid=to_regprocedure('oracle2.hosting_source_visible(uuid,uuid)');
 IF owner_oid IS NULL OR helper_owner IS DISTINCT FROM owner_oid
 OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR EXISTS(SELECT 1 FROM pg_roles r WHERE r.rolname IN
 ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata')
 AND pg_has_role(r.oid,owner_oid,'MEMBER')) THEN
  RAISE EXCEPTION 'reviewed dedicated schema/helper owner required';
 END IF;
END $owner$;

CREATE OR REPLACE FUNCTION oracle2._processing_source(
 workspace uuid, source uuid, principal uuid, expected_runtime text, expected_registry text, want_raw boolean)
 RETURNS TABLE(revision integer, original_hash text, reading_hash text, parser_id text, original_reading text, provenance text, valid_until timestamptz, checked_at timestamptz)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_role_source_admissions%ROWTYPE;
 r oracle2.hosting_role_runtime_admissions%ROWTYPE; owner_oid oid; login_oid oid;
 kinds text[]; kind text; reading text; metadata jsonb; n bigint; source_revision integer; source_status text;
 scope_name text; permitted boolean; require_extraction boolean; deadline timestamptz; scope_deadline timestamptz;
BEGIN
 -- Use the SAME connection as an enclosing ledger transaction; never a nested lock connection.
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 SELECT oid INTO login_oid FROM pg_roles WHERE rolname=SESSION_USER
 AND NOT (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication);
 IF login_oid IS NULL OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR pg_has_role(login_oid,owner_oid,'MEMBER') THEN RAISE insufficient_privilege USING MESSAGE='processing owner/session denied'; END IF;
 SELECT array_agg(rolname::text ORDER BY rolname) INTO kinds FROM pg_roles
 WHERE rolname IN ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata')
 AND pg_has_role(login_oid,oid,'MEMBER');
 IF coalesce(cardinality(kinds),0)<>1 THEN RAISE insufficient_privilege USING MESSAGE='exclusive processing role required'; END IF;
 kind:=kinds[1];
 IF want_raw AND kind NOT IN ('oracle2_source_reader','oracle2_candidate_compiler') THEN
  RAISE insufficient_privilege USING MESSAGE='raw processing role denied';
 END IF;
 require_extraction:=kind<>'oracle2_documentary_executor';
 SELECT * INTO r FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 SELECT c.* INTO a FROM oracle2.hosting_role_source_admissions c
 JOIN oracle2.sources s ON s.workspace_id=c.workspace_id AND s.source_id=c.source_id AND s.revision=c.revision
 WHERE c.role_name=SESSION_USER AND c.workspace_id=workspace AND c.source_id=source
 AND c.runtime_hash=expected_runtime AND c.registry_hash=expected_registry
 AND c.principal_id=principal FOR SHARE OF c;
 IF r.role_name IS NULL OR a.role_name IS NULL OR expected_runtime !~ '^[0-9a-f]{64}$'
 OR expected_registry !~ '^[0-9a-f]{64}$' OR r.runtime_hash IS DISTINCT FROM expected_runtime
 OR r.registry_hash IS DISTINCT FROM expected_registry OR a.expires_at<=clock_timestamp()
 OR r.expires_at<=clock_timestamp() OR NOT isfinite(r.expires_at) OR NOT isfinite(a.expires_at) THEN RAISE insufficient_privilege USING MESSAGE='current processing admission denied'; END IF;
 deadline:=least(a.expires_at,r.expires_at);
 SELECT s.revision,s.status INTO source_revision,source_status FROM oracle2.sources s
 WHERE s.workspace_id=workspace AND s.source_id=source FOR SHARE;
 IF source_revision IS DISTINCT FROM a.revision OR source_status NOT IN ('draft','confirmed') OR source_status IS NULL THEN
  RAISE insufficient_privilege USING MESSAGE='current processing source denied';
 END IF;
 -- SHARE also prevents new duplicate draft/original rows (row locks alone allow phantoms).
 LOCK TABLE oracle2.drafts,oracle2.source_blocks IN SHARE MODE;
 -- drafts.status is the current schema's withdrawal marker; its CONTENT is never accepted as truth.
 PERFORM 1 FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source ORDER BY d.draft_id FOR SHARE;
 SELECT count(*) INTO n FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source;
 IF n<>1 OR NOT EXISTS(SELECT 1 FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source AND d.status IN ('draft','confirmed')) THEN
  RAISE insufficient_privilege USING MESSAGE='processing source withdrawn or ambiguous';
 END IF;
 PERFORM 1 FROM oracle2.source_blocks b WHERE b.workspace_id=workspace AND b.source_id=source
 AND b.kind IN ('original','original-metadata') ORDER BY b.block_id FOR SHARE;
 SELECT count(*),min(b.text) INTO n,reading FROM oracle2.source_blocks b
 WHERE b.workspace_id=workspace AND b.source_id=source AND b.kind='original';
 IF n<>1 THEN RAISE insufficient_privilege USING MESSAGE='unique processing original required'; END IF;
 SELECT count(*),min(b.text)::jsonb INTO n,metadata FROM oracle2.source_blocks b
 WHERE b.workspace_id=workspace AND b.source_id=source AND b.kind='original-metadata';
 IF n<>1 OR jsonb_typeof(metadata) IS DISTINCT FROM 'object'
 OR NOT metadata ?& ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt']
 OR (metadata-ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt'])<>'{}'::jsonb
 OR EXISTS(SELECT 1 FROM unnest(ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','review_receipt']) k
 WHERE jsonb_typeof(metadata->k) IS DISTINCT FROM 'string')
 OR metadata->>'evidence_kind' NOT IN ('native_text','visual_transcription')
 OR metadata->>'parser_identity' !~ '^[0-9a-f]{64}$' OR metadata->>'review_receipt' !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(metadata->'page_count') IS DISTINCT FROM 'number' OR (metadata->>'page_count')::numeric NOT BETWEEN 1 AND 40
 OR (metadata->>'page_count')::numeric<>trunc((metadata->>'page_count')::numeric)
 OR metadata->>'original_hash' IS DISTINCT FROM a.original_hash
 OR metadata->>'content_hash' IS DISTINCT FROM a.reading_hash
 OR metadata->>'parser_identity' IS DISTINCT FROM a.parser_id
 OR encode(sha256(convert_to(reading,'UTF8')),'hex') IS DISTINCT FROM a.reading_hash THEN
  RAISE insufficient_privilege USING MESSAGE='processing original provenance denied';
 END IF;
 IF EXISTS(SELECT 1 FROM oracle2.operating_model_source_receipts q WHERE q.workspace_id=workspace
 AND q.source_id=source AND q.revision=a.revision
 AND (q.original_hash,q.reading_hash,q.parser_id) IS DISTINCT FROM (a.original_hash,a.reading_hash,a.parser_id)) THEN
  RAISE insufficient_privilege USING MESSAGE='processing receipt identity differs';
 END IF;
 PERFORM 1 FROM oracle2.appointments p WHERE p.workspace_id=workspace ORDER BY p.appointment_id FOR SHARE;
 FOREACH scope_name IN ARRAY CASE WHEN require_extraction THEN ARRAY['source-read:'||source::text,'source-extraction:'||source::text]
 ELSE ARRAY['source-read:'||source::text] END LOOP
  WITH RECURSIVE lineage AS (
   SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.actor_id,p.granted_by,
    ARRAY[p.appointment_id] seen, true valid,1 depth
   FROM oracle2.appointments p WHERE p.workspace_id=workspace AND p.actor_id=principal AND p.scope IN (scope_name,'root')
   UNION ALL
   SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.actor_id,p.granted_by,
    l.seen||p.appointment_id,l.valid AND p.actor_id=l.granted_by AND p.scope IN (scope_name,'root'),l.depth+1
   FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id
   WHERE p.workspace_id=workspace AND l.depth<16 AND NOT p.appointment_id=ANY(l.seen))
  , valid_paths AS (SELECT min(expires_at) expiry FROM lineage GROUP BY start_id HAVING
   bool_and(valid AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp()))
   AND bool_or(scope='root' AND parent_id IS NULL))
  SELECT EXISTS(SELECT 1 FROM valid_paths),max(coalesce(expiry,'infinity'::timestamptz))
  INTO permitted,scope_deadline FROM valid_paths;
  IF NOT permitted THEN RAISE insufficient_privilege USING MESSAGE='current processing scope lineage denied'; END IF;
  deadline:=least(deadline,scope_deadline);
 END LOOP;
 IF deadline<=clock_timestamp() OR a.expires_at<=clock_timestamp() OR r.expires_at<=clock_timestamp() OR NOT isfinite(r.expires_at) OR NOT isfinite(a.expires_at) THEN
  RAISE insufficient_privilege USING MESSAGE='processing admission expired during qualification';
 END IF;
 RETURN QUERY SELECT a.revision,a.original_hash,a.reading_hash,a.parser_id,
 CASE WHEN want_raw THEN reading ELSE NULL::text END,
 CASE WHEN want_raw THEN metadata::text ELSE NULL::text END,deadline,clock_timestamp();
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='invalid processing provenance';
END $body$;
REVOKE ALL ON FUNCTION oracle2._processing_source(uuid,uuid,uuid,text,text,boolean) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_processing_source_receipt(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,original_reading text,provenance text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
 SELECT * FROM oracle2._processing_source(workspace,source,principal,expected_runtime,expected_registry,true)
$body$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_source_receipt(uuid,uuid,uuid,text,text) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_processing_source_receipt(uuid,uuid,uuid,text,text)
 TO oracle2_source_reader,oracle2_candidate_compiler;

CREATE OR REPLACE FUNCTION oracle2.hosting_current_source_identity(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
 SELECT q.revision,q.original_hash,q.reading_hash,q.parser_id,q.valid_until,q.checked_at
 FROM oracle2._processing_source(workspace,source,principal,expected_runtime,expected_registry,false) q
$body$;
REVOKE ALL ON FUNCTION oracle2.hosting_current_source_identity(uuid,uuid,uuid,text,text) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_current_source_identity(uuid,uuid,uuid,text,text)
 TO oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
