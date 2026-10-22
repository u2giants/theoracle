-- Dedicated Oracle SOURCE capability. No runtime LOGIN, appointment or actual
-- target grant is installed here. No provider, policy approval or ERP effect.
DO $owner$ BEGIN
 IF (SELECT nspowner FROM pg_namespace WHERE nspname='oracle2') IS DISTINCT FROM
 (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR (SELECT proowner FROM pg_proc WHERE oid=to_regprocedure('oracle2._processing_immutable_artifact_metadata_v1(uuid,uuid,integer,jsonb)'))
 IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 THEN RAISE EXCEPTION 'exact canonical processing owner required'; END IF;
END $owner$;

CREATE TABLE oracle2.recommendation_action_admissions_v1 (
 admission_id uuid PRIMARY KEY,role_name name NOT NULL,principal_id uuid NOT NULL,workspace_id uuid NOT NULL,model_id uuid NOT NULL,
 operation text NOT NULL CHECK(operation IN('register','read','feedback','measurement')),
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),registry_hash text NOT NULL CHECK(registry_hash ~ '^[0-9a-f]{64}$'),
 config_hash text NOT NULL CHECK(config_hash ~ '^[0-9a-f]{64}$'),membership_appointment uuid NOT NULL REFERENCES oracle2.appointments,
 source_refs jsonb NOT NULL CHECK(jsonb_typeof(source_refs)='array' AND jsonb_array_length(source_refs) BETWEEN 1 AND 64),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL,issued_at timestamptz NOT NULL,expires_at timestamptz NOT NULL,
 original_horizon timestamptz NOT NULL,
 CHECK(isfinite(expires_at) AND isfinite(original_horizon) AND issued_at<expires_at AND expires_at<=original_horizon),
 CHECK(issuer_actor<>reviewer_actor AND principal_id NOT IN(issuer_actor,reviewer_actor)));
CREATE TABLE oracle2.recommendation_action_revocations_v1 (
 admission_id uuid PRIMARY KEY REFERENCES oracle2.recommendation_action_admissions_v1,
 revoked_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE oracle2.recommendation_registrations_v1 (
 workspace_id uuid NOT NULL,artifact_id uuid NOT NULL,version integer NOT NULL,content_hash text NOT NULL,
 parent_model uuid NOT NULL,parent_version integer NOT NULL,parent_hash text NOT NULL,source_refs jsonb NOT NULL,
 recommendation_index jsonb NOT NULL,registered_by uuid NOT NULL,admission_id uuid NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),original_operation_valid_until timestamptz NOT NULL CHECK(isfinite(original_operation_valid_until)),
 PRIMARY KEY(workspace_id,artifact_id,version),FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests,
 FOREIGN KEY(workspace_id,parent_model,parent_version) REFERENCES oracle2.processing_model_revisions_v1);
CREATE TABLE oracle2.recommendation_action_events_v1 (
 event_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,principal_id uuid NOT NULL,
 artifact_id uuid NOT NULL,version integer NOT NULL,recommendation_id uuid NOT NULL,sequence integer NOT NULL CHECK(sequence BETWEEN 1 AND 128),
 kind text NOT NULL CHECK(kind IN('feedback','baseline','followup')),
 command_id uuid NOT NULL,command_sha256 text NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{64}$'),
 command_bytes bytea NOT NULL CHECK(octet_length(command_bytes) BETWEEN 1 AND 16384),
 admission_id uuid NOT NULL,payload jsonb NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 original_operation_valid_until timestamptz NOT NULL CHECK(isfinite(original_operation_valid_until)),
 UNIQUE(workspace_id,principal_id,command_id),UNIQUE(workspace_id,principal_id,artifact_id,version,recommendation_id,sequence),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.recommendation_registrations_v1);
CREATE UNIQUE INDEX recommendation_measurement_once_v1 ON oracle2.recommendation_action_events_v1
 (workspace_id,principal_id,artifact_id,version,recommendation_id,(payload->>'experiment_id'),kind)
 WHERE kind IN('baseline','followup');
CREATE TABLE oracle2.recommendation_repairs_v1 (
 workspace_id uuid NOT NULL,recommendation_id uuid NOT NULL,rejection_event uuid NOT NULL UNIQUE REFERENCES oracle2.recommendation_action_events_v1,
 artifact_id uuid NOT NULL,version integer NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,recommendation_id),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.recommendation_registrations_v1);
DO $immutable$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['recommendation_action_admissions_v1','recommendation_action_revocations_v1','recommendation_registrations_v1','recommendation_action_events_v1','recommendation_repairs_v1'] LOOP
  EXECUTE format('REVOKE ALL ON oracle2.%I FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,oracle2_replacement_requester,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer',t);
  EXECUTE format('CREATE TRIGGER immutable_%I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()',t,t);
 END LOOP;
END $immutable$;

CREATE FUNCTION oracle2._recommendation_action_context_v1(appointment uuid,op text,runtime text,registry text,config text,deadline timestamptz,mutation boolean DEFAULT false)
 RETURNS oracle2.recommendation_action_admissions_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.recommendation_action_admissions_v1;login oid;until_at timestamptz;valid_path boolean;rooted boolean;
BEGIN
 SELECT oid INTO login FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin AND NOT(rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication);
 IF login IS NULL OR CURRENT_USER::text IS DISTINCT FROM (SELECT rolname::text FROM pg_roles WHERE oid=(SELECT nspowner FROM pg_namespace WHERE nspname='oracle2'))
 OR current_setting('role') NOT IN('none',SESSION_USER::text)
 OR NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl)
 OR deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() OR deadline>clock_timestamp()+interval '30 seconds'
 OR pg_has_role(login,(SELECT nspowner FROM pg_namespace WHERE nspname='oracle2'),'MEMBER')
 THEN RAISE insufficient_privilege USING MESSAGE='exact bounded own TLS recommendation consumer required'; END IF;
 SELECT * INTO a FROM oracle2.recommendation_action_admissions_v1 WHERE admission_id=appointment FOR SHARE;
 IF a.role_name IS DISTINCT FROM SESSION_USER OR a.operation IS DISTINCT FROM op
 OR (a.runtime_hash,a.registry_hash,a.config_hash) IS DISTINCT FROM(runtime,registry,config)
 OR a.issued_at>clock_timestamp() OR least(a.expires_at,a.original_horizon)<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.recommendation_action_revocations_v1 WHERE admission_id=appointment)
 THEN RAISE insufficient_privilege USING MESSAGE='exact current independently installed advice appointment required'; END IF;
 IF mutation THEN
  -- SAME canonical workspace authz key, before any scope/source locks.
  -- Canonical accepted-artifact writers also require this key (after their
  -- own artifact key); this owner never acquires an artifact key afterward.
  PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||a.workspace_id::text));
 END IF;
 IF op='register' THEN
  IF NOT pg_has_role(login,'oracle2_candidate_compiler','MEMBER') THEN RAISE insufficient_privilege; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid<>login AND(pg_has_role(login,r.oid,'MEMBER') OR pg_has_role(login,r.oid,'SET') OR pg_has_role(login,r.oid,'USAGE')))
  OR EXISTS(SELECT 1 FROM oracle2.recommendation_action_admissions_v1 x WHERE x.role_name=a.role_name AND x.operation<>a.operation
   AND x.issued_at<=clock_timestamp() AND x.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM oracle2.recommendation_action_revocations_v1 v WHERE v.admission_id=x.admission_id))
  THEN RAISE insufficient_privilege USING MESSAGE='distinct fixed advice operation LOGIN required'; END IF;
 END IF;
 PERFORM oracle2._replacement_scope(a.workspace_id,a.principal_id,'recommendation-'||op||':'||a.model_id::text);
 -- The selected named path is mandatory even if an alternate scope survives.
 WITH RECURSIVE path AS (
  SELECT p.appointment_id,p.parent_id,p.actor_id,p.granted_by,p.scope,p.revoked_at,p.expires_at,
   ARRAY[p.appointment_id] seen,true valid,1 depth FROM oracle2.appointments p
  WHERE p.appointment_id=a.membership_appointment AND p.workspace_id=a.workspace_id AND p.actor_id=a.principal_id
   AND p.scope='recommendation-'||op||':'||a.model_id::text
  UNION ALL SELECT p.appointment_id,p.parent_id,p.actor_id,p.granted_by,p.scope,p.revoked_at,p.expires_at,
   path.seen||p.appointment_id,path.valid AND p.actor_id=path.granted_by AND p.scope IN('root','recommendation-'||op||':'||a.model_id::text),path.depth+1
  FROM path JOIN oracle2.appointments p ON p.appointment_id=path.parent_id AND p.workspace_id=a.workspace_id
  WHERE path.depth<16 AND NOT p.appointment_id=ANY(path.seen))
 SELECT coalesce(min(expires_at),'infinity'),bool_and(valid AND revoked_at IS NULL AND(expires_at IS NULL OR expires_at>clock_timestamp())),
 bool_or(scope='root' AND parent_id IS NULL) INTO until_at,valid_path,rooted FROM path;
 IF valid_path IS DISTINCT FROM true OR rooted IS DISTINCT FROM true THEN RAISE insufficient_privilege; END IF;
 a.expires_at:=least(a.expires_at,a.original_horizon,deadline,until_at);
 IF a.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN a;
END $$;

CREATE FUNCTION oracle2._recommendation_current_sources_v1(a oracle2.recommendation_action_admissions_v1,refs jsonb)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE ref jsonb;until_at timestamptz:=a.expires_at;
BEGIN
 IF jsonb_typeof(refs) IS DISTINCT FROM 'array' OR jsonb_array_length(refs) NOT BETWEEN 1 AND 64
 OR NOT a.source_refs @> refs OR (SELECT count(DISTINCT r->>'source_id') FROM jsonb_array_elements(refs) r)<>jsonb_array_length(refs)
 THEN RAISE insufficient_privilege; END IF;
 FOR ref IN SELECT value FROM jsonb_array_elements(refs) LOOP
  IF ref->>'workspace_id' IS DISTINCT FROM a.workspace_id::text
  OR NOT EXISTS(SELECT 1 FROM oracle2.sources s JOIN oracle2.source_original_revisions o USING(workspace_id,source_id,revision)
   JOIN oracle2.source_reading_qualifications q USING(workspace_id,source_id,revision)
   WHERE s.workspace_id=a.workspace_id AND s.source_id=(ref->>'source_id')::uuid AND s.revision=(ref->>'revision')::integer
    AND s.status IN('draft','confirmed') AND (o.original_sha256,q.original_sha256,q.reading_sha256,q.parser_id)
    =(ref->>'original_sha256',ref->>'original_sha256',ref->>'reading_sha256',ref->>'parser_id'))
  OR EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE w.workspace_id=a.workspace_id AND w.source_id=(ref->>'source_id')::uuid)
  THEN RAISE insufficient_privilege USING MESSAGE='current exact qualified original and reading source required'; END IF;
  until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||(ref->>'source_id')));
 END LOOP;
 IF until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN until_at;
END $$;

CREATE FUNCTION oracle2._recommendation_registration_current_v1(a oracle2.recommendation_action_admissions_v1,artifact uuid,ver integer)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE r oracle2.recommendation_registrations_v1;manifest jsonb;parent jsonb;until_at timestamptz;
BEGIN
 SELECT * INTO r FROM oracle2.recommendation_registrations_v1 WHERE workspace_id=a.workspace_id AND artifact_id=artifact AND version=ver FOR SHARE;
 IF r.artifact_id IS NULL OR r.parent_model<>a.model_id OR r.parent_version<>(SELECT max(version) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=a.model_id)
 OR r.version<>(SELECT max(version) FROM oracle2.recommendation_registrations_v1 WHERE workspace_id=a.workspace_id AND artifact_id=artifact)
 OR r.version<>(SELECT max(version) FROM oracle2.artifact_manifests WHERE workspace_id=a.workspace_id AND artifact_id=artifact AND kind='processing_recommendation_v1')
 THEN RAISE insufficient_privilege USING MESSAGE='recommendation or parent changed; reload current evidence'; END IF;
 until_at:=oracle2._recommendation_current_sources_v1(a,r.source_refs);
 parent:=oracle2._processing_immutable_artifact_metadata_v1(a.workspace_id,r.parent_model,r.parent_version,r.source_refs);
 manifest:=oracle2._processing_immutable_artifact_metadata_v1(a.workspace_id,artifact,ver,r.source_refs);
 IF parent->>'kind'<>'processing_qualified_model_v1' OR parent->>'content_hash'<>r.parent_hash
 OR manifest->>'kind'<>'processing_recommendation_v1' OR manifest->>'content_hash'<>r.content_hash
 OR NOT EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=artifact AND d.version=ver
  AND d.upstream_kind='artifact' AND d.upstream_id=r.parent_model::text AND d.upstream_revision=r.parent_version::text)
 THEN RAISE insufficient_privilege; END IF;
 RETURN jsonb_build_object('manifest',manifest,'parentManifest',parent,'sourceRefs',r.source_refs,'recommendationIndex',r.recommendation_index,'validUntil',until_at);
END $$;

CREATE FUNCTION oracle2.register_recommendation_actions_v1(artifact uuid,ver integer,payload_bytes bytea,parent_bytes bytea,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.recommendation_action_admissions_v1;p jsonb;b jsonb;c jsonb;m jsonb;pm jsonb;idx jsonb:='[]';item jsonb;plan jsonb;options jsonb;experiments jsonb;
 parent_version integer;registered_head integer;prior oracle2.recommendation_registrations_v1;reject_event oracle2.recommendation_action_events_v1;repair uuid;until_at timestamptz;
BEGIN
 a:=oracle2._recommendation_action_context_v1(appointment,'register',runtime,registry,config,deadline,true);
 IF payload_bytes IS NULL OR octet_length(payload_bytes) NOT BETWEEN 1 AND 1048576
 OR parent_bytes IS NULL OR octet_length(parent_bytes) NOT BETWEEN 1 AND 16777216 OR ver<1 THEN RAISE insufficient_privilege; END IF;
 p:=convert_from(payload_bytes,'UTF8')::jsonb;b:=p->'recommendations';c:=convert_from(parent_bytes,'UTF8')::jsonb;
 IF convert_to(oracle2._processing_canonical_jsonb_v1(p),'UTF8')<>payload_bytes
 OR convert_to(oracle2._processing_canonical_jsonb_v1(c),'UTF8')<>parent_bytes
 OR p-ARRAY['source_refs','findings','recommendations']<>'{}'::jsonb OR p->'findings'<>'[]'::jsonb
 OR b->>'contract'<>'qualified-consulting-recommendations-v2' OR b->>'parent_model_id'<>a.model_id::text
 OR jsonb_typeof(b->'recommendations') IS DISTINCT FROM 'array' OR jsonb_array_length(b->'recommendations') NOT BETWEEN 1 AND 64
 THEN RAISE insufficient_privilege USING MESSAGE='actual canonical consulting artifact bytes required'; END IF;
 parent_version:=(b->>'parent_version')::integer;
 until_at:=oracle2._recommendation_current_sources_v1(a,p->'source_refs');
 pm:=oracle2._processing_immutable_artifact_metadata_v1(a.workspace_id,a.model_id,parent_version,p->'source_refs');
 m:=oracle2._processing_immutable_artifact_metadata_v1(a.workspace_id,artifact,ver,p->'source_refs');
 IF pm->>'kind'<>'processing_qualified_model_v1' OR m->>'kind'<>'processing_recommendation_v1'
 OR pm->>'content_hash'<>encode(sha256(parent_bytes),'hex') OR m->>'content_hash'<>encode(sha256(payload_bytes),'hex')
 OR b->>'parent_content_hash'<>pm->>'content_hash' OR c->'source_refs' IS DISTINCT FROM p->'source_refs'
 OR c->'consolidation_core'->>'contract'<>'qualified-consolidation-core-v1'
 OR NOT EXISTS(SELECT 1 FROM oracle2.processing_model_revisions_v1 r WHERE r.workspace_id=a.workspace_id AND r.artifact_id=a.model_id
  AND r.version=parent_version AND r.content_hash=pm->>'content_hash' AND r.version=(SELECT max(version) FROM oracle2.processing_model_revisions_v1 WHERE workspace_id=a.workspace_id AND artifact_id=a.model_id))
 OR (SELECT count(*) FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=artifact AND d.version=ver AND d.upstream_kind='artifact')<>1
 OR NOT EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id AND d.artifact_id=artifact AND d.version=ver
  AND d.upstream_kind='artifact' AND d.upstream_id=a.model_id::text AND d.upstream_revision=parent_version::text)
 THEN RAISE insufficient_privilege USING MESSAGE='exact accepted qualified purpose parent and dependency required'; END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(b->'recommendations') LOOP
  PERFORM (item->>'recommendation_id')::uuid;
  IF item->'policy_accepted' IS DISTINCT FROM 'false'::jsonb OR item->'effect_executed' IS DISTINCT FROM 'false'::jsonb
  OR item->'realized_savings_verified' IS DISTINCT FROM 'false'::jsonb OR item->>'expected_benefit'<>'unknown'
  OR item->'advice'->>'lens' NOT IN('handoff_rework','approval_exception','information_duplication')
  OR item->'advice'->>'recommendation_id'<>item->>'recommendation_id'
  OR (SELECT count(*) FROM jsonb_array_elements(item->'advice'->'options') o WHERE o->'is_no_change'='true'::jsonb)<>1
  THEN RAISE insufficient_privilege; END IF;
  SELECT jsonb_agg(o->'option_id' ORDER BY o->>'option_id') INTO options FROM jsonb_array_elements(item->'advice'->'options') o;
  experiments:='[]';
  FOR plan IN SELECT value FROM jsonb_array_elements(item->'experiments') LOOP
   experiments:=experiments||jsonb_build_array(plan-ARRAY['success_metric','reversible_step']);
  END LOOP;
  idx:=idx||jsonb_build_array(jsonb_build_object('recommendation_id',item->'recommendation_id','scope',item->'scope','option_ids',options,'experiments',experiments));
 END LOOP;
 IF (SELECT count(DISTINCT x->>'recommendation_id') FROM jsonb_array_elements(idx) x)<>jsonb_array_length(idx) THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO prior FROM oracle2.recommendation_registrations_v1 WHERE workspace_id=a.workspace_id AND artifact_id=artifact AND version=ver;
 IF prior.artifact_id IS NOT NULL THEN
  IF prior.content_hash<>m->>'content_hash' OR prior.recommendation_index<>idx THEN RAISE unique_violation; END IF;
  RETURN oracle2._recommendation_receipt_v1(a,artifact,ver,NULL,NULL);
 END IF;
 -- The workspace lock above serializes even TWO first registrations at
 -- different artifact/admission UUIDs. No check relies on test sequencing.
 SELECT coalesce(max(version),0) INTO registered_head FROM oracle2.recommendation_registrations_v1
 WHERE workspace_id=a.workspace_id AND artifact_id=artifact;
 IF ver<>registered_head+1 OR ver<>(SELECT max(version) FROM oracle2.artifact_manifests WHERE workspace_id=a.workspace_id AND artifact_id=artifact AND kind='processing_recommendation_v1')
 OR EXISTS(SELECT 1 FROM oracle2.recommendation_registrations_v1 old,jsonb_array_elements(old.recommendation_index) old_item,jsonb_array_elements(idx) new_item
  WHERE old.workspace_id=a.workspace_id AND old.artifact_id<>artifact AND old_item->>'recommendation_id'=new_item->>'recommendation_id')
 THEN RAISE serialization_failure USING MESSAGE='stable advice identity/version fork; reload canonical current version'; END IF;
 INSERT INTO oracle2.recommendation_registrations_v1(workspace_id,artifact_id,version,content_hash,parent_model,parent_version,parent_hash,source_refs,recommendation_index,registered_by,admission_id,original_operation_valid_until)
 VALUES(a.workspace_id,artifact,ver,m->>'content_hash',a.model_id,parent_version,pm->>'content_hash',p->'source_refs',idx,a.principal_id,appointment,least(a.expires_at,until_at,deadline));
 repair:=(b->>'repair_of_event')::uuid;
 IF repair IS NOT NULL THEN
  SELECT * INTO reject_event FROM oracle2.recommendation_action_events_v1 WHERE event_id=repair AND workspace_id=a.workspace_id AND principal_id=a.principal_id AND kind='feedback' AND payload->>'decision'='reject';
  IF reject_event.event_id IS NULL OR jsonb_array_length(idx)<>1 OR idx->0->>'recommendation_id'<>reject_event.recommendation_id::text
  OR reject_event.artifact_id<>artifact OR reject_event.version<>registered_head OR ver<>reject_event.version+1 THEN RAISE insufficient_privilege; END IF;
  INSERT INTO oracle2.recommendation_repairs_v1(workspace_id,recommendation_id,rejection_event,artifact_id,version)
  VALUES(a.workspace_id,reject_event.recommendation_id,repair,artifact,ver);
 END IF;
 a:=oracle2._recommendation_action_context_v1(appointment,'register',runtime,registry,config,deadline,true);
 RETURN oracle2._recommendation_receipt_v1(a,artifact,ver,NULL,NULL);
END $$;

CREATE FUNCTION oracle2._recommendation_own_status_v1(a oracle2.recommendation_action_admissions_v1,artifact uuid,ver integer,recommendation uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE fresh jsonb;permitted boolean:=true;events jsonb;r oracle2.recommendation_registrations_v1;head integer;
BEGIN
 SELECT * INTO r FROM oracle2.recommendation_registrations_v1 WHERE workspace_id=a.workspace_id AND artifact_id=artifact AND version=ver AND parent_model=a.model_id;
 IF r.artifact_id IS NULL OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(r.recommendation_index) x WHERE x->>'recommendation_id'=recommendation::text) THEN RAISE insufficient_privilege; END IF;
 BEGIN fresh:=oracle2._recommendation_registration_current_v1(a,artifact,ver);
 EXCEPTION WHEN insufficient_privilege THEN permitted:=false;fresh:=NULL; END;
 SELECT coalesce(max(sequence),0),coalesce(jsonb_agg(jsonb_build_object('event_id',event_id,'sequence',sequence,'kind',kind,'recorded_at',recorded_at,
  'payload',CASE WHEN permitted THEN payload ELSE 'null'::jsonb END) ORDER BY sequence),'[]') INTO head,events
 FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=a.workspace_id AND principal_id=a.principal_id AND artifact_id=artifact AND version=ver AND recommendation_id=recommendation;
 RETURN jsonb_build_object('schema_version',1,'artifact_id',artifact,'artifact_version',ver,'recommendation_id',recommendation,'head_revision',head,
  'stale',NOT permitted,'redacted',NOT permitted,'events',events,'context',fresh,'valid_until',least(a.expires_at,coalesce((fresh->>'validUntil')::timestamptz,a.expires_at)),
  'policy_accepted',false,'effect_executed',false,'causal_savings',false,'realized_savings_verified',false,'business_acceptance',false);
END $$;

CREATE FUNCTION oracle2.read_recommendation_actions_v1(artifact uuid,ver integer,recommendation uuid,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.recommendation_action_admissions_v1;result jsonb;
BEGIN
 a:=oracle2._recommendation_action_context_v1(appointment,'read',runtime,registry,config,deadline);
 result:=oracle2._recommendation_own_status_v1(a,artifact,ver,recommendation);
 a:=oracle2._recommendation_action_context_v1(appointment,'read',runtime,registry,config,deadline);
 RETURN result;
END $$;

-- Fixed own-read index; no caller workspace/model or arbitrary query selector.
CREATE FUNCTION oracle2.list_recommendation_actions_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.recommendation_action_admissions_v1;r oracle2.recommendation_registrations_v1;
 fresh jsonb;item jsonb;selectors jsonb:='[]';gap boolean:=false;until_at timestamptz;
BEGIN
 a:=oracle2._recommendation_action_context_v1(appointment,'read',runtime,registry,config,deadline);
 -- Prove complete independently installed original population before selecting
 -- any readable label/UUID. Source denial never masquerades as an empty list.
 until_at:=oracle2._recommendation_current_sources_v1(a,a.source_refs);
 FOR r IN SELECT x.* FROM oracle2.recommendation_registrations_v1 x
  WHERE x.workspace_id=a.workspace_id AND x.parent_model=a.model_id
   AND x.version=(SELECT max(y.version) FROM oracle2.recommendation_registrations_v1 y WHERE y.workspace_id=x.workspace_id AND y.artifact_id=x.artifact_id)
  ORDER BY x.artifact_id,x.version LOOP
  BEGIN
   fresh:=oracle2._recommendation_registration_current_v1(a,r.artifact_id,r.version);
  EXCEPTION WHEN insufficient_privilege THEN CONTINUE; END;
  until_at:=least(until_at,(fresh->>'validUntil')::timestamptz);
  FOR item IN SELECT value FROM jsonb_array_elements(r.recommendation_index) ORDER BY value->>'recommendation_id' LOOP
   IF jsonb_array_length(selectors)=64 THEN gap:=true;EXIT;END IF;
   selectors:=selectors||jsonb_build_array(jsonb_build_object('schema_version',1,'artifact_id',r.artifact_id,'artifact_version',r.version,'artifact_sha256',r.content_hash,'recommendation_id',item->'recommendation_id'));
  END LOOP;
  IF gap THEN EXIT;END IF;
 END LOOP;
 a:=oracle2._recommendation_action_context_v1(appointment,'read',runtime,registry,config,deadline);
 until_at:=least(until_at,oracle2._recommendation_current_sources_v1(a,a.source_refs),a.expires_at);
 RETURN jsonb_build_object('schema_version',1,'kind','recommendation-index-v1','selectors',selectors,'coverage_gap',gap,'list_complete',NOT gap,
  'scope','current-permitted-model-advice','valid_until',until_at,'policy_accepted',false,'effect_executed',false,'business_acceptance',false);
END $$;

CREATE FUNCTION oracle2._recommendation_command_v1(raw bytea,operation_name text)
 RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q jsonb;fields text[];
BEGIN
 IF raw IS NULL OR octet_length(raw) NOT BETWEEN 1 AND 16384 THEN RAISE invalid_parameter_value; END IF;
 q:=convert_from(raw,'UTF8')::jsonb;
 fields:=ARRAY['schema_version','operation','selector','expected_head','command_id','caller_deadline'];
 IF operation_name='feedback' THEN fields:=fields||ARRAY['decision','option_id','reason'];
 ELSE fields:=fields||ARRAY['experiment_id','phase','assertion_id','assertion_revision']; END IF;
 IF jsonb_typeof(q) IS DISTINCT FROM 'object' OR q-fields<>'{}'::jsonb OR NOT q ?& fields
 OR q->'schema_version' IS DISTINCT FROM '1'::jsonb OR q->>'operation'<>operation_name
 OR convert_to(oracle2._processing_canonical_jsonb_v1(q),'UTF8')<>raw
 OR jsonb_typeof(q->'expected_head') IS DISTINCT FROM 'number' OR q->>'expected_head' !~ '^(0|[1-9][0-9]{0,4})$' OR (q->>'expected_head')::integer>16383
 OR jsonb_typeof(q->'selector') IS DISTINCT FROM 'object' OR NOT q->'selector' ?& ARRAY['schema_version','artifact_id','artifact_version','artifact_sha256','recommendation_id']
 OR (q->'selector')-ARRAY['schema_version','artifact_id','artifact_version','artifact_sha256','recommendation_id']<>'{}'::jsonb
 OR q->'selector'->'schema_version' IS DISTINCT FROM '1'::jsonb OR jsonb_typeof(q->'selector'->'artifact_version') IS DISTINCT FROM 'number'
 OR q->'selector'->>'artifact_version' !~ '^[1-9][0-9]*$' OR q->'selector'->>'artifact_sha256' !~ '^[0-9a-f]{64}$'
 THEN RAISE invalid_parameter_value USING MESSAGE='closed canonical action command required'; END IF;
 IF q->>'command_id' IS DISTINCT FROM ((q->>'command_id')::uuid)::text
 OR q->'selector'->>'artifact_id' IS DISTINCT FROM ((q->'selector'->>'artifact_id')::uuid)::text
 OR q->'selector'->>'recommendation_id' IS DISTINCT FROM ((q->'selector'->>'recommendation_id')::uuid)::text
 OR q->>'caller_deadline' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{6})?Z$'
 OR q->>'caller_deadline' ~ '\.000000Z$' THEN RAISE invalid_parameter_value; END IF;
 RETURN q;
END $$;

CREATE FUNCTION oracle2._recommendation_append_v1(a oracle2.recommendation_action_admissions_v1,q jsonb,raw bytea,kind text,payload jsonb)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE artifact uuid:=(q->'selector'->>'artifact_id')::uuid;ver integer:=(q->'selector'->>'artifact_version')::integer;
 recommendation uuid:=(q->'selector'->>'recommendation_id')::uuid;head integer;prior oracle2.recommendation_action_events_v1;
BEGIN
 -- Fixed mutation context holds canonical authz workspace lock: global command
 -- uniqueness and per-recommendation CAS survive reinstall/new admission.
 SELECT * INTO prior FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=a.workspace_id AND principal_id=a.principal_id AND command_id=(q->>'command_id')::uuid;
 IF prior.event_id IS NOT NULL THEN
  IF prior.command_bytes<>raw THEN RAISE unique_violation USING MESSAGE='global recommendation command collision'; END IF;
  RETURN oracle2._recommendation_receipt_v1(a,artifact,ver,recommendation,(q->>'command_id')::uuid);
 END IF;
 SELECT coalesce(max(sequence),0) INTO head FROM oracle2.recommendation_action_events_v1
 WHERE workspace_id=a.workspace_id AND principal_id=a.principal_id AND artifact_id=artifact AND version=ver AND recommendation_id=recommendation;
 IF head<>(q->>'expected_head')::integer THEN RAISE serialization_failure USING MESSAGE='recommendation feedback changed; reload'; END IF;
 IF head>=128 THEN RAISE program_limit_exceeded USING MESSAGE='bounded history full; retained facts unchanged'; END IF;
 INSERT INTO oracle2.recommendation_action_events_v1(event_id,workspace_id,principal_id,artifact_id,version,recommendation_id,sequence,kind,command_id,command_sha256,command_bytes,admission_id,payload,original_operation_valid_until)
 VALUES(gen_random_uuid(),a.workspace_id,a.principal_id,artifact,ver,recommendation,head+1,kind,(q->>'command_id')::uuid,encode(sha256(raw),'hex'),raw,a.admission_id,payload,a.expires_at);
 RETURN oracle2._recommendation_receipt_v1(a,artifact,ver,recommendation,(q->>'command_id')::uuid);
END $$;

CREATE FUNCTION oracle2._recommendation_receipt_v1(a oracle2.recommendation_action_admissions_v1,artifact uuid,ver integer,recommendation uuid,command uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE e oracle2.recommendation_action_events_v1;r oracle2.recommendation_registrations_v1;fresh jsonb;permitted boolean:=true;
BEGIN
 SELECT * INTO r FROM oracle2.recommendation_registrations_v1 WHERE workspace_id=a.workspace_id AND artifact_id=artifact AND version=ver AND parent_model=a.model_id;
 IF r.artifact_id IS NULL THEN RAISE insufficient_privilege; END IF;
 BEGIN fresh:=oracle2._recommendation_registration_current_v1(a,artifact,ver);
 EXCEPTION WHEN insufficient_privilege THEN permitted:=false;fresh:=NULL; END;
 IF a.operation='register' THEN
  IF command IS NOT NULL OR r.registered_by<>a.principal_id THEN RAISE insufficient_privilege; END IF;
  RETURN jsonb_build_object('schema_version',1,'receipt_kind','registration','artifact_id',artifact,'artifact_version',ver,'content_hash',r.content_hash,
   'recorded_at',r.recorded_at,'original_operation_valid_until',r.original_operation_valid_until,'original_operation_window_unexpired',r.original_operation_valid_until>clock_timestamp(),'receipt_read_only',true,'write_authorized',false,'dispatch_authorized',false,'stale',NOT permitted,'redacted',NOT permitted,'valid_until',least(a.expires_at,coalesce((fresh->>'validUntil')::timestamptz,a.expires_at)));
 END IF;
 SELECT * INTO e FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=a.workspace_id AND principal_id=a.principal_id
 AND artifact_id=artifact AND version=ver AND recommendation_id=recommendation AND command_id=command;
 IF e.event_id IS NULL OR (a.operation='feedback' AND e.kind<>'feedback') OR (a.operation='measurement' AND e.kind NOT IN('baseline','followup'))
 OR a.operation NOT IN('feedback','measurement') THEN RAISE insufficient_privilege; END IF;
 RETURN jsonb_build_object('schema_version',1,'receipt_kind','action','artifact_id',artifact,'artifact_version',ver,'recommendation_id',recommendation,
  'artifact_sha256',r.content_hash,'command_id',command,'event_id',e.event_id,'sequence',e.sequence,'kind',e.kind,'recorded_at',e.recorded_at,'original_operation_valid_until',e.original_operation_valid_until,'original_operation_window_unexpired',e.original_operation_valid_until>clock_timestamp(),'receipt_read_only',true,'write_authorized',false,'dispatch_authorized',false,'stale',NOT permitted,'redacted',NOT permitted,
  'valid_until',least(a.expires_at,coalesce((fresh->>'validUntil')::timestamptz,a.expires_at)));
END $$;

CREATE FUNCTION oracle2.reconcile_recommendation_action_v1(artifact uuid,ver integer,recommendation uuid,command uuid,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.recommendation_action_admissions_v1;op text;result jsonb;
BEGIN
 SELECT operation INTO op FROM oracle2.recommendation_action_admissions_v1 WHERE admission_id=appointment;
 IF op NOT IN('register','feedback','measurement') THEN RAISE insufficient_privilege; END IF;
 a:=oracle2._recommendation_action_context_v1(appointment,op,runtime,registry,config,deadline);
 result:=oracle2._recommendation_receipt_v1(a,artifact,ver,recommendation,command);
 a:=oracle2._recommendation_action_context_v1(appointment,op,runtime,registry,config,deadline);
 RETURN result;
END $$;

CREATE FUNCTION oracle2.record_recommendation_feedback_v1(command_bytes bytea,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.recommendation_action_admissions_v1;q jsonb;fresh jsonb;item jsonb;result jsonb;
BEGIN
 q:=oracle2._recommendation_command_v1(command_bytes,'feedback');
 IF (q->>'caller_deadline')::timestamptz IS DISTINCT FROM deadline THEN RAISE insufficient_privilege; END IF;
 a:=oracle2._recommendation_action_context_v1(appointment,'feedback',runtime,registry,config,deadline,true);
 fresh:=oracle2._recommendation_registration_current_v1(a,(q->'selector'->>'artifact_id')::uuid,(q->'selector'->>'artifact_version')::integer);
 SELECT value INTO item FROM jsonb_array_elements(fresh->'recommendationIndex') x WHERE x->>'recommendation_id'=q->'selector'->>'recommendation_id';
 IF item IS NULL OR fresh->'manifest'->>'content_hash'<>q->'selector'->>'artifact_sha256'
 OR jsonb_typeof(q->'decision') IS DISTINCT FROM 'string' OR q->>'decision' NOT IN('accept','reject','defer')
 OR jsonb_typeof(q->'reason') IS DISTINCT FROM 'string' OR length(btrim(q->>'reason')) NOT BETWEEN 1 AND 1600
 OR (q->>'decision'='accept' AND (jsonb_typeof(q->'option_id') IS DISTINCT FROM 'string' OR NOT item->'option_ids' @> jsonb_build_array(q->'option_id')))
 OR (q->>'decision'<>'accept' AND q->'option_id' IS DISTINCT FROM 'null'::jsonb)
 THEN RAISE invalid_parameter_value; END IF;
 a.expires_at:=least(a.expires_at,(fresh->>'validUntil')::timestamptz);
 result:=oracle2._recommendation_append_v1(a,q,command_bytes,'feedback',jsonb_build_object('decision',q->'decision','option_id',q->'option_id','reason',q->'reason','falsifies_facts',false,'policy_accepted',false,'effect_executed',false));
 a:=oracle2._recommendation_action_context_v1(appointment,'feedback',runtime,registry,config,deadline,true);
 PERFORM oracle2._recommendation_registration_current_v1(a,(q->'selector'->>'artifact_id')::uuid,(q->'selector'->>'artifact_version')::integer);
 RETURN result;
END $$;

CREATE FUNCTION oracle2.record_recommendation_measurement_v1(command_bytes bytea,assertion_bytes bytea,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.recommendation_action_admissions_v1;q jsonb;fresh jsonb;item jsonb;plan jsonb;assertion jsonb;measured jsonb;idx jsonb;result jsonb;start_at timestamptz;end_at timestamptz;observed timestamptz;
BEGIN
 q:=oracle2._recommendation_command_v1(command_bytes,'measurement');
 IF (q->>'caller_deadline')::timestamptz IS DISTINCT FROM deadline OR assertion_bytes IS NULL OR octet_length(assertion_bytes) NOT BETWEEN 1 AND 16384 THEN RAISE insufficient_privilege; END IF;
 a:=oracle2._recommendation_action_context_v1(appointment,'measurement',runtime,registry,config,deadline,true);
 fresh:=oracle2._recommendation_registration_current_v1(a,(q->'selector'->>'artifact_id')::uuid,(q->'selector'->>'artifact_version')::integer);
 SELECT value INTO item FROM jsonb_array_elements(fresh->'recommendationIndex') x WHERE x->>'recommendation_id'=q->'selector'->>'recommendation_id';
 IF item IS NULL OR fresh->'manifest'->>'content_hash'<>q->'selector'->>'artifact_sha256' OR q->>'phase' NOT IN('baseline','followup') THEN RAISE insufficient_privilege; END IF;
 SELECT value INTO plan FROM jsonb_array_elements(item->'experiments') x WHERE x->>'experiment_id'=q->>'experiment_id';
 assertion:=convert_from(assertion_bytes,'UTF8')::jsonb;
 SELECT x INTO idx FROM oracle2.processing_model_revisions_v1 r,jsonb_array_elements(r.assertion_index) x
 WHERE r.workspace_id=a.workspace_id AND r.artifact_id=a.model_id AND r.version=(fresh->'parentManifest'->>'version')::integer
 AND x->>'assertion_id'=q->>'assertion_id' AND x->'revision'=q->'assertion_revision';
 IF plan IS NULL OR idx IS NULL OR idx->>'assertion_hash'<>encode(sha256(assertion_bytes),'hex')
 OR convert_to(oracle2._processing_canonical_jsonb_v1(assertion),'UTF8')<>assertion_bytes
 OR assertion->>'predicate'<>'measurement:observation:v1' OR assertion->>'unit'<>'canonical-measurement-v1'
 OR assertion->>'subject_id'<>plan->>'metric_id' OR assertion->'scope' IS DISTINCT FROM item->'scope'
 OR assertion->>'valid_time'<>'evidenced' OR jsonb_array_length(assertion->'supporting_observations')<1 OR jsonb_array_length(assertion->'temporal_observations')<1
 THEN RAISE insufficient_privilege USING MESSAGE='actual qualified assertion body/window required'; END IF;
 measured:=(assertion->>'value')::jsonb;
 IF measured-ARRAY['schema_version','contract','amount','unit','currency','period','population_id','window_start','window_end','observed_through','complete','censored']<>'{}'::jsonb
 OR NOT measured ?& ARRAY['schema_version','contract','amount','unit','currency','period','population_id','window_start','window_end','observed_through','complete','censored']
 OR measured->'schema_version' IS DISTINCT FROM '1'::jsonb OR measured->>'contract'<>'qualified-measurement-evidence-v1'
 OR oracle2._processing_canonical_jsonb_v1(measured)<>assertion->>'value'
 OR jsonb_typeof(measured->'amount') IS DISTINCT FROM 'string' OR measured->>'amount' !~ '^(0|[1-9][0-9]{0,35})(\.[0-9]{0,17}[1-9])?$'
 OR length(replace(measured->>'amount','.',''))>36 OR jsonb_typeof(measured->'complete') IS DISTINCT FROM 'boolean' OR jsonb_typeof(measured->'censored') IS DISTINCT FROM 'boolean'
 OR (measured->'unit',measured->'currency',measured->'period',measured->'population_id') IS DISTINCT FROM (plan->'unit',plan->'currency',plan->'period',plan->'population_id')
 THEN RAISE insufficient_privilege USING MESSAGE='exact source measurement fields required; no inferred number/unit'; END IF;
 start_at:=(measured->>'window_start')::timestamptz;end_at:=(measured->>'window_end')::timestamptz;observed:=(measured->>'observed_through')::timestamptz;
 IF NOT isfinite(start_at) OR NOT isfinite(end_at) OR NOT isfinite(observed) OR start_at>=end_at OR observed<start_at OR observed>clock_timestamp()
 OR measured->>'window_start' !~ 'Z$' OR measured->>'window_end' !~ 'Z$' OR measured->>'observed_through' !~ 'Z$'
 OR start_at<>(assertion->>'valid_from')::timestamptz OR end_at<>(assertion->>'valid_to')::timestamptz
 OR start_at<>(plan->>(CASE WHEN q->>'phase'='baseline' THEN 'baseline_start' ELSE 'followup_start' END))::timestamptz
 OR end_at<>(plan->>(CASE WHEN q->>'phase'='baseline' THEN 'baseline_end' ELSE 'followup_end' END))::timestamptz
 OR (measured->'complete'='true'::jsonb AND(measured->'censored'<>'false'::jsonb OR observed<end_at))
 THEN RAISE insufficient_privilege; END IF;
 a.expires_at:=least(a.expires_at,(fresh->>'validUntil')::timestamptz);
 result:=oracle2._recommendation_append_v1(a,q,command_bytes,q->>'phase',jsonb_build_object('experiment_id',q->'experiment_id','assertion_id',q->'assertion_id','assertion_revision',q->'assertion_revision',
  'assertion_sha256',idx->'assertion_hash','measurement',measured,'reported_only',true,'causal_savings',false,'realized_savings_verified',false));
 a:=oracle2._recommendation_action_context_v1(appointment,'measurement',runtime,registry,config,deadline,true);
 PERFORM oracle2._recommendation_registration_current_v1(a,(q->'selector'->>'artifact_id')::uuid,(q->'selector'->>'artifact_version')::integer);
 RETURN result;
END $$;

-- No runtime receives a helper or an operation grant by migration presence.
DO $acl$ DECLARE p regprocedure; BEGIN
 FOR p IN SELECT oid::regprocedure FROM pg_proc WHERE pronamespace='oracle2'::regnamespace AND proname IN(
 '_recommendation_action_context_v1','_recommendation_current_sources_v1','_recommendation_registration_current_v1','register_recommendation_actions_v1',
 '_recommendation_own_status_v1','read_recommendation_actions_v1','list_recommendation_actions_v1','_recommendation_command_v1','_recommendation_append_v1','_recommendation_receipt_v1','reconcile_recommendation_action_v1','record_recommendation_feedback_v1','record_recommendation_measurement_v1') LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,oracle2_replacement_requester,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer',p);
 END LOOP;
END $acl$;
