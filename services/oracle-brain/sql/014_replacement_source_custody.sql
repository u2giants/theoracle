-- Dedicated Oracle ledger only. Additive source custody; no admission issuance.
-- Source-only candidate: installer must pin trusted owner and exact target.
DO $owner$
DECLARE owner_oid oid;
BEGIN
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR owner_oid IS DISTINCT FROM (SELECT proowner FROM pg_proc WHERE oid=to_regprocedure('oracle2._processing_source(uuid,uuid,uuid,text,text,boolean)')) THEN
  RAISE EXCEPTION 'reviewed dedicated schema/helper owner required';
 END IF;
END $owner$;
DO $groups$
DECLARE group_name text;
BEGIN
 FOREACH group_name IN ARRAY ARRAY['oracle2_source_original_reader','oracle2_source_original_reviewer','oracle2_source_original_viewer','oracle2_replacement_requester'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=group_name) THEN
   EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',group_name);
  END IF;
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=group_name AND (rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
   OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=group_name)) THEN
   RAISE EXCEPTION 'unsafe exclusive replacement group';
  END IF;
  EXECUTE format('REVOKE ALL ON SCHEMA oracle2 FROM %I',group_name);
  EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA oracle2 FROM %I',group_name);
  EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA oracle2 FROM %I',group_name);
  EXECUTE format('GRANT USAGE ON SCHEMA oracle2 TO %I',group_name);
 END LOOP;
END $groups$;
CREATE UNIQUE INDEX IF NOT EXISTS sources_workspace_identity ON oracle2.sources(workspace_id,source_id);
CREATE TABLE IF NOT EXISTS oracle2.source_original_revisions (
 workspace_id uuid NOT NULL,source_id uuid NOT NULL,revision integer NOT NULL CHECK(revision>0),
 original_sha256 text NOT NULL CHECK(original_sha256 ~ '^[0-9a-f]{64}$'),
 byte_count bigint NOT NULL CHECK(byte_count>0 AND byte_count<=26214400),media_type text NOT NULL CHECK(length(media_type) BETWEEN 1 AND 255),
 filename text NOT NULL CHECK(length(filename) BETWEEN 1 AND 255),
 custody_locator_seal_sha256 text NOT NULL CHECK(custody_locator_seal_sha256 ~ '^[0-9a-f]{64}$'),
 private_object_key text NOT NULL CHECK(length(private_object_key) BETWEEN 1 AND 1024),uploaded_by uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,source_id,revision),
 FOREIGN KEY(workspace_id,source_id) REFERENCES oracle2.sources(workspace_id,source_id));
CREATE TABLE IF NOT EXISTS oracle2.original_source_populations_v1 (
 population_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,
 purpose text NOT NULL CHECK(purpose IN('source-original-reading','source-original-review')),
 original_root_hash text NOT NULL CHECK(original_root_hash ~ '^[0-9a-f]{64}$'),
 population_digest text NOT NULL CHECK(population_digest ~ '^[0-9a-f]{64}$'),
 operation_registry_hash text NOT NULL CHECK(operation_registry_hash ~ '^[0-9a-f]{64}$'),
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),
 source_registry_hash text NOT NULL CHECK(source_registry_hash ~ '^[0-9a-f]{64}$'),
 original_allocation_hash text NOT NULL CHECK(original_allocation_hash ~ '^[0-9a-f]{64}$'),
 original_horizon timestamptz NOT NULL CHECK(isfinite(original_horizon)),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL CHECK(issuer_actor<>reviewer_actor),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at) AND expires_at<=original_horizon));
CREATE TABLE IF NOT EXISTS oracle2.original_source_population_members_v1 (
 population_id uuid NOT NULL REFERENCES oracle2.original_source_populations_v1(population_id),
 ordinal integer NOT NULL CHECK(ordinal BETWEEN 0 AND 4095),workspace_id uuid NOT NULL,source_id uuid NOT NULL,revision integer NOT NULL,
 raw_ref_sha256 text NOT NULL CHECK(raw_ref_sha256 ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(population_id,ordinal),UNIQUE(population_id,source_id),
 FOREIGN KEY(workspace_id,source_id,revision) REFERENCES oracle2.source_original_revisions(workspace_id,source_id,revision));
CREATE TABLE IF NOT EXISTS oracle2.hosting_original_population_admissions_v1 (
 role_name name NOT NULL,population_id uuid NOT NULL REFERENCES oracle2.original_source_populations_v1(population_id),
 principal_id uuid NOT NULL,purpose text NOT NULL CHECK(purpose IN('source-original-reading','source-original-review')),
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),
 source_registry_hash text NOT NULL CHECK(source_registry_hash ~ '^[0-9a-f]{64}$'),
 operation_registry_hash text NOT NULL CHECK(operation_registry_hash ~ '^[0-9a-f]{64}$'),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),PRIMARY KEY(role_name,population_id));
CREATE TABLE IF NOT EXISTS oracle2.source_reading_qualifications (
 workspace_id uuid NOT NULL,source_id uuid NOT NULL,revision integer NOT NULL,
 original_sha256 text NOT NULL CHECK(original_sha256 ~ '^[0-9a-f]{64}$'),
 reading_sha256 text NOT NULL CHECK(reading_sha256 ~ '^[0-9a-f]{64}$'),parser_id text NOT NULL CHECK(length(parser_id) BETWEEN 1 AND 255),
 view_manifest_sha256 text NOT NULL CHECK(view_manifest_sha256 ~ '^[0-9a-f]{64}$'),
 locator_map_sha256 text NOT NULL CHECK(locator_map_sha256 ~ '^[0-9a-f]{64}$'),
 reader_native_commit_sha256 text NOT NULL CHECK(reader_native_commit_sha256 ~ '^[0-9a-f]{64}$'),
 reviewer_native_commit_sha256 text NOT NULL CHECK(reviewer_native_commit_sha256 ~ '^[0-9a-f]{64}$'),
 reader_principal_id uuid NOT NULL,reviewer_principal_id uuid NOT NULL CHECK(reviewer_principal_id<>reader_principal_id),
 qualified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,source_id,revision),
 FOREIGN KEY(workspace_id,source_id,revision) REFERENCES oracle2.source_original_revisions(workspace_id,source_id,revision));
CREATE TABLE IF NOT EXISTS oracle2.hosting_original_source_admissions (
 role_name name NOT NULL,workspace_id uuid NOT NULL,source_id uuid NOT NULL,revision integer NOT NULL,
 principal_id uuid NOT NULL,original_sha256 text NOT NULL CHECK(original_sha256 ~ '^[0-9a-f]{64}$'),
 purpose text NOT NULL CHECK(purpose IN ('source-original-reading','source-original-review','source-original-view')),
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),registry_hash text NOT NULL CHECK(registry_hash ~ '^[0-9a-f]{64}$'),
 population_id uuid REFERENCES oracle2.original_source_populations_v1(population_id),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 CHECK((purpose='source-original-view')=(population_id IS NULL)),
 PRIMARY KEY(role_name,workspace_id,source_id,revision),
 FOREIGN KEY(workspace_id,source_id,revision) REFERENCES oracle2.source_original_revisions(workspace_id,source_id,revision));
CREATE TABLE IF NOT EXISTS oracle2.hosting_request_principal_admissions (
 role_name name PRIMARY KEY,principal_id uuid NOT NULL,workspace_id uuid NOT NULL,
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),registry_hash text NOT NULL CHECK(registry_hash ~ '^[0-9a-f]{64}$'),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)));
CREATE TABLE IF NOT EXISTS oracle2.source_intake_reservations_v1 (
 reservation_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,source_id uuid NOT NULL,principal_id uuid NOT NULL,
 expected_head integer NOT NULL CHECK(expected_head>=0),revision integer NOT NULL CHECK(revision=expected_head+1),
 filename text NOT NULL CHECK(length(filename) BETWEEN 1 AND 255),media_type text NOT NULL CHECK(length(media_type) BETWEEN 1 AND 255),
 byte_count bigint NOT NULL CHECK(byte_count>0 AND byte_count<=26214400),private_object_key text NOT NULL,
 idempotency_key uuid NOT NULL,request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 original_sha256 text CHECK(original_sha256 ~ '^[0-9a-f]{64}$'),custody_seal_sha256 text CHECK(custody_seal_sha256 ~ '^[0-9a-f]{64}$'),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),finalized_at timestamptz,
 UNIQUE(workspace_id,principal_id,idempotency_key));
CREATE TABLE IF NOT EXISTS oracle2.processing_journey_runs_v1 (
 run_id uuid PRIMARY KEY REFERENCES oracle2.runs(run_id),workspace_id uuid NOT NULL,actor_id uuid NOT NULL,
 schema_version integer NOT NULL DEFAULT 1 CHECK(schema_version=1),journey_revision integer NOT NULL CHECK(journey_revision>0),
 population_sha256 text NOT NULL CHECK(population_sha256 ~ '^[0-9a-f]{64}$'),original_population jsonb NOT NULL CHECK(jsonb_typeof(original_population)='array'),
 summary_targets jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(summary_targets)='array' AND jsonb_array_length(summary_targets)<=64),
 current_model_id uuid,current_model_version integer CHECK(current_model_version>0),current_model_content_hash text CHECK(current_model_content_hash ~ '^[0-9a-f]{64}$'),
 current_ack_event_id uuid REFERENCES oracle2.outbox(event_id),
 state text NOT NULL CHECK(state IN ('pending','processing','delivered','revision_pending','cancelled','error')),
 answer_hold boolean NOT NULL DEFAULT true,cancelled_at timestamptz,
 CHECK((current_model_id IS NULL)=(current_model_version IS NULL)),CHECK((current_model_id IS NULL)=(current_model_content_hash IS NULL)));
CREATE TABLE IF NOT EXISTS oracle2.replacement_journey_events (
 event_id uuid PRIMARY KEY,run_id uuid NOT NULL REFERENCES oracle2.processing_journey_runs_v1(run_id),workspace_id uuid NOT NULL,
 journey_revision integer NOT NULL CHECK(journey_revision>0),actor_id uuid NOT NULL,
 action text NOT NULL CHECK(action IN ('create','correct','confirm','cancel','withdraw')),
 payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
 idempotency_key uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(run_id,journey_revision),UNIQUE(workspace_id,actor_id,idempotency_key));
CREATE TABLE IF NOT EXISTS oracle2.hosting_replacement_executor_runs_v1 (
 role_name name NOT NULL,run_id uuid NOT NULL REFERENCES oracle2.processing_journey_runs_v1(run_id),workspace_id uuid NOT NULL,
 principal_id uuid NOT NULL,runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),
 source_registry_hash text NOT NULL CHECK(source_registry_hash ~ '^[0-9a-f]{64}$'),
 population_sha256 text NOT NULL CHECK(population_sha256 ~ '^[0-9a-f]{64}$'),
 model_id uuid NOT NULL,model_version integer NOT NULL CHECK(model_version>0),model_content_hash text NOT NULL CHECK(model_content_hash ~ '^[0-9a-f]{64}$'),
 ack_event_id uuid NOT NULL REFERENCES oracle2.outbox(event_id),projection_digest text NOT NULL CHECK(projection_digest ~ '^[0-9a-f]{64}$'),
 summary_targets_sha256 text NOT NULL CHECK(summary_targets_sha256 ~ '^[0-9a-f]{64}$'),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),PRIMARY KEY(role_name,run_id),
 FOREIGN KEY(workspace_id,model_id,model_version) REFERENCES oracle2.artifact_manifests(workspace_id,artifact_id,version));
-- No runtime receives direct table access. Exact named capabilities follow.
REVOKE ALL ON oracle2.source_original_revisions,oracle2.source_reading_qualifications,
 oracle2.original_source_populations_v1,oracle2.original_source_population_members_v1,oracle2.hosting_original_population_admissions_v1,
 oracle2.hosting_original_source_admissions,oracle2.hosting_request_principal_admissions,
 oracle2.source_intake_reservations_v1,oracle2.processing_journey_runs_v1,oracle2.replacement_journey_events
 ,oracle2.hosting_replacement_executor_runs_v1
 FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

-- Only strict seal metadata uses this encoder: no decimal/float interpretation.
-- Arrays retain order and object keys use the same UTF-8 canonical ordering as
-- the application. A byte commitment must equal this output before hashing.
CREATE OR REPLACE FUNCTION oracle2._replacement_metadata_json(value jsonb)
 RETURNS text LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE result text;
BEGIN
 CASE jsonb_typeof(value)
 WHEN 'object' THEN
  SELECT '{'||coalesce(string_agg(to_jsonb(x.key)::text||':'||oracle2._replacement_metadata_json(x.value),',' ORDER BY x.key COLLATE "C"),'')||'}'
   INTO result FROM jsonb_each(value) x;
 WHEN 'array' THEN
  SELECT '['||coalesce(string_agg(oracle2._replacement_metadata_json(x.value),',' ORDER BY x.ordinality),'')||']'
   INTO result FROM jsonb_array_elements(value) WITH ORDINALITY x;
 WHEN 'number' THEN
  IF value::text !~ '^-?[0-9]+$' THEN RAISE invalid_parameter_value USING MESSAGE='integer seal metadata required'; END IF;
  result:=value::text;
 WHEN 'string','boolean','null' THEN result:=value::text;
 ELSE RAISE invalid_parameter_value USING MESSAGE='strict seal metadata required';
 END CASE;
 RETURN result;
END $body$;
REVOKE ALL ON FUNCTION oracle2._replacement_metadata_json(jsonb) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2._replacement_request_context()
 RETURNS oracle2.hosting_request_principal_admissions LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;r oracle2.hosting_role_runtime_admissions%ROWTYPE;
 owner_oid oid;login_oid oid;group_oid oid;initial_workspace uuid;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl) THEN
  RAISE insufficient_privilege USING MESSAGE='TLS replacement session required';
 END IF;
 IF current_setting('statement_timeout')='0' OR current_setting('statement_timeout')::interval>interval '5 seconds' THEN
  RAISE insufficient_privilege USING MESSAGE='bounded replacement statement required';
 END IF;
 IF current_setting('lock_timeout')='0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN
  PERFORM set_config('lock_timeout','2s',true);
 END IF;
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 SELECT oid INTO login_oid FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin
  AND NOT(rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
 SELECT oid INTO group_oid FROM pg_roles WHERE rolname='oracle2_replacement_requester' AND NOT(rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
 IF login_oid IS NULL OR group_oid IS NULL OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR NOT pg_has_role(login_oid,group_oid,'MEMBER')
 OR current_setting('role') NOT IN ('none',SESSION_USER::text,'oracle2_replacement_requester')
 OR EXISTS(SELECT 1 FROM pg_roles x WHERE x.oid NOT IN(login_oid,group_oid)
  AND(pg_has_role(login_oid,x.oid,'MEMBER') OR pg_has_role(login_oid,x.oid,'SET') OR pg_has_role(login_oid,x.oid,'USAGE'))) THEN
  RAISE insufficient_privilege USING MESSAGE='exclusive replacement session denied';
 END IF;
 SELECT workspace_id INTO initial_workspace FROM oracle2.hosting_request_principal_admissions WHERE role_name=SESSION_USER;
 IF initial_workspace IS NULL THEN RAISE insufficient_privilege USING MESSAGE='current replacement identity denied'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||initial_workspace::text));
 SELECT * INTO a FROM oracle2.hosting_request_principal_admissions WHERE role_name=SESSION_USER FOR SHARE;
 SELECT * INTO r FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 IF a.role_name IS NULL OR a.workspace_id IS DISTINCT FROM initial_workspace OR r.role_name IS NULL OR a.runtime_hash IS DISTINCT FROM r.runtime_hash
 OR a.registry_hash IS DISTINCT FROM r.registry_hash OR a.expires_at<=clock_timestamp()
 OR r.expires_at<=clock_timestamp() OR NOT isfinite(r.expires_at) THEN
  RAISE insufficient_privilege USING MESSAGE='current replacement identity denied';
 END IF;
 a.expires_at:=least(a.expires_at,r.expires_at);RETURN a;
END $body$;
REVOKE ALL ON FUNCTION oracle2._replacement_request_context() FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2._replacement_scope(workspace uuid,principal uuid,required_scope text)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE deadline timestamptz;permitted boolean;
BEGIN
 PERFORM 1 FROM oracle2.appointments p WHERE p.workspace_id=workspace ORDER BY p.appointment_id FOR SHARE;
 WITH RECURSIVE lineage AS (
  SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.actor_id,p.granted_by,
   ARRAY[p.appointment_id] seen,true valid,1 depth
  FROM oracle2.appointments p WHERE p.workspace_id=workspace AND p.actor_id=principal AND p.scope IN(required_scope,'root')
  UNION ALL
  SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.actor_id,p.granted_by,
   l.seen||p.appointment_id,l.valid AND p.actor_id=l.granted_by AND p.scope IN(required_scope,'root'),l.depth+1
  FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id
  WHERE p.workspace_id=workspace AND l.depth<16 AND NOT p.appointment_id=ANY(l.seen)),
 valid_paths AS(SELECT min(expires_at) expiry FROM lineage GROUP BY start_id HAVING
  bool_and(valid AND revoked_at IS NULL AND(expires_at IS NULL OR expires_at>clock_timestamp()))
  AND bool_or(scope='root' AND parent_id IS NULL))
 SELECT EXISTS(SELECT 1 FROM valid_paths),max(coalesce(expiry,'infinity'::timestamptz)) INTO permitted,deadline FROM valid_paths;
 IF NOT permitted THEN RAISE insufficient_privilege USING MESSAGE='current replacement scope denied'; END IF;
 RETURN deadline;
END $body$;
REVOKE ALL ON FUNCTION oracle2._replacement_scope(uuid,uuid,text) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2._replacement_private_context(a oracle2.hosting_request_principal_admissions,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
BEGIN
 IF a.role_name IS DISTINCT FROM SESSION_USER OR NOT isfinite(deadline) OR deadline<=clock_timestamp()
 OR deadline>a.expires_at THEN
  RAISE insufficient_privilege USING MESSAGE='current replacement identity denied';
 END IF;
 RETURN jsonb_build_object('principal_id',a.principal_id,'workspace_id',a.workspace_id,'session_role',SESSION_USER,
  'runtime_hash',a.runtime_hash,'source_registry_hash',a.registry_hash,'checked_at',clock_timestamp(),'valid_until',deadline);
END $body$;
REVOKE ALL ON FUNCTION oracle2._replacement_private_context(oracle2.hosting_request_principal_admissions,timestamptz) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2.reserve_source_revision_v1(expected_head integer,intake jsonb,idempotency uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;prior oracle2.source_intake_reservations_v1%ROWTYPE;
 source uuid;reservation uuid;head integer;request_hash text;until timestamptz;caller_deadline timestamptz;scope_until timestamptz;key text;
BEGIN
 a:=oracle2._replacement_request_context();
 IF expected_head IS NULL OR expected_head<0 OR idempotency IS NULL OR jsonb_typeof(intake) IS DISTINCT FROM 'object'
 OR NOT intake ?& ARRAY['source_id','filename','media_type','byte_count','caller_deadline'] OR (intake-ARRAY['source_id','filename','media_type','byte_count','caller_deadline'])<>'{}'::jsonb
 OR jsonb_typeof(intake->'source_id') NOT IN ('null','string') OR jsonb_typeof(intake->'filename') IS DISTINCT FROM 'string'
 OR length(intake->>'filename') NOT BETWEEN 1 AND 255 OR intake->>'filename' ~ E'[/\\\\[:cntrl:]]'
 OR jsonb_typeof(intake->'media_type') IS DISTINCT FROM 'string'
 OR intake->>'media_type' NOT IN('application/pdf','text/plain') OR jsonb_typeof(intake->'byte_count') IS DISTINCT FROM 'number'
 OR (intake->>'byte_count')::numeric<>trunc((intake->>'byte_count')::numeric)
 OR (intake->>'byte_count')::numeric NOT BETWEEN 1 AND 26214400
 OR jsonb_typeof(intake->'caller_deadline') IS DISTINCT FROM 'string'
 OR intake->>'caller_deadline' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
  RAISE invalid_parameter_value USING MESSAGE='strict replacement intake required';
 END IF;
 caller_deadline:=(intake->>'caller_deadline')::timestamptz;
 IF NOT isfinite(caller_deadline) OR caller_deadline<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='replacement caller deadline expired';
 END IF;
 until:=least(a.expires_at,caller_deadline,oracle2._replacement_scope(a.workspace_id,a.principal_id,'intake'));
 request_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('expected_head',expected_head,'intake',intake)),'UTF8')),'hex');
 SELECT * INTO prior FROM oracle2.source_intake_reservations_v1 r WHERE r.workspace_id=a.workspace_id
 AND r.principal_id=a.principal_id AND r.idempotency_key=idempotency FOR UPDATE;
 IF prior.reservation_id IS NOT NULL THEN
  IF prior.request_sha256 IS DISTINCT FROM request_hash THEN
   RAISE unique_violation USING MESSAGE='replacement idempotency conflict';
  END IF;
  IF prior.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='replacement intake expired'; END IF;
  IF prior.expected_head>0 THEN
   PERFORM oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||prior.source_id::text);
  END IF;
  RETURN jsonb_build_object('schema_version',1,'context',oracle2._replacement_private_context(a,least(until,prior.expires_at)),
   'reservation',jsonb_build_object('reservation_id',prior.reservation_id,'source_id',prior.source_id,'revision',prior.revision,
   'expires_at',prior.expires_at,'private_object_key',prior.private_object_key));
 END IF;
 IF intake->>'source_id' IS NULL THEN
  IF expected_head<>0 THEN RAISE serialization_failure USING MESSAGE='replacement revision conflict'; END IF;
  source:=gen_random_uuid();
 ELSE
  source:=(intake->>'source_id')::uuid;
  PERFORM oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||source::text);
  SELECT revision INTO head FROM oracle2.sources WHERE workspace_id=a.workspace_id AND source_id=source FOR UPDATE;
  IF head IS NULL OR head<>expected_head OR expected_head=0 THEN
   RAISE serialization_failure USING MESSAGE='replacement revision conflict';
  END IF;
 END IF;
 reservation:=gen_random_uuid();key:='source-originals/'||a.workspace_id::text||'/'||source::text||'/'||(expected_head+1)::text||'/'||reservation::text;
 -- Deadline is original admission/grant horizon, never renewed on replay.
 IF until<=clock_timestamp() OR NOT isfinite(until) THEN RAISE insufficient_privilege USING MESSAGE='replacement intake expired'; END IF;
 INSERT INTO oracle2.source_intake_reservations_v1(reservation_id,workspace_id,source_id,principal_id,expected_head,revision,
  filename,media_type,byte_count,private_object_key,idempotency_key,request_sha256,expires_at)
 VALUES(reservation,a.workspace_id,source,a.principal_id,expected_head,expected_head+1,intake->>'filename',intake->>'media_type',
  (intake->>'byte_count')::bigint,key,idempotency,request_hash,until);
 PERFORM oracle2._replacement_scope(a.workspace_id,a.principal_id,'intake');
 IF until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='replacement intake expired'; END IF;
 RETURN jsonb_build_object('schema_version',1,'context',oracle2._replacement_private_context(a,until),
  'reservation',jsonb_build_object('reservation_id',reservation,'source_id',source,'revision',expected_head+1,'expires_at',until,'private_object_key',key));
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_datetime_format OR datetime_field_overflow THEN
 RAISE invalid_parameter_value USING MESSAGE='strict replacement intake required';
END $body$;
REVOKE ALL ON FUNCTION oracle2.reserve_source_revision_v1(integer,jsonb,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.reserve_source_revision_v1(integer,jsonb,uuid) TO oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2._replacement_affected(workspace uuid,source uuid)
 RETURNS TABLE(artifact_id uuid,version integer) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 WITH RECURSIVE affected(artifact_id,version) AS (
  SELECT d.artifact_id,d.version FROM oracle2.artifact_dependencies d
   WHERE d.workspace_id=workspace AND d.upstream_kind='source' AND d.upstream_id=source::text
  UNION
  SELECT d.artifact_id,d.version FROM oracle2.artifact_dependencies d JOIN affected a
   ON d.upstream_kind='artifact' AND d.upstream_id=a.artifact_id::text AND d.upstream_revision=a.version::text
   WHERE d.workspace_id=workspace
 ) SELECT a.artifact_id,a.version FROM affected a ORDER BY a.artifact_id,a.version;$$;
REVOKE ALL ON FUNCTION oracle2._replacement_affected(uuid,uuid) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

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
REVOKE ALL ON FUNCTION oracle2.finalize_source_revision_v1(uuid,integer,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.finalize_source_revision_v1(uuid,integer,jsonb) TO oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2._original_revision_member_access(source uuid,wanted_revision integer,wanted_group text)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_original_source_admissions%ROWTYPE;r oracle2.hosting_role_runtime_admissions%ROWTYPE;
 original oracle2.source_original_revisions%ROWTYPE;owner_oid oid;login_oid oid;group_oid oid;purpose_name text;
 initial_workspace uuid;current_revision integer;current_status text;deadline timestamptz;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl) THEN
  RAISE insufficient_privilege USING MESSAGE='TLS replacement session required';
 END IF;
 IF current_setting('statement_timeout')='0' OR current_setting('statement_timeout')::interval>interval '5 seconds' THEN
  RAISE insufficient_privilege USING MESSAGE='bounded original statement required';
 END IF;
 IF current_setting('lock_timeout')='0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN
  PERFORM set_config('lock_timeout','2s',true);
 END IF;
 purpose_name:=CASE wanted_group WHEN 'oracle2_source_original_reader' THEN 'source-original-reading'
  WHEN 'oracle2_source_original_reviewer' THEN 'source-original-review'
  WHEN 'oracle2_source_original_viewer' THEN 'source-original-view' ELSE NULL END;
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 SELECT oid INTO login_oid FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin
  AND NOT(rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
 SELECT oid INTO group_oid FROM pg_roles WHERE rolname=wanted_group AND NOT(rolcanlogin OR rolinherit OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
 IF purpose_name IS NULL OR login_oid IS NULL OR group_oid IS NULL
 OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR NOT pg_has_role(login_oid,group_oid,'MEMBER') OR current_setting('role') NOT IN('none',SESSION_USER::text,wanted_group)
 OR EXISTS(SELECT 1 FROM pg_roles x WHERE x.oid NOT IN(login_oid,group_oid)
  AND(pg_has_role(login_oid,x.oid,'MEMBER') OR pg_has_role(login_oid,x.oid,'SET') OR pg_has_role(login_oid,x.oid,'USAGE'))) THEN
  RAISE insufficient_privilege USING MESSAGE='exclusive original session denied';
 END IF;
 SELECT workspace_id INTO initial_workspace FROM oracle2.hosting_original_source_admissions
 WHERE role_name=SESSION_USER AND source_id=source AND revision=wanted_revision;
 IF initial_workspace IS NULL THEN RAISE insufficient_privilege USING MESSAGE='original admission denied'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||initial_workspace::text));
 SELECT * INTO a FROM oracle2.hosting_original_source_admissions WHERE role_name=SESSION_USER
 AND workspace_id=initial_workspace AND source_id=source AND revision=wanted_revision FOR SHARE;
 SELECT * INTO r FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 IF a.role_name IS NULL OR r.role_name IS NULL OR a.purpose IS DISTINCT FROM purpose_name
 OR a.runtime_hash IS DISTINCT FROM r.runtime_hash OR a.registry_hash IS DISTINCT FROM r.registry_hash
 OR a.expires_at<=clock_timestamp() OR r.expires_at<=clock_timestamp() OR NOT isfinite(r.expires_at) THEN
  RAISE insufficient_privilege USING MESSAGE='current original admission denied';
 END IF;
 SELECT revision,status INTO current_revision,current_status FROM oracle2.sources
 WHERE workspace_id=a.workspace_id AND source_id=source FOR SHARE;
 SELECT * INTO original FROM oracle2.source_original_revisions WHERE workspace_id=a.workspace_id
 AND source_id=source AND revision=wanted_revision FOR SHARE;
 LOCK TABLE oracle2.drafts IN SHARE MODE;
 IF EXISTS(SELECT 1 FROM oracle2.drafts d WHERE d.workspace_id=a.workspace_id AND d.source_id=source AND d.status='withdrawn')
 OR (SELECT count(*) FROM oracle2.drafts d WHERE d.workspace_id=a.workspace_id AND d.source_id=source)>1 THEN
  RAISE insufficient_privilege USING MESSAGE='original source withdrawn or ambiguous';
 END IF;
 IF current_revision IS DISTINCT FROM wanted_revision OR current_status NOT IN('processing','draft','confirmed')
 OR current_status IS NULL OR original.source_id IS NULL OR original.original_sha256 IS DISTINCT FROM a.original_sha256 THEN
  RAISE insufficient_privilege USING MESSAGE='exact current original revision denied';
 END IF;
 deadline:=least(a.expires_at,r.expires_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||source::text));
 IF purpose_name<>'source-original-view' THEN
  deadline:=least(deadline,oracle2._replacement_scope(a.workspace_id,a.principal_id,purpose_name||':'||source::text));
 END IF;
 IF deadline<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='original admission expired'; END IF;
 RETURN jsonb_build_object('schema_version',1,'workspace_id',a.workspace_id,'source_id',source,'revision',wanted_revision,
  'principal_id',a.principal_id,'original_sha256',original.original_sha256,'byte_count',original.byte_count,
  'media_type',original.media_type,'private_object_key',original.private_object_key,'runtime_hash',a.runtime_hash,
  'registry_hash',a.registry_hash,'population_id',a.population_id,'valid_until',deadline,'checked_at',clock_timestamp());
END $body$;
REVOKE ALL ON FUNCTION oracle2._original_revision_member_access(uuid,integer,text) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;
CREATE OR REPLACE FUNCTION oracle2._original_revision_access(source uuid,wanted_revision integer,wanted_group text)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE identity jsonb;population jsonb;
BEGIN
 identity:=oracle2._original_revision_member_access(source,wanted_revision,wanted_group);
 IF wanted_group<>'oracle2_source_original_viewer' THEN
  IF identity->>'population_id' IS NULL THEN RAISE insufficient_privilege USING MESSAGE='complete raw population required'; END IF;
  population:=oracle2.original_population_current_v1((identity->>'population_id')::uuid);
  identity:=identity||jsonb_build_object('valid_until',least((identity->>'valid_until')::timestamptz,(population->>'valid_until')::timestamptz));
 END IF;
 RETURN identity;
END $body$;
REVOKE ALL ON FUNCTION oracle2._original_revision_access(uuid,integer,text) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;
CREATE OR REPLACE FUNCTION oracle2.original_revision_read_v1(source uuid,revision integer)
 RETURNS jsonb LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT oracle2._original_revision_access(source,revision,'oracle2_source_original_reader');$$;
CREATE OR REPLACE FUNCTION oracle2.original_revision_view_v1(source uuid,revision integer)
 RETURNS jsonb LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT oracle2._original_revision_access(source,revision,'oracle2_source_original_viewer');$$;
CREATE OR REPLACE FUNCTION oracle2.original_revision_review_input_v1(source uuid,revision integer)
 RETURNS jsonb LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT oracle2._original_revision_access(source,revision,'oracle2_source_original_reviewer');$$;
REVOKE ALL ON FUNCTION oracle2.original_revision_read_v1(uuid,integer),oracle2.original_revision_view_v1(uuid,integer),
 oracle2.original_revision_review_input_v1(uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.original_revision_read_v1(uuid,integer) TO oracle2_source_original_reader;
GRANT EXECUTE ON FUNCTION oracle2.original_revision_view_v1(uuid,integer) TO oracle2_source_original_viewer;
GRANT EXECUTE ON FUNCTION oracle2.original_revision_review_input_v1(uuid,integer) TO oracle2_source_original_reviewer;

CREATE OR REPLACE FUNCTION oracle2.replacement_source_head_v1(source uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;s oracle2.sources%ROWTYPE;
 o oracle2.source_original_revisions%ROWTYPE;q oracle2.source_reading_qualifications%ROWTYPE;
 ref jsonb;until timestamptz;qualified boolean;
BEGIN
 a:=oracle2._replacement_request_context();
 until:=least(a.expires_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||source::text));
 SELECT * INTO s FROM oracle2.sources WHERE workspace_id=a.workspace_id AND source_id=source FOR SHARE;
 SELECT * INTO o FROM oracle2.source_original_revisions WHERE workspace_id=a.workspace_id AND source_id=source AND revision=s.revision FOR SHARE;
 IF s.source_id IS NULL OR s.status NOT IN('processing','draft','confirmed','error') OR o.source_id IS NULL THEN
  RAISE insufficient_privilege USING MESSAGE='replacement source unavailable';
 END IF;
 SELECT * INTO q FROM oracle2.source_reading_qualifications WHERE workspace_id=a.workspace_id AND source_id=source AND revision=s.revision FOR SHARE;
 qualified:=q.source_id IS NOT NULL AND q.original_sha256=o.original_sha256 AND EXISTS(
  SELECT 1 FROM oracle2.operating_model_source_receipts x WHERE x.workspace_id=a.workspace_id AND x.source_id=source
  AND x.revision=s.revision AND x.original_hash=q.original_sha256 AND x.reading_hash=q.reading_sha256 AND x.parser_id=q.parser_id);
 IF qualified THEN
  ref:=jsonb_build_object('workspaceId',a.workspace_id,'sourceId',source,'revision',s.revision,'originalSha256',q.original_sha256,
   'readingSha256',q.reading_sha256,'parserId',q.parser_id);
 ELSE ref:='null'::jsonb; END IF;
 IF until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='replacement source authority expired'; END IF;
 RETURN jsonb_build_object('sourceId',source,'revision',s.revision,'originalSha256',o.original_sha256,'byteCount',o.byte_count,
  'mediaType',o.media_type,'filename',s.filename,'state',CASE WHEN qualified THEN 'qualified' WHEN s.status='error' THEN 'reading_failed' ELSE 'awaiting_original_reading' END,
  'qualifiedSourceRef',ref);
END $body$;
REVOKE ALL ON FUNCTION oracle2.replacement_source_head_v1(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.replacement_source_head_v1(uuid) TO oracle2_replacement_requester;

-- Actual role-authorized response records. These do not attest model semantics.
CREATE TABLE IF NOT EXISTS oracle2.original_phase_response_commits (
 commit_sha256 text PRIMARY KEY CHECK(commit_sha256 ~ '^[0-9a-f]{64}$'),
 workspace_id uuid NOT NULL,source_id uuid NOT NULL,revision integer NOT NULL,
 purpose text NOT NULL CHECK(purpose IN('source-original-reading','source-original-review')),
 principal_id uuid NOT NULL,session_role name NOT NULL,runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),
 source_registry_hash text NOT NULL CHECK(source_registry_hash ~ '^[0-9a-f]{64}$'),
 original_sha256 text NOT NULL CHECK(original_sha256 ~ '^[0-9a-f]{64}$'),
 original_root_hash text NOT NULL CHECK(original_root_hash ~ '^[0-9a-f]{64}$'),
 allocation_hash text NOT NULL CHECK(allocation_hash ~ '^[0-9a-f]{64}$'),
 transport text NOT NULL CHECK(transport IN('paid-native-v1','native-utf8-byte-roundtrip-v1')),
 context_hash text NOT NULL CHECK(context_hash ~ '^[0-9a-f]{64}$'),
 population_id uuid NOT NULL REFERENCES oracle2.original_source_populations_v1(population_id),
 operation_registry_hash text NOT NULL CHECK(operation_registry_hash ~ '^[0-9a-f]{64}$'),
 native_dispatch_id uuid,body jsonb NOT NULL CHECK(jsonb_typeof(body)='object'),canonical_body bytea NOT NULL,
 CHECK((transport='paid-native-v1')=(native_dispatch_id IS NOT NULL)),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),original_horizon timestamptz NOT NULL CHECK(isfinite(original_horizon)),
 UNIQUE(session_role,native_dispatch_id),UNIQUE(session_role,context_hash,purpose),
 FOREIGN KEY(workspace_id,source_id,revision) REFERENCES oracle2.source_original_revisions(workspace_id,source_id,revision));
REVOKE ALL ON oracle2.original_phase_response_commits FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2._commit_original_response(commit_bytes bytea,review boolean)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE body jsonb;ref jsonb;identity jsonb;snapshot jsonb;required text[];hash_keys text[];k text;seal text;deadline timestamptz;
 prior oracle2.original_phase_response_commits%ROWTYPE;reading oracle2.original_phase_response_commits%ROWTYPE;
 producer_time timestamptz;horizon timestamptz;dispatch uuid;source uuid;revision integer;population uuid;
 phase_purpose text;transport text;actual_principal uuid;actual_runtime text;actual_registry text;
BEGIN
 IF commit_bytes IS NULL OR octet_length(commit_bytes)>65536 THEN
  RAISE invalid_parameter_value USING MESSAGE='bounded canonical original response required';
 END IF;
 BEGIN body:=convert_from(commit_bytes,'UTF8')::jsonb;
 EXCEPTION WHEN character_not_in_repertoire OR invalid_text_representation THEN
  RAISE invalid_parameter_value USING MESSAGE='canonical original response JSON required';
 END;
 IF jsonb_typeof(body) IS DISTINCT FROM 'object' OR body->'schema_version' IS DISTINCT FROM '1'::jsonb
 OR body->>'schema_version' IS DISTINCT FROM '1'
 OR convert_to(oracle2._replacement_metadata_json(body),'UTF8')<>commit_bytes THEN
  RAISE invalid_parameter_value USING MESSAGE='exact canonical original response required';
 END IF;
 transport:=body->>'transport';
 phase_purpose:=CASE WHEN review THEN 'source-original-review' ELSE 'source-original-reading' END;
 required:=ARRAY['schema_version','transport','purpose','raw_ref','population_id','operation_registry_hash','original_root_hash',
  'allocation_hash','population_hash','source_registry_hash','context_hash','view_manifest_hash','locator_map_hash',
  'reading_sha256','parser_id','committed_at','original_horizon','reading_body_hash'];
 hash_keys:=ARRAY['operation_registry_hash','original_root_hash','allocation_hash','population_hash','source_registry_hash',
  'context_hash','view_manifest_hash','locator_map_hash','reading_sha256','parser_id','reading_body_hash'];
 IF transport='paid-native-v1' THEN
  required:=required||ARRAY['native_dispatch_id','native_job_hash','request_hash','raw_wire_hash','model_content_hash',
   'native_custody_receipt_hash','authorized_phase_commit_hash'];
  hash_keys:=hash_keys||ARRAY['native_job_hash','request_hash','raw_wire_hash','model_content_hash',
   'native_custody_receipt_hash','authorized_phase_commit_hash'];
 ELSIF transport IS DISTINCT FROM 'native-utf8-byte-roundtrip-v1' THEN
  RAISE invalid_parameter_value USING MESSAGE='closed original response transport required';
 END IF;
 IF review THEN
  required:=required||ARRAY['reading_commit_hash','reading_population_id','reading_operation_registry_hash','review_body_hash','qualification_pass'];
  hash_keys:=hash_keys||ARRAY['reading_commit_hash','reading_operation_registry_hash','review_body_hash'];
 END IF;
 IF NOT body ?& required OR body-required<>'{}'::jsonb OR body->>'purpose' IS DISTINCT FROM
  (CASE WHEN review THEN 'observed-authorized-original-review-response-v1' ELSE 'observed-authorized-original-reading-response-v1' END)
 OR jsonb_typeof(body->'raw_ref') IS DISTINCT FROM 'object' THEN
  RAISE invalid_parameter_value USING MESSAGE='strict original phase response required';
 END IF;
 FOREACH k IN ARRAY hash_keys LOOP
  IF jsonb_typeof(body->k) IS DISTINCT FROM 'string' OR body->>k !~ '^[0-9a-f]{64}$' THEN
   RAISE invalid_parameter_value USING MESSAGE='exact original response seals required';
  END IF;
 END LOOP;
 IF jsonb_typeof(body->'population_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(body->'committed_at') IS DISTINCT FROM 'string' OR body->>'committed_at' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
 OR jsonb_typeof(body->'original_horizon') IS DISTINCT FROM 'string' OR body->>'original_horizon' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
 OR (review AND (body->'qualification_pass' IS DISTINCT FROM 'true'::jsonb OR jsonb_typeof(body->'reading_population_id') IS DISTINCT FROM 'string')) THEN
  RAISE invalid_parameter_value USING MESSAGE='exact original response identity required';
 END IF;
 ref:=body->'raw_ref';source:=(ref->>'source_id')::uuid;revision:=(ref->>'revision')::integer;population:=(body->>'population_id')::uuid;
 IF source IS NULL OR revision IS NULL OR population IS NULL THEN RAISE invalid_parameter_value; END IF;
 identity:=oracle2._original_revision_access(source,revision,CASE WHEN review THEN 'oracle2_source_original_reviewer' ELSE 'oracle2_source_original_reader' END);
 snapshot:=oracle2.original_population_current_v1(population);
 IF (identity->>'population_id')::uuid IS DISTINCT FROM population
 OR (identity->>'principal_id')::uuid IS DISTINCT FROM (snapshot->>'actual_principal_id')::uuid
 OR snapshot->>'session_role' IS DISTINCT FROM SESSION_USER::text
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot->'population'->'raw_refs') x WHERE x=ref)
 OR body->>'operation_registry_hash' IS DISTINCT FROM snapshot->'population'->>'operation_registry_hash'
 OR body->>'source_registry_hash' IS DISTINCT FROM snapshot->'population'->>'source_registry_hash'
 OR body->>'original_root_hash' IS DISTINCT FROM snapshot->'population'->>'original_root_hash'
 OR body->>'population_hash' IS DISTINCT FROM snapshot->'population'->>'population_digest'
 OR body->>'allocation_hash' IS DISTINCT FROM snapshot->>'original_allocation_hash' THEN
  RAISE insufficient_privilege USING MESSAGE='original response differs from complete actual phase custody';
 END IF;
 actual_principal:=(identity->>'principal_id')::uuid;actual_runtime:=identity->>'runtime_hash';actual_registry:=identity->>'registry_hash';
 IF transport='paid-native-v1' THEN
  IF ref->>'media_type' IS DISTINCT FROM 'application/pdf' OR jsonb_typeof(body->'native_dispatch_id') IS DISTINCT FROM 'string' THEN
   RAISE invalid_parameter_value USING MESSAGE='paid original response requires actual PDF operation';
  END IF;
  dispatch:=(body->>'native_dispatch_id')::uuid;
 ELSIF ref->>'media_type' IS DISTINCT FROM 'text/plain' OR body->>'reading_sha256' IS DISTINCT FROM ref->>'original_sha256' THEN
  RAISE invalid_parameter_value USING MESSAGE='native UTF8 response must preserve exact original byte hash';
 END IF;
 producer_time:=(body->>'committed_at')::timestamptz;horizon:=(body->>'original_horizon')::timestamptz;
 deadline:=least((identity->>'valid_until')::timestamptz,(snapshot->>'valid_until')::timestamptz,horizon);
 IF NOT isfinite(producer_time) OR NOT isfinite(horizon) OR horizon IS DISTINCT FROM (snapshot->>'original_horizon')::timestamptz
 OR producer_time>=horizon OR producer_time>clock_timestamp() OR deadline<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='original response horizon expired or changed';
 END IF;
 IF review THEN
  SELECT * INTO reading FROM oracle2.original_phase_response_commits WHERE commit_sha256=body->>'reading_commit_hash'
   AND purpose='source-original-reading' FOR SHARE;
  IF reading.commit_sha256 IS NULL OR reading.workspace_id IS DISTINCT FROM (identity->>'workspace_id')::uuid
  OR reading.source_id IS DISTINCT FROM source OR reading.revision IS DISTINCT FROM revision
  OR reading.principal_id=actual_principal OR reading.session_role=SESSION_USER
  OR reading.transport IS DISTINCT FROM transport OR reading.original_sha256 IS DISTINCT FROM ref->>'original_sha256'
  OR reading.original_root_hash IS DISTINCT FROM body->>'original_root_hash' OR reading.allocation_hash IS DISTINCT FROM body->>'allocation_hash'
  OR reading.original_horizon IS DISTINCT FROM horizon OR reading.population_id IS DISTINCT FROM (body->>'reading_population_id')::uuid
  OR reading.operation_registry_hash IS DISTINCT FROM body->>'reading_operation_registry_hash'
  OR reading.body->>'population_hash' IS DISTINCT FROM body->>'population_hash'
  OR reading.body->>'reading_body_hash' IS DISTINCT FROM body->>'reading_body_hash'
  OR reading.body->>'reading_sha256' IS DISTINCT FROM body->>'reading_sha256'
  OR reading.body->>'parser_id' IS DISTINCT FROM body->>'parser_id'
  OR reading.body->>'view_manifest_hash' IS DISTINCT FROM body->>'view_manifest_hash'
  OR reading.body->>'locator_map_hash' IS DISTINCT FROM body->>'locator_map_hash' THEN
   RAISE insufficient_privilege USING MESSAGE='genuine independent historical original reading commit required';
  END IF;
 END IF;
 seal:=encode(sha256(commit_bytes),'hex');
 SELECT * INTO prior FROM oracle2.original_phase_response_commits WHERE session_role=SESSION_USER
  AND context_hash=body->>'context_hash' AND purpose=phase_purpose FOR UPDATE;
 IF prior.commit_sha256 IS NULL AND dispatch IS NOT NULL THEN
  SELECT * INTO prior FROM oracle2.original_phase_response_commits WHERE session_role=SESSION_USER AND native_dispatch_id=dispatch FOR UPDATE;
 END IF;
 IF prior.commit_sha256 IS NOT NULL THEN
  IF prior.commit_sha256 IS DISTINCT FROM seal OR prior.canonical_body IS DISTINCT FROM commit_bytes THEN
   RAISE unique_violation USING MESSAGE='original response idempotency conflict';
  END IF;
 ELSE
  INSERT INTO oracle2.original_phase_response_commits(commit_sha256,workspace_id,source_id,revision,purpose,principal_id,session_role,runtime_hash,
   source_registry_hash,original_sha256,original_root_hash,allocation_hash,transport,context_hash,population_id,operation_registry_hash,
   native_dispatch_id,body,canonical_body,original_horizon)
  VALUES(seal,(identity->>'workspace_id')::uuid,source,revision,phase_purpose,actual_principal,SESSION_USER,actual_runtime,actual_registry,
   ref->>'original_sha256',body->>'original_root_hash',body->>'allocation_hash',transport,body->>'context_hash',population,
   body->>'operation_registry_hash',dispatch,body,commit_bytes,horizon);
 END IF;
 -- Reprove own authority after every possible row wait. Completed reader grants
 -- are historical evidence and are deliberately not reborrowed by the reviewer.
 identity:=oracle2._original_revision_access(source,revision,CASE WHEN review THEN 'oracle2_source_original_reviewer' ELSE 'oracle2_source_original_reader' END);
 snapshot:=oracle2.original_population_current_v1(population);
 IF actual_principal IS DISTINCT FROM (identity->>'principal_id')::uuid OR actual_runtime IS DISTINCT FROM identity->>'runtime_hash'
 OR actual_registry IS DISTINCT FROM identity->>'registry_hash'
 OR clock_timestamp()>=least(deadline,(identity->>'valid_until')::timestamptz,(snapshot->>'valid_until')::timestamptz) THEN
  RAISE insufficient_privilege USING MESSAGE='original response authority expired before commit';
 END IF;
 RETURN jsonb_build_object('commit_sha256',seal,'principal_id',actual_principal,'session_role',SESSION_USER,
  'runtime_hash',actual_runtime,'population_id',population,'operation_registry_hash',body->>'operation_registry_hash',
  'checked_at',clock_timestamp(),'valid_until',least(deadline,(identity->>'valid_until')::timestamptz,(snapshot->>'valid_until')::timestamptz));
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR invalid_datetime_format OR datetime_field_overflow THEN
 RAISE invalid_parameter_value USING MESSAGE='strict original response metadata required';
END $body$;
REVOKE ALL ON FUNCTION oracle2._commit_original_response(bytea,boolean) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;
CREATE OR REPLACE FUNCTION oracle2.commit_original_reading_response_v1(commit_bytes bytea)
 RETURNS jsonb LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT oracle2._commit_original_response(commit_bytes,false);$$;
CREATE OR REPLACE FUNCTION oracle2.commit_original_review_response_v1(commit_bytes bytea)
 RETURNS jsonb LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT oracle2._commit_original_response(commit_bytes,true);$$;
REVOKE ALL ON FUNCTION oracle2.commit_original_reading_response_v1(bytea),oracle2.commit_original_review_response_v1(bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.commit_original_reading_response_v1(bytea) TO oracle2_source_original_reader;
GRANT EXECUTE ON FUNCTION oracle2.commit_original_review_response_v1(bytea) TO oracle2_source_original_reviewer;

CREATE OR REPLACE FUNCTION oracle2.original_population_current_v1(wanted_population uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE p oracle2.original_source_populations_v1%ROWTYPE;a oracle2.hosting_original_population_admissions_v1%ROWTYPE;
 m oracle2.original_source_population_members_v1%ROWTYPE;o oracle2.source_original_revisions%ROWTYPE;
 identity jsonb;ref jsonb;refs jsonb:='[]';population jsonb;until_at timestamptz;initial_workspace uuid;
 total integer;first_ordinal integer;last_ordinal integer;expected_group text;seal text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl)
 OR current_setting('statement_timeout')='0' OR current_setting('statement_timeout')::interval>interval '5 seconds' THEN
  RAISE insufficient_privilege USING MESSAGE='bounded TLS raw population session required';
 END IF;
 IF current_setting('lock_timeout')='0' OR current_setting('lock_timeout')::interval>interval '2 seconds' THEN
  PERFORM set_config('lock_timeout','2s',true);
 END IF;
 SELECT x.workspace_id INTO initial_workspace FROM oracle2.original_source_populations_v1 x
 JOIN oracle2.hosting_original_population_admissions_v1 y ON y.population_id=x.population_id AND y.role_name=SESSION_USER
 WHERE x.population_id=wanted_population;
 IF initial_workspace IS NULL THEN RAISE insufficient_privilege USING MESSAGE='complete raw population unavailable'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||initial_workspace::text));
 SELECT * INTO p FROM oracle2.original_source_populations_v1 WHERE population_id=wanted_population FOR SHARE;
 SELECT * INTO a FROM oracle2.hosting_original_population_admissions_v1 WHERE role_name=SESSION_USER AND population_id=wanted_population FOR SHARE;
 IF p.population_id IS NULL OR a.role_name IS NULL OR p.workspace_id IS DISTINCT FROM initial_workspace
 OR a.purpose IS DISTINCT FROM p.purpose OR a.runtime_hash IS DISTINCT FROM p.runtime_hash
 OR a.source_registry_hash IS DISTINCT FROM p.source_registry_hash OR a.operation_registry_hash IS DISTINCT FROM p.operation_registry_hash
 OR p.expires_at<=clock_timestamp() OR a.expires_at<=clock_timestamp() OR p.original_horizon<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='current raw population admission denied';
 END IF;
 expected_group:=CASE p.purpose WHEN 'source-original-reading' THEN 'oracle2_source_original_reader'
  WHEN 'source-original-review' THEN 'oracle2_source_original_reviewer' ELSE NULL END;
 LOCK TABLE oracle2.original_source_population_members_v1 IN SHARE MODE;
 PERFORM 1 FROM oracle2.original_source_population_members_v1 WHERE population_id=wanted_population ORDER BY ordinal FOR SHARE;
 SELECT count(*),min(ordinal),max(ordinal) INTO total,first_ordinal,last_ordinal
 FROM oracle2.original_source_population_members_v1 WHERE population_id=wanted_population;
 IF expected_group IS NULL OR total NOT BETWEEN 1 AND 4096 OR first_ordinal<>0 OR last_ordinal<>total-1 THEN
  RAISE insufficient_privilege USING MESSAGE='complete ordered raw population required';
 END IF;
 until_at:=least(p.expires_at,a.expires_at,p.original_horizon);
 FOR m IN SELECT * FROM oracle2.original_source_population_members_v1 WHERE population_id=wanted_population ORDER BY ordinal LOOP
  IF m.workspace_id IS DISTINCT FROM p.workspace_id THEN RAISE insufficient_privilege USING MESSAGE='raw population workspace differs'; END IF;
  identity:=oracle2._original_revision_member_access(m.source_id,m.revision,expected_group);
  IF (identity->>'principal_id')::uuid IS DISTINCT FROM a.principal_id
  OR (identity->>'population_id')::uuid IS DISTINCT FROM wanted_population
  OR identity->>'runtime_hash' IS DISTINCT FROM p.runtime_hash OR identity->>'registry_hash' IS DISTINCT FROM p.source_registry_hash THEN
   RAISE insufficient_privilege USING MESSAGE='actual raw population role differs';
  END IF;
  SELECT * INTO o FROM oracle2.source_original_revisions WHERE workspace_id=p.workspace_id AND source_id=m.source_id AND revision=m.revision FOR SHARE;
  ref:=jsonb_build_object('schema_version',1,'workspace_id',p.workspace_id,'source_id',m.source_id,'revision',m.revision,
   'original_sha256',o.original_sha256,'byte_count',o.byte_count,'media_type',o.media_type,'filename',o.filename,
   'custody_locator_seal_sha256',o.custody_locator_seal_sha256);
  seal:=encode(sha256(convert_to(oracle2._replacement_metadata_json(ref),'UTF8')),'hex');
  IF seal IS DISTINCT FROM m.raw_ref_sha256 THEN RAISE insufficient_privilege USING MESSAGE='immutable raw population member changed'; END IF;
  refs:=refs||jsonb_build_array(ref);until_at:=least(until_at,(identity->>'valid_until')::timestamptz);
 END LOOP;
 seal:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('raw_refs',refs)),'UTF8')),'hex');
 IF seal IS DISTINCT FROM p.population_digest OR until_at<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='raw population seal or current horizon differs';
 END IF;
 population:=jsonb_build_object('schema_version',1,'purpose','raw-original-population-v1','population_id',p.population_id,
  'workspace_id',p.workspace_id,'original_root_hash',p.original_root_hash,'operation_registry_hash',p.operation_registry_hash,
  'runtime_hash',p.runtime_hash,'source_registry_hash',p.source_registry_hash,'raw_refs',refs,'population_digest',p.population_digest,
  'issuer_actor',p.issuer_actor,'reviewer_actor',p.reviewer_actor,'expires_at',p.expires_at);
 RETURN jsonb_build_object('population',population,'original_allocation_hash',p.original_allocation_hash,
  'original_horizon',p.original_horizon,'actual_principal_id',a.principal_id,'session_role',SESSION_USER,
  'checked_at',clock_timestamp(),'valid_until',until_at);
END $body$;
REVOKE ALL ON FUNCTION oracle2.original_population_current_v1(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.original_population_current_v1(uuid) TO oracle2_source_original_reader,oracle2_source_original_reviewer;

CREATE OR REPLACE FUNCTION oracle2.replacement_executor_target_v1(wanted_run uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE before_admission oracle2.hosting_replacement_executor_runs_v1%ROWTYPE;a oracle2.hosting_replacement_executor_runs_v1%ROWTYPE;
 before_run oracle2.processing_journey_runs_v1%ROWTYPE;j oracle2.processing_journey_runs_v1%ROWTYPE;
 base_run oracle2.runs%ROWTYPE;confirmed oracle2.replacement_journey_events%ROWTYPE;
 known uuid[];actual uuid[];artifact uuid;ref jsonb;target jsonb;targets jsonb:='[]';confirmation jsonb:='null';
 source record;delivery record;summary record;until_at timestamptz;confirm_until timestamptz;expected_sha text;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 IF NOT pg_has_role(SESSION_USER,'oracle2_documentary_executor','MEMBER') THEN RAISE insufficient_privilege; END IF;
 -- Only owner-registered current-login selectors are inspected before locks.
 SELECT * INTO before_admission FROM oracle2.hosting_replacement_executor_runs_v1
  WHERE role_name=SESSION_USER AND run_id=wanted_run;
 SELECT * INTO before_run FROM oracle2.processing_journey_runs_v1 WHERE run_id=wanted_run;
 IF before_admission.role_name IS NULL OR before_run.run_id IS NULL
 OR before_admission.workspace_id IS DISTINCT FROM before_run.workspace_id OR before_admission.expires_at<=clock_timestamp() THEN
  RAISE insufficient_privilege USING MESSAGE='appointed replacement run unavailable';
 END IF;
 SELECT array_agg(DISTINCT x ORDER BY x) INTO known FROM (
  SELECT before_admission.model_id x UNION ALL
  SELECT (t->>'summary_artifact_id')::uuid FROM jsonb_array_elements(before_run.summary_targets) t) ids;
 FOREACH artifact IN ARRAY known LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('operating-model:'||before_admission.workspace_id::text||':'||artifact::text,0));
 END LOOP;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||before_admission.workspace_id::text));
 until_at:=before_admission.expires_at;
 IF jsonb_typeof(before_run.original_population) IS DISTINCT FROM 'array'
 OR jsonb_array_length(before_run.original_population) NOT BETWEEN 1 AND 4096 THEN RAISE insufficient_privilege; END IF;
 -- Source/grant rows precede companion/admission rows. The same exclusive
 -- workspace lock serializes retained nested manifest/source row ordering.
 FOR ref IN SELECT value FROM jsonb_array_elements(before_run.original_population) LOOP
  SELECT * INTO STRICT source FROM oracle2.hosting_current_source_identity(before_admission.workspace_id,
   (ref->>'source_id')::uuid,before_admission.principal_id,before_admission.runtime_hash,before_admission.source_registry_hash);
  IF jsonb_build_object('schema_version',1,'workspace_id',before_admission.workspace_id,'source_id',(ref->>'source_id')::uuid,
    'revision',source.revision,'original_sha256',source.original_hash,'reading_sha256',source.reading_hash,'parser_id',source.parser_id)
   IS DISTINCT FROM ref THEN RAISE insufficient_privilege USING MESSAGE='replacement full population changed'; END IF;
  until_at:=least(until_at,source.valid_until);
 END LOOP;
 SELECT * INTO a FROM oracle2.hosting_replacement_executor_runs_v1 WHERE role_name=SESSION_USER AND run_id=wanted_run FOR SHARE;
 SELECT * INTO j FROM oracle2.processing_journey_runs_v1 WHERE run_id=wanted_run FOR SHARE;
 SELECT * INTO base_run FROM oracle2.runs WHERE run_id=wanted_run FOR SHARE;
 IF a IS DISTINCT FROM before_admission OR j.run_id IS NULL OR base_run.run_id IS NULL
 OR j.workspace_id IS DISTINCT FROM a.workspace_id OR j.actor_id IS DISTINCT FROM a.principal_id
 OR base_run.workspace_id IS DISTINCT FROM a.workspace_id OR base_run.actor_id IS DISTINCT FROM a.principal_id
 OR j.original_population IS DISTINCT FROM before_run.original_population
 OR j.population_sha256 IS DISTINCT FROM a.population_sha256
 OR (j.current_model_id,j.current_model_version,j.current_model_content_hash,j.current_ack_event_id)
  IS DISTINCT FROM (a.model_id,a.model_version,a.model_content_hash,a.ack_event_id) THEN
  RAISE insufficient_privilege USING MESSAGE='actual same-principal replacement target changed';
 END IF;
 SELECT array_agg(DISTINCT x ORDER BY x) INTO actual FROM (
  SELECT a.model_id x UNION ALL SELECT (t->>'summary_artifact_id')::uuid FROM jsonb_array_elements(j.summary_targets) t) ids;
 IF NOT actual<@known THEN RAISE serialization_failure USING MESSAGE='replacement target set expanded'; END IF;
 expected_sha:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('source_refs',j.original_population)),'UTF8')),'hex');
 IF expected_sha IS DISTINCT FROM j.population_sha256
 OR (SELECT count(DISTINCT r->>'source_id') FROM jsonb_array_elements(j.original_population) r)<>jsonb_array_length(j.original_population)
 OR encode(sha256(convert_to(oracle2._replacement_metadata_json(j.summary_targets),'UTF8')),'hex') IS DISTINCT FROM a.summary_targets_sha256 THEN
  RAISE insufficient_privilege USING MESSAGE='registered replacement population or summaries changed';
 END IF;
 -- Retained helper has NO artifact advisory acquisition. All model/summary
 -- artifact advisories are already held before its workspace/row/table locks.
 SELECT * INTO STRICT delivery FROM oracle2._processing_projection_delivery_v3(a.workspace_id,a.model_id,a.model_version,
  a.principal_id,a.runtime_hash,a.source_registry_hash);
 IF delivery.receipt->>'event_id' IS DISTINCT FROM a.ack_event_id::text
 OR delivery.receipt->>'content_hash' IS DISTINCT FROM a.model_content_hash
 OR delivery.receipt->>'projection_digest' IS DISTINCT FROM a.projection_digest
 OR jsonb_array_length(delivery.source_refs)<>jsonb_array_length(j.original_population)
 OR EXISTS(SELECT value FROM jsonb_array_elements(delivery.source_refs) EXCEPT SELECT value FROM jsonb_array_elements(j.original_population))
 OR EXISTS(SELECT value FROM jsonb_array_elements(j.original_population) EXCEPT SELECT value FROM jsonb_array_elements(delivery.source_refs)) THEN
  RAISE insufficient_privilege USING MESSAGE='current replacement ACK or complete sources changed';
 END IF;
 until_at:=least(until_at,delivery.valid_until);
 FOR target IN SELECT value FROM jsonb_array_elements(j.summary_targets) LOOP
  IF NOT target ?& ARRAY['schema_version','summary_artifact_id','summary_version','summary_content_hash','qualified_parent_id','qualified_parent_version','qualified_parent_content_hash']
  OR target-ARRAY['schema_version','summary_artifact_id','summary_version','summary_content_hash','qualified_parent_id','qualified_parent_version','qualified_parent_content_hash']<>'{}'::jsonb
  OR target->'schema_version' IS DISTINCT FROM '1'::jsonb OR target->>'schema_version' IS DISTINCT FROM '1'
  OR target->>'qualified_parent_id' IS DISTINCT FROM a.model_id::text OR target->>'qualified_parent_version' IS DISTINCT FROM a.model_version::text
  OR target->>'qualified_parent_content_hash' IS DISTINCT FROM a.model_content_hash THEN
   RAISE insufficient_privilege USING MESSAGE='strict registered replacement summary required';
  END IF;
  SELECT * INTO STRICT summary FROM oracle2._processing_artifact_metadata(a.workspace_id,(target->>'summary_artifact_id')::uuid,
   (target->>'summary_version')::integer,a.principal_id,a.runtime_hash,a.source_registry_hash);
  IF summary.manifest->>'kind' IS DISTINCT FROM 'processing_summary_v1' OR summary.manifest->>'state' IS DISTINCT FROM 'ready'
  OR summary.manifest->>'content_hash' IS DISTINCT FROM target->>'summary_content_hash'
  OR jsonb_array_length(summary.source_refs)<>jsonb_array_length(delivery.source_refs)
  OR EXISTS(SELECT value FROM jsonb_array_elements(summary.source_refs) EXCEPT SELECT value FROM jsonb_array_elements(delivery.source_refs))
  OR (SELECT count(*) FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id
   AND d.artifact_id=(target->>'summary_artifact_id')::uuid AND d.version=(target->>'summary_version')::integer AND d.upstream_kind='artifact')<>1
  OR NOT EXISTS(SELECT 1 FROM oracle2.artifact_dependencies d WHERE d.workspace_id=a.workspace_id
   AND d.artifact_id=(target->>'summary_artifact_id')::uuid AND d.version=(target->>'summary_version')::integer
   AND d.upstream_kind='artifact' AND d.upstream_id=a.model_id::text AND d.upstream_revision=a.model_version::text) THEN
   RAISE insufficient_privilege USING MESSAGE='actual registered summary dependency changed';
  END IF;
  targets:=targets||jsonb_build_array(target);
 END LOOP;
 IF (SELECT count(DISTINCT (x->>'summary_artifact_id')||':'||(x->>'summary_version')) FROM jsonb_array_elements(targets) x)<>jsonb_array_length(targets) THEN
  RAISE insufficient_privilege USING MESSAGE='unique registered summaries required';
 END IF;
 SELECT * INTO confirmed FROM oracle2.replacement_journey_events e WHERE e.run_id=wanted_run AND e.workspace_id=a.workspace_id
  AND e.actor_id=a.principal_id AND e.action='confirm' AND e.payload->>'version'=a.model_version::text
  AND e.payload->>'content_hash'=a.model_content_hash AND NOT EXISTS(SELECT 1 FROM oracle2.replacement_journey_events w
   WHERE w.run_id=wanted_run AND w.action='withdraw' AND w.payload->>'confirmation_id'=e.event_id::text)
  ORDER BY e.journey_revision DESC LIMIT 1;
 IF confirmed.event_id IS NOT NULL AND j.state='delivered' AND NOT j.answer_hold AND j.cancelled_at IS NULL
 AND jsonb_typeof(confirmed.payload->'workflow_id')='string' AND length(confirmed.payload->>'workflow_id') BETWEEN 1 AND 200 THEN
  BEGIN confirm_until:=oracle2._replacement_scope(a.workspace_id,a.principal_id,'process-confirm');
  EXCEPTION WHEN insufficient_privilege THEN confirm_until:=NULL; END;
  IF confirm_until IS NOT NULL THEN
   confirmation:=jsonb_build_object('schema_version',1,'workflow_id',confirmed.payload->>'workflow_id','version',a.model_version,
    'content_hash',a.model_content_hash,'eligible',true);until_at:=least(until_at,confirm_until);
  END IF;
 END IF;
 IF NOT isfinite(until_at) OR until_at<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='current replacement target expired'; END IF;
 RETURN jsonb_build_object('schema_version',1,'run_id',wanted_run,'journey_revision',j.journey_revision,'state',j.state,
  'answer_hold',j.answer_hold,'cancelled',j.state='cancelled','population_sha256',j.population_sha256,
  'requester_principal_id',a.principal_id,'workspace_id',a.workspace_id,'model_id',a.model_id,'model_version',a.model_version,
  'model_content_hash',a.model_content_hash,'ack_event_id',a.ack_event_id,'projection_digest',a.projection_digest,
  'source_refs',delivery.source_refs,'current_confirmation',confirmation,'summary_targets',targets,'checked_at',clock_timestamp(),'valid_until',until_at);
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range OR invalid_datetime_format OR datetime_field_overflow THEN
 RAISE insufficient_privilege USING MESSAGE='current replacement target unavailable';
END $body$;
REVOKE ALL ON FUNCTION oracle2.replacement_executor_target_v1(uuid) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;
GRANT EXECUTE ON FUNCTION oracle2.replacement_executor_target_v1(uuid) TO oracle2_documentary_executor;
