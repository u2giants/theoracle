-- Dedicated native ledger; additive capabilities, no issuance or old policy edits.
-- Trusted compiler authenticates registry/custody and seals actual private bytes.
-- SQL validates PROVIDED bytes/current source authority, not filesystem/registry truth.
DO $owner$
DECLARE owner_oid oid;
BEGIN
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF owner_oid IS NULL OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR owner_oid IS DISTINCT FROM (SELECT proowner FROM pg_proc WHERE oid=to_regprocedure('oracle2._processing_source(uuid,uuid,uuid,text,text,boolean)'))
 OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata') AND pg_has_role(oid,owner_oid,'MEMBER')) THEN
 RAISE EXCEPTION 'reviewed unreachable processing owner required'; END IF;
END $owner$;

-- Metadata only: workflow identifiers are extracted from the exact content-
-- hash-validated model payload, never provided separately by a confirmer.
CREATE TABLE IF NOT EXISTS oracle2.processing_artifact_workflows_v1 (
 workspace_id uuid NOT NULL,artifact_id uuid NOT NULL,version integer NOT NULL,
 workflow_id text NOT NULL CHECK(length(workflow_id) BETWEEN 1 AND 200),
 PRIMARY KEY(workspace_id,artifact_id,version,workflow_id),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests);
REVOKE ALL ON oracle2.processing_artifact_workflows_v1 FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
DO $immutable$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='immutable_processing_artifact_workflows_v1'
 AND tgrelid='oracle2.processing_artifact_workflows_v1'::regclass) THEN
  CREATE TRIGGER immutable_processing_artifact_workflows_v1 BEFORE UPDATE OR DELETE
   ON oracle2.processing_artifact_workflows_v1 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
 END IF;
END $immutable$;

CREATE OR REPLACE FUNCTION oracle2._processing_dependency_digest(workspace uuid,artifact uuid,ver integer)
 RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT encode(sha256(convert_to('{"dependencies":['||coalesce(string_agg(
 '['||to_jsonb(upstream_kind)::text||','||to_jsonb(upstream_id)::text||','||to_jsonb(upstream_revision)::text||']',','
 ORDER BY upstream_kind COLLATE "C",upstream_id COLLATE "C",upstream_revision COLLATE "C"),'')||']}', 'UTF8')),'hex')
 FROM oracle2.artifact_dependencies WHERE workspace_id=workspace AND artifact_id=artifact AND version=ver;
$$;
REVOKE ALL ON FUNCTION oracle2._processing_dependency_digest(uuid,uuid,integer) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.commit_processing_candidate(
 supplied_manifest jsonb, payload_bytes bytea, refs_bytes bytea, dependency_bytes bytea,
 supplied_receipts jsonb, expected_runtime text, expected_registry text, caller_deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE m jsonb:=supplied_manifest; p jsonb; refs jsonb; deps jsonb; ref jsonb; receipt jsonb; observation jsonb; dep jsonb;
 w uuid; aid uuid; ver integer; actor uuid; this_actor uuid; source uuid; rev integer;
 q record; existing jsonb; upstream jsonb; n bigint; expiry timestamptz:='infinity'; kinds text[];
BEGIN
 IF current_setting('lock_timeout')::interval=interval '0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN PERFORM set_config('lock_timeout','2s',true); END IF;
 IF caller_deadline IS NULL OR NOT isfinite(caller_deadline) OR caller_deadline<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 expiry:=least(expiry,caller_deadline);
 SELECT array_agg(rolname::text ORDER BY rolname) INTO kinds FROM pg_roles WHERE rolname IN
 ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata')
 AND pg_has_role(SESSION_USER,oid,'MEMBER');
 IF kinds IS DISTINCT FROM ARRAY['oracle2_candidate_compiler']::text[] THEN RAISE insufficient_privilege; END IF;
 IF jsonb_typeof(m) IS DISTINCT FROM 'object' OR NOT m ?& ARRAY['schema_version','workspace_id','artifact_id','version','kind','input_digest','source_digest','permission_digest','compiler_digest','dependency_digest','content_hash','private_object_key','state']
 OR (m-ARRAY['schema_version','workspace_id','artifact_id','version','kind','input_digest','source_digest','permission_digest','compiler_digest','dependency_digest','content_hash','private_object_key','state'])<>'{}'::jsonb
 OR m->'schema_version'<>'1'::jsonb OR jsonb_typeof(m->'kind') IS DISTINCT FROM 'string' OR jsonb_typeof(m->'version') IS DISTINCT FROM 'number' OR m->>'version' !~ '^[1-9][0-9]*$' OR m->>'kind' NOT IN ('processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1','processing_failed_assembly_v1')
 OR m->>'state' IS DISTINCT FROM (CASE WHEN m->>'kind' IN ('processing_failed_extraction_v1','processing_failed_assembly_v1') THEN 'failed' ELSE 'ready' END)
 OR EXISTS(SELECT 1 FROM unnest(ARRAY['input_digest','source_digest','permission_digest','compiler_digest','dependency_digest','content_hash']) k WHERE jsonb_typeof(m->k) IS DISTINCT FROM 'string' OR m->>k !~ '^[0-9a-f]{64}$')
 OR m->>'compiler_digest' IS DISTINCT FROM expected_runtime THEN RAISE insufficient_privilege USING MESSAGE='processing manifest denied'; END IF;
 w:=(m->>'workspace_id')::uuid; aid:=(m->>'artifact_id')::uuid; ver:=(m->>'version')::integer;
 IF w IS NULL OR aid IS NULL OR ver IS NULL OR ver<1 THEN RAISE insufficient_privilege; END IF;
 -- Preserve established order. No later acquisition of another artifact lock.
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-model:'||w::text||':'||aid::text,0));
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||w::text));
 p:=convert_from(payload_bytes,'UTF8')::jsonb;
 refs:=(convert_from(refs_bytes,'UTF8')::jsonb)->'refs';
 deps:=(convert_from(dependency_bytes,'UTF8')::jsonb)->'dependencies';
 IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR jsonb_typeof(refs) IS DISTINCT FROM 'array' OR jsonb_array_length(refs)=0
 OR p->'source_refs' IS DISTINCT FROM refs OR jsonb_typeof(deps) IS DISTINCT FROM 'array'
 OR jsonb_typeof(supplied_receipts) IS DISTINCT FROM 'array' OR jsonb_array_length(supplied_receipts)<>jsonb_array_length(refs)
 OR (SELECT count(DISTINCT x->>'source_id') FROM jsonb_array_elements(refs) x)<>jsonb_array_length(refs)
 OR m->>'content_hash' IS DISTINCT FROM encode(sha256(payload_bytes),'hex')
 OR m->>'source_digest' IS DISTINCT FROM encode(sha256(refs_bytes),'hex')
 OR m->>'input_digest' IS DISTINCT FROM m->>'source_digest'
 OR m->>'dependency_digest' IS DISTINCT FROM encode(sha256(dependency_bytes),'hex')
 OR m->>'private_object_key' IS DISTINCT FROM 'operating-model/'||w::text||'/'||(m->>'content_hash')||'.json' THEN
 RAISE insufficient_privilege USING MESSAGE='processing bundle integrity denied'; END IF;
 FOR ref IN SELECT value FROM jsonb_array_elements(refs) LOOP
  IF jsonb_typeof(ref) IS DISTINCT FROM 'object' OR (ref-ARRAY['schema_version','workspace_id','source_id','revision','original_sha256','reading_sha256','parser_id'])<>'{}'::jsonb
  OR NOT ref ?& ARRAY['schema_version','workspace_id','source_id','revision','original_sha256','reading_sha256','parser_id'] OR ref->'schema_version'<>'1'::jsonb
  OR ref->>'workspace_id' IS DISTINCT FROM w::text THEN RAISE insufficient_privilege; END IF;
  IF jsonb_typeof(ref->'revision') IS DISTINCT FROM 'number' OR ref->>'revision' !~ '^[1-9][0-9]*$' THEN RAISE insufficient_privilege; END IF;
  source:=(ref->>'source_id')::uuid;rev:=(ref->>'revision')::integer;
  IF ref->>'source_id' IS DISTINCT FROM source::text THEN RAISE insufficient_privilege; END IF;
  SELECT principal_id INTO this_actor FROM oracle2.hosting_role_source_admissions
  WHERE role_name=SESSION_USER AND workspace_id=w AND source_id=source AND revision=rev;
  IF this_actor IS NULL OR (actor IS NOT NULL AND actor<>this_actor) THEN RAISE insufficient_privilege USING MESSAGE='one current admitted compiler actor required'; END IF;
  actor:=this_actor;
  SELECT * INTO q FROM oracle2._processing_source(w,source,actor,expected_runtime,expected_registry,true);
  IF (q.revision,q.original_hash,q.reading_hash,q.parser_id) IS DISTINCT FROM (rev,ref->>'original_sha256',ref->>'reading_sha256',ref->>'parser_id') THEN RAISE insufficient_privilege; END IF;
  expiry:=least(expiry,q.valid_until);
  SELECT count(*),min(value::text)::jsonb INTO n,receipt FROM jsonb_array_elements(supplied_receipts)
  WHERE value->'ref'=ref;
  IF n<>1 OR jsonb_typeof(receipt) IS DISTINCT FROM 'object' OR receipt->'schema_version'<>'1'::jsonb
  OR (receipt-ARRAY['schema_version','ref','reading','display_revision','aliases'])<>'{}'::jsonb
  OR receipt->>'reading' IS DISTINCT FROM q.original_reading OR receipt->>'display_revision' IS DISTINCT FROM 'r'||rev::text
  OR jsonb_typeof(receipt->'aliases') IS DISTINCT FROM 'array'
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(receipt->'aliases') x WHERE jsonb_typeof(x) IS DISTINCT FROM 'string') THEN
  RAISE insufficient_privilege USING MESSAGE='authoritative processing receipt required'; END IF;
  SELECT r.receipt INTO existing FROM oracle2.operating_model_source_receipts r WHERE r.workspace_id=w AND r.source_id=source AND r.revision=rev;
  IF FOUND AND (existing-'aliases') IS DISTINCT FROM (receipt-'aliases') THEN RAISE insufficient_privilege USING MESSAGE='immutable receipt conflict'; END IF;
 END LOOP;
 -- Typed quote/support validation is the trusted compiler boundary. SQL also
 -- prevents a submitted generated record from labelling itself confirmed.
 IF jsonb_path_exists(p,'$.workflows[*].status ? (@ != "reported")')
 OR jsonb_path_exists(p,'$.operating_models[*].workflows[*].status ? (@ != "reported")')
 OR jsonb_path_exists(p,'$.findings[*].status ? (@ != "unresolved" && @ != "needs_evidence")') THEN
 RAISE insufficient_privilege USING MESSAGE='generated confirmation/review denied'; END IF;
 IF p ? 'observations' AND jsonb_typeof(p->'observations') IS DISTINCT FROM 'array' THEN RAISE insufficient_privilege; END IF;
 FOR observation IN SELECT value FROM jsonb_array_elements(coalesce(p->'observations','[]'::jsonb)) LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(refs) x WHERE x=observation->'ref')
  OR jsonb_typeof(observation->'observation_id') IS DISTINCT FROM 'string' OR observation->>'observation_id'=''
  OR (observation->>'workspace_id' IS NOT NULL AND observation->>'workspace_id'<>w::text) THEN RAISE insufficient_privilege USING MESSAGE='observation outside processing population'; END IF;
  SELECT o.payload INTO existing FROM oracle2.document_observations o WHERE o.workspace_id=w AND o.observation_id=observation->>'observation_id';
  IF FOUND AND existing IS DISTINCT FROM observation THEN RAISE insufficient_privilege USING MESSAGE='immutable observation conflict'; END IF;
 END LOOP;
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-lineage:'||w::text,0));
 -- Writer owns one self-compatible lock before any INSERT; two SHARE holders
 -- must never both upgrade to ROW EXCLUSIVE in competing workspaces.
 LOCK TABLE oracle2.artifact_manifests,oracle2.artifact_dependencies,oracle2.artifact_invalidations IN SHARE ROW EXCLUSIVE MODE;
 FOR dep IN SELECT value FROM jsonb_array_elements(deps) LOOP
  IF jsonb_typeof(dep) IS DISTINCT FROM 'array' OR jsonb_array_length(dep)<>3 OR EXISTS(SELECT 1 FROM jsonb_array_elements(dep) x WHERE jsonb_typeof(x) IS DISTINCT FROM 'string')
  OR dep->>0 NOT IN ('source','artifact') THEN RAISE insufficient_privilege USING MESSAGE='processing dependency kind denied'; END IF;
  IF dep->>0='source' THEN
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(refs) x WHERE x->>'source_id'=dep->>1 AND x->>'revision'=dep->>2) THEN RAISE insufficient_privilege; END IF;
  ELSE
   IF (dep->>1,dep->>2)=(aid::text,ver::text) THEN RAISE insufficient_privilege USING MESSAGE='artifact lineage cycle'; END IF;
   SELECT a.manifest INTO upstream FROM oracle2.artifact_manifests a WHERE a.workspace_id=w AND a.artifact_id=(dep->>1)::uuid AND a.version=(dep->>2)::integer AND a.state='ready' FOR SHARE;
   IF NOT FOUND OR upstream->>'kind' NOT IN ('processing_extraction_v1','processing_qualified_model_v1')
   OR EXISTS(SELECT 1 FROM oracle2.artifact_invalidations i WHERE i.workspace_id=w AND i.artifact_id=(dep->>1)::uuid AND i.version=(dep->>2)::integer)
   OR EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=w AND d.artifact_id=(dep->>1)::uuid AND d.version=(dep->>2)::integer AND d.upstream_kind='source'
    AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(refs) x WHERE x->>'source_id'=d.upstream_id AND x->>'revision'=d.upstream_revision)) THEN RAISE insufficient_privilege USING MESSAGE='current contained processing parent required'; END IF;
   PERFORM oracle2.hosting_processing_artifact(w,(dep->>1)::uuid,(dep->>2)::integer,actor,expected_runtime,expected_registry);
  END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(refs) candidate_ref WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(deps) d WHERE d->>0='source' AND d->>1=candidate_ref->>'source_id' AND d->>2=candidate_ref->>'revision')) THEN RAISE insufficient_privilege USING MESSAGE='complete source dependencies required'; END IF;
 IF m->>'kind'='processing_summary_v1' AND ((SELECT count(*) FROM jsonb_array_elements(deps) d WHERE d->>0='artifact')<>1
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(deps) d JOIN oracle2.artifact_manifests a ON a.workspace_id=w AND a.artifact_id=(d->>1)::uuid AND a.version=(d->>2)::integer WHERE d->>0='artifact' AND a.kind='processing_qualified_model_v1')) THEN RAISE insufficient_privilege USING MESSAGE='qualified summary parent required'; END IF;
 IF m->>'kind'='processing_qualified_model_v1' AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(deps) d WHERE d->>0='artifact') THEN RAISE insufficient_privilege USING MESSAGE='qualified model extraction parents required'; END IF;
 SELECT a.manifest INTO existing FROM oracle2.artifact_manifests a WHERE a.workspace_id=w AND a.artifact_id=aid AND a.version=ver;
 IF FOUND THEN
  IF existing IS DISTINCT FROM m OR oracle2._processing_dependency_digest(w,aid,ver) IS DISTINCT FROM m->>'dependency_digest' THEN RAISE insufficient_privilege USING MESSAGE='immutable artifact conflict'; END IF;
  IF expiry<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
  RETURN existing;
 END IF;
 FOR receipt IN SELECT value FROM jsonb_array_elements(supplied_receipts) LOOP
  ref:=receipt->'ref';
  INSERT INTO oracle2.operating_model_source_receipts(workspace_id,source_id,revision,original_hash,reading_hash,parser_id,receipt)
  VALUES(w,(ref->>'source_id')::uuid,(ref->>'revision')::integer,ref->>'original_sha256',ref->>'reading_sha256',ref->>'parser_id',receipt) ON CONFLICT DO NOTHING;
 END LOOP;
 FOR observation IN SELECT value FROM jsonb_array_elements(coalesce(p->'observations','[]'::jsonb)) LOOP
  INSERT INTO oracle2.document_observations(workspace_id,observation_id,source_id,source_revision,payload)
  VALUES(w,observation->>'observation_id',(observation->'ref'->>'source_id')::uuid,(observation->'ref'->>'revision')::integer,observation) ON CONFLICT DO NOTHING;
 END LOOP;
 INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest)
 VALUES(w,aid,ver,m->>'kind',m->>'input_digest',m->>'source_digest',m->>'permission_digest',m->>'compiler_digest',m->>'dependency_digest',m->>'content_hash',m->>'private_object_key',m->>'state',m);
 FOR dep IN SELECT value FROM jsonb_array_elements(deps) LOOP
  INSERT INTO oracle2.artifact_dependencies(workspace_id,artifact_id,version,upstream_kind,upstream_id,upstream_revision) VALUES(w,aid,ver,dep->>0,dep->>1,dep->>2) ON CONFLICT DO NOTHING;
 END LOOP;
 -- Index only identifiers actually present in the sealed generated body.
 IF m->>'kind'='processing_qualified_model_v1' THEN
  FOR observation IN SELECT value FROM jsonb_path_query(p,
   '$.workflows[*]') AS x(value) UNION ALL SELECT value FROM jsonb_path_query(p,'$.operating_models[*].workflows[*]') AS x(value) LOOP
   IF jsonb_typeof(observation->'workflow_id') IS DISTINCT FROM 'string'
   OR length(observation->>'workflow_id') NOT BETWEEN 1 AND 200
   OR observation->>'status' IS DISTINCT FROM 'reported' THEN
    RAISE insufficient_privilege USING MESSAGE='bounded sealed workflow identity required';
   END IF;
   INSERT INTO oracle2.processing_artifact_workflows_v1 VALUES(w,aid,ver,observation->>'workflow_id') ON CONFLICT DO NOTHING;
  END LOOP;
 END IF;
 -- Only qualified models have a graph projection. Other artifacts emit nothing.
 IF m->>'kind'='processing_qualified_model_v1' THEN
  INSERT INTO oracle2.outbox(event_id,workspace_id,assertion_id,revision,operation,payload)
  VALUES(gen_random_uuid(),w,aid,ver,'project',jsonb_build_object('namespace','oracle_processing_v1','manifest',m));
 END IF;
 IF oracle2._processing_dependency_digest(w,aid,ver) IS DISTINCT FROM m->>'dependency_digest' THEN RAISE insufficient_privilege USING MESSAGE='exact canonical dependency seal required'; END IF;
 IF expiry<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='processing authority expired before commit'; END IF;
 RETURN m;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR null_value_not_allowed THEN
 RAISE insufficient_privilege USING MESSAGE='invalid processing bundle';
END $body$;
REVOKE ALL ON FUNCTION oracle2.commit_processing_candidate(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamptz) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.commit_processing_candidate(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamptz) TO oracle2_candidate_compiler;

-- No receipt bodies or original text in this getter. It serves only the caller's
-- exact current source population and rejects forged/extended relational lineage.
-- Shared immutable lineage validation; source authorization stays with each
-- caller's existing role-specific boundary. Never granted to a runtime role.
CREATE OR REPLACE FUNCTION oracle2._processing_immutable_artifact_metadata_v1(
 workspace uuid,artifact uuid,ver integer,refs jsonb)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE m jsonb;a record;cycle boolean;
BEGIN
 SELECT x.manifest INTO STRICT m FROM oracle2.artifact_manifests x
 WHERE x.workspace_id=workspace AND x.artifact_id=artifact AND x.version=ver FOR SHARE;
 IF jsonb_typeof(refs) IS DISTINCT FROM 'array' OR jsonb_array_length(refs)=0
 OR (SELECT count(*) FROM oracle2.artifact_dependencies x WHERE x.workspace_id=workspace
  AND x.artifact_id=artifact AND x.version=ver AND x.upstream_kind='source')<>jsonb_array_length(refs)
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(refs) r WHERE NOT EXISTS(
  SELECT 1 FROM oracle2.artifact_dependencies x WHERE x.workspace_id=workspace AND x.artifact_id=artifact
   AND x.version=ver AND x.upstream_kind='source' AND x.upstream_id=r->>'source_id' AND x.upstream_revision=r->>'revision')) THEN
  RAISE insufficient_privilege USING MESSAGE='exact complete artifact source set required';
 END IF;
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
 IF cycle THEN RAISE insufficient_privilege USING MESSAGE='processing lineage cycle or expired authority'; END IF;
 RETURN m;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='invalid processing lineage';
END $body$;
REVOKE ALL ON FUNCTION oracle2._processing_immutable_artifact_metadata_v1(uuid,uuid,integer,jsonb) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2._processing_artifact_metadata(
 workspace uuid,artifact uuid,ver integer,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(manifest jsonb,source_refs jsonb)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE m jsonb; a record; d record; q record; refs jsonb:='[]'; expiry timestamptz:='infinity'; kinds text[]; cycle boolean;
BEGIN
 IF current_setting('lock_timeout')::interval=interval '0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN PERFORM set_config('lock_timeout','2s',true); END IF;
 SELECT array_agg(rolname::text ORDER BY rolname) INTO kinds FROM pg_roles WHERE rolname IN
 ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata') AND pg_has_role(SESSION_USER,oid,'MEMBER');
 IF coalesce(cardinality(kinds),0)<>1 OR kinds[1] NOT IN ('oracle2_candidate_compiler','oracle2_documentary_executor') THEN RAISE insufficient_privilege; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));
 SELECT x.manifest INTO m FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=artifact AND x.version=ver FOR SHARE;
 IF NOT FOUND OR m->>'kind' NOT IN ('processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1','processing_failed_assembly_v1') THEN RAISE insufficient_privilege USING MESSAGE='processing artifact absent'; END IF;
 -- Qualify rows before taking lineage-table locks, preserving source-first order.
 FOR d IN SELECT x.upstream_id,x.upstream_revision FROM oracle2.artifact_dependencies x
 WHERE x.workspace_id=workspace AND x.artifact_id=artifact AND x.version=ver AND x.upstream_kind='source' ORDER BY x.upstream_id,x.upstream_revision LOOP
  SELECT * INTO q FROM oracle2._processing_source(workspace,d.upstream_id::uuid,principal,expected_runtime,expected_registry,false);
  IF q.revision::text<>d.upstream_revision THEN RAISE insufficient_privilege; END IF;
  expiry:=least(expiry,q.valid_until);
  refs:=refs||jsonb_build_array(jsonb_build_object('schema_version',1,'workspace_id',workspace,'source_id',d.upstream_id::uuid,
   'revision',q.revision,'original_sha256',q.original_hash,'reading_sha256',q.reading_hash,'parser_id',q.parser_id));
 END LOOP;
 IF jsonb_array_length(refs)=0 THEN RAISE insufficient_privilege USING MESSAGE='processing source population missing'; END IF;
 m:=oracle2._processing_immutable_artifact_metadata_v1(workspace,artifact,ver,refs);
 IF expiry<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='processing lineage cycle or expired authority'; END IF;
 RETURN QUERY SELECT m,refs;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE insufficient_privilege USING MESSAGE='invalid processing lineage';
END $body$;
REVOKE ALL ON FUNCTION oracle2._processing_artifact_metadata(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_processing_artifact(
 workspace uuid,artifact uuid,ver integer,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(manifest jsonb,source_refs jsonb)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q record;
BEGIN
 SELECT * INTO STRICT q FROM oracle2._processing_artifact_metadata(workspace,artifact,ver,principal,expected_runtime,expected_registry);
 IF pg_has_role(SESSION_USER,'oracle2_documentary_executor','MEMBER')
 AND q.manifest->>'kind' NOT IN ('processing_qualified_model_v1','processing_summary_v1') THEN
  RAISE insufficient_privilege USING MESSAGE='executor candidate body capability denied';
 END IF;
 RETURN QUERY SELECT q.manifest,q.source_refs;
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_artifact(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_processing_artifact(uuid,uuid,integer,uuid,text,text) TO oracle2_candidate_compiler,oracle2_documentary_executor;

-- A seal is metadata only. The full manifest/private key never leaves this getter.
CREATE OR REPLACE FUNCTION oracle2.hosting_processing_extraction_seal(
 workspace uuid,artifact uuid,ver integer,principal uuid,expected_runtime text,expected_registry text)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q record; manifest_hash text;
BEGIN
 SELECT * INTO STRICT q FROM oracle2._processing_artifact_metadata(workspace,artifact,ver,principal,expected_runtime,expected_registry);
 IF q.manifest->>'kind'<>'processing_extraction_v1' OR q.manifest->>'state'<>'ready' THEN RAISE insufficient_privilege; END IF;
 -- ArtifactManifest consists only of canonical scalar values. Preserve exact
 -- private-path bytes inside the digest without returning those bytes.
 SELECT encode(sha256(convert_to('{'||string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")||'}','UTF8')),'hex')
 INTO manifest_hash FROM jsonb_each(q.manifest);
 RETURN jsonb_build_object('schema_version',1,'workspace_id',workspace,'artifact_id',artifact,'version',ver,
 'kind','processing_extraction_v1','state','ready','content_hash',q.manifest->>'content_hash',
 'input_digest',q.manifest->>'input_digest','source_digest',q.manifest->>'source_digest',
 'permission_digest',q.manifest->>'permission_digest','compiler_digest',q.manifest->>'compiler_digest',
 'manifest_hash',manifest_hash,'dependency_digest',q.manifest->>'dependency_digest','source_refs',q.source_refs);
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_extraction_seal(uuid,uuid,integer,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_processing_extraction_seal(uuid,uuid,integer,uuid,text,text) TO oracle2_candidate_compiler,oracle2_documentary_executor;

-- Existing queue, explicit processing lease fencing. Legacy rows stay NULL and
-- legacy lease/receipt handlers are not changed or admitted to this namespace.
ALTER TABLE oracle2.outbox ADD COLUMN IF NOT EXISTS processing_lease_role name;
ALTER TABLE oracle2.outbox ADD COLUMN IF NOT EXISTS processing_lease_token uuid;

CREATE OR REPLACE FUNCTION oracle2._processing_projection_actor(workspace uuid,artifact uuid,ver integer,runtime text,registry text)
 RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE actor uuid;
BEGIN
 SELECT a.principal_id INTO actor FROM oracle2.artifact_dependencies d JOIN oracle2.hosting_role_source_admissions a
 ON a.role_name=SESSION_USER AND a.workspace_id=d.workspace_id AND a.source_id=d.upstream_id::uuid AND a.revision=d.upstream_revision::integer
 WHERE d.workspace_id=workspace AND d.artifact_id=artifact AND d.version=ver AND d.upstream_kind='source' ORDER BY d.upstream_id LIMIT 1;
 IF actor IS NULL THEN RAISE insufficient_privilege; END IF;
 PERFORM oracle2.hosting_processing_artifact(workspace,artifact,ver,actor,runtime,registry);
 RETURN actor;
END $$;
REVOKE ALL ON FUNCTION oracle2._processing_projection_actor(uuid,uuid,integer,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2._processing_projection_eligible(workspace uuid,artifact uuid,ver integer,event_payload jsonb,runtime text,registry text)
 RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE m jsonb;
BEGIN
 PERFORM oracle2._processing_projection_actor(workspace,artifact,ver,runtime,registry);
 SELECT x.manifest INTO m FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=artifact AND x.version=ver;
 RETURN event_payload=jsonb_build_object('namespace','oracle_processing_v1','manifest',m)
 AND m->>'kind'='processing_qualified_model_v1' AND m->>'state'='ready'
 AND ver=(SELECT max(x.version) FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=artifact AND x.kind='processing_qualified_model_v1' AND x.state='ready');
EXCEPTION WHEN insufficient_privilege OR invalid_text_representation OR numeric_value_out_of_range THEN
 RETURN false;
END $$;
REVOKE ALL ON FUNCTION oracle2._processing_projection_eligible(uuid,uuid,integer,jsonb,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.lease_processing_projection(workspace uuid,runtime text,registry text,lease_seconds integer)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE candidate record; e oracle2.outbox%ROWTYPE; actor uuid; current_manifest jsonb; token uuid; scanned integer:=0;
BEGIN
 -- Timeout must be set BEFORE the command begins; setting it inside a function
 -- would not reliably arm the current statement's timer. The fixed adapter does so.
 IF current_setting('statement_timeout')::interval<=interval '0' OR current_setting('statement_timeout')::interval>interval '5 seconds' THEN RAISE insufficient_privilege USING MESSAGE='bounded statement timeout required'; END IF;
 IF lease_seconds IS NULL OR lease_seconds<1 OR lease_seconds>60
 OR NOT pg_has_role(SESSION_USER,'oracle2_candidate_compiler','MEMBER') THEN RAISE insufficient_privilege; END IF;
 IF current_setting('lock_timeout')::interval=interval '0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN PERFORM set_config('lock_timeout','2s',true); END IF;
 -- Exact workspace prevents an unauthorized/blocked workspace starving another.
 -- Bounded scan and existing MAX_ATTEMPTS=10 prevent unbounded automatic replay.
 FOR candidate IN SELECT event_id,assertion_id,revision FROM oracle2.outbox o
 WHERE o.workspace_id=workspace AND o.payload->>'namespace'='oracle_processing_v1'
 AND o.operation='project' AND o.payload->'manifest'->>'kind'='processing_qualified_model_v1'
 AND o.delivered_at IS NULL AND (o.lease_until IS NULL OR o.lease_until<clock_timestamp()) AND o.attempts<10
 AND EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d JOIN oracle2.hosting_role_source_admissions a ON a.role_name=SESSION_USER AND a.workspace_id=d.workspace_id AND a.source_id=d.upstream_id::uuid AND a.revision=d.upstream_revision::integer
 WHERE d.workspace_id=workspace AND d.artifact_id=o.assertion_id AND d.version=o.revision AND d.upstream_kind='source')
 AND oracle2._processing_projection_eligible(workspace,o.assertion_id,o.revision,o.payload,runtime,registry)
 ORDER BY o.revision,o.event_id LIMIT 64 LOOP
  BEGIN
   -- No artifact advisory lock is taken by leasing; none is taken after workspace.
   actor:=oracle2._processing_projection_actor(workspace,candidate.assertion_id,candidate.revision,runtime,registry);
   SELECT x.manifest INTO current_manifest FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=candidate.assertion_id AND x.version=candidate.revision;
   SELECT * INTO e FROM oracle2.outbox o WHERE o.event_id=candidate.event_id AND o.workspace_id=workspace
    AND o.delivered_at IS NULL AND (o.lease_until IS NULL OR o.lease_until<clock_timestamp()) AND o.attempts<10 FOR UPDATE SKIP LOCKED;
   IF NOT FOUND THEN CONTINUE; END IF;
   IF e.payload IS DISTINCT FROM jsonb_build_object('namespace','oracle_processing_v1','manifest',current_manifest)
   OR current_manifest->>'kind'<>'processing_qualified_model_v1' OR current_manifest->>'state'<>'ready'
   OR e.revision<>(SELECT max(x.version) FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=e.assertion_id AND x.kind='processing_qualified_model_v1' AND x.state='ready') THEN CONTINUE; END IF;
   token:=gen_random_uuid();
   UPDATE oracle2.outbox SET attempts=attempts+1,lease_until=clock_timestamp()+make_interval(secs=>lease_seconds),processing_lease_role=SESSION_USER,processing_lease_token=token WHERE event_id=e.event_id RETURNING * INTO e;
   -- Actual authority must remain current after the row wait/claim.
   PERFORM oracle2._processing_projection_actor(workspace,e.assertion_id,e.revision,runtime,registry);
   RETURN jsonb_build_object('event_id',e.event_id,'workspace_id',workspace,'assertion_id',e.assertion_id,'revision',e.revision,'operation',e.operation,'payload',e.payload,'attempts',e.attempts,'lease_role',e.processing_lease_role,'lease_token',e.processing_lease_token,'lease_until',e.lease_until);
  EXCEPTION WHEN insufficient_privilege OR invalid_text_representation OR numeric_value_out_of_range THEN
   -- Entire denied candidate subtransaction rolls back; return no candidate data.
   CONTINUE;
  END;
 END LOOP;
 RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION oracle2.lease_processing_projection(uuid,text,text,integer) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.lease_processing_projection(uuid,text,text,integer) TO oracle2_candidate_compiler;

CREATE OR REPLACE FUNCTION oracle2.ack_processing_projection(
 event uuid,workspace uuid,token uuid,attempt integer,receipt jsonb,receipt_signature text,runtime text,registry text,caller_deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE e oracle2.outbox%ROWTYPE; actor uuid; m jsonb; prior oracle2.operating_projection_receipts%ROWTYPE;
 base_keys text[]:=ARRAY['schema_version','event_id','workspace_id','artifact_id','version','content_hash','source_digest','permission_digest','graph_name','record_digest','sdk_version','projector_id','lease_role','lease_token','lease_attempt','lease_until','projection_schema','projection_digest'];
 paid_hashes text[]:=ARRAY['embedding_inventory_hash','embedding_context_hash','embedding_native_receipt_hash','embedding_wire_hash','embedding_commit_hash','embedding_vectors_hash','embedding_coverage_hash'];
 receipt_keys text[]; paid boolean;
BEGIN
 IF caller_deadline IS NULL OR NOT isfinite(caller_deadline) OR caller_deadline<=clock_timestamp()
 OR NOT pg_has_role(SESSION_USER,'oracle2_candidate_compiler','MEMBER') OR receipt_signature IS NULL OR receipt_signature !~ '^[0-9a-f]{64}$' THEN RAISE insufficient_privilege; END IF;
 IF current_setting('lock_timeout')::interval=interval '0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN PERFORM set_config('lock_timeout','2s',true); END IF;
 SELECT * INTO e FROM oracle2.outbox o WHERE o.event_id=event AND o.workspace_id=workspace;
 IF NOT FOUND THEN RAISE insufficient_privilege; END IF;
 paid:=coalesce(receipt->'schema_version'='3'::jsonb AND receipt->>'schema_version'='3',false);
 receipt_keys:=base_keys||CASE WHEN paid THEN ARRAY['embedding_protocol']||paid_hashes ELSE ARRAY[]::text[] END;
 actor:=oracle2._processing_projection_actor(workspace,e.assertion_id,e.revision,runtime,registry);
 SELECT * INTO e FROM oracle2.outbox o WHERE o.event_id=event AND o.workspace_id=workspace FOR UPDATE;
 SELECT x.manifest INTO m FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=e.assertion_id AND x.version=e.revision;
 IF e.processing_lease_role IS DISTINCT FROM SESSION_USER OR e.processing_lease_token IS DISTINCT FROM token OR e.attempts IS DISTINCT FROM attempt
 OR e.operation<>'project' OR e.payload IS DISTINCT FROM jsonb_build_object('namespace','oracle_processing_v1','manifest',m)
 OR m->>'kind' IS DISTINCT FROM 'processing_qualified_model_v1' OR m->>'state' IS DISTINCT FROM 'ready'
 OR e.revision<>(SELECT max(x.version) FROM oracle2.artifact_manifests x WHERE x.workspace_id=workspace AND x.artifact_id=e.assertion_id AND x.kind='processing_qualified_model_v1' AND x.state='ready')
 OR jsonb_typeof(receipt) IS DISTINCT FROM 'object'
 OR NOT receipt ?& receipt_keys
 OR (receipt-receipt_keys)<>'{}'::jsonb
 OR EXISTS(SELECT 1 FROM unnest(ARRAY['event_id','workspace_id','artifact_id','content_hash','source_digest','permission_digest','graph_name','record_digest','sdk_version','projector_id','lease_role','lease_token','lease_until','projection_schema','projection_digest']) k WHERE jsonb_typeof(receipt->k) IS DISTINCT FROM 'string')
 OR jsonb_typeof(receipt->'version') IS DISTINCT FROM 'number' OR jsonb_typeof(receipt->'lease_attempt') IS DISTINCT FROM 'number'
 OR (NOT paid AND receipt->'schema_version' IS DISTINCT FROM '1'::jsonb)
 OR (paid AND (receipt->>'embedding_protocol' IS DISTINCT FROM 'paid-sdk-embedding-v3'
  OR EXISTS(SELECT 1 FROM unnest(paid_hashes) k WHERE jsonb_typeof(receipt->k) IS DISTINCT FROM 'string' OR receipt->>k !~ '^[0-9a-f]{64}$')))
 OR receipt->>'event_id' IS DISTINCT FROM event::text
 OR receipt->>'workspace_id' IS DISTINCT FROM workspace::text OR receipt->>'artifact_id' IS DISTINCT FROM e.assertion_id::text OR receipt->>'version' IS DISTINCT FROM e.revision::text
 OR receipt->>'content_hash' IS DISTINCT FROM m->>'content_hash' OR receipt->>'source_digest' IS DISTINCT FROM m->>'source_digest' OR receipt->>'permission_digest' IS DISTINCT FROM m->>'permission_digest'
 OR receipt->>'projection_schema' IS DISTINCT FROM 'qualified-evidence-projection-v1' OR receipt->>'projection_digest' !~ '^[0-9a-f]{64}$'
 OR receipt->>'sdk_version' IS DISTINCT FROM '1.4.0' OR jsonb_typeof(receipt->'projector_id') IS DISTINCT FROM 'string' OR receipt->>'projector_id'=''
 OR receipt->>'record_digest' !~ '^[0-9a-f]{64}$' OR receipt->>'lease_role' IS DISTINCT FROM SESSION_USER::text OR receipt->>'lease_token' IS DISTINCT FROM token::text OR receipt->>'lease_attempt' IS DISTINCT FROM attempt::text
 OR receipt->>'graph_name' !~ ('^oracle_processing_v1_'||replace(workspace::text,'-','')||'_'||replace(e.assertion_id::text,'-','')||'_'||e.revision::text||'_[0-9a-f]{32}$') THEN
 RAISE insufficient_privilege USING MESSAGE='exact processing delivery receipt and current claim required'; END IF;
 SELECT * INTO prior FROM oracle2.operating_projection_receipts r WHERE r.event_id=event;
 IF FOUND THEN
  IF e.delivered_at IS NULL OR prior.payload IS DISTINCT FROM receipt OR prior.signature IS DISTINCT FROM receipt_signature THEN RAISE insufficient_privilege USING MESSAGE='conflicting processing ACK'; END IF;
  IF caller_deadline<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
  RETURN jsonb_build_object('receipt',prior.payload,'signature',prior.signature);
 END IF;
 IF e.delivered_at IS NOT NULL OR e.lease_until IS NULL OR NOT isfinite(e.lease_until) OR e.lease_until<=clock_timestamp()
 OR (receipt->>'lease_until')::timestamptz IS DISTINCT FROM e.lease_until THEN RAISE insufficient_privilege USING MESSAGE='processing lease expired or replaced'; END IF;
 INSERT INTO oracle2.operating_projection_receipts(event_id,workspace_id,artifact_id,version,payload,signature)
 VALUES(event,workspace,e.assertion_id,e.revision,receipt,receipt_signature);
 UPDATE oracle2.outbox SET delivered_at=clock_timestamp(),lease_until=NULL WHERE event_id=event;
 PERFORM oracle2._processing_projection_actor(workspace,e.assertion_id,e.revision,runtime,registry);
 IF caller_deadline<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='processing semantic authority expired before ACK'; END IF;
 RETURN jsonb_build_object('receipt',receipt,'signature',receipt_signature);
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE insufficient_privilege USING MESSAGE='invalid processing ACK';
END $$;
REVOKE ALL ON FUNCTION oracle2.ack_processing_projection(uuid,uuid,uuid,integer,jsonb,text,text,text,timestamptz) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.ack_processing_projection(uuid,uuid,uuid,integer,jsonb,text,text,text,timestamptz) TO oracle2_candidate_compiler;
