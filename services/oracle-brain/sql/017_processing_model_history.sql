-- Dedicated canonical processing owner. SOURCE ONLY: no appointments/login roles
-- or installation grants are issued. 015/016 special-target proof scripts excluded.
DO $owner$ DECLARE owner_oid oid; BEGIN
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR owner_oid IS DISTINCT FROM (SELECT proowner FROM pg_proc WHERE oid=to_regprocedure('oracle2.commit_processing_candidate(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamp with time zone)'))
 THEN RAISE EXCEPTION 'canonical processing owner required'; END IF;
END $owner$;

CREATE TABLE oracle2.processing_model_revisions_v1 (
 workspace_id uuid NOT NULL,artifact_id uuid NOT NULL,version integer NOT NULL CHECK(version>0),
 content_hash text NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'),
 predecessor_version integer NOT NULL CHECK(predecessor_version>=0),predecessor_hash text,
 core_hash text NOT NULL CHECK(core_hash ~ '^[0-9a-f]{64}$'),
 qualification_hash text NOT NULL CHECK(qualification_hash ~ '^[0-9a-f]{64}$'),
 assertion_index jsonb NOT NULL CHECK(jsonb_typeof(assertion_index)='array'),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 registered_by uuid NOT NULL,admission_id uuid NOT NULL,idempotency uuid NOT NULL,
 PRIMARY KEY(workspace_id,artifact_id,version),UNIQUE(workspace_id,artifact_id,idempotency),
 CHECK(version=predecessor_version+1),CHECK((predecessor_version=0)=(predecessor_hash IS NULL)),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests);
CREATE TABLE oracle2.processing_model_events_v1 (
 event_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,artifact_id uuid NOT NULL,version integer NOT NULL,
 kind text NOT NULL CHECK(kind IN('business-accept','business-reject','business-challenge','business-withdraw','derived-stale')),
 actor_id uuid NOT NULL,admission_id uuid NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),idempotency uuid NOT NULL,
 UNIQUE(workspace_id,artifact_id,idempotency),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests);
-- External installation input, purpose separated from old runtime admissions.
CREATE TABLE oracle2.processing_model_admissions_v1 (
 admission_id uuid PRIMARY KEY,role_name name NOT NULL,principal_id uuid NOT NULL,workspace_id uuid NOT NULL,model_id uuid NOT NULL,
 operation text NOT NULL CHECK(operation IN('consolidate','history-read','business-review')),
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),registry_hash text NOT NULL CHECK(registry_hash ~ '^[0-9a-f]{64}$'),
 config_hash text NOT NULL CHECK(config_hash ~ '^[0-9a-f]{64}$'),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL,
 decision_kind text CHECK(decision_kind IN('employee-account','process-policy','company-policy')),
 -- Finite command authority window; accepted company policy has NO implicit
 -- expiry from this field or former approver authority loss. Explicit withdrawal
 -- and current source/reader/version checks determine availability/in-force state.
 decision_valid_until timestamptz CHECK(decision_valid_until IS NULL OR isfinite(decision_valid_until)),
 scope_hash text CHECK(scope_hash ~ '^[0-9a-f]{64}$'),
 membership_appointment uuid REFERENCES oracle2.appointments(appointment_id),
 source_refs jsonb NOT NULL CHECK(jsonb_typeof(source_refs)='array' AND jsonb_array_length(source_refs) BETWEEN 1 AND 64),
 issued_at timestamptz NOT NULL,expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 CHECK(issued_at<expires_at AND issuer_actor<>reviewer_actor AND principal_id NOT IN(issuer_actor,reviewer_actor)),
 CHECK((operation='business-review')=(decision_kind IS NOT NULL AND scope_hash IS NOT NULL AND membership_appointment IS NOT NULL AND decision_valid_until IS NOT NULL)),
 CHECK(decision_valid_until IS NULL OR decision_valid_until>issued_at AND decision_valid_until<=expires_at));
CREATE TABLE oracle2.processing_model_admission_revocations_v1 (
 admission_id uuid PRIMARY KEY REFERENCES oracle2.processing_model_admissions_v1,revoked_at timestamptz NOT NULL DEFAULT clock_timestamp());
-- Only actual source-owner wrapper can classify a NEW replacement invalidation.
CREATE TABLE oracle2.processing_preserved_supersessions_v1 (
 workspace_id uuid NOT NULL,artifact_id uuid NOT NULL,version integer NOT NULL,event_id uuid NOT NULL,
 source_id uuid NOT NULL,old_revision integer NOT NULL,new_revision integer NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,artifact_id,version,event_id),
 FOREIGN KEY(workspace_id,artifact_id,version,event_id) REFERENCES oracle2.artifact_invalidations,
 CHECK(new_revision=old_revision+1));
DO $immutable$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['processing_model_revisions_v1','processing_model_events_v1','processing_model_admissions_v1','processing_model_admission_revocations_v1','processing_preserved_supersessions_v1'] LOOP
  EXECUTE format('REVOKE ALL ON oracle2.%I FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester',t);
  EXECUTE format('CREATE TRIGGER immutable_%I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()',t,t);
 END LOOP;
END $immutable$;

CREATE FUNCTION oracle2._processing_model_admission_v1(appointment uuid,operation_name text,runtime text,registry text,config text,deadline timestamptz)
 RETURNS oracle2.processing_model_admissions_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1; login oid; owner_oid oid; permitted_until timestamptz;member_ok boolean;root_ok boolean;
BEGIN
 SELECT oid INTO login FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin
 AND NOT(rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication);
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF login IS NULL OR CURRENT_USER::text<>(SELECT rolname::text FROM pg_roles WHERE oid=owner_oid)
 OR pg_has_role(login,owner_oid,'MEMBER') OR current_setting('role') NOT IN('none',SESSION_USER::text)
 OR deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO a FROM oracle2.processing_model_admissions_v1 WHERE admission_id=appointment FOR SHARE;
 IF a.role_name IS DISTINCT FROM SESSION_USER OR a.operation IS DISTINCT FROM operation_name
 OR (a.runtime_hash,a.registry_hash,a.config_hash) IS DISTINCT FROM(runtime,registry,config)
 OR a.issued_at>clock_timestamp() OR a.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.processing_model_admission_revocations_v1 WHERE admission_id=appointment)
 THEN RAISE insufficient_privilege USING MESSAGE='current exact processing purpose appointment required'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||a.workspace_id::text));
 IF operation_name='consolidate' THEN
  IF NOT pg_has_role(login,'oracle2_candidate_compiler','MEMBER') THEN RAISE insufficient_privilege; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid<>login AND
   (pg_has_role(login,r.oid,'MEMBER') OR pg_has_role(login,r.oid,'SET') OR pg_has_role(login,r.oid,'USAGE')))
  THEN RAISE insufficient_privilege USING MESSAGE='distinct exact history/business login required'; END IF;
 END IF;
 IF operation_name='business-review' THEN
  IF a.decision_valid_until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='declared finite business decision window expired'; END IF;
  IF NOT EXISTS(SELECT 1 FROM oracle2.appointments p WHERE p.appointment_id=a.membership_appointment
    AND p.workspace_id=a.workspace_id AND p.actor_id=a.principal_id AND p.revoked_at IS NULL
    AND (p.expires_at IS NULL OR p.expires_at>clock_timestamp())
    AND p.scope='processing-business:'||a.decision_kind||':'||a.scope_hash)
  THEN RAISE insufficient_privilege USING MESSAGE='exact business membership/delegation missing'; END IF;
  -- Retain canonical locking/currentness, then prove THIS appointed path.
  PERFORM oracle2._replacement_scope(a.workspace_id,a.principal_id,'processing-business:'||a.decision_kind||':'||a.scope_hash);
  WITH RECURSIVE exact_path AS (
   SELECT p.appointment_id,p.parent_id,p.actor_id,p.granted_by,p.scope,p.revoked_at,p.expires_at,
    ARRAY[p.appointment_id] seen,true valid,1 depth
   FROM oracle2.appointments p WHERE p.workspace_id=a.workspace_id AND p.appointment_id=a.membership_appointment
    AND p.actor_id=a.principal_id AND p.scope='processing-business:'||a.decision_kind||':'||a.scope_hash
   UNION ALL
   SELECT p.appointment_id,p.parent_id,p.actor_id,p.granted_by,p.scope,p.revoked_at,p.expires_at,
    path.seen||p.appointment_id,path.valid AND p.actor_id=path.granted_by
     AND p.scope IN('processing-business:'||a.decision_kind||':'||a.scope_hash,'root'),path.depth+1
   FROM exact_path path JOIN oracle2.appointments p ON p.appointment_id=path.parent_id AND p.workspace_id=a.workspace_id
   WHERE path.depth<16 AND NOT p.appointment_id=ANY(path.seen))
  SELECT coalesce(min(expires_at),'infinity'::timestamptz),
   bool_and(valid AND revoked_at IS NULL AND(expires_at IS NULL OR expires_at>clock_timestamp())),
   bool_or(scope='root' AND parent_id IS NULL)
  INTO permitted_until,member_ok,root_ok FROM exact_path;
  IF member_ok IS DISTINCT FROM true OR root_ok IS DISTINCT FROM true THEN
   RAISE insufficient_privilege USING MESSAGE='exact appointed business delegation path denied';
  END IF;
  permitted_until:=least(permitted_until,a.decision_valid_until);
 ELSE
  permitted_until:=oracle2._replacement_scope(a.workspace_id,a.principal_id,
    CASE WHEN operation_name='history-read' THEN 'processing-history' ELSE 'processing-consolidate' END);
 END IF;
 a.expires_at:=least(a.expires_at,deadline,permitted_until);
 IF a.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN a;
END $$;
REVOKE ALL ON FUNCTION oracle2._processing_model_admission_v1(uuid,text,text,text,text,timestamptz) FROM PUBLIC;

-- Deterministic JSON bytes for the closed string/integer assertion contract.
CREATE FUNCTION oracle2._processing_canonical_jsonb_v1(value jsonb)
 RETURNS text LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE result text;
BEGIN
 CASE jsonb_typeof(value)
 WHEN 'object' THEN SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||oracle2._processing_canonical_jsonb_v1(v),',' ORDER BY key COLLATE "C"),'')||'}' INTO result FROM jsonb_each(value) x(key,v);
 WHEN 'array' THEN SELECT '['||coalesce(string_agg(oracle2._processing_canonical_jsonb_v1(v),',' ORDER BY ord),'')||']' INTO result FROM jsonb_array_elements(value) WITH ORDINALITY x(v,ord);
 ELSE result:=value::text;
 END CASE;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION oracle2._processing_canonical_jsonb_v1(jsonb) FROM PUBLIC;

CREATE FUNCTION oracle2.commit_processing_model_revision_v1(
 supplied_manifest jsonb,payload_bytes bytea,refs_bytes bytea,dependency_bytes bytea,receipts jsonb,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz,idempotency uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;m jsonb;p jsonb;c jsonb;prior oracle2.processing_model_revisions_v1;
 w uuid;aid uuid;v integer;item jsonb;idx jsonb;qual jsonb;source_set jsonb;dep jsonb;legacy jsonb;previous_assertion jsonb;assertion_hash text;event uuid:=gen_random_uuid();
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'consolidate',runtime,registry,config,deadline);
 p:=convert_from(payload_bytes,'UTF8')::jsonb;c:=p->'consolidation_core';qual:=p->'assembly_qualification';
 w:=(supplied_manifest->>'workspace_id')::uuid;aid:=(supplied_manifest->>'artifact_id')::uuid;v:=(supplied_manifest->>'version')::integer;
 IF w IS DISTINCT FROM a.workspace_id OR idempotency IS NULL OR supplied_manifest->>'kind'<>'processing_qualified_model_v1'
 OR c->>'contract' IS DISTINCT FROM 'qualified-consolidation-core-v1'
 OR c->'model' IS DISTINCT FROM p->'operating_models'->0
 OR a.model_id IS DISTINCT FROM aid
 OR c->'model'->>'model_id' IS DISTINCT FROM aid::text OR c->'model'->>'version' IS DISTINCT FROM v::text
 OR p->'assembly_capture'->>'candidate_schema' IS DISTINCT FROM 'purpose-captured-consolidation-v1'
 OR qual->'schema_version' IS DISTINCT FROM '3'::jsonb
 OR qual->'admission'->>'captured_schema' IS DISTINCT FROM 'purpose-captured-consolidation-v1'
 OR qual->'admission'->>'compiler_actor' IS DISTINCT FROM a.principal_id::text
 OR (qual->'admission'->>'expires_at')::timestamptz<=clock_timestamp()
 OR jsonb_typeof(c->'assertions') IS DISTINCT FROM 'array' OR jsonb_array_length(c->'assertions') NOT BETWEEN 1 AND 2048
 OR c->>'expected_predecessor_version' IS DISTINCT FROM (v-1)::text
 OR v>1 AND jsonb_array_length(c->'correction_source_ids')=0
 THEN RAISE insufficient_privilege USING MESSAGE='fresh exact qualified consolidation core required'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-model:'||w::text||':'||aid::text,0));
 SELECT * INTO prior FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=w AND artifact_id=aid ORDER BY version DESC LIMIT 1 FOR SHARE;
 IF prior.version IS NULL THEN
  SELECT manifest INTO legacy FROM oracle2.artifact_manifests WHERE workspace_id=w AND artifact_id=aid AND kind='processing_qualified_model_v1' ORDER BY version DESC LIMIT 1 FOR SHARE;
 END IF;
 IF (prior.version IS NULL AND legacy IS NULL AND v<>1)
 OR (prior.version IS NULL AND legacy IS NOT NULL AND ((legacy->>'version')::integer<>v-1 OR legacy->>'content_hash' IS DISTINCT FROM c->>'expected_predecessor_hash'))
 OR (prior.version IS NOT NULL AND (prior.version<>v-1 OR prior.content_hash IS DISTINCT FROM c->>'expected_predecessor_hash'))
 OR EXISTS(SELECT 1 FROM oracle2.artifact_manifests WHERE workspace_id=w AND artifact_id=aid AND version>=v)
 OR (v=1 AND c->'expected_predecessor_hash'<>'null'::jsonb)
 OR EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=w AND d.artifact_id=aid AND d.version=v AND d.upstream_kind='artifact' AND d.upstream_id=aid::text)
 THEN RAISE serialization_failure USING MESSAGE='consolidation head changed'; END IF;
 FOR dep IN SELECT value FROM jsonb_array_elements((convert_from(dependency_bytes,'UTF8')::jsonb)->'dependencies') LOOP
  IF dep->>0='artifact' AND dep->>1=aid::text THEN RAISE insufficient_privilege USING MESSAGE='predecessor lineage is not supporting evidence'; END IF;
 END LOOP;
 source_set:=(convert_from(refs_bytes,'UTF8')::jsonb)->'refs';
 IF source_set IS DISTINCT FROM a.source_refs THEN RAISE insufficient_privilege; END IF;
 -- A correction must bring an actual new qualified original revision; a fresh
 -- appointment alone cannot turn the predecessor population into new evidence.
 IF v>1 AND NOT EXISTS (
  SELECT 1 FROM jsonb_array_elements(source_set) r
  WHERE c->'correction_source_ids' @> jsonb_build_array(r->'source_id')
  AND NOT EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d
   WHERE d.workspace_id=w AND d.artifact_id=aid AND d.version=v-1
   AND d.upstream_kind='source' AND d.upstream_id=r->>'source_id' AND d.upstream_revision=r->>'revision'))
 THEN RAISE insufficient_privilege USING MESSAGE='new qualified original revision required for correction'; END IF;
 idx:='[]'::jsonb;
 FOR item IN SELECT value FROM jsonb_array_elements(c->'assertions') LOOP
  IF jsonb_typeof(item) IS DISTINCT FROM 'object' OR item ?| ARRAY['confirmed','approved','recorded_at']
  OR item->>'assertion_id' IS NULL OR item->>'revision' !~ '^[1-9][0-9]*$'
  THEN RAISE insufficient_privilege; END IF;
  assertion_hash:=encode(sha256(convert_to(oracle2._processing_canonical_jsonb_v1(item),'UTF8')),'hex');
  SELECT value INTO previous_assertion FROM jsonb_array_elements(coalesce(prior.assertion_index,'[]'::jsonb)) WHERE value->'assertion_id'=item->'assertion_id';
  IF previous_assertion IS NULL THEN
   IF item->>'revision'<>'1' OR item->'predecessor_hash' IS NOT NULL AND item->'predecessor_hash'<>'null'::jsonb THEN RAISE insufficient_privilege USING MESSAGE='new assertion starts at revision one'; END IF;
  ELSIF previous_assertion->>'assertion_hash'=assertion_hash THEN
   IF previous_assertion->'revision' IS DISTINCT FROM item->'revision' THEN RAISE insufficient_privilege; END IF;
  ELSIF (item->>'revision')::integer<>(previous_assertion->>'revision')::integer+1 OR item->>'predecessor_hash' IS DISTINCT FROM previous_assertion->>'assertion_hash' THEN
   RAISE insufficient_privilege USING MESSAGE='exact immutable assertion predecessor required';
  END IF;
  idx:=idx||jsonb_build_array(jsonb_build_object('assertion_id',item->'assertion_id','revision',item->'revision','assertion_hash',assertion_hash,
   'subject_id',item->'subject_id',
    'scope',item->'scope','provenance',item->'provenance','valid_time',item->'valid_time','valid_from',item->'valid_from','valid_to',item->'valid_to'));
 END LOOP;
 IF (SELECT count(DISTINCT x->>'assertion_id') FROM jsonb_array_elements(idx) x)<>jsonb_array_length(idx) THEN RAISE insufficient_privilege; END IF;
 m:=oracle2._commit_processing_candidate_canonical_v1(supplied_manifest,payload_bytes,refs_bytes,dependency_bytes,receipts,runtime,registry,least(a.expires_at,deadline));
 INSERT INTO oracle2.processing_model_revisions_v1(workspace_id,artifact_id,version,content_hash,predecessor_version,predecessor_hash,
  core_hash,qualification_hash,assertion_index,registered_by,admission_id,idempotency)
 VALUES(w,aid,v,m->>'content_hash',v-1,c->>'expected_predecessor_hash',encode(sha256(convert_to(c::text,'UTF8')),'hex'),
  encode(sha256(convert_to(qual::text,'UTF8')),'hex'),idx,a.principal_id,appointment,idempotency);
 IF v>1 THEN
  UPDATE oracle2.processing_journey_runs_v1 SET answer_hold=true,state='revision_pending',journey_revision=journey_revision+1 WHERE workspace_id=w AND current_model_id=aid AND current_model_version<=v-1 AND cancelled_at IS NULL;
  -- Typed current staleness is separate from immutable evidence ancestry/history.
  WITH RECURSIVE affected(id,ver) AS (
   SELECT d.artifact_id,d.version FROM oracle2.artifact_dependencies d WHERE d.workspace_id=w AND d.upstream_kind='artifact' AND d.upstream_id=aid::text AND d.upstream_revision=(v-1)::text
   UNION SELECT d.artifact_id,d.version FROM oracle2.artifact_dependencies d JOIN affected x ON d.upstream_kind='artifact' AND d.upstream_id=x.id::text AND d.upstream_revision=x.ver::text WHERE d.workspace_id=w)
  INSERT INTO oracle2.processing_model_events_v1(event_id,workspace_id,artifact_id,version,kind,actor_id,admission_id,payload,idempotency)
  SELECT gen_random_uuid(),w,id,ver,'derived-stale',a.principal_id,appointment,
   jsonb_build_object('cause_model_id',aid,'cause_version',v,'previous_version',v-1),gen_random_uuid() FROM affected;
 END IF;
 a:=oracle2._processing_model_admission_v1(appointment,'consolidate',runtime,registry,config,deadline);
 RETURN jsonb_build_object('manifest',m,'recordedAt',(SELECT recorded_at FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=w AND artifact_id=aid AND version=v),'validUntil',a.expires_at);
END $$;
REVOKE ALL ON FUNCTION oracle2.commit_processing_model_revision_v1(jsonb,bytea,bytea,bytea,jsonb,uuid,text,text,text,timestamptz,uuid) FROM PUBLIC;

-- Same function identity and privileges; ONLY the exact new transaction event is
-- classified. All old untyped invalidations retain hard historical denial.
DO $catalog$ BEGIN
 IF (SELECT md5(prosrc) FROM pg_catalog.pg_proc WHERE oid=pg_catalog.to_regprocedure('oracle2.finalize_source_revision_v1(uuid,integer,jsonb)')) IS DISTINCT FROM 'cc145f5bdc87f7d84ca6210c465974ae'
 OR (SELECT proowner FROM pg_catalog.pg_proc WHERE oid=pg_catalog.to_regprocedure('oracle2.finalize_source_revision_v1(uuid,integer,jsonb)')) IS DISTINCT FROM (SELECT nspowner FROM pg_catalog.pg_namespace WHERE nspname='oracle2')
 THEN RAISE EXCEPTION 'exact retained source lifecycle function changed'; END IF;
END $catalog$;
CREATE OR REPLACE FUNCTION oracle2.finalize_source_revision_v1(reservation uuid,expected_head integer,custody jsonb)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;r oracle2.source_intake_reservations_v1%ROWTYPE;
 candidate oracle2.source_intake_reservations_v1%ROWTYPE;item record;known uuid[];actual uuid[];head integer;
 pins jsonb;deadline timestamptz;caller_deadline timestamptz;event uuid:=gen_random_uuid();snapshot jsonb;
BEGIN
 -- Selector-only prereads acquire no authority. Every target is reproved below.
 SELECT reserved.* INTO candidate FROM oracle2.source_intake_reservations_v1 reserved
 JOIN oracle2.hosting_request_principal_admissions p ON p.role_name=SESSION_USER
  AND p.workspace_id=reserved.workspace_id AND p.principal_id=reserved.principal_id WHERE reserved.reservation_id=reservation;
 IF candidate.reservation_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='replacement reservation unavailable'; END IF;
 SELECT coalesce(array_agg(DISTINCT x.artifact_id ORDER BY x.artifact_id),'{}'::uuid[]) INTO known
 FROM oracle2._replacement_affected(candidate.workspace_id,candidate.source_id) x;
 FOREACH event IN ARRAY known LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('operating-model:'||candidate.workspace_id::text||':'||event::text,0));
 END LOOP;
 event:=gen_random_uuid();
 a:=oracle2._replacement_request_context();
 SELECT * INTO r FROM oracle2.source_intake_reservations_v1 WHERE reservation_id=reservation FOR UPDATE;
 IF r.reservation_id IS NULL OR r.workspace_id IS DISTINCT FROM a.workspace_id OR r.principal_id IS DISTINCT FROM a.principal_id
 OR r.source_id IS DISTINCT FROM candidate.source_id OR r.workspace_id IS DISTINCT FROM candidate.workspace_id
 OR expected_head IS DISTINCT FROM r.expected_head OR r.expires_at<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='current replacement reservation denied';
 END IF;
 IF jsonb_typeof(custody) IS DISTINCT FROM 'object' OR NOT custody ?& ARRAY['original_sha256','byte_count','custody_seal_sha256','expected_context','caller_deadline']
 OR custody-ARRAY['original_sha256','byte_count','custody_seal_sha256','expected_context','caller_deadline']<>'{}'::jsonb
 OR jsonb_typeof(custody->'original_sha256') IS DISTINCT FROM 'string' OR custody->>'original_sha256' !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(custody->'custody_seal_sha256') IS DISTINCT FROM 'string' OR custody->>'custody_seal_sha256' !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(custody->'byte_count') IS DISTINCT FROM 'number' OR custody->'byte_count'<>to_jsonb(r.byte_count)
 OR jsonb_typeof(custody->'caller_deadline') IS DISTINCT FROM 'string'
 OR custody->>'caller_deadline' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
  RAISE invalid_parameter_value USING MESSAGE='strict replacement custody required';
 END IF;
 caller_deadline:=(custody->>'caller_deadline')::timestamptz;
 IF NOT isfinite(caller_deadline) OR caller_deadline<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='replacement caller deadline expired';
 END IF;
 pins:=jsonb_build_object('principal_id',a.principal_id,'workspace_id',a.workspace_id,'session_role',SESSION_USER,
  'runtime_hash',a.runtime_hash,'source_registry_hash',a.registry_hash);
 IF custody->'expected_context' IS DISTINCT FROM pins THEN
  RAISE insufficient_privilege USING MESSAGE='replacement startup identity changed';
 END IF;
 deadline:=least(a.expires_at,r.expires_at,caller_deadline,oracle2._replacement_scope(a.workspace_id,a.principal_id,'intake'));
 IF r.expected_head>0 THEN
  deadline:=least(deadline,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||r.source_id::text));
 END IF;
 SELECT revision INTO head FROM oracle2.sources WHERE workspace_id=a.workspace_id AND source_id=r.source_id FOR UPDATE;
 IF (r.finalized_at IS NULL AND coalesce(head,0)<>r.expected_head)
 OR (r.finalized_at IS NOT NULL AND head IS DISTINCT FROM r.revision) THEN
  RAISE serialization_failure USING MESSAGE='replacement revision conflict';
 END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-lineage:'||a.workspace_id::text,0));
 LOCK TABLE oracle2.artifact_manifests,oracle2.artifact_dependencies,oracle2.artifact_invalidations IN SHARE ROW EXCLUSIVE MODE;
 SELECT coalesce(array_agg(DISTINCT x.artifact_id ORDER BY x.artifact_id),'{}'::uuid[]) INTO actual
 FROM oracle2._replacement_affected(a.workspace_id,r.source_id) x;
 IF NOT actual<@known THEN RAISE serialization_failure USING MESSAGE='replacement dependency set changed'; END IF;
 IF deadline<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='replacement intake expired before mutation'; END IF;
 IF r.finalized_at IS NOT NULL THEN
  IF r.original_sha256 IS DISTINCT FROM custody->>'original_sha256' OR r.custody_seal_sha256 IS DISTINCT FROM custody->>'custody_seal_sha256' THEN
   RAISE unique_violation USING MESSAGE='replacement idempotency conflict';
  END IF;
 ELSE
  IF r.expected_head=0 THEN
   INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status,revision)
    VALUES(r.source_id,a.workspace_id,a.principal_id,r.filename,r.media_type,'processing',r.revision);
  ELSE
   UPDATE oracle2.sources SET revision=r.revision,filename=r.filename,content_type=r.media_type,status='processing',error=NULL
    WHERE source_id=r.source_id AND workspace_id=a.workspace_id AND revision=r.expected_head;
   IF NOT FOUND THEN RAISE serialization_failure USING MESSAGE='replacement revision conflict'; END IF;
   INSERT INTO oracle2.artifact_invalidations(workspace_id,artifact_id,version,reason,event_id)
    SELECT a.workspace_id,x.artifact_id,x.version,'source revision replaced',event
    FROM oracle2._replacement_affected(a.workspace_id,r.source_id) x ON CONFLICT DO NOTHING;
   INSERT INTO oracle2.processing_preserved_supersessions_v1(workspace_id,artifact_id,version,event_id,source_id,old_revision,new_revision)
    SELECT i.workspace_id,i.artifact_id,i.version,i.event_id,r.source_id,r.expected_head,r.revision
    FROM oracle2.artifact_invalidations i WHERE i.workspace_id=a.workspace_id AND i.event_id=event;

  END IF;
  INSERT INTO oracle2.source_original_revisions(workspace_id,source_id,revision,original_sha256,byte_count,media_type,filename,
   custody_locator_seal_sha256,private_object_key,uploaded_by)
   VALUES(a.workspace_id,r.source_id,r.revision,custody->>'original_sha256',r.byte_count,r.media_type,r.filename,
    custody->>'custody_seal_sha256',r.private_object_key,a.principal_id);
  UPDATE oracle2.source_intake_reservations_v1 SET original_sha256=custody->>'original_sha256',
   custody_seal_sha256=custody->>'custody_seal_sha256',finalized_at=clock_timestamp() WHERE reservation_id=reservation;
 END IF;
 -- No SourceRef exists until an independently authorized reading is qualified.
 snapshot:=jsonb_build_object('sourceId',r.source_id,'revision',r.revision,'originalSha256',custody->>'original_sha256',
  'byteCount',r.byte_count,'mediaType',r.media_type,'filename',r.filename,'state','awaiting_original_reading','qualifiedSourceRef',NULL);
 a:=oracle2._replacement_request_context();
 deadline:=least(deadline,a.expires_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'intake'));
 IF r.expected_head>0 THEN deadline:=least(deadline,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||r.source_id::text)); END IF;
 IF pins IS DISTINCT FROM jsonb_build_object('principal_id',a.principal_id,'workspace_id',a.workspace_id,'session_role',SESSION_USER,
  'runtime_hash',a.runtime_hash,'source_registry_hash',a.registry_hash) OR deadline<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='replacement intake authority changed before commit';
 END IF;
 RETURN jsonb_build_object('schema_version',1,'context',oracle2._replacement_private_context(a,deadline),'snapshot',snapshot);
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_datetime_format OR datetime_field_overflow THEN
 RAISE invalid_parameter_value USING MESSAGE='strict replacement custody required';
END $body$;

CREATE FUNCTION oracle2._processing_history_metadata_v1(a oracle2.processing_model_admissions_v1,model uuid,ver integer)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE m jsonb;r oracle2.processing_model_revisions_v1;ref jsonb;node record;source_set jsonb;expiry timestamptz;
BEGIN
 SELECT * INTO r FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=ver FOR SHARE;
 SELECT manifest INTO m FROM oracle2.artifact_manifests WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=ver AND state='ready' FOR SHARE;
 IF r.artifact_id IS NULL OR m IS NULL OR r.content_hash IS DISTINCT FROM m->>'content_hash' THEN RAISE insufficient_privilege; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-lineage:'||a.workspace_id::text,0));
 LOCK TABLE oracle2.artifact_manifests,oracle2.artifact_dependencies,oracle2.artifact_invalidations IN SHARE MODE;
 SELECT jsonb_agg(receipt->'ref' ORDER BY source_id) INTO source_set FROM oracle2.operating_model_source_receipts s
 WHERE s.workspace_id=a.workspace_id AND EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=s.workspace_id AND d.artifact_id=model AND d.version=ver AND d.upstream_kind='source' AND d.upstream_id=s.source_id::text AND d.upstream_revision=s.revision::text);
 IF source_set IS NULL OR (SELECT count(*) FROM jsonb_array_elements(source_set))<>(SELECT count(*) FROM oracle2.artifact_dependencies WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=ver AND upstream_kind='source')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(source_set) x WHERE NOT a.source_refs @> jsonb_build_array(x))
 THEN RAISE insufficient_privilege USING MESSAGE='complete explicitly appointed history source set required'; END IF;
 expiry:=a.expires_at;
 FOR ref IN SELECT value FROM jsonb_array_elements(source_set) LOOP
  expiry:=least(expiry,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||(ref->>'source_id')),
   oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-history:'||(ref->>'source_id')||':'||(ref->>'revision')));
  IF NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.status IN('processing','draft','confirmed'))
  OR EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE w.workspace_id=a.workspace_id AND w.source_id=(ref->>'source_id')::uuid)
  OR NOT EXISTS(SELECT 1 FROM oracle2.source_original_revisions o JOIN oracle2.source_reading_qualifications q USING(workspace_id,source_id,revision)
   WHERE o.workspace_id=a.workspace_id AND o.source_id=(ref->>'source_id')::uuid AND o.revision=(ref->>'revision')::integer
   AND (o.original_sha256,q.reading_sha256,q.parser_id)=(ref->>'original_sha256',ref->>'reading_sha256',ref->>'parser_id'))
  THEN RAISE insufficient_privilege USING MESSAGE='currently retained qualified history source required'; END IF;
 END LOOP;
 FOR node IN WITH RECURSIVE parents(id,v) AS (
  SELECT model,ver UNION SELECT d.upstream_id::uuid,d.upstream_revision::integer FROM oracle2.artifact_dependencies d JOIN parents p ON d.artifact_id=p.id AND d.version=p.v WHERE d.workspace_id=a.workspace_id AND d.upstream_kind='artifact') SELECT * FROM parents LOOP
  IF EXISTS(WITH RECURSIVE reach(id,v) AS (SELECT d.upstream_id::uuid,d.upstream_revision::integer FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=node.id AND d.version=node.v AND d.upstream_kind='artifact' UNION SELECT d.upstream_id::uuid,d.upstream_revision::integer FROM oracle2.artifact_dependencies d JOIN reach x ON d.artifact_id=x.id AND d.version=x.v WHERE d.workspace_id=a.workspace_id AND d.upstream_kind='artifact') SELECT 1 FROM reach WHERE id=node.id AND v=node.v) OR EXISTS(SELECT 1 FROM oracle2.artifact_invalidations i WHERE i.workspace_id=a.workspace_id AND i.artifact_id=node.id AND i.version=node.v
   AND NOT EXISTS(SELECT 1 FROM oracle2.processing_preserved_supersessions_v1 s WHERE (s.workspace_id,s.artifact_id,s.version,s.event_id)=(i.workspace_id,i.artifact_id,i.version,i.event_id)))
  OR NOT EXISTS(SELECT 1 FROM oracle2.artifact_manifests x WHERE x.workspace_id=a.workspace_id AND x.artifact_id=node.id AND x.version=node.v AND x.state='ready' AND x.dependency_digest=oracle2._processing_dependency_digest(a.workspace_id,node.id,node.v))
  THEN RAISE insufficient_privilege USING MESSAGE='untyped/security/withdrawn lineage unavailable historically'; END IF;
 END LOOP;
 IF expiry<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN jsonb_build_object('manifest',m,'sourceRefs',source_set,'recordedAt',r.recorded_at,
  'businessDecisions',coalesce((SELECT jsonb_agg(item ORDER BY recorded_at,event_id) FROM (
   SELECT e.recorded_at,e.event_id,jsonb_build_object('eventId',e.event_id,'recordedAt',e.recorded_at,'decisionKind',e.payload->'decision_kind',
    'scopeSha256',e.payload->'scope_hash','assertions',e.payload->'assertions',
    'challenged',EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 change WHERE change.workspace_id=a.workspace_id AND change.artifact_id=model AND change.kind='business-challenge' AND change.payload->>'target_event_id'=e.event_id::text),
    'withdrawn',EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 change WHERE change.workspace_id=a.workspace_id AND change.artifact_id=model AND change.kind='business-withdraw' AND change.payload->>'target_event_id'=e.event_id::text),
    'policyInForce',e.payload->>'decision_kind'='company-policy' AND e.payload->>'policy_longevity'='remain-in-force-until-withdrawn'
     AND r.version=(SELECT max(version) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model)
     AND NOT EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 withdrawal WHERE withdrawal.workspace_id=a.workspace_id AND withdrawal.artifact_id=model AND withdrawal.kind='business-withdraw' AND withdrawal.payload->>'target_event_id'=e.event_id::text)) item
   FROM oracle2.processing_model_events_v1 e WHERE e.workspace_id=a.workspace_id AND e.artifact_id=model AND e.version=ver AND e.kind='business-accept'
   ORDER BY e.recorded_at DESC,e.event_id DESC LIMIT 64) decisions),'[]'::jsonb),
  'assertionIndex',r.assertion_index,'validUntil',expiry,'mode','historical','policyAccepted',false);
END $$;
REVOKE ALL ON FUNCTION oracle2._processing_history_metadata_v1(oracle2.processing_model_admissions_v1,uuid,integer) FROM PUBLIC;

CREATE FUNCTION oracle2.hosting_historical_consolidated_model_v1(model uuid,valid_at timestamptz,known_at timestamptz,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;v integer;result jsonb;
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 IF model IS DISTINCT FROM a.model_id THEN RAISE insufficient_privilege; END IF;
 IF valid_at IS NULL OR known_at IS NULL OR NOT isfinite(valid_at) OR NOT isfinite(known_at) OR known_at>clock_timestamp() THEN RAISE invalid_parameter_value; END IF;
 SELECT version INTO v FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model AND recorded_at<=known_at ORDER BY version DESC LIMIT 1;
 IF v IS NULL THEN RAISE no_data_found USING MESSAGE='no registered committed knowledge at requested time'; END IF;
 result:=oracle2._processing_history_metadata_v1(a,model,v);
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 RETURN result||jsonb_build_object('validAt',valid_at,'knownAt',known_at,'validUntil',least((result->>'validUntil')::timestamptz,a.expires_at));
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_historical_consolidated_model_v1(uuid,timestamptz,timestamptz,uuid,text,text,text,timestamptz) FROM PUBLIC;

-- Explicit retained version, never a fabricated business-valid or known time.
CREATE FUNCTION oracle2.hosting_consolidated_model_version_v1(model uuid,ver integer,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;result jsonb;
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 IF model IS DISTINCT FROM a.model_id OR ver IS NULL OR ver<=0 THEN RAISE insufficient_privilege; END IF;
 result:=oracle2._processing_history_metadata_v1(a,model,ver);
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 RETURN result||jsonb_build_object('mode','retained-version','validUntil',least((result->>'validUntil')::timestamptz,a.expires_at));
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_consolidated_model_version_v1(uuid,integer,uuid,text,text,text,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.hosting_current_consolidated_model_v1(model uuid,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;v integer;result jsonb;ref jsonb;
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 IF model IS DISTINCT FROM a.model_id THEN RAISE insufficient_privilege; END IF;
 SELECT max(version) INTO v FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model;
 IF v IS NULL THEN RAISE no_data_found; END IF;
 result:=oracle2._processing_history_metadata_v1(a,model,v);
 FOR ref IN SELECT value FROM jsonb_array_elements(result->'sourceRefs') LOOP
  IF NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.revision=(ref->>'revision')::integer AND s.status IN('draft','confirmed')) THEN RAISE insufficient_privilege; END IF;
 END LOOP;
 IF EXISTS(SELECT 1 FROM oracle2.artifact_invalidations WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=v)
 OR NOT EXISTS(SELECT 1 FROM oracle2.outbox e JOIN oracle2.operating_projection_receipts r USING(event_id)
  WHERE e.workspace_id=a.workspace_id AND e.assertion_id=model AND e.revision=v AND e.delivered_at IS NOT NULL
  AND r.payload->>'content_hash'=result->'manifest'->>'content_hash'
  AND r.payload->>'projection_schema'='qualified-evidence-projection-v1')
 THEN RAISE insufficient_privilege USING MESSAGE='current exact activated projection required'; END IF;
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 RETURN result||jsonb_build_object('mode','current','validUntil',least(a.expires_at,(result->>'validUntil')::timestamptz));
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_current_consolidated_model_v1(uuid,uuid,text,text,text,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.record_processing_model_review_v1(model uuid,ver integer,expected_hash text,decision text,
 scope_bytes bytea,assertions jsonb,bundle_hash text,idempotency uuid,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;r oracle2.processing_model_revisions_v1;scope jsonb;ref jsonb;item jsonb;until_at timestamptz;event uuid:=gen_random_uuid();
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'business-review',runtime,registry,config,deadline);
 IF model IS DISTINCT FROM a.model_id THEN RAISE insufficient_privilege; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-model:'||a.workspace_id::text||':'||model::text,0));
 IF model IS DISTINCT FROM a.model_id THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO r FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model ORDER BY version DESC LIMIT 1 FOR SHARE;
 IF r.version IS DISTINCT FROM ver OR r.content_hash IS DISTINCT FROM expected_hash THEN RAISE serialization_failure USING MESSAGE='coherent review head changed'; END IF;
 scope:=convert_from(scope_bytes,'UTF8')::jsonb;
 IF a.scope_hash IS DISTINCT FROM encode(sha256(scope_bytes),'hex') OR decision NOT IN('accept','reject')
 OR jsonb_typeof(assertions) IS DISTINCT FROM 'array' OR jsonb_array_length(assertions) NOT BETWEEN 1 AND 2048
 OR (SELECT count(DISTINCT x::text) FROM jsonb_array_elements(assertions) x)<>jsonb_array_length(assertions)
 OR bundle_hash !~ '^[0-9a-f]{64}$' OR idempotency IS NULL THEN RAISE insufficient_privilege; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(assertions) LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(r.assertion_index) x WHERE
   jsonb_build_object('assertion_id',x->'assertion_id','revision',x->'revision')=item AND x->'scope'=scope
   AND CASE a.decision_kind WHEN 'employee-account' THEN x->>'provenance'='employee_account'
     WHEN 'process-policy' THEN x->>'provenance'='documented_process'
     WHEN 'company-policy' THEN x->>'provenance'='reported_policy' ELSE false END)
  THEN RAISE insufficient_privilege USING MESSAGE='exact scoped business decision selection required'; END IF;
 END LOOP;
 until_at:=a.expires_at;
 FOR ref IN SELECT receipt->'ref' FROM oracle2.operating_model_source_receipts s WHERE s.workspace_id=a.workspace_id
  AND EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=model AND d.version=ver AND d.upstream_kind='source' AND d.upstream_id=s.source_id::text AND d.upstream_revision=s.revision::text) LOOP
  IF NOT a.source_refs @> jsonb_build_array(ref) OR NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.revision=(ref->>'revision')::integer AND s.status IN('draft','confirmed'))
  THEN RAISE insufficient_privilege; END IF;
  until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||(ref->>'source_id')));
 END LOOP;
 IF EXISTS(SELECT 1 FROM oracle2.artifact_invalidations WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=ver)
 OR EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=ver AND kind='derived-stale')
 OR until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 INSERT INTO oracle2.processing_model_events_v1(event_id,workspace_id,artifact_id,version,kind,actor_id,admission_id,payload,idempotency)
 VALUES(event,a.workspace_id,model,ver,'business-'||decision,a.principal_id,appointment,
  jsonb_build_object('model_content_hash',expected_hash,'decision_kind',a.decision_kind,'scope_hash',a.scope_hash,
   'assertions',assertions,'bundle_hash',bundle_hash,'membership_appointment',a.membership_appointment,'decision_valid_until',a.decision_valid_until,'policy_longevity',CASE WHEN a.decision_kind='company-policy' THEN 'remain-in-force-until-withdrawn' ELSE 'not-company-policy' END),idempotency);
 a:=oracle2._processing_model_admission_v1(appointment,'business-review',runtime,registry,config,deadline);
 RETURN jsonb_build_object('eventId',event,'modelId',model,'version',ver,'decision',decision,'validUntil',least(a.expires_at,until_at));
END $$;
REVOKE ALL ON FUNCTION oracle2.record_processing_model_review_v1(uuid,integer,text,text,bytea,jsonb,text,uuid,uuid,text,text,text,timestamptz) FROM PUBLIC;

-- Current-only typed stale enforcement in existing canonical owner.
CREATE OR REPLACE FUNCTION oracle2._processing_immutable_artifact_metadata_v1(
 workspace uuid,artifact uuid,ver integer,refs jsonb)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE m jsonb;a record;cycle boolean;
BEGIN
 IF EXISTS(SELECT 1 FROM oracle2.processing_model_revisions_v1 r WHERE r.workspace_id=workspace AND r.artifact_id=artifact AND r.version=ver) AND ver<>(SELECT max(r.version) FROM oracle2.processing_model_revisions_v1 r WHERE r.workspace_id=workspace AND r.artifact_id=artifact) THEN RAISE insufficient_privilege USING MESSAGE='superseded qualified model requires separate history authority'; END IF;
 IF EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 WHERE workspace_id=workspace AND artifact_id=artifact AND version=ver AND kind='derived-stale') THEN RAISE insufficient_privilege USING MESSAGE='derived processing artifact stale'; END IF;
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
  OR a.kind NOT IN ('processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1','processing_recommendation_v1','processing_failed_assembly_v1')
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

CREATE FUNCTION oracle2.hosting_processing_review_diff_v1(model uuid,expected_version integer,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;r oracle2.processing_model_revisions_v1;ref jsonb;until_at timestamptz;
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'business-review',runtime,registry,config,deadline);
 IF model IS DISTINCT FROM a.model_id THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO r FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model ORDER BY version DESC LIMIT 1 FOR SHARE;
 IF r.artifact_id IS NULL THEN RAISE no_data_found; END IF;
 until_at:=a.expires_at;
 FOR ref IN SELECT receipt->'ref' FROM oracle2.operating_model_source_receipts s WHERE s.workspace_id=a.workspace_id AND EXISTS(
  SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=model AND d.version=r.version AND d.upstream_kind='source' AND d.upstream_id=s.source_id::text AND d.upstream_revision=s.revision::text) LOOP
  IF NOT a.source_refs @> jsonb_build_array(ref) OR NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.revision=(ref->>'revision')::integer AND s.status IN('draft','confirmed')) THEN RAISE insufficient_privilege; END IF;
  until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||(ref->>'source_id')));
 END LOOP;
 IF EXISTS(SELECT 1 FROM oracle2.artifact_invalidations WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=r.version) OR until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN jsonb_build_object('modelId',model,'currentVersion',r.version,'currentContentHash',r.content_hash,'recordedAt',r.recorded_at,
  'decisionKind',a.decision_kind,'scopeSha256',a.scope_hash,'conflict',r.version<>expected_version,'basePermitted',r.version=expected_version,
  'message',CASE WHEN r.version=expected_version THEN 'Current exact version.' ELSE 'Base history requires separate permission; reload current review.' END,'validUntil',until_at);
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_review_diff_v1(uuid,integer,uuid,text,text,text,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.hosting_processing_model_revision_v1(model uuid,ver integer,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;r oracle2.processing_model_revisions_v1;q record;
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'consolidate',runtime,registry,config,deadline);
 IF model IS DISTINCT FROM a.model_id THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO r FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model AND version=ver;
 IF r.artifact_id IS NULL OR r.version<>(SELECT max(version) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=model) THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO q FROM oracle2._processing_artifact_metadata(a.workspace_id,model,ver,a.principal_id,runtime,registry);
 a:=oracle2._processing_model_admission_v1(appointment,'consolidate',runtime,registry,config,deadline);
 RETURN jsonb_build_object('manifest',q.manifest,'recordedAt',r.recorded_at,'validUntil',least(a.expires_at,deadline));
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_model_revision_v1(uuid,integer,uuid,text,text,text,timestamptz) FROM PUBLIC;

-- Canonical recommendation kind; no competing generic writer.
CREATE FUNCTION oracle2._commit_processing_candidate_canonical_v1(
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
 OR m->'schema_version'<>'1'::jsonb OR jsonb_typeof(m->'kind') IS DISTINCT FROM 'string' OR jsonb_typeof(m->'version') IS DISTINCT FROM 'number' OR m->>'version' !~ '^[1-9][0-9]*$' OR m->>'kind' NOT IN ('processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1','processing_recommendation_v1','processing_failed_assembly_v1')
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
 IF m->>'kind' IN('processing_summary_v1','processing_recommendation_v1') AND ((SELECT count(*) FROM jsonb_array_elements(deps) d WHERE d->>0='artifact')<>1
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
REVOKE ALL ON FUNCTION oracle2._commit_processing_candidate_canonical_v1(jsonb,bytea,bytea,bytea,jsonb,text,text,timestamptz) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;
CREATE OR REPLACE FUNCTION oracle2.commit_processing_candidate(
 supplied_manifest jsonb,payload_bytes bytea,refs_bytes bytea,dependency_bytes bytea,
 supplied_receipts jsonb,expected_runtime text,expected_registry text,caller_deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
BEGIN
 IF convert_from(payload_bytes,'UTF8')::jsonb ? 'consolidation_core' THEN
  RAISE insufficient_privilege USING MESSAGE='temporal core requires canonical revision CAS';
 END IF;
 IF supplied_manifest->>'kind'='processing_qualified_model_v1' THEN
  PERFORM pg_advisory_xact_lock(hashtextextended('operating-model:'||(supplied_manifest->>'workspace_id')::uuid::text||':'||(supplied_manifest->>'artifact_id')::uuid::text,0));
  IF EXISTS(SELECT 1 FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=(supplied_manifest->>'workspace_id')::uuid AND artifact_id=(supplied_manifest->>'artifact_id')::uuid) THEN
   RAISE insufficient_privilege USING MESSAGE='registered temporal model requires canonical revision CAS';
  END IF;
 END IF;
 RETURN oracle2._commit_processing_candidate_canonical_v1(supplied_manifest,payload_bytes,refs_bytes,dependency_bytes,supplied_receipts,expected_runtime,expected_registry,caller_deadline);
END $$;


-- Canonical recommendation kind; no competing generic writer.
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
 IF NOT FOUND OR m->>'kind' NOT IN ('processing_extraction_v1','processing_failed_extraction_v1','processing_qualified_model_v1','processing_summary_v1','processing_recommendation_v1','processing_failed_assembly_v1') THEN RAISE insufficient_privilege USING MESSAGE='processing artifact absent'; END IF;
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

CREATE FUNCTION oracle2.hosting_historical_source_revision_v1(source_ref jsonb,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;o oracle2.source_original_revisions;q oracle2.source_reading_qualifications;r jsonb;until_at timestamptz;
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 IF NOT a.source_refs @> jsonb_build_array(source_ref) OR source_ref->>'workspace_id' IS DISTINCT FROM a.workspace_id::text THEN RAISE insufficient_privilege; END IF;
 until_at:=least(a.expires_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||(source_ref->>'source_id')),
   oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-history:'||(source_ref->>'source_id')||':'||(source_ref->>'revision')));
 SELECT * INTO o FROM oracle2.source_original_revisions WHERE workspace_id=a.workspace_id AND source_id=(source_ref->>'source_id')::uuid AND revision=(source_ref->>'revision')::integer FOR SHARE;
 SELECT * INTO q FROM oracle2.source_reading_qualifications WHERE workspace_id=o.workspace_id AND source_id=o.source_id AND revision=o.revision FOR SHARE;
 SELECT receipt INTO r FROM oracle2.operating_model_source_receipts WHERE workspace_id=o.workspace_id AND source_id=o.source_id AND revision=o.revision;
 IF o.source_id IS NULL OR q.source_id IS NULL OR r->'ref' IS DISTINCT FROM source_ref
 OR (o.original_sha256,q.reading_sha256,q.parser_id) IS DISTINCT FROM(source_ref->>'original_sha256',source_ref->>'reading_sha256',source_ref->>'parser_id')
 OR NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=o.workspace_id AND s.source_id=o.source_id AND s.status IN('processing','draft','confirmed'))
 OR EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE w.workspace_id=o.workspace_id AND w.source_id=o.source_id)
 OR until_at<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='exact retained current history citation permission required'; END IF;
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 RETURN jsonb_build_object('sourceRef',source_ref,'originalSha256',o.original_sha256,'byteCount',o.byte_count,
  'mediaType',o.media_type,'privateObjectKey',o.private_object_key,'custodySealSha256',o.custody_locator_seal_sha256,
  'viewManifestSha256',q.view_manifest_sha256,'locatorMapSha256',q.locator_map_sha256,
  'validUntil',least(until_at,a.expires_at),'historical',true);
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_historical_source_revision_v1(jsonb,uuid,text,text,text,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.record_processing_model_decision_change_v1(target_event uuid,action_name text,idempotency uuid,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;e oracle2.processing_model_events_v1;ref jsonb;until_at timestamptz;event uuid:=gen_random_uuid();
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'business-review',runtime,registry,config,deadline);
 SELECT * INTO e FROM oracle2.processing_model_events_v1 WHERE event_id=target_event AND workspace_id=a.workspace_id AND kind='business-accept' FOR SHARE;
 IF e.artifact_id IS DISTINCT FROM a.model_id THEN RAISE insufficient_privilege; END IF;
 IF e.event_id IS NULL OR action_name NOT IN('challenge','withdraw') OR idempotency IS NULL
 OR e.payload->>'scope_hash' IS DISTINCT FROM a.scope_hash OR e.payload->>'decision_kind' IS DISTINCT FROM a.decision_kind THEN RAISE insufficient_privilege; END IF;
 until_at:=a.expires_at;
 FOR ref IN SELECT receipt->'ref' FROM oracle2.operating_model_source_receipts s WHERE s.workspace_id=a.workspace_id AND EXISTS(
  SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=e.artifact_id AND d.version=e.version AND d.upstream_kind='source' AND d.upstream_id=s.source_id::text AND d.upstream_revision=s.revision::text) LOOP
  IF NOT a.source_refs @> jsonb_build_array(ref) THEN RAISE insufficient_privilege; END IF;
  until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||(ref->>'source_id')));
  IF NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.status IN('processing','draft','confirmed')) THEN RAISE insufficient_privilege; END IF;
  IF NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.revision=(ref->>'revision')::integer) THEN
   until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-history:'||(ref->>'source_id')||':'||(ref->>'revision')));
  END IF;
 END LOOP;
 IF until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 INSERT INTO oracle2.processing_model_events_v1(event_id,workspace_id,artifact_id,version,kind,actor_id,admission_id,payload,idempotency)
 VALUES(event,a.workspace_id,e.artifact_id,e.version,'business-'||action_name,a.principal_id,appointment,
  jsonb_build_object('target_event_id',target_event,'scope_hash',a.scope_hash,'decision_kind',a.decision_kind,'model_content_hash',e.payload->'model_content_hash','membership_appointment',a.membership_appointment),idempotency);
 a:=oracle2._processing_model_admission_v1(appointment,'business-review',runtime,registry,config,deadline);
 RETURN jsonb_build_object('eventId',event,'targetEventId',target_event,'action',action_name,'validUntil',least(until_at,a.expires_at));
END $$;
REVOKE ALL ON FUNCTION oracle2.record_processing_model_decision_change_v1(uuid,text,uuid,uuid,text,text,text,timestamptz) FROM PUBLIC;

-- Qualified documentary recommendation body only; no report/legacy bypass.
CREATE OR REPLACE FUNCTION oracle2.hosting_processing_artifact(
 workspace uuid,artifact uuid,ver integer,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(manifest jsonb,source_refs jsonb)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q record;
BEGIN
 SELECT * INTO STRICT q FROM oracle2._processing_artifact_metadata(workspace,artifact,ver,principal,expected_runtime,expected_registry);
 IF pg_has_role(SESSION_USER,'oracle2_documentary_executor','MEMBER')
 AND q.manifest->>'kind' NOT IN ('processing_qualified_model_v1','processing_summary_v1','processing_recommendation_v1') THEN
  RAISE insufficient_privilege USING MESSAGE='executor candidate body capability denied';
 END IF;
 RETURN QUERY SELECT q.manifest,q.source_refs;
END $$;

CREATE FUNCTION oracle2.hosting_processing_decision_event_v1(event uuid,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;e oracle2.processing_model_events_v1;ref jsonb;until_at timestamptz;
BEGIN
 a:=oracle2._processing_model_admission_v1(appointment,'business-review',runtime,registry,config,deadline);
 SELECT * INTO e FROM oracle2.processing_model_events_v1 WHERE event_id=event AND workspace_id=a.workspace_id AND artifact_id=a.model_id AND kind IN('business-accept','business-reject','business-challenge','business-withdraw');
 IF e.event_id IS NULL OR e.payload->>'scope_hash' IS DISTINCT FROM a.scope_hash OR e.payload->>'decision_kind' IS DISTINCT FROM a.decision_kind THEN RAISE insufficient_privilege; END IF;
 until_at:=a.expires_at;
 FOR ref IN SELECT receipt->'ref' FROM oracle2.operating_model_source_receipts s WHERE s.workspace_id=a.workspace_id AND EXISTS(
  SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=e.artifact_id AND d.version=e.version AND d.upstream_kind='source' AND d.upstream_id=s.source_id::text AND d.upstream_revision=s.revision::text) LOOP
  IF NOT a.source_refs @> jsonb_build_array(ref) OR NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.status IN('processing','draft','confirmed')) THEN RAISE insufficient_privilege; END IF;
  until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||(ref->>'source_id')));
  IF NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.revision=(ref->>'revision')::integer) THEN
   until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-history:'||(ref->>'source_id')||':'||(ref->>'revision')));
  END IF;
 END LOOP;
 IF until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 a:=oracle2._processing_model_admission_v1(appointment,'business-review',runtime,registry,config,deadline);
 RETURN jsonb_build_object('eventId',e.event_id,'modelId',e.artifact_id,'version',e.version,'kind',e.kind,'recordedAt',e.recorded_at,'validUntil',least(until_at,a.expires_at),'policyAccepted',false);
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_processing_decision_event_v1(uuid,uuid,text,text,text,timestamptz) FROM PUBLIC;
