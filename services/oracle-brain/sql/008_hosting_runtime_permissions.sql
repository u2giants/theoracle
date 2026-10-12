-- NEW dedicated ledger only; requires SQL007 and reviewed bootstrap admissions.
-- Runtime registry checks are supplied by the installer-owned binding helper.
CREATE TABLE IF NOT EXISTS oracle2.hosting_role_runtime_admissions (
 role_name name PRIMARY KEY, runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),
 registry_hash text NOT NULL CHECK(registry_hash ~ '^[0-9a-f]{64}$'), expires_at timestamptz NOT NULL);
REVOKE ALL ON oracle2.hosting_role_runtime_admissions FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor;
DO $$ BEGIN
 IF to_regprocedure('pg_catalog.sha256(bytea)') IS NULL THEN RAISE EXCEPTION 'native SHA256 unavailable'; END IF;
END $$;
CREATE OR REPLACE FUNCTION oracle2.hosting_source_visible(workspace uuid, source uuid)
 RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.hosting_role_source_admissions%ROWTYPE; reading text; metadata jsonb; n bigint;
BEGIN
 SELECT c.* INTO a FROM oracle2.hosting_role_source_admissions c
 JOIN oracle2.hosting_role_runtime_admissions r ON r.role_name=c.role_name
 AND r.runtime_hash=c.runtime_hash AND r.registry_hash=c.registry_hash AND r.expires_at>clock_timestamp()
 JOIN oracle2.sources s ON s.workspace_id=c.workspace_id AND s.source_id=c.source_id AND s.revision=c.revision
 WHERE c.role_name=SESSION_USER AND c.workspace_id=workspace AND c.source_id=source AND c.expires_at>clock_timestamp()
 AND s.status IN ('draft','confirmed');
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT count(*) INTO n FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source;
 IF n<>1 OR NOT EXISTS(SELECT 1 FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source AND d.status='confirmed') THEN RETURN false; END IF;
 SELECT count(*),min(b.text) INTO n,reading FROM oracle2.source_blocks b WHERE b.workspace_id=workspace AND b.source_id=source AND b.kind='original';
 IF n<>1 THEN RETURN false; END IF;
 SELECT count(*),min(b.text)::jsonb INTO n,metadata FROM oracle2.source_blocks b WHERE b.workspace_id=workspace AND b.source_id=source AND b.kind='original-metadata';
 IF n<>1 OR jsonb_typeof(metadata) IS DISTINCT FROM 'object'
 OR NOT metadata ?& ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt']
 OR (metadata-ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt'])<>'{}'::jsonb
 OR jsonb_typeof(metadata->'content_type') IS DISTINCT FROM 'string'
 OR metadata->>'evidence_kind' NOT IN ('native_text','visual_transcription')
 OR metadata->>'parser_identity' !~ '^[0-9a-f]{64}$' OR metadata->>'review_receipt' !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(metadata->'page_count') IS DISTINCT FROM 'number' OR (metadata->>'page_count')::numeric NOT BETWEEN 1 AND 40
 OR (metadata->>'page_count')::numeric<>trunc((metadata->>'page_count')::numeric)
 OR metadata->>'original_hash' IS DISTINCT FROM a.original_hash
 OR metadata->>'content_hash' IS DISTINCT FROM a.reading_hash
 OR metadata->>'parser_identity' IS DISTINCT FROM a.parser_id
 OR encode(sha256(convert_to(reading,'UTF8')),'hex') IS DISTINCT FROM a.reading_hash THEN RETURN false; END IF;
 IF EXISTS(SELECT 1 FROM oracle2.operating_model_source_receipts r WHERE r.workspace_id=workspace AND r.source_id=source AND r.revision=a.revision
 AND (r.original_hash,r.reading_hash,r.parser_id) IS DISTINCT FROM (a.original_hash,a.reading_hash,a.parser_id)) THEN RETURN false; END IF;
 RETURN EXISTS(WITH RECURSIVE lineage AS (
 SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,1 depth
 FROM oracle2.appointments p WHERE p.workspace_id=workspace AND p.actor_id=a.principal_id AND p.scope IN ('source-read:'||source::text,'root')
 UNION ALL SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,l.depth+1
 FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id WHERE l.depth<16 AND p.workspace_id=l.workspace_id)
 SELECT 1 FROM lineage GROUP BY start_id HAVING bool_and(revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp())) AND bool_or(scope='root' AND parent_id IS NULL));
EXCEPTION WHEN invalid_text_representation THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_source_visible(uuid,uuid) FROM PUBLIC;
CREATE OR REPLACE FUNCTION oracle2.hosting_workspace_visible(workspace uuid)
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT EXISTS(SELECT 1 FROM oracle2.hosting_role_source_admissions a
 WHERE a.role_name=SESSION_USER AND a.workspace_id=workspace
 AND oracle2.hosting_source_visible(a.workspace_id,a.source_id));
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_workspace_visible(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_workspace_visible(uuid) TO oracle2_candidate_compiler,oracle2_documentary_executor;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['artifact_manifests','artifact_dependencies','document_observations','operating_model_source_receipts','operational_imports'] LOOP
 EXECUTE format('ALTER TABLE oracle2.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('DROP POLICY IF EXISTS hosting_candidate_read ON oracle2.%I',t);
 EXECUTE format('CREATE POLICY hosting_candidate_read ON oracle2.%I FOR SELECT TO oracle2_candidate_compiler USING(oracle2.hosting_workspace_visible(workspace_id))',t);
 EXECUTE format('GRANT SELECT ON oracle2.%I TO oracle2_candidate_compiler',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['artifact_manifests','artifact_dependencies','operating_model_source_receipts','artifact_invalidations','finding_events','operating_release_manifests','operating_release_selectors'] LOOP
 EXECUTE format('ALTER TABLE oracle2.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('DROP POLICY IF EXISTS hosting_documentary_read ON oracle2.%I',t);
 EXECUTE format('CREATE POLICY hosting_documentary_read ON oracle2.%I FOR SELECT TO oracle2_documentary_executor USING(oracle2.hosting_workspace_visible(workspace_id))',t);
 EXECUTE format('GRANT SELECT ON oracle2.%I TO oracle2_documentary_executor',t);
 END LOOP;
END $$;
-- Private candidate bodies cannot be used by metadata-only gateway.
-- UPDATE/DELETE and schema/appointment/source/selector mutations never granted.
-- Preserve SQL006's existing metadata-only projection. Column grants still
-- prohibit private manifest/receipt bodies; RLS must not silently disable it.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['artifact_manifests','artifact_dependencies','operating_model_source_receipts','artifact_invalidations','operating_release_manifests','operating_release_selectors'] LOOP
 EXECUTE format('DROP POLICY IF EXISTS hosting_gateway_metadata_read ON oracle2.%I',t);
 EXECUTE format('CREATE POLICY hosting_gateway_metadata_read ON oracle2.%I FOR SELECT TO oracle2_gateway_metadata USING(true)',t);
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION oracle2.hosting_receipt_insert(workspace uuid,source uuid,rev integer,original text,reading text,parser text)
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT oracle2.hosting_source_visible(workspace,source) AND EXISTS(
 SELECT 1 FROM oracle2.hosting_role_source_admissions a WHERE a.role_name=SESSION_USER AND a.workspace_id=workspace AND a.source_id=source
 AND (a.revision,a.original_hash,a.reading_hash,a.parser_id)=(rev,original,reading,parser));
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_receipt_insert(uuid,uuid,integer,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_receipt_insert(uuid,uuid,integer,text,text,text) TO oracle2_candidate_compiler;
-- Exact admitted revision/hash only: receipt bodies can contain originals.
GRANT EXECUTE ON FUNCTION oracle2.hosting_receipt_insert(uuid,uuid,integer,text,text,text) TO oracle2_documentary_executor;
DROP POLICY IF EXISTS hosting_candidate_read ON oracle2.operating_model_source_receipts;
CREATE POLICY hosting_candidate_read ON oracle2.operating_model_source_receipts FOR SELECT TO oracle2_candidate_compiler
 USING(oracle2.hosting_receipt_insert(workspace_id,source_id,revision,original_hash,reading_hash,parser_id));
DROP POLICY IF EXISTS hosting_documentary_read ON oracle2.operating_model_source_receipts;
CREATE POLICY hosting_documentary_read ON oracle2.operating_model_source_receipts FOR SELECT TO oracle2_documentary_executor
 USING(oracle2.hosting_receipt_insert(workspace_id,source_id,revision,original_hash,reading_hash,parser_id));
DROP POLICY IF EXISTS hosting_candidate_read ON oracle2.document_observations;
CREATE POLICY hosting_candidate_read ON oracle2.document_observations FOR SELECT TO oracle2_candidate_compiler
 USING(oracle2.hosting_source_visible(workspace_id,source_id) AND EXISTS(SELECT 1 FROM oracle2.operating_model_source_receipts r WHERE r.workspace_id=document_observations.workspace_id AND r.source_id=document_observations.source_id AND r.revision=document_observations.source_revision));
DROP POLICY IF EXISTS hosting_candidate_receipt_insert ON oracle2.operating_model_source_receipts;
CREATE POLICY hosting_candidate_receipt_insert ON oracle2.operating_model_source_receipts FOR INSERT TO oracle2_candidate_compiler
 WITH CHECK(oracle2.hosting_receipt_insert(workspace_id,source_id,revision,original_hash,reading_hash,parser_id));
DROP POLICY IF EXISTS hosting_candidate_observation_insert ON oracle2.document_observations;
CREATE POLICY hosting_candidate_observation_insert ON oracle2.document_observations FOR INSERT TO oracle2_candidate_compiler
 WITH CHECK(oracle2.hosting_source_visible(workspace_id,source_id) AND EXISTS(SELECT 1 FROM oracle2.operating_model_source_receipts r WHERE r.workspace_id=document_observations.workspace_id AND r.source_id=document_observations.source_id AND r.revision=document_observations.source_revision));
CREATE OR REPLACE FUNCTION oracle2.hosting_runtime_matches(runtime text)
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT EXISTS(SELECT 1 FROM oracle2.hosting_role_runtime_admissions r WHERE r.role_name=SESSION_USER AND r.expires_at>clock_timestamp() AND r.runtime_hash=runtime);
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_runtime_matches(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_runtime_matches(text) TO oracle2_candidate_compiler,oracle2_documentary_executor;
DROP POLICY IF EXISTS hosting_candidate_manifest_insert ON oracle2.artifact_manifests;
CREATE POLICY hosting_candidate_manifest_insert ON oracle2.artifact_manifests FOR INSERT TO oracle2_candidate_compiler
 WITH CHECK(oracle2.hosting_workspace_visible(workspace_id) AND oracle2.hosting_runtime_matches(compiler_digest));
DROP POLICY IF EXISTS hosting_candidate_dependency_insert ON oracle2.artifact_dependencies;
CREATE POLICY hosting_candidate_dependency_insert ON oracle2.artifact_dependencies FOR INSERT TO oracle2_candidate_compiler
 WITH CHECK(oracle2.hosting_workspace_visible(workspace_id) AND EXISTS(SELECT 1 FROM oracle2.artifact_manifests m WHERE m.workspace_id=artifact_dependencies.workspace_id AND m.artifact_id=artifact_dependencies.artifact_id AND m.version=artifact_dependencies.version)
 AND (upstream_kind<>'source' OR oracle2.hosting_source_visible(workspace_id,upstream_id::uuid)));
DROP POLICY IF EXISTS hosting_candidate_import_insert ON oracle2.operational_imports;
CREATE POLICY hosting_candidate_import_insert ON oracle2.operational_imports FOR INSERT TO oracle2_candidate_compiler
 WITH CHECK(oracle2.hosting_workspace_visible(workspace_id) AND EXISTS(SELECT 1 FROM oracle2.artifact_manifests m WHERE m.workspace_id=operational_imports.workspace_id AND m.artifact_id=operational_imports.artifact_id AND m.version=operational_imports.revision));
GRANT INSERT ON oracle2.artifact_manifests,oracle2.artifact_dependencies,oracle2.document_observations,oracle2.operating_model_source_receipts,oracle2.operational_imports TO oracle2_candidate_compiler;
CREATE OR REPLACE FUNCTION oracle2.hosting_view_authorized(workspace uuid, actor uuid,release uuid,release_hash text,refs jsonb)
 RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE m jsonb; ref jsonb; n bigint;
BEGIN
 SELECT r.payload INTO m FROM oracle2.operating_release_manifests r JOIN oracle2.operating_release_selectors s
 ON s.workspace_id=r.workspace_id AND s.release_id=r.release_id
 WHERE r.workspace_id=workspace AND r.release_id=release AND r.content_hash=release_hash
 AND s.watermark=(r.payload->>'ledger_watermark')::bigint
 AND s.watermark=(SELECT coalesce(max(sequence),0) FROM oracle2.operating_model_change_log WHERE workspace_id=workspace);
 IF NOT FOUND OR NOT oracle2.hosting_runtime_matches(m->>'runtime_digest') OR jsonb_typeof(refs) IS DISTINCT FROM 'array'
 OR jsonb_typeof(m->'source_refs') IS DISTINCT FROM 'array' OR refs IS DISTINCT FROM m->'source_refs' OR jsonb_array_length(refs)=0 THEN RETURN false; END IF;
 FOR ref IN SELECT value FROM jsonb_array_elements(refs) LOOP
 IF ref->>'workspace_id'<>workspace::text OR NOT oracle2.hosting_source_visible(workspace,(ref->>'source_id')::uuid)
 OR NOT EXISTS(SELECT 1 FROM oracle2.hosting_role_source_admissions a WHERE a.role_name=SESSION_USER AND a.principal_id=actor
 AND a.workspace_id=workspace AND a.source_id=(ref->>'source_id')::uuid AND a.revision=(ref->>'revision')::integer
 AND a.original_hash=ref->>'original_sha256' AND a.reading_hash=ref->>'reading_sha256' AND a.parser_id=ref->>'parser_id') THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_view_authorized(uuid,uuid,uuid,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_view_authorized(uuid,uuid,uuid,text,jsonb) TO oracle2_documentary_executor;
ALTER TABLE oracle2.operating_view_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hosting_documentary_job_read ON oracle2.operating_view_runs;
CREATE POLICY hosting_documentary_job_read ON oracle2.operating_view_runs FOR SELECT TO oracle2_documentary_executor
 USING(expires_at>clock_timestamp() AND oracle2.hosting_view_authorized(workspace_id,actor_id,release_id,release_hash,source_refs));
DROP POLICY IF EXISTS hosting_documentary_job_update ON oracle2.operating_view_runs;
DROP POLICY IF EXISTS hosting_gateway_view_read ON oracle2.operating_view_runs;
CREATE POLICY hosting_gateway_view_read ON oracle2.operating_view_runs FOR SELECT TO oracle2_gateway_metadata USING(true);
GRANT SELECT ON oracle2.operating_view_runs TO oracle2_documentary_executor;
REVOKE UPDATE ON oracle2.operating_view_runs FROM oracle2_documentary_executor;
REVOKE UPDATE(status,pack) ON oracle2.operating_view_runs FROM oracle2_documentary_executor;
DROP TRIGGER IF EXISTS hosting_view_completion ON oracle2.operating_view_runs;
DROP FUNCTION IF EXISTS oracle2.guard_hosting_view_completion();
DROP FUNCTION IF EXISTS oracle2.hosting_compact_json(jsonb);
CREATE TABLE IF NOT EXISTS oracle2.operating_view_pack_receipts (
 run_id uuid PRIMARY KEY REFERENCES oracle2.operating_view_runs, workspace_id uuid NOT NULL, actor_id uuid NOT NULL,
 release_id uuid NOT NULL,release_hash text NOT NULL,runtime_hash text NOT NULL,
 canonical_pack bytea NOT NULL,pack_hash text NOT NULL CHECK(pack_hash ~ '^[0-9a-f]{64}$'),published_at timestamptz NOT NULL DEFAULT now());
REVOKE ALL ON oracle2.operating_view_pack_receipts FROM PUBLIC,oracle2_documentary_executor,oracle2_candidate_compiler,oracle2_gateway_metadata;
DROP TRIGGER IF EXISTS hosting_view_pack_immutable ON oracle2.operating_view_pack_receipts;
CREATE TRIGGER hosting_view_pack_immutable BEFORE UPDATE OR DELETE ON oracle2.operating_view_pack_receipts FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
ALTER TABLE oracle2.operating_view_pack_receipts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hosting_documentary_pack_read ON oracle2.operating_view_pack_receipts;
CREATE POLICY hosting_documentary_pack_read ON oracle2.operating_view_pack_receipts FOR SELECT TO oracle2_documentary_executor
 USING(EXISTS(SELECT 1 FROM oracle2.operating_view_runs v WHERE v.run_id=operating_view_pack_receipts.run_id
 AND v.workspace_id=operating_view_pack_receipts.workspace_id AND v.actor_id=operating_view_pack_receipts.actor_id
 AND v.release_id=operating_view_pack_receipts.release_id AND v.release_hash=operating_view_pack_receipts.release_hash));
GRANT SELECT ON oracle2.operating_view_pack_receipts TO oracle2_documentary_executor;
CREATE OR REPLACE FUNCTION oracle2.hosting_runtime_registered()
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT EXISTS(SELECT 1 FROM oracle2.hosting_role_runtime_admissions r WHERE r.role_name=SESSION_USER AND r.expires_at>clock_timestamp()
 AND EXISTS(SELECT 1 FROM oracle2.hosting_role_source_admissions a WHERE a.role_name=r.role_name AND a.runtime_hash=r.runtime_hash AND a.registry_hash=r.registry_hash AND a.expires_at>clock_timestamp()));
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_runtime_registered() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_runtime_registered() TO oracle2_documentary_executor;
CREATE OR REPLACE FUNCTION oracle2.complete_documentary_view(run uuid,bytes bytea)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE job oracle2.operating_view_runs%ROWTYPE; parsed_pack jsonb; budget integer; hash text; runtime text;
BEGIN
 IF NOT pg_has_role(SESSION_USER,'oracle2_documentary_executor','member') OR NOT oracle2.hosting_runtime_registered() THEN
 RAISE EXCEPTION 'registered documentary runtime required' USING ERRCODE='42501'; END IF;
 SELECT * INTO job FROM oracle2.operating_view_runs WHERE run_id=run FOR UPDATE;
 IF NOT FOUND OR job.status<>'pending' OR job.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'canonical pending job required' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||job.workspace_id::text));
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-selector:'||job.workspace_id::text,0));
 PERFORM 1 FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 PERFORM 1 FROM oracle2.hosting_role_source_admissions WHERE role_name=SESSION_USER AND workspace_id=job.workspace_id FOR SHARE;
 PERFORM 1 FROM oracle2.operating_release_selectors WHERE workspace_id=job.workspace_id FOR SHARE;
 PERFORM 1 FROM oracle2.sources WHERE workspace_id=job.workspace_id AND source_id IN
 (SELECT (value->>'source_id')::uuid FROM jsonb_array_elements(job.source_refs)) FOR UPDATE;
 PERFORM 1 FROM oracle2.source_blocks WHERE workspace_id=job.workspace_id AND source_id IN
 (SELECT (value->>'source_id')::uuid FROM jsonb_array_elements(job.source_refs)) FOR SHARE;
 PERFORM 1 FROM oracle2.drafts WHERE workspace_id=job.workspace_id AND source_id IN
 (SELECT (value->>'source_id')::uuid FROM jsonb_array_elements(job.source_refs)) FOR SHARE;
 PERFORM 1 FROM oracle2.appointments WHERE workspace_id=job.workspace_id FOR SHARE;
 IF NOT oracle2.hosting_view_authorized(job.workspace_id,job.actor_id,job.release_id,job.release_hash,job.source_refs)
 OR job.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'current documentary authority required' USING ERRCODE='42501'; END IF;
 SELECT payload->>'artifact_content_hash',payload->>'runtime_digest' INTO hash,runtime FROM oracle2.operating_release_manifests
 WHERE workspace_id=job.workspace_id AND release_id=job.release_id;
 IF jsonb_typeof(job.query_plan->'max_bytes') IS DISTINCT FROM 'number' OR job.query_plan->>'max_bytes' !~ '^[0-9]+$' THEN RAISE EXCEPTION 'invalid byte budget' USING ERRCODE='42501'; END IF;
 budget=(job.query_plan->>'max_bytes')::integer;
 IF budget NOT BETWEEN 1024 AND 131072 OR bytes IS NULL OR octet_length(bytes)>budget THEN RAISE EXCEPTION 'pack byte budget exceeded' USING ERRCODE='42501'; END IF;
 parsed_pack=convert_from(bytes,'UTF8')::jsonb;
 IF jsonb_typeof(parsed_pack) IS DISTINCT FROM 'object' OR parsed_pack->>'artifact_hash' IS DISTINCT FROM hash THEN RAISE EXCEPTION 'current pack seal required' USING ERRCODE='42501'; END IF;
 IF job.expires_at<=clock_timestamp() OR NOT oracle2.hosting_view_authorized(job.workspace_id,job.actor_id,job.release_id,job.release_hash,job.source_refs) THEN RAISE EXCEPTION 'authority expired before publication' USING ERRCODE='42501'; END IF;
 INSERT INTO oracle2.operating_view_pack_receipts(run_id,workspace_id,actor_id,release_id,release_hash,runtime_hash,canonical_pack,pack_hash)
 VALUES(job.run_id,job.workspace_id,job.actor_id,job.release_id,job.release_hash,runtime,bytes,encode(sha256(bytes),'hex'));
 UPDATE oracle2.operating_view_runs SET status='completed',pack=parsed_pack WHERE run_id=job.run_id;
END $$;
REVOKE ALL ON FUNCTION oracle2.complete_documentary_view(uuid,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.complete_documentary_view(uuid,bytea) TO oracle2_documentary_executor;
-- Finding review/event import writes intentionally remain denied until a
-- canonical SQL-visible finding seal is admitted. Source implementation retained.
ALTER TABLE oracle2.operating_model_change_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hosting_documentary_watermark_read ON oracle2.operating_model_change_log;
CREATE POLICY hosting_documentary_watermark_read ON oracle2.operating_model_change_log FOR SELECT TO oracle2_documentary_executor
 USING(oracle2.hosting_workspace_visible(workspace_id));
DROP POLICY IF EXISTS hosting_gateway_watermark_read ON oracle2.operating_model_change_log;
CREATE POLICY hosting_gateway_watermark_read ON oracle2.operating_model_change_log FOR SELECT TO oracle2_gateway_metadata USING(true);
GRANT SELECT(workspace_id,sequence) ON oracle2.operating_model_change_log TO oracle2_documentary_executor;
