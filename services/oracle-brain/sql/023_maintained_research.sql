-- Dedicated Oracle operational research register. SOURCE ONLY. No runtime role,
-- source rights, appointment or platform schedule is issued by this migration.
DO $owner$ BEGIN
 IF CURRENT_USER::text IS DISTINCT FROM (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2')
 THEN RAISE insufficient_privilege USING MESSAGE='canonical Oracle owner required'; END IF;
END $owner$;

CREATE TABLE oracle2.research_registrations_v1 (
 workspace_id uuid NOT NULL,source_id uuid NOT NULL,revision integer NOT NULL CHECK(revision>0),
 definition jsonb NOT NULL CHECK(jsonb_typeof(definition)='object'),
 definition_sha256 text NOT NULL CHECK(definition_sha256 ~ '^[a-f0-9]{64}$'),
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,source_id,revision),
 CHECK(definition ?& ARRAY['source_id','publisher','url','jurisdiction','scope','access','cadence','enabled','rights_confirmed']),
 CHECK(definition-ARRAY['source_id','publisher','url','jurisdiction','scope','access','cadence','enabled','rights_confirmed']='{}'::jsonb),
 CHECK(definition->>'access' IN('public','licensed','member') AND definition->>'cadence' IN('weekly','quarterly')),
 CHECK(jsonb_typeof(definition->'enabled')='boolean' AND jsonb_typeof(definition->'rights_confirmed')='boolean'),
 CHECK(length(definition->>'source_id') BETWEEN 1 AND 80 AND length(definition->>'publisher') BETWEEN 1 AND 200),
 CHECK(length(definition->>'url') BETWEEN 1 AND 2048),
 CHECK(definition_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(definition),'UTF8')),'hex')));
CREATE TABLE oracle2.research_admissions_v1 (
 admission_id uuid PRIMARY KEY,role_name name NOT NULL,principal_id uuid NOT NULL,
 workspace_id uuid NOT NULL,source_id uuid NOT NULL,source_revision integer NOT NULL,
 operation text NOT NULL CHECK(operation IN('schedule','fetch','read')),
 membership_appointment uuid NOT NULL REFERENCES oracle2.appointments(appointment_id),
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[a-f0-9]{64}$'),
 registry_hash text NOT NULL CHECK(registry_hash ~ '^[a-f0-9]{64}$'),
 config_hash text NOT NULL CHECK(config_hash ~ '^[a-f0-9]{64}$'),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL,
 issued_at timestamptz NOT NULL,original_horizon timestamptz NOT NULL CHECK(isfinite(original_horizon)),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 FOREIGN KEY(workspace_id,source_id,source_revision) REFERENCES oracle2.research_registrations_v1,
 CHECK(issued_at<expires_at AND expires_at<=original_horizon),
 CHECK(issuer_actor<>reviewer_actor AND principal_id NOT IN(issuer_actor,reviewer_actor)));
CREATE TABLE oracle2.research_admission_revocations_v1 (
 admission_id uuid PRIMARY KEY REFERENCES oracle2.research_admissions_v1,
 revoked_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE oracle2.research_state_v1 (
 workspace_id uuid NOT NULL,source_id uuid NOT NULL,revision integer NOT NULL,
 next_due timestamptz NOT NULL DEFAULT '-infinity',last_success timestamptz,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 4),
 inflight uuid,exhausted boolean NOT NULL DEFAULT false,
 PRIMARY KEY(workspace_id,source_id,revision),
 FOREIGN KEY(workspace_id,source_id,revision) REFERENCES oracle2.research_registrations_v1);
CREATE TABLE oracle2.research_attempts_v1 (
 run_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,source_id uuid NOT NULL,source_revision integer NOT NULL,
 attempt integer NOT NULL CHECK(attempt BETWEEN 1 AND 4),
 schedule_admission uuid NOT NULL REFERENCES oracle2.research_admissions_v1,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,source_id,source_revision) REFERENCES oracle2.research_registrations_v1);
CREATE TABLE oracle2.research_run_heads_v1 (
 run_id uuid PRIMARY KEY REFERENCES oracle2.research_attempts_v1,
 state text NOT NULL CHECK(state IN('pending','INFLIGHT','observed','UNKNOWN')),
 claim_id uuid,fetch_admission uuid REFERENCES oracle2.research_admissions_v1,
 claim_deadline timestamptz,observation_sha256 text CHECK(observation_sha256 ~ '^[a-f0-9]{64}$'),
 CHECK((claim_id IS NULL)=(claim_deadline IS NULL)));
CREATE TABLE oracle2.research_events_v1 (
 event_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES oracle2.research_attempts_v1,
 kind text NOT NULL CHECK(kind IN('pending','claimed','observed','UNKNOWN')),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'));
DO $immutable$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['research_registrations_v1','research_admissions_v1','research_admission_revocations_v1','research_attempts_v1','research_events_v1'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_%I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()',t,t);
 END LOOP;
END $immutable$;

CREATE FUNCTION oracle2._research_admission_v1(appointment uuid,wanted text,runtime text,registry text,config text,deadline timestamptz)
 RETURNS oracle2.research_admissions_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;login oid;owner_oid oid;bound timestamptz;r oracle2.research_registrations_v1;
 selected_bound timestamptz;selected_ok boolean;selected_root boolean;selected_scope text;
BEGIN
 SELECT oid INTO login FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin
  AND NOT(rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication);
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF login IS NULL OR CURRENT_USER::text IS DISTINCT FROM pg_get_userbyid(owner_oid)
 OR current_setting('role') NOT IN('none',SESSION_USER::text)
 OR EXISTS(SELECT 1 FROM pg_roles p WHERE p.oid<>login AND (pg_has_role(login,p.oid,'MEMBER') OR pg_has_role(login,p.oid,'SET') OR pg_has_role(login,p.oid,'USAGE')))
 OR current_setting('transaction_isolation')<>'read committed'
 OR current_setting('statement_timeout')::interval NOT BETWEEN interval '1 millisecond' AND interval '5 seconds'
 OR current_setting('lock_timeout')::interval NOT BETWEEN interval '1 millisecond' AND interval '2 seconds'
 OR deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() OR deadline>clock_timestamp()+interval '30 seconds'
 THEN RAISE insufficient_privilege USING MESSAGE='exact bounded own research role required'; END IF;
 SELECT * INTO a FROM oracle2.research_admissions_v1 WHERE admission_id=appointment FOR SHARE;
 IF a.role_name IS DISTINCT FROM SESSION_USER OR a.operation IS DISTINCT FROM wanted
 OR (a.runtime_hash,a.registry_hash,a.config_hash) IS DISTINCT FROM(runtime,registry,config)
 OR a.issued_at>clock_timestamp() OR a.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.research_admission_revocations_v1 WHERE admission_id=appointment)
 THEN RAISE insufficient_privilege USING MESSAGE='current independent research appointment required'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||a.workspace_id::text));
 selected_scope:='research-'||wanted||':'||a.source_id::text;
 bound:=oracle2._replacement_scope(a.workspace_id,a.principal_id,selected_scope);
 WITH RECURSIVE selected_path AS (
  SELECT p.appointment_id,p.parent_id,p.actor_id,p.granted_by,p.scope,p.revoked_at,p.expires_at,
   ARRAY[p.appointment_id] seen,true valid,1 depth FROM oracle2.appointments p
   WHERE p.appointment_id=a.membership_appointment AND p.workspace_id=a.workspace_id
    AND p.actor_id=a.principal_id AND p.scope=selected_scope
  UNION ALL
  SELECT p.appointment_id,p.parent_id,p.actor_id,p.granted_by,p.scope,p.revoked_at,p.expires_at,
   path.seen||p.appointment_id,path.valid AND p.actor_id=path.granted_by AND p.scope IN(selected_scope,'root'),path.depth+1
  FROM selected_path path JOIN oracle2.appointments p ON p.appointment_id=path.parent_id AND p.workspace_id=a.workspace_id
  WHERE path.depth<16 AND NOT p.appointment_id=ANY(path.seen))
 SELECT coalesce(min(expires_at),'infinity'::timestamptz),
  bool_and(valid AND revoked_at IS NULL AND(expires_at IS NULL OR expires_at>clock_timestamp())),
  bool_or(scope='root' AND parent_id IS NULL)
 INTO selected_bound,selected_ok,selected_root FROM selected_path;
 IF selected_ok IS DISTINCT FROM true OR selected_root IS DISTINCT FROM true THEN
  RAISE insufficient_privilege USING MESSAGE='exact selected research delegation path required'; END IF;
 bound:=least(bound,selected_bound);
 SELECT * INTO r FROM oracle2.research_registrations_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 IF r.revision IS NULL OR r.revision<>(SELECT max(revision) FROM oracle2.research_registrations_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id)
 OR (wanted<>'read' AND (r.definition->'enabled'<>'true'::jsonb OR (r.definition->>'access'<>'public' AND r.definition->'rights_confirmed'<>'true'::jsonb)))
 THEN RAISE insufficient_privilege USING MESSAGE='current source revision and existing rights required'; END IF;
 a.expires_at:=least(a.expires_at,a.original_horizon,deadline,bound);
 IF a.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN a;
END $$;

CREATE FUNCTION oracle2.research_fetch_current_v1(run uuid,claim uuid,appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;t oracle2.research_attempts_v1;h oracle2.research_run_heads_v1;bound timestamptz;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'fetch',runtime,registry,config,deadline);
 SELECT * INTO t FROM oracle2.research_attempts_v1 WHERE run_id=run;
 IF (t.workspace_id,t.source_id,t.source_revision) IS DISTINCT FROM(a.workspace_id,a.source_id,a.source_revision) THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO h FROM oracle2.research_run_heads_v1 WHERE run_id=run FOR UPDATE;
 IF h.claim_id IS DISTINCT FROM claim OR h.fetch_admission IS DISTINCT FROM appointment THEN RAISE insufficient_privilege; END IF;
 bound:=least(a.expires_at,h.claim_deadline);
 RETURN jsonb_build_object('schema_version',1,'run_id',run,'claim_id',claim,
  'current',h.state='INFLIGHT' AND bound>clock_timestamp(),'valid_until',bound,'resend_authorized',false,'context',oracle2._research_context_v1(a));
END $$;

CREATE FUNCTION oracle2.research_claim_due_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;s oracle2.research_state_v1;run uuid:=gen_random_uuid();
BEGIN
 a:=oracle2._research_admission_v1(appointment,'schedule',runtime,registry,config,deadline);
 INSERT INTO oracle2.research_state_v1(workspace_id,source_id,revision) VALUES(a.workspace_id,a.source_id,a.source_revision) ON CONFLICT DO NOTHING;
 SELECT * INTO s FROM oracle2.research_state_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision FOR UPDATE;
 IF s.inflight IS NOT NULL THEN RETURN jsonb_build_object('schema_version',1,'state','existing','run_id',s.inflight,'dispatch_authorized',false,'context',oracle2._research_context_v1(a)); END IF;
 IF s.next_due>clock_timestamp() THEN RETURN jsonb_build_object('schema_version',1,'state','not_due','dispatch_authorized',false,'context',oracle2._research_context_v1(a)); END IF;
 IF a.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 IF s.exhausted THEN s.attempts:=0; END IF;
 INSERT INTO oracle2.research_attempts_v1 VALUES(run,a.workspace_id,a.source_id,a.source_revision,s.attempts+1,appointment,clock_timestamp());
 INSERT INTO oracle2.research_run_heads_v1(run_id,state) VALUES(run,'pending');
 INSERT INTO oracle2.research_events_v1 VALUES(gen_random_uuid(),run,'pending',clock_timestamp(),jsonb_build_object('schedule_admission',appointment));
 UPDATE oracle2.research_state_v1 SET inflight=run,attempts=s.attempts+1,exhausted=false WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 RETURN jsonb_build_object('schema_version',1,'state','pending','run_id',run,'dispatch_authorized',true,'valid_until',a.expires_at,'context',oracle2._research_context_v1(a));
END $$;

-- Queue reconciliation reveals ONLY the existing opaque pending run. Repeated
-- queue delivery cannot recreate a fetch claim or renew an INFLIGHT operation.
CREATE FUNCTION oracle2.research_pending_queue_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;s oracle2.research_state_v1;h oracle2.research_run_heads_v1;state text;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'schedule',runtime,registry,config,deadline);
 SELECT * INTO s FROM oracle2.research_state_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 IF s.inflight IS NOT NULL THEN SELECT * INTO h FROM oracle2.research_run_heads_v1 WHERE run_id=s.inflight; END IF;
 state:=CASE WHEN h.state='INFLIGHT' AND h.claim_deadline<=clock_timestamp() THEN 'UNKNOWN' ELSE coalesce(h.state,'idle') END;
 RETURN jsonb_build_object('schema_version',1,'state',state,'run_id',s.inflight,
  'queue_authorized',h.state IS NOT DISTINCT FROM 'pending' AND h.claim_id IS NULL,
  'fetch_authorized',false,'context',oracle2._research_context_v1(a));
END $$;

CREATE FUNCTION oracle2.research_claim_fetch_v1(run uuid,appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;t oracle2.research_attempts_v1;h oracle2.research_run_heads_v1;claim uuid:=gen_random_uuid();r oracle2.research_registrations_v1;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'fetch',runtime,registry,config,deadline);
 SELECT * INTO t FROM oracle2.research_attempts_v1 WHERE run_id=run;
 IF (t.workspace_id,t.source_id,t.source_revision) IS DISTINCT FROM(a.workspace_id,a.source_id,a.source_revision) THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO h FROM oracle2.research_run_heads_v1 WHERE run_id=run FOR UPDATE;
 IF h.state<>'pending' THEN RETURN jsonb_build_object('schema_version',1,'state','UNKNOWN','run_id',run,'fetch_authorized',false,'context',oracle2._research_context_v1(a)); END IF;
 SELECT * INTO r FROM oracle2.research_registrations_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 IF a.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 UPDATE oracle2.research_run_heads_v1 SET state='INFLIGHT',claim_id=claim,fetch_admission=appointment,claim_deadline=a.expires_at WHERE run_id=run;
 INSERT INTO oracle2.research_events_v1 VALUES(gen_random_uuid(),run,'claimed',clock_timestamp(),jsonb_build_object('claim_id',claim,'fetch_admission',appointment,'deadline',a.expires_at));
 RETURN jsonb_build_object('schema_version',1,'state','INFLIGHT','run_id',run,'claim_id',claim,'workspace_id',a.workspace_id,'source_id',a.source_id,
  'source_revision',a.source_revision,'definition',r.definition,'definition_sha256',r.definition_sha256,'valid_until',a.expires_at,'fetch_authorized',true,'context',oracle2._research_context_v1(a));
END $$;

-- Never accept client-supplied reference semantics as a fetched or reviewed fact.
-- This stores only exact custody metadata observed by the independently installed
-- fetch owner. Lost acknowledgements retain the original run and forbid retries.
CREATE FUNCTION oracle2.research_observe_fetch_v1(run uuid,claim uuid,observation bytea,appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;t oracle2.research_attempts_v1;h oracle2.research_run_heads_v1;o jsonb;seal text;delay interval;ok boolean;cadence text;stamp timestamptz;retrieved timestamptz;claimed_at timestamptz;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'fetch',runtime,registry,config,deadline);
 IF observation IS NULL OR octet_length(observation) NOT BETWEEN 1 AND 4096 THEN RAISE invalid_parameter_value; END IF;
 o:=convert_from(observation,'UTF8')::jsonb;seal:=encode(sha256(observation),'hex');
 IF jsonb_typeof(o)<>'object' OR NOT o ?& ARRAY['schema_version','state','http_status','wire_sha256','wire_byte_count','body_sha256','body_byte_count','private_key','trace_sha256','trace_byte_count','trace_private_key','retrieved_at']
 OR o-ARRAY['schema_version','state','http_status','wire_sha256','wire_byte_count','body_sha256','body_byte_count','private_key','trace_sha256','trace_byte_count','trace_private_key','retrieved_at']<>'{}'::jsonb
 OR convert_to(oracle2._replacement_metadata_json(o),'UTF8') IS DISTINCT FROM observation
 OR o->'schema_version' IS DISTINCT FROM '1'::jsonb
 OR jsonb_typeof(o->'state') IS DISTINCT FROM 'string' OR o->>'state' NOT IN('observed','known_failure','UNKNOWN')
 THEN RAISE invalid_parameter_value USING MESSAGE='closed actual fetch custody observation required'; END IF;
 SELECT * INTO t FROM oracle2.research_attempts_v1 WHERE run_id=run;
 IF (t.workspace_id,t.source_id,t.source_revision) IS DISTINCT FROM(a.workspace_id,a.source_id,a.source_revision) THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO h FROM oracle2.research_run_heads_v1 WHERE run_id=run FOR UPDATE;
 IF h.claim_id IS DISTINCT FROM claim OR h.fetch_admission IS DISTINCT FROM appointment THEN RAISE insufficient_privilege; END IF;
 IF EXISTS(SELECT 1 FROM oracle2.research_events_v1 WHERE run_id=run AND payload->>'observation_sha256'=seal) THEN
  RETURN jsonb_build_object('schema_version',1,'state','duplicate','run_id',run,'resend_authorized',false,'context',oracle2._research_context_v1(a));
 END IF;
 IF h.state='observed' THEN RAISE unique_violation USING MESSAGE='conflicting retained terminal fetch outcome'; END IF;
 IF h.state NOT IN('INFLIGHT','UNKNOWN') THEN RAISE insufficient_privilege; END IF;
 IF o->>'state'<>'UNKNOWN' AND (jsonb_typeof(o->'wire_sha256') IS DISTINCT FROM 'string'
  OR jsonb_typeof(o->'body_sha256') IS DISTINCT FROM 'string'
  OR o->>'wire_sha256' !~ '^[a-f0-9]{64}$' OR o->>'body_sha256' !~ '^[a-f0-9]{64}$'
  OR jsonb_typeof(o->'wire_byte_count') IS DISTINCT FROM 'number' OR jsonb_typeof(o->'body_byte_count') IS DISTINCT FROM 'number'
  OR (o->>'wire_byte_count')::integer NOT BETWEEN 1 AND 1064960 OR (o->>'body_byte_count')::integer NOT BETWEEN 0 AND 1048576
  OR o->>'private_key' IS DISTINCT FROM 'research/'||a.workspace_id::text||'/'||a.source_id::text||'/'||run::text||'/'||claim::text||'.wire'
  OR jsonb_typeof(o->'trace_sha256') IS DISTINCT FROM 'string' OR o->>'trace_sha256' !~ '^[a-f0-9]{64}$'
  OR jsonb_typeof(o->'trace_byte_count') IS DISTINCT FROM 'number' OR (o->>'trace_byte_count')::integer NOT BETWEEN 1 AND 65536
  OR o->>'trace_private_key' IS DISTINCT FROM 'research/'||a.workspace_id::text||'/'||a.source_id::text||'/'||run::text||'/'||claim::text||'.trace.json'
  OR jsonb_typeof(o->'http_status') IS DISTINCT FROM 'number' OR (o->>'http_status')::integer NOT BETWEEN 200 AND 599)
 THEN RAISE invalid_parameter_value USING MESSAGE='exact retained original response required'; END IF;
 ok:=o->>'state'='observed' AND o->'http_status'='200'::jsonb;
 IF o->>'state'='observed' AND NOT ok THEN RAISE invalid_parameter_value; END IF;
 stamp:=clock_timestamp();
 IF o->>'state'<>'UNKNOWN' THEN
  IF jsonb_typeof(o->'retrieved_at') IS DISTINCT FROM 'string'
   OR o->>'retrieved_at' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|\+00:00)$' THEN RAISE invalid_parameter_value; END IF;
  retrieved:=(o->>'retrieved_at')::timestamptz;
  SELECT recorded_at INTO claimed_at FROM oracle2.research_events_v1 WHERE run_id=run AND kind='claimed' AND payload->>'claim_id'=claim::text;
  IF NOT isfinite(retrieved) OR claimed_at IS NULL OR retrieved<claimed_at OR retrieved>least(stamp,h.claim_deadline) THEN
   RAISE invalid_parameter_value USING MESSAGE='original actual retrieval time required'; END IF;
 END IF;
 IF a.expires_at<=stamp THEN RAISE insufficient_privilege; END IF;
 INSERT INTO oracle2.research_events_v1 VALUES(gen_random_uuid(),run,CASE WHEN o->>'state'='UNKNOWN' THEN 'UNKNOWN' ELSE 'observed' END,stamp,jsonb_build_object('claim_id',claim,'observation',o,'observation_sha256',seal));
 UPDATE oracle2.research_run_heads_v1 SET state=CASE WHEN o->>'state'='UNKNOWN' THEN 'UNKNOWN' ELSE 'observed' END,observation_sha256=seal WHERE run_id=run;
 IF o->>'state'<>'UNKNOWN' THEN
  SELECT definition->>'cadence' INTO cadence FROM oracle2.research_registrations_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
  delay:=CASE WHEN ok OR t.attempt>=4 THEN CASE WHEN cadence='weekly' THEN interval '7 days' ELSE interval '91 days' END
   WHEN t.attempt=1 THEN interval '15 minutes' WHEN t.attempt=2 THEN interval '1 hour' ELSE interval '6 hours' END;
  UPDATE oracle2.research_state_v1 SET inflight=NULL,next_due=CASE WHEN ok THEN retrieved ELSE stamp END+delay,
   last_success=CASE WHEN ok THEN retrieved ELSE last_success END,attempts=CASE WHEN ok THEN 0 ELSE attempts END,
   exhausted=NOT ok AND t.attempt>=4 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision AND inflight=run;
 END IF;
 RETURN jsonb_build_object('schema_version',1,'state',CASE WHEN o->>'state'='UNKNOWN' THEN 'UNKNOWN' ELSE 'observed' END,'run_id',run,'resend_authorized',false,'context',oracle2._research_context_v1(a));
END $$;

CREATE FUNCTION oracle2.research_status_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;s oracle2.research_state_v1;r oracle2.research_registrations_v1;h oracle2.research_run_heads_v1;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'read',runtime,registry,config,deadline);
 SELECT * INTO r FROM oracle2.research_registrations_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 SELECT * INTO s FROM oracle2.research_state_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 SELECT * INTO h FROM oracle2.research_run_heads_v1 WHERE run_id=s.inflight;
 RETURN jsonb_build_object('schema_version',1,'workspace_id',a.workspace_id,'source_id',a.source_id,'source_revision',a.source_revision,
  'publisher',r.definition->>'publisher','original_url',r.definition->>'url','access',r.definition->>'access','cadence',r.definition->>'cadence',
  'last_success',s.last_success,'next_due',CASE WHEN isfinite(s.next_due) THEN s.next_due ELSE NULL END,
  'attempts',coalesce(s.attempts,0),'exhausted',coalesce(s.exhausted,false),'run_id',s.inflight,
  'state',CASE WHEN r.definition->'enabled'<>'true'::jsonb THEN 'disabled'
   WHEN r.definition->>'access'<>'public' AND r.definition->'rights_confirmed'<>'true'::jsonb THEN 'rights_gap'
   WHEN h.state='INFLIGHT' AND h.claim_deadline<=clock_timestamp() THEN 'UNKNOWN' ELSE coalesce(h.state,'idle') END,
  'company_policy',false,'semantically_reviewed',false,'valid_until',a.expires_at,'context',oracle2._research_context_v1(a));
END $$;

CREATE FUNCTION oracle2._research_context_v1(a oracle2.research_admissions_v1)
 RETURNS jsonb LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT jsonb_build_object('admission_id',(a).admission_id,'principal_id',(a).principal_id,'workspace_id',(a).workspace_id,
  'source_id',(a).source_id,'source_revision',(a).source_revision,'session_role',(a).role_name,'operation',(a).operation,
  'runtime_hash',(a).runtime_hash,'registry_hash',(a).registry_hash,'config_hash',(a).config_hash,
  'issuer_actor',(a).issuer_actor,'reviewer_actor',(a).reviewer_actor,'valid_until',(a).expires_at)
$$;

-- Metadata-only reconciliation of an already claimed operation. This never
-- returns a dispatchable definition or extends the original fetch deadline.
CREATE FUNCTION oracle2.research_latest_reference_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;r oracle2.research_registrations_v1;e oracle2.research_events_v1;t oracle2.research_attempts_v1;h oracle2.research_run_heads_v1;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'read',runtime,registry,config,deadline);
 SELECT * INTO r FROM oracle2.research_registrations_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 IF r.definition->'enabled'='true'::jsonb AND (r.definition->>'access'='public' OR r.definition->'rights_confirmed'='true'::jsonb) THEN
  SELECT ev.* INTO e FROM oracle2.research_events_v1 ev JOIN oracle2.research_attempts_v1 x USING(run_id)
   WHERE (x.workspace_id,x.source_id,x.source_revision)=(a.workspace_id,a.source_id,a.source_revision)
   AND ev.kind='observed' AND ev.payload->'observation'->>'state'='observed'
   AND ev.payload->'observation'->'http_status'='200'::jsonb ORDER BY ev.recorded_at DESC,ev.event_id LIMIT 1;
 END IF;
 IF e.event_id IS NOT NULL THEN
  SELECT * INTO t FROM oracle2.research_attempts_v1 WHERE run_id=e.run_id;
  SELECT * INTO h FROM oracle2.research_run_heads_v1 WHERE run_id=e.run_id;
 END IF;
 RETURN jsonb_build_object('schema_version',1,'state',CASE WHEN e.event_id IS NULL THEN 'unavailable' ELSE 'available' END,
  'workspace_id',a.workspace_id,'source_id',a.source_id,'source_revision',a.source_revision,'definition',r.definition,'definition_sha256',r.definition_sha256,
  'run_id',e.run_id,'claim_id',h.claim_id,'original_deadline',h.claim_deadline,'receipt_event_id',e.event_id,'recorded_at',e.recorded_at,
  'observation',e.payload->'observation','company_policy',false,'semantically_reviewed',false,'context',oracle2._research_context_v1(a));
END $$;

CREATE FUNCTION oracle2.research_retained_fetch_v1(run uuid,appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;t oracle2.research_attempts_v1;h oracle2.research_run_heads_v1;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'fetch',runtime,registry,config,deadline);
 SELECT * INTO t FROM oracle2.research_attempts_v1 WHERE run_id=run;
 IF (t.workspace_id,t.source_id,t.source_revision) IS DISTINCT FROM(a.workspace_id,a.source_id,a.source_revision) THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO h FROM oracle2.research_run_heads_v1 WHERE run_id=run;
 IF h.fetch_admission IS DISTINCT FROM appointment OR h.claim_id IS NULL THEN RAISE insufficient_privilege; END IF;
 RETURN jsonb_build_object('schema_version',1,'run_id',run,'claim_id',h.claim_id,'state',h.state,
  'original_deadline',h.claim_deadline,'resend_authorized',false,'context',oracle2._research_context_v1(a));
END $$;

CREATE FUNCTION oracle2.research_current_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;wanted text;
BEGIN
 SELECT operation INTO wanted FROM oracle2.research_admissions_v1 WHERE admission_id=appointment;
 a:=oracle2._research_admission_v1(appointment,wanted,runtime,registry,config,deadline);
 RETURN jsonb_build_object('schema_version',1,'context',oracle2._research_context_v1(a));
END $$;

CREATE FUNCTION oracle2.research_force_due_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.research_admissions_v1;s oracle2.research_state_v1;
BEGIN
 a:=oracle2._research_admission_v1(appointment,'schedule',runtime,registry,config,deadline);
 INSERT INTO oracle2.research_state_v1(workspace_id,source_id,revision) VALUES(a.workspace_id,a.source_id,a.source_revision) ON CONFLICT DO NOTHING;
 SELECT * INTO s FROM oracle2.research_state_v1 WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision FOR UPDATE;
 IF s.inflight IS NOT NULL OR s.exhausted THEN
  RETURN jsonb_build_object('schema_version',1,'state',CASE WHEN s.inflight IS NOT NULL THEN 'existing' ELSE 'exhausted' END,
   'run_id',s.inflight,'dispatch_authorized',false,'context',oracle2._research_context_v1(a));
 END IF;
 IF a.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 UPDATE oracle2.research_state_v1 SET next_due=clock_timestamp() WHERE workspace_id=a.workspace_id AND source_id=a.source_id AND revision=a.source_revision;
 RETURN jsonb_build_object('schema_version',1,'state','due','dispatch_authorized',false,'context',oracle2._research_context_v1(a));
END $$;

DO $private$ DECLARE t text;f record; BEGIN
 FOREACH t IN ARRAY ARRAY['research_registrations_v1','research_admissions_v1','research_admission_revocations_v1','research_state_v1','research_attempts_v1','research_run_heads_v1','research_events_v1'] LOOP
  EXECUTE format('REVOKE ALL ON oracle2.%I FROM PUBLIC',t);
 END LOOP;
 FOR f IN SELECT p.oid::regprocedure signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='oracle2' AND (p.proname LIKE 'research\_%\_v1' ESCAPE '\' OR p.proname IN('_research_admission_v1','_research_context_v1')) LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.signature);
 END LOOP;
END $private$;
