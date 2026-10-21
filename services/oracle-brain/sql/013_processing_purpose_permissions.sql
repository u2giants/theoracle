-- Explicit purpose V2, additive dedicated Oracle ledger capabilities only.
-- No table/role/appointment/runtime issuance, old helper or policy mutation.
-- TRUST A: SQL proves current fixed session/source/runtime/exact scope; trusted
-- application proves complete parent/phase/model/account/operation/registry.
DO $owner$
DECLARE owner_oid oid;
BEGIN
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF owner_oid IS NULL OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR owner_oid IS DISTINCT FROM (SELECT proowner FROM pg_proc WHERE oid=to_regprocedure('oracle2._processing_source(uuid,uuid,uuid,text,text,boolean)'))
 OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata') AND (pg_has_role(oid,owner_oid,'MEMBER') OR pg_has_role(oid,owner_oid,'SET') OR pg_has_role(oid,owner_oid,'USAGE'))) THEN
 RAISE EXCEPTION 'reviewed unreachable purpose owner required'; END IF;
END $owner$;

-- One shared V2 validator preserves the V1 integrity algorithm and adds exact
-- purpose leaves. It deliberately does not call V1: extraction authority cannot
-- substitute for any newly appointed purpose. V1 definitions stay unchanged.
-- Statement deadline must be configured BEFORE the caller starts its SELECT.
CREATE OR REPLACE FUNCTION oracle2._purpose_deadlines_v2()
 RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
BEGIN
 IF current_setting('statement_timeout')::interval<=interval '0' OR current_setting('statement_timeout')::interval>interval '5 seconds' THEN
  RAISE insufficient_privilege USING MESSAGE='preconfigured bounded purpose statement deadline required';
 END IF;
 IF current_setting('lock_timeout')::interval<=interval '0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN
  PERFORM set_config('lock_timeout','2s',true);
 END IF;
END $$;
REVOKE ALL ON FUNCTION oracle2._purpose_deadlines_v2() FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2._purpose_source_v2(
 workspace uuid, source uuid, principal uuid, expected_runtime text, expected_registry text, purpose text, want_raw boolean)
 RETURNS TABLE(revision integer, original_hash text, reading_hash text, parser_id text, original_reading text, provenance text, valid_until timestamptz, checked_at timestamptz)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_role_source_admissions%ROWTYPE;
 r oracle2.hosting_role_runtime_admissions%ROWTYPE; owner_oid oid; login_oid oid;
 kinds text[]; kind text; reading text; metadata jsonb; n bigint; source_revision integer; source_status text;
 scope_name text; permitted boolean; deadline timestamptz; scope_deadline timestamptz;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 -- Use the SAME connection as an enclosing ledger transaction; never a nested lock connection.
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 SELECT oid INTO login_oid FROM pg_roles WHERE rolname=SESSION_USER
 AND rolcanlogin AND NOT (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication);
 IF login_oid IS NULL OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR pg_has_role(login_oid,owner_oid,'MEMBER') THEN RAISE insufficient_privilege USING MESSAGE='processing owner/session denied'; END IF;
 SELECT array_agg(rolname::text ORDER BY rolname) INTO kinds FROM pg_roles
 WHERE rolname IN ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata')
 AND pg_has_role(login_oid,oid,'MEMBER');
 IF coalesce(cardinality(kinds),0)<>1 THEN RAISE insufficient_privilege USING MESSAGE='exclusive processing role required'; END IF;
 kind:=kinds[1];
 -- PG16 MEMBER, SET and inherited USAGE have different option semantics.
 -- The new processing issuer permits no other reachable role, even harmless
 -- intermediate/monitor membership. Legacy SourceRoleBinding is unchanged.
 IF EXISTS(SELECT 1 FROM pg_roles x WHERE x.rolname NOT IN (SESSION_USER::text,kind)
 AND (pg_has_role(login_oid,x.oid,'MEMBER') OR pg_has_role(login_oid,x.oid,'SET') OR pg_has_role(login_oid,x.oid,'USAGE')))
 OR EXISTS(SELECT 1 FROM pg_roles x WHERE x.rolname=kind AND (x.rolcanlogin OR x.rolinherit OR x.rolsuper OR x.rolbypassrls OR x.rolcreaterole OR x.rolcreatedb OR x.rolreplication))
 OR current_setting('role') NOT IN ('none',SESSION_USER::text,kind) THEN
 RAISE insufficient_privilege USING MESSAGE='exact processing role/SET membership required'; END IF;
 IF purpose IS NULL OR purpose NOT IN ('source-census','operating-audit','independent-source-semantic-acceptance','source-extraction')
 OR kind NOT IN ('oracle2_source_reader','oracle2_gateway_metadata')
 OR (want_raw AND (kind<>'oracle2_source_reader' OR purpose='source-extraction'))
 OR (purpose='source-extraction' AND kind<>'oracle2_gateway_metadata') THEN
  RAISE insufficient_privilege USING MESSAGE='fixed purpose V2 role/operation denied';
 END IF;
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
 FOREACH scope_name IN ARRAY ARRAY['source-read:'||source::text,purpose||':'||source::text] LOOP
  WITH RECURSIVE lineage AS (
   SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.actor_id,p.granted_by,
    ARRAY[p.appointment_id] seen, true valid,1 depth
   FROM oracle2.appointments p WHERE p.workspace_id=workspace AND p.actor_id=principal AND p.scope=scope_name
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
REVOKE ALL ON FUNCTION oracle2._purpose_source_v2(uuid,uuid,uuid,text,text,text,boolean) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_source_census_receipt_v2(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,original_reading text,provenance text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT * FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'source-census',true)
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_source_census_receipt_v2(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_source_census_receipt_v2(uuid,uuid,uuid,text,text) TO oracle2_source_reader;

CREATE OR REPLACE FUNCTION oracle2.hosting_operating_audit_receipt_v2(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,original_reading text,provenance text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT * FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'operating-audit',true)
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_operating_audit_receipt_v2(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_operating_audit_receipt_v2(uuid,uuid,uuid,text,text) TO oracle2_source_reader;

CREATE OR REPLACE FUNCTION oracle2.hosting_independent_semantic_receipt_v2(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,original_reading text,provenance text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT * FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'independent-source-semantic-acceptance',true)
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_independent_semantic_receipt_v2(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_independent_semantic_receipt_v2(uuid,uuid,uuid,text,text) TO oracle2_source_reader;

CREATE OR REPLACE FUNCTION oracle2.hosting_source_census_identity_v2(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT q.revision,q.original_hash,q.reading_hash,q.parser_id,q.valid_until,q.checked_at
 FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'source-census',false) q
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_source_census_identity_v2(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_source_census_identity_v2(uuid,uuid,uuid,text,text) TO oracle2_source_reader,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_operating_audit_identity_v2(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT q.revision,q.original_hash,q.reading_hash,q.parser_id,q.valid_until,q.checked_at
 FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'operating-audit',false) q
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_operating_audit_identity_v2(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_operating_audit_identity_v2(uuid,uuid,uuid,text,text) TO oracle2_source_reader,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_independent_semantic_identity_v2(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT q.revision,q.original_hash,q.reading_hash,q.parser_id,q.valid_until,q.checked_at
 FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'independent-source-semantic-acceptance',false) q
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_independent_semantic_identity_v2(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_independent_semantic_identity_v2(uuid,uuid,uuid,text,text) TO oracle2_source_reader,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_projection_embedding_identity_v2(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT q.revision,q.original_hash,q.reading_hash,q.parser_id,q.valid_until,q.checked_at
 FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'source-extraction',false) q
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_projection_embedding_identity_v2(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_projection_embedding_identity_v2(uuid,uuid,uuid,text,text) TO oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2._purpose_embedding_artifact_v2(
 workspace uuid,artifact uuid,ver integer,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(manifest jsonb,source_refs jsonb)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE m jsonb; a record; d record; q record; refs jsonb:='[]'; expiry timestamptz:='infinity'; kinds text[]; cycle boolean;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 IF current_setting('lock_timeout')::interval=interval '0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN PERFORM set_config('lock_timeout','2s',true); END IF;
 SELECT array_agg(rolname::text ORDER BY rolname) INTO kinds FROM pg_roles WHERE rolname IN
 ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata') AND pg_has_role(SESSION_USER,oid,'MEMBER');
 IF coalesce(cardinality(kinds),0)<>1 OR kinds[1]<>'oracle2_gateway_metadata' THEN RAISE insufficient_privilege; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));
 SELECT x.manifest INTO m FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=artifact AND x.version=ver FOR SHARE;
 IF NOT FOUND OR m->>'kind' NOT IN ('processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1','processing_failed_assembly_v1') THEN RAISE insufficient_privilege USING MESSAGE='processing artifact absent'; END IF;
 -- Qualify rows before taking lineage-table locks, preserving source-first order.
 FOR d IN SELECT x.upstream_id,x.upstream_revision FROM oracle2.artifact_dependencies x
 WHERE x.workspace_id=workspace AND x.artifact_id=artifact AND x.version=ver AND x.upstream_kind='source' ORDER BY x.upstream_id,x.upstream_revision LOOP
  SELECT * INTO q FROM oracle2._purpose_source_v2(workspace,d.upstream_id::uuid,principal,expected_runtime,expected_registry,'source-extraction',false);
  IF q.revision::text<>d.upstream_revision THEN RAISE insufficient_privilege; END IF;
  expiry:=least(expiry,q.valid_until);
  refs:=refs||jsonb_build_array(jsonb_build_object('schema_version',1,'workspace_id',workspace,'source_id',d.upstream_id::uuid,
   'revision',q.revision,'original_sha256',q.original_hash,'reading_sha256',q.reading_hash,'parser_id',q.parser_id));
 END LOOP;
 IF jsonb_array_length(refs)=0 THEN RAISE insufficient_privilege USING MESSAGE='processing source population missing'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-lineage:'||workspace::text,0));
 LOCK TABLE oracle2.artifact_manifests,oracle2.artifact_dependencies,oracle2.artifact_invalidations IN SHARE MODE;
 -- UNION reaches a finite immutable population even if untrusted legacy INSERTs
 -- introduced cycles; pair reachability below detects cycles without depth guesses.
 FOR a IN WITH RECURSIVE ancestors(id,v) AS (
  SELECT artifact,ver UNION SELECT x.upstream_id::uuid,x.upstream_revision::integer FROM oracle2.artifact_dependencies x JOIN ancestors n ON x.artifact_id=n.id AND x.version=n.v
  WHERE x.workspace_id=workspace AND x.upstream_kind='artifact')
 SELECT x.* FROM ancestors n JOIN oracle2.artifact_manifests x ON x.workspace_id=workspace AND x.artifact_id=n.id AND x.version=n.v LOOP
  IF (to_jsonb(a)-ARRAY['manifest','created_at']) IS DISTINCT FROM (a.manifest-'schema_version') OR a.manifest->'schema_version' IS DISTINCT FROM '1'::jsonb
  OR a.kind NOT IN ('processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1','processing_failed_assembly_v1')
  OR ((a.artifact_id,a.version)<>(artifact,ver) AND a.state<>'ready')
  OR a.manifest->>'dependency_digest' IS DISTINCT FROM oracle2._processing_dependency_digest(workspace,a.artifact_id,a.version)
  OR EXISTS(SELECT 1 FROM oracle2.artifact_invalidations i WHERE i.workspace_id=workspace AND i.artifact_id=a.artifact_id AND i.version=a.version)
  OR EXISTS(SELECT 1 FROM oracle2.artifact_dependencies x WHERE x.workspace_id=workspace AND x.artifact_id=a.artifact_id AND x.version=a.version
   AND ((x.upstream_kind='source' AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(refs) r WHERE r->>'source_id'=x.upstream_id AND r->>'revision'=x.upstream_revision))
   OR x.upstream_kind NOT IN ('source','artifact')
   OR (x.upstream_kind='artifact' AND NOT EXISTS(SELECT 1 FROM oracle2.artifact_manifests parent WHERE parent.workspace_id=workspace AND parent.artifact_id=x.upstream_id::uuid AND parent.version=x.upstream_revision::integer)))) THEN
   RAISE insufficient_privilege USING MESSAGE='processing lineage unavailable or extended'; END IF;
 END LOOP;
 WITH RECURSIVE ancestors(id,v) AS (
  SELECT artifact,ver UNION SELECT x.upstream_id::uuid,x.upstream_revision::integer FROM oracle2.artifact_dependencies x JOIN ancestors n ON x.artifact_id=n.id AND x.version=n.v WHERE x.workspace_id=workspace AND x.upstream_kind='artifact'),
 paths(origin,ov,id,v) AS (
  SELECT x.artifact_id,x.version,x.upstream_id::uuid,x.upstream_revision::integer FROM oracle2.artifact_dependencies x JOIN ancestors n ON x.artifact_id=n.id AND x.version=n.v WHERE x.workspace_id=workspace AND x.upstream_kind='artifact'
  UNION SELECT p.origin,p.ov,x.upstream_id::uuid,x.upstream_revision::integer FROM paths p JOIN oracle2.artifact_dependencies x ON x.artifact_id=p.id AND x.version=p.v WHERE x.workspace_id=workspace AND x.upstream_kind='artifact')
 SELECT EXISTS(SELECT 1 FROM paths WHERE (origin,ov)=(id,v)) INTO cycle;
 IF cycle OR expiry<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='processing lineage cycle or expired authority'; END IF;
 RETURN QUERY SELECT m,refs;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE insufficient_privilege USING MESSAGE='invalid processing lineage';
END $body$;
REVOKE ALL ON FUNCTION oracle2._purpose_embedding_artifact_v2(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

-- Metadata-only embedding capability; Trust A app owns semantic/body validation.
CREATE OR REPLACE FUNCTION oracle2.hosting_projection_embedding_seal_v2(
 workspace uuid,artifact uuid,ver integer,principal uuid,expected_runtime text,expected_registry text)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q record; e record; x record; mh text; eh text; extracts jsonb:='[]';
BEGIN
 SELECT * INTO STRICT q FROM oracle2._purpose_embedding_artifact_v2(workspace,artifact,ver,principal,expected_runtime,expected_registry);
 IF q.manifest->>'kind'<>'processing_qualified_model_v1' OR q.manifest->>'state'<>'ready' THEN RAISE insufficient_privilege; END IF;
 FOR x IN WITH RECURSIVE ancestors(id,v) AS (
  SELECT artifact,ver UNION SELECT d.upstream_id::uuid,d.upstream_revision::integer
  FROM oracle2.artifact_dependencies d JOIN ancestors n ON d.artifact_id=n.id AND d.version=n.v
  WHERE d.workspace_id=workspace AND d.upstream_kind='artifact')
 SELECT a.artifact_id,a.version FROM ancestors n JOIN oracle2.artifact_manifests a
 ON a.workspace_id=workspace AND a.artifact_id=n.id AND a.version=n.v
 WHERE a.kind='processing_extraction_v1' ORDER BY a.artifact_id,a.version LOOP
  SELECT * INTO STRICT e FROM oracle2._purpose_embedding_artifact_v2(workspace,x.artifact_id,x.version,principal,expected_runtime,expected_registry);
  SELECT encode(sha256(convert_to('{'||string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")||'}','UTF8')),'hex') INTO eh FROM jsonb_each(e.manifest);
  extracts:=extracts||jsonb_build_array(jsonb_build_object('schema_version',1,'workspace_id',workspace,'artifact_id',x.artifact_id,'version',x.version,
   'kind','processing_extraction_v1','state','ready','content_hash',e.manifest->>'content_hash','input_digest',e.manifest->>'input_digest',
   'source_digest',e.manifest->>'source_digest','permission_digest',e.manifest->>'permission_digest','compiler_digest',e.manifest->>'compiler_digest',
   'dependency_digest',e.manifest->>'dependency_digest','manifest_hash',eh,'source_refs',e.source_refs));
 END LOOP;
 IF jsonb_array_length(extracts)=0 THEN RAISE insufficient_privilege; END IF;
 -- Recheck the whole population's actual clock after all extraction seals.
 SELECT * INTO STRICT q FROM oracle2._purpose_embedding_artifact_v2(workspace,artifact,ver,principal,expected_runtime,expected_registry);
 SELECT encode(sha256(convert_to('{'||string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")||'}','UTF8')),'hex') INTO mh FROM jsonb_each(q.manifest);
 RETURN jsonb_build_object('schema_version',2,'workspace_id',workspace,'artifact_id',artifact,'version',ver,
 'kind','processing_qualified_model_v1','state','ready','content_hash',q.manifest->>'content_hash','input_digest',q.manifest->>'input_digest',
 'source_digest',q.manifest->>'source_digest','permission_digest',q.manifest->>'permission_digest','compiler_digest',q.manifest->>'compiler_digest',
 'dependency_digest',q.manifest->>'dependency_digest','manifest_hash',mh,'source_refs',q.source_refs,'extraction_seals',extracts);
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_projection_embedding_seal_v2(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_projection_embedding_seal_v2(uuid,uuid,integer,uuid,text,text) TO oracle2_gateway_metadata;

-- Immutable ACK readback only. SQL authenticates current ledger custody and
-- original access, not the graph, paid wire, HMAC or semantic admission.
-- One exact immutable paid-V3 ACK protocol, reused after each caller's own
-- authorization. Owner-only: this helper grants no source or execution rights.
CREATE OR REPLACE FUNCTION oracle2._processing_projection_receipt_v3(
 workspace uuid,artifact uuid,ver integer,manifest jsonb)
 RETURNS TABLE(receipt jsonb,signature text)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE e record;
 keys text[]:=ARRAY['schema_version','event_id','workspace_id','artifact_id','version','content_hash','source_digest','permission_digest','graph_name','record_digest','sdk_version','projector_id','lease_role','lease_token','lease_attempt','lease_until','projection_schema','projection_digest','embedding_protocol','embedding_inventory_hash','embedding_context_hash','embedding_native_receipt_hash','embedding_wire_hash','embedding_commit_hash','embedding_vectors_hash','embedding_coverage_hash'];
 hashes text[]:=ARRAY['record_digest','projection_digest','embedding_inventory_hash','embedding_context_hash','embedding_native_receipt_hash','embedding_wire_hash','embedding_commit_hash','embedding_vectors_hash','embedding_coverage_hash'];
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
  RAISE insufficient_privilege USING MESSAGE='fresh read-committed projection snapshot required';
 END IF;
 IF manifest IS DISTINCT FROM (SELECT a.manifest FROM oracle2.artifact_manifests a
  WHERE a.workspace_id=workspace AND a.artifact_id=artifact AND a.version=ver AND a.state='ready'
   AND a.kind='processing_qualified_model_v1')
 OR ver IS DISTINCT FROM (SELECT max(a.version) FROM oracle2.artifact_manifests a
  WHERE a.workspace_id=workspace AND a.artifact_id=artifact AND a.kind='processing_qualified_model_v1' AND a.state='ready') THEN
  RAISE insufficient_privilege USING MESSAGE='exact current qualified model required';
 END IF;
 SELECT o.event_id,o.delivered_at,o.processing_lease_role,o.processing_lease_token,o.attempts,r.payload AS body,r.signature AS seal INTO STRICT e
 FROM oracle2.outbox o JOIN oracle2.operating_projection_receipts r ON r.event_id=o.event_id
 AND r.workspace_id=o.workspace_id AND r.artifact_id=o.assertion_id AND r.version=o.revision
 WHERE o.workspace_id=workspace AND o.assertion_id=artifact AND o.revision=ver AND o.operation='project'
 AND o.payload=jsonb_build_object('namespace','oracle_processing_v1','manifest',manifest) AND o.delivered_at IS NOT NULL FOR SHARE OF o,r;
 IF jsonb_typeof(e.body) IS DISTINCT FROM 'object' OR NOT e.body ?& keys OR (e.body-keys)<>'{}'::jsonb
 OR e.body->'schema_version' IS DISTINCT FROM '3'::jsonb OR e.body->>'schema_version' IS DISTINCT FROM '3'
 OR EXISTS(SELECT 1 FROM unnest(keys) k WHERE k NOT IN ('schema_version','version','lease_attempt') AND jsonb_typeof(e.body->k) IS DISTINCT FROM 'string')
 OR jsonb_typeof(e.body->'version') IS DISTINCT FROM 'number' OR jsonb_typeof(e.body->'lease_attempt') IS DISTINCT FROM 'number'
 OR e.body->>'event_id' IS DISTINCT FROM e.event_id::text OR e.body->>'workspace_id' IS DISTINCT FROM workspace::text
 OR e.body->>'artifact_id' IS DISTINCT FROM artifact::text OR e.body->>'version' IS DISTINCT FROM ver::text
 OR e.body->>'content_hash' IS DISTINCT FROM manifest->>'content_hash' OR e.body->>'source_digest' IS DISTINCT FROM manifest->>'source_digest'
 OR e.body->>'permission_digest' IS DISTINCT FROM manifest->>'permission_digest'
 OR e.body->>'projection_schema' IS DISTINCT FROM 'qualified-evidence-projection-v1' OR e.body->>'sdk_version' IS DISTINCT FROM '1.4.0'
 OR e.body->>'embedding_protocol' IS DISTINCT FROM 'paid-sdk-embedding-v3'
 OR EXISTS(SELECT 1 FROM unnest(hashes) k WHERE e.body->>k !~ '^[0-9a-f]{64}$')
 OR e.body->>'projector_id'='' OR e.seal IS NULL OR e.seal !~ '^[0-9a-f]{64}$'
 OR e.body->>'lease_role' IS DISTINCT FROM e.processing_lease_role::text
 OR e.body->>'lease_token' IS DISTINCT FROM e.processing_lease_token::text OR e.body->>'lease_attempt' IS DISTINCT FROM e.attempts::text
 OR NOT isfinite((e.body->>'lease_until')::timestamptz) OR e.delivered_at>=(e.body->>'lease_until')::timestamptz
 OR e.body->>'graph_name' !~ ('^oracle_processing_v1_'||replace(workspace::text,'-','')||'_'||replace(artifact::text,'-','')||'_'||ver::text||'_[0-9a-f]{32}$') THEN
 RAISE insufficient_privilege USING MESSAGE='exact delivered paid V3 receipt required'; END IF;
 RETURN QUERY SELECT e.body,e.seal;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='paid projection delivery unavailable';
END $$;
REVOKE ALL ON FUNCTION oracle2._processing_projection_receipt_v3(uuid,uuid,integer,jsonb) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2._processing_projection_delivery_v3(
 workspace uuid,artifact uuid,ver integer,principal uuid,runtime text,registry text)
 RETURNS TABLE(receipt jsonb,signature text,source_refs jsonb,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q record; e record; s record; ref jsonb; until_at timestamptz:='infinity';

BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 SELECT * INTO STRICT q FROM oracle2._processing_artifact_metadata(workspace,artifact,ver,principal,runtime,registry);
 IF q.manifest->>'kind' IS DISTINCT FROM 'processing_qualified_model_v1' OR q.manifest->>'state' IS DISTINCT FROM 'ready'
 OR ver IS DISTINCT FROM (SELECT max(a.version) FROM oracle2.artifact_manifests a WHERE a.workspace_id=workspace AND a.artifact_id=artifact AND a.kind='processing_qualified_model_v1' AND a.state='ready') THEN RAISE insufficient_privilege; END IF;
 SELECT r.receipt AS body,r.signature AS seal INTO STRICT e
 FROM oracle2._processing_projection_receipt_v3(workspace,artifact,ver,q.manifest) r;
 FOR ref IN SELECT value FROM jsonb_array_elements(q.source_refs) LOOP
  SELECT * INTO STRICT s FROM oracle2.hosting_current_source_identity(workspace,(ref->>'source_id')::uuid,principal,runtime,registry);
  IF (s.revision,s.original_hash,s.reading_hash,s.parser_id) IS DISTINCT FROM ((ref->>'revision')::integer,ref->>'original_sha256',ref->>'reading_sha256',ref->>'parser_id') THEN RAISE insufficient_privilege; END IF;
  until_at:=least(until_at,s.valid_until);
 END LOOP;
 IF NOT isfinite(until_at) OR until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN QUERY SELECT e.body,e.seal,q.source_refs,until_at,clock_timestamp();
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='paid projection delivery unavailable';
END $$;
REVOKE ALL ON FUNCTION oracle2._processing_projection_delivery_v3(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_processing_projection_receipt_v3(
 workspace uuid,artifact uuid,ver integer,principal uuid,runtime text,registry text)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q record;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 IF NOT pg_has_role(SESSION_USER,'oracle2_candidate_compiler','MEMBER') THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO STRICT q FROM oracle2._processing_projection_delivery_v3(workspace,artifact,ver,principal,runtime,registry);
 RETURN jsonb_build_object('schema_version',3,'receipt',q.receipt,'signature',q.signature,'source_refs',q.source_refs,'valid_until',q.valid_until,'checked_at',q.checked_at);
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_projection_receipt_v3(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_processing_projection_receipt_v3(uuid,uuid,integer,uuid,text,text) TO oracle2_candidate_compiler;

CREATE OR REPLACE FUNCTION oracle2.hosting_processing_projection_delivery_v3(
 workspace uuid,artifact uuid,ver integer,principal uuid,runtime text,registry text)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q record; result jsonb; body_hash text;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 IF NOT pg_has_role(SESSION_USER,'oracle2_documentary_executor','MEMBER') THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO STRICT q FROM oracle2._processing_projection_delivery_v3(workspace,artifact,ver,principal,runtime,registry);
 -- Exact ACK fields are scalars with integer-only numeric spellings. This is
 -- the same tested canonical scalar encoding used by extraction manifest seals.
 SELECT encode(sha256(convert_to('{'||string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")||'}','UTF8')),'hex') INTO body_hash FROM jsonb_each(q.receipt);
 SELECT jsonb_object_agg(key,value) INTO result FROM jsonb_each(q.receipt) WHERE key=ANY(ARRAY[
 'schema_version','event_id','workspace_id','artifact_id','version','content_hash','source_digest','permission_digest','graph_name','record_digest','sdk_version','projection_schema','projection_digest',
 'embedding_protocol','embedding_inventory_hash','embedding_context_hash','embedding_native_receipt_hash','embedding_wire_hash','embedding_commit_hash','embedding_vectors_hash','embedding_coverage_hash']);
 RETURN result||jsonb_build_object('kind','processing_qualified_model_v1','state','ready','receipt_body_hash',body_hash,
 'signature',q.signature,'source_refs',q.source_refs,'valid_until',q.valid_until,'checked_at',q.checked_at);
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_projection_delivery_v3(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_processing_projection_delivery_v3(uuid,uuid,integer,uuid,text,text) TO oracle2_documentary_executor;
