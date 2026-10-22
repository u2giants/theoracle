-- Dedicated Oracle operational capture only. No accepted truth/admission issuer.
-- External installation must independently appoint exact immutable admission IDs.
DO $owner$ BEGIN
 IF (SELECT nspowner FROM pg_namespace WHERE nspname='oracle2') IS DISTINCT FROM
    (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR (SELECT proowner FROM pg_proc WHERE oid=to_regprocedure('oracle2._replacement_request_context()')) IS DISTINCT FROM
    (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER) THEN
  RAISE EXCEPTION 'dedicated reviewed Oracle owner required';
 END IF;
END $owner$;
CREATE TABLE oracle2.meeting_capture_admissions_v1 (
 admission_id uuid PRIMARY KEY,admission_sha256 text NOT NULL CHECK(admission_sha256~'^[a-f0-9]{64}$'),
 workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,principal_id uuid NOT NULL,role_name name NOT NULL,
 leaf_appointment_id uuid NOT NULL REFERENCES oracle2.appointments(appointment_id),
 provider text NOT NULL CHECK(provider IN('recall','graph')),provider_account text NOT NULL CHECK(length(btrim(provider_account)) BETWEEN 1 AND 256 AND provider_account=btrim(provider_account)),
 tenant_id text NOT NULL CHECK(length(btrim(tenant_id)) BETWEEN 1 AND 256 AND tenant_id=btrim(tenant_id)),
 provider_meeting_id text NOT NULL CHECK(length(btrim(provider_meeting_id)) BETWEEN 1 AND 2048),
 stop_relation_id uuid,supervisor_admission_id uuid,supervision_scope_sha256 text CHECK(supervision_scope_sha256~'^[a-f0-9]{64}$'),stop_mapping_sha256 text CHECK(stop_mapping_sha256~'^[a-f0-9]{64}$'),
 stop_valid_from timestamptz,stop_until timestamptz,scheduler_poll_seconds integer,stop_request_seconds integer,safety_allowance_seconds integer,stop_margin_seconds integer,
 final_mapping_id uuid,final_mapping_sha256 text CHECK(final_mapping_sha256~'^[a-f0-9]{64}$'),
 participant_epoch_id uuid,participant_epoch_sha256 text CHECK(participant_epoch_sha256~'^[a-f0-9]{64}$'),
 bot_id text,final_artifact_sha256 text CHECK(final_artifact_sha256~'^[a-f0-9]{64}$'),verifier_secret_sha256 text CHECK(verifier_secret_sha256~'^[a-f0-9]{64}$'),
 consent_packet_sha256 text NOT NULL CHECK(consent_packet_sha256~'^[a-f0-9]{64}$'),
 runtime_hash text NOT NULL CHECK(runtime_hash~'^[a-f0-9]{64}$'),registry_hash text NOT NULL CHECK(registry_hash~'^[a-f0-9]{64}$'),
 actions text[] NOT NULL CHECK(cardinality(actions) BETWEEN 1 AND 16 AND actions<@ARRAY['invite','create_intent','create_observed','create_unknown','ingress','final_artifact','process','normalized','review','cancel','status','outbox','supervised','supervise','stop_intent','stop_observed','stop_unknown','stop_reconciled','participant_turn']),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL CHECK(issuer_actor<>reviewer_actor),
 capture_until timestamptz NOT NULL,valid_from timestamptz NOT NULL,original_horizon timestamptz NOT NULL,expires_at timestamptz NOT NULL,
 CHECK(isfinite(valid_from) AND isfinite(expires_at) AND isfinite(original_horizon) AND valid_from<expires_at AND expires_at<=original_horizon),
 CHECK(isfinite(capture_until) AND valid_from<capture_until AND capture_until<=original_horizon),
 CHECK(principal_id<>issuer_actor AND principal_id<>reviewer_actor),
 CHECK(NOT ('ingress'=ANY(actions)) OR (bot_id IS NOT NULL AND length(btrim(bot_id)) BETWEEN 1 AND 256 AND verifier_secret_sha256 IS NOT NULL)));
CREATE TABLE oracle2.meeting_capture_revocations_v1 (
 revocation_id uuid PRIMARY KEY,admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),
 revoked_at timestamptz NOT NULL CHECK(isfinite(revoked_at)),reason_sha256 text NOT NULL CHECK(reason_sha256~'^[a-f0-9]{64}$'));
CREATE TABLE oracle2.meeting_capture_heads_v1 (
 workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,capture_until timestamptz NOT NULL CHECK(isfinite(capture_until)),version integer NOT NULL CHECK(version>=0),
 state text NOT NULL CHECK(state IN('invited','joining','pending_mapping','waiting_room','recording_permission_pending','recording_permission_denied','capturing','capture_ended','processing','final_artifact_pending','capture_status_unknown','review','failed','UNKNOWN','cancelled')),
 pending_ingress uuid[] NOT NULL DEFAULT '{}',processed_ingress uuid[] NOT NULL DEFAULT '{}',
 last_event_id uuid,last_normalized_event_id uuid,create_intent_id uuid,last_capture_event_id uuid,capture_open boolean NOT NULL DEFAULT false,
 stop_intent_id uuid,stop_observation_id uuid,stop_state text NOT NULL DEFAULT 'not_attempted' CHECK(stop_state IN('not_attempted','inflight','observed','UNKNOWN','terminal_observed')),
 PRIMARY KEY(workspace_id,meeting_id),CHECK(cardinality(pending_ingress)<=4096 AND cardinality(processed_ingress)<=4096));
CREATE TABLE oracle2.meeting_capture_events_v1 (
 event_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,version integer NOT NULL CHECK(version>0),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),
 actor_id uuid NOT NULL,action text NOT NULL,payload_sha256 text NOT NULL CHECK(payload_sha256~'^[a-f0-9]{64}$'),payload jsonb NOT NULL,
 operation_id uuid NOT NULL,provider text,provider_account text,provider_event_id text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,meeting_id,version),UNIQUE(workspace_id,meeting_id,operation_id),
 UNIQUE(provider,provider_account,provider_event_id),
 FOREIGN KEY(workspace_id,meeting_id) REFERENCES oracle2.meeting_capture_heads_v1(workspace_id,meeting_id));
CREATE TABLE oracle2.meeting_participant_epochs_v1 (
 epoch_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,epoch_revision integer NOT NULL CHECK(epoch_revision>0),
 epoch_sha256 text NOT NULL CHECK(epoch_sha256~'^[a-f0-9]{64}$'),epoch_payload jsonb NOT NULL,
 UNIQUE(workspace_id,meeting_id,epoch_revision),CHECK(jsonb_typeof(epoch_payload)='object' AND octet_length(epoch_payload::text)<=1048576),
 CHECK(epoch_payload->>'purpose'='meeting-live-participant-epoch-v1' AND epoch_payload->>'epoch_id'=epoch_id::text AND epoch_payload->>'workspace_id'=workspace_id::text AND epoch_payload->>'meeting_id'=meeting_id::text),
 CHECK(epoch_payload->>'epoch_revision'=epoch_revision::text),
 CHECK(epoch_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(epoch_payload),'UTF8')),'hex')));
CREATE TABLE oracle2.meeting_participant_epoch_revocations_v1 (
 revocation_id uuid PRIMARY KEY,epoch_id uuid NOT NULL REFERENCES oracle2.meeting_participant_epochs_v1(epoch_id),
 revoked_at timestamptz NOT NULL CHECK(isfinite(revoked_at)),reason_sha256 text NOT NULL CHECK(reason_sha256~'^[a-f0-9]{64}$'));
ALTER TABLE oracle2.meeting_capture_admissions_v1 ADD CONSTRAINT meeting_participant_epoch_fk FOREIGN KEY(participant_epoch_id) REFERENCES oracle2.meeting_participant_epochs_v1(epoch_id);
CREATE TABLE oracle2.meeting_final_mappings_v1 (
 mapping_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,mapping_revision integer NOT NULL CHECK(mapping_revision>0),
 raw_sha256 text NOT NULL CHECK(raw_sha256~'^[a-f0-9]{64}$'),mapping_sha256 text NOT NULL CHECK(mapping_sha256~'^[a-f0-9]{64}$'),mapping_payload jsonb NOT NULL,
 UNIQUE(workspace_id,meeting_id,raw_sha256,mapping_revision),CHECK(jsonb_typeof(mapping_payload)='object' AND octet_length(mapping_payload::text)<=1048576),
 CHECK(mapping_payload->>'purpose'='meeting-final-workspace-mapping-v1' AND mapping_payload->>'mapping_id'=mapping_id::text AND mapping_payload->>'workspace_id'=workspace_id::text AND mapping_payload->>'meeting_id'=meeting_id::text AND mapping_payload->>'mapping_revision'=mapping_revision::text AND mapping_payload->>'raw_sha256'=raw_sha256),
 CHECK(mapping_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(mapping_payload),'UTF8')),'hex')));
CREATE TABLE oracle2.meeting_final_mapping_revocations_v1 (
 revocation_id uuid PRIMARY KEY,mapping_id uuid NOT NULL REFERENCES oracle2.meeting_final_mappings_v1(mapping_id),
 revoked_at timestamptz NOT NULL CHECK(isfinite(revoked_at)),reason_sha256 text NOT NULL CHECK(reason_sha256~'^[a-f0-9]{64}$'));
ALTER TABLE oracle2.meeting_capture_admissions_v1 ADD CONSTRAINT meeting_final_mapping_fk FOREIGN KEY(final_mapping_id) REFERENCES oracle2.meeting_final_mappings_v1(mapping_id);
REVOKE ALL ON oracle2.meeting_final_mappings_v1,oracle2.meeting_final_mapping_revocations_v1 FROM PUBLIC,oracle2_replacement_requester;
CREATE TABLE oracle2.meeting_create_stop_relations_v1 (
 mapping_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,
 mapping_sha256 text NOT NULL CHECK(mapping_sha256~'^[a-f0-9]{64}$'),mapping_payload jsonb NOT NULL,
 installed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(jsonb_typeof(mapping_payload)='object' AND octet_length(mapping_payload::text)<=16384),
 CHECK(mapping_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(mapping_payload),'UTF8')),'hex')));
CREATE TABLE oracle2.meeting_create_stop_relation_revocations_v1 (
 revocation_id uuid PRIMARY KEY,mapping_id uuid NOT NULL REFERENCES oracle2.meeting_create_stop_relations_v1(mapping_id),
 revoked_at timestamptz NOT NULL CHECK(isfinite(revoked_at)),reason_sha256 text NOT NULL CHECK(reason_sha256~'^[a-f0-9]{64}$'));
ALTER TABLE oracle2.meeting_capture_admissions_v1 ADD CONSTRAINT meeting_stop_relation_fk FOREIGN KEY(stop_relation_id) REFERENCES oracle2.meeting_create_stop_relations_v1(mapping_id);
ALTER TABLE oracle2.meeting_capture_admissions_v1 ADD CONSTRAINT meeting_stop_relation_pin CHECK(stop_relation_id IS NULL OR stop_mapping_sha256 IS NOT NULL);
REVOKE ALL ON oracle2.meeting_create_stop_relations_v1,oracle2.meeting_create_stop_relation_revocations_v1 FROM PUBLIC,oracle2_replacement_requester;
DO $immutable$ DECLARE n text; BEGIN
 FOREACH n IN ARRAY ARRAY['meeting_capture_admissions_v1','meeting_capture_revocations_v1','meeting_capture_events_v1','meeting_participant_epochs_v1','meeting_participant_epoch_revocations_v1','meeting_final_mappings_v1','meeting_final_mapping_revocations_v1','meeting_create_stop_relations_v1','meeting_create_stop_relation_revocations_v1'] LOOP
  EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()','immutable_'||n,n);
 END LOOP;
END $immutable$;
REVOKE ALL ON oracle2.meeting_capture_admissions_v1,oracle2.meeting_capture_revocations_v1,oracle2.meeting_capture_heads_v1,oracle2.meeting_capture_events_v1,oracle2.meeting_participant_epochs_v1,oracle2.meeting_participant_epoch_revocations_v1 FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_capture_lineage_v1(m oracle2.meeting_capture_admissions_v1)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE p oracle2.appointments%ROWTYPE;seen uuid[]:='{}';until timestamptz:=m.expires_at;rooted boolean:=false;
BEGIN
 SELECT * INTO p FROM oracle2.appointments WHERE appointment_id=m.leaf_appointment_id FOR SHARE;
 IF p.appointment_id IS NULL OR p.workspace_id<>m.workspace_id OR p.actor_id<>m.principal_id OR p.scope<>'meeting-capture' THEN
  RAISE insufficient_privilege USING MESSAGE='exact meeting leaf denied';
 END IF;
 LOOP
  IF p.appointment_id=ANY(seen) OR cardinality(seen)>=16 OR p.workspace_id<>m.workspace_id OR p.revoked_at IS NOT NULL
  OR (p.expires_at IS NOT NULL AND (NOT isfinite(p.expires_at) OR p.expires_at<=clock_timestamp())) THEN
   RAISE insufficient_privilege USING MESSAGE='meeting lineage denied';
  END IF;
  seen:=array_append(seen,p.appointment_id);until:=least(until,coalesce(p.expires_at,until));
  IF p.parent_id IS NULL THEN rooted:=(p.scope='root');EXIT;END IF;
  SELECT parent.* INTO p FROM oracle2.appointments parent WHERE parent.appointment_id=p.parent_id
   AND parent.actor_id=p.granted_by AND parent.scope IN('meeting-capture','root') FOR SHARE;
  IF p.appointment_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='meeting lineage broken';END IF;
 END LOOP;
 IF NOT rooted OR until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='meeting root denied';END IF;
 RETURN until;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_capture_lineage_v1(oracle2.meeting_capture_admissions_v1) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_capture_admission_v1(selected uuid,seal text,act text,deadline timestamptz)
 RETURNS oracle2.meeting_capture_admissions_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;m oracle2.meeting_capture_admissions_v1%ROWTYPE;
 p oracle2.appointments%ROWTYPE;seen uuid[]:='{}';until timestamptz;rooted boolean:=false;committed_end timestamptz;
BEGIN
 a:=oracle2._replacement_request_context();
 SELECT * INTO m FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=selected FOR SHARE;
 IF m.admission_id IS NULL OR m.admission_sha256 IS DISTINCT FROM seal OR m.workspace_id<>a.workspace_id OR m.principal_id<>a.principal_id
 OR m.role_name<>SESSION_USER OR m.runtime_hash<>a.runtime_hash OR m.registry_hash<>a.registry_hash
 OR NOT(act=ANY(m.actions)) OR NOT isfinite(deadline) OR deadline<=clock_timestamp() OR deadline>clock_timestamp()+interval '30 seconds'
 OR m.valid_from>clock_timestamp() OR m.expires_at<=clock_timestamp() OR m.original_horizon<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.meeting_capture_revocations_v1 WHERE admission_id=selected) THEN
  RAISE insufficient_privilege USING MESSAGE='current meeting admission denied';
 END IF;
 SELECT capture_until INTO committed_end FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 IF committed_end IS NOT NULL AND committed_end IS DISTINCT FROM m.capture_until THEN RAISE insufficient_privilege USING MESSAGE='capture end cannot change';END IF;
 until:=least(a.expires_at,m.expires_at,m.original_horizon,deadline);
 IF act IN('ingress','create_intent','participant_turn') THEN until:=least(until,m.capture_until);END IF;
 IF act IN('stop_intent','stop_observed','stop_unknown','stop_reconciled') THEN
  IF m.stop_valid_from IS NULL OR m.stop_until IS NULL OR m.stop_valid_from>clock_timestamp() OR m.stop_until<=clock_timestamp() OR m.stop_until>m.original_horizon THEN RAISE insufficient_privilege USING MESSAGE='preinstalled STOP-only window denied';END IF;
  until:=least(until,m.stop_until);
 END IF;
 IF m.stop_relation_id IS NOT NULL THEN until:=least(until,(oracle2._meeting_stop_relation_v1(m)->>'expires_at')::timestamptz);END IF;
 m.expires_at:=until;until:=oracle2._meeting_capture_lineage_v1(m);
 m.expires_at:=until;RETURN m;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_capture_admission_v1(uuid,text,text,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

-- A descriptor is installed BEFORE invitation; runtime cannot choose a bot.
CREATE FUNCTION oracle2._meeting_stop_relation_change_v1() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,oracle2 AS $f$
DECLARE workspace uuid;BEGIN
 IF TG_TABLE_NAME='meeting_create_stop_relations_v1' THEN workspace:=NEW.workspace_id;
 ELSE SELECT workspace_id INTO workspace FROM oracle2.meeting_create_stop_relations_v1 WHERE mapping_id=NEW.mapping_id;END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));RETURN NEW;END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_stop_relation_change_v1() FROM PUBLIC;
CREATE TRIGGER meeting_stop_relation_install_lock BEFORE INSERT ON oracle2.meeting_create_stop_relations_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_stop_relation_change_v1();
CREATE TRIGGER meeting_stop_relation_revoke_lock BEFORE INSERT ON oracle2.meeting_create_stop_relation_revocations_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_stop_relation_change_v1();

CREATE FUNCTION oracle2._meeting_stop_relation_v1(m oracle2.meeting_capture_admissions_v1)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE r oracle2.meeting_create_stop_relations_v1%ROWTYPE;p jsonb;invited timestamptz;field text;stop_owner oracle2.meeting_capture_admissions_v1%ROWTYPE;
BEGIN
 IF m.stop_relation_id IS NULL THEN RETURN NULL;END IF;
 SELECT * INTO r FROM oracle2.meeting_create_stop_relations_v1 WHERE mapping_id=m.stop_relation_id
  AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;p:=r.mapping_payload;
 SELECT min(created_at) INTO invited FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='invite';
 IF r.mapping_id IS NULL OR r.mapping_sha256 IS DISTINCT FROM m.stop_mapping_sha256
  OR invited IS NOT NULL AND r.installed_at>invited
  OR EXISTS(SELECT 1 FROM oracle2.meeting_create_stop_relation_revocations_v1 WHERE mapping_id=r.mapping_id)
  OR NOT(p?&ARRAY['schema_version','purpose','mapping_id','workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id','create_operation_id','create_request_sha256','supervision_scope_sha256','scheduler_id','stop_owner_id','scheduler_runtime_sha256','scheduler_config_sha256','stop_runtime_sha256','stop_config_sha256','capture_until','stop_valid_from','stop_until','original_horizon','issuer_actor','reviewer_actor','valid_from','expires_at'])
  OR p-ARRAY['schema_version','purpose','mapping_id','workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id','create_operation_id','create_request_sha256','supervision_scope_sha256','scheduler_id','stop_owner_id','scheduler_runtime_sha256','scheduler_config_sha256','stop_runtime_sha256','stop_config_sha256','capture_until','stop_valid_from','stop_until','original_horizon','issuer_actor','reviewer_actor','valid_from','expires_at']<>'{}'::jsonb
  OR p->'schema_version' IS DISTINCT FROM '1'::jsonb OR p->>'purpose' IS DISTINCT FROM 'meeting-create-operation-stop-relation-v1'
  OR p->>'mapping_id' IS DISTINCT FROM r.mapping_id::text OR p->>'workspace_id' IS DISTINCT FROM m.workspace_id::text OR p->>'meeting_id' IS DISTINCT FROM m.meeting_id::text
  OR p->>'supervision_scope_sha256' IS DISTINCT FROM m.supervision_scope_sha256
  OR p->>'provider' IS DISTINCT FROM m.provider OR p->>'provider_account' IS DISTINCT FROM m.provider_account OR p->>'tenant_id' IS DISTINCT FROM m.tenant_id OR p->>'provider_meeting_id' IS DISTINCT FROM m.provider_meeting_id
  OR p->>'issuer_actor'=p->>'reviewer_actor' OR p->>'scheduler_id'=p->>'stop_owner_id'
  OR p->>'scheduler_id' IN(p->>'issuer_actor',p->>'reviewer_actor') OR p->>'stop_owner_id' IN(p->>'issuer_actor',p->>'reviewer_actor')
  OR (p->>'valid_from')::timestamptz>clock_timestamp() OR (p->>'stop_valid_from')::timestamptz>clock_timestamp()
  OR (p->>'expires_at')::timestamptz<=clock_timestamp()
  OR (p->>'capture_until')::timestamptz IS DISTINCT FROM m.capture_until OR (p->>'stop_valid_from')::timestamptz IS DISTINCT FROM m.stop_valid_from
  OR (p->>'stop_until')::timestamptz IS DISTINCT FROM m.stop_until OR (p->>'original_horizon')::timestamptz IS DISTINCT FROM m.original_horizon
  OR NOT((p->>'valid_from')::timestamptz<=(p->>'stop_valid_from')::timestamptz AND (p->>'stop_valid_from')::timestamptz<m.capture_until AND m.capture_until<=m.stop_until AND m.stop_until<=m.original_horizon AND (p->>'stop_valid_from')::timestamptz<(p->>'expires_at')::timestamptz AND (p->>'expires_at')::timestamptz<=m.stop_until)
  THEN RAISE insufficient_privilege USING MESSAGE='exact current preinvitation operation STOP relation required';END IF;
 FOREACH field IN ARRAY ARRAY['valid_from','expires_at','capture_until','stop_valid_from','stop_until','original_horizon'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR NOT isfinite((p->>field)::timestamptz) OR p->>field IS DISTINCT FROM to_char((p->>field)::timestamptz AT TIME ZONE 'UTC',CASE WHEN date_trunc('second',(p->>field)::timestamptz)=(p->>field)::timestamptz THEN 'YYYY-MM-DD"T"HH24:MI:SS"Z"' ELSE 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"' END) THEN RAISE EXCEPTION 'finite original relation instant required';END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['purpose','provider','provider_account','tenant_id','provider_meeting_id'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR length(p->>field)<1 OR p->>field IS DISTINCT FROM btrim(p->>field) OR p->>field~'[[:cntrl:]]' THEN RAISE EXCEPTION 'canonical installed provider scope required';END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['mapping_id','workspace_id','meeting_id','create_operation_id','scheduler_id','stop_owner_id','issuer_actor','reviewer_actor'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR p->>field IS DISTINCT FROM ((p->>field)::uuid)::text THEN RAISE EXCEPTION 'canonical installed relation UUID required';END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['create_request_sha256','supervision_scope_sha256','scheduler_runtime_sha256','scheduler_config_sha256','stop_runtime_sha256','stop_config_sha256'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR p->>field !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'exact installed relation SHA required';END IF;
 END LOOP;
 IF m.worker_effect='capture-create' AND (p->>'create_operation_id' IS DISTINCT FROM m.worker_create_operation_id::text
  OR p->>'create_request_sha256' IS DISTINCT FROM m.worker_create_request_sha256 OR p->>'supervision_scope_sha256' IS DISTINCT FROM m.supervision_scope_sha256
  OR m.principal_id::text IN(p->>'scheduler_id',p->>'stop_owner_id',p->>'issuer_actor',p->>'reviewer_actor')) THEN RAISE insufficient_privilege USING MESSAGE='separate exact creator relation required';END IF;
 IF m.worker_effect='capture-create' THEN
  IF (p->>'expires_at')::timestamptz<m.stop_until THEN RAISE insufficient_privilege USING MESSAGE='full original unattended STOP relation window required';END IF;
  SELECT a.* INTO stop_owner FROM oracle2.meeting_capture_admissions_v1 a
   JOIN oracle2.hosting_request_principal_admissions h ON h.role_name=a.role_name AND h.principal_id=a.principal_id AND h.workspace_id=a.workspace_id
   JOIN oracle2.hosting_role_runtime_admissions runtime ON runtime.role_name=a.role_name
   JOIN pg_roles role ON role.rolname=a.role_name
   WHERE a.workspace_id=m.workspace_id AND a.meeting_id=m.meeting_id AND a.principal_id::text=p->>'stop_owner_id'
    AND a.stop_relation_id=r.mapping_id AND a.stop_mapping_sha256=r.mapping_sha256 AND a.worker_effect='capture-leave'
    AND a.provider=m.provider AND a.provider_account=m.provider_account AND a.tenant_id=m.tenant_id AND a.provider_meeting_id=m.provider_meeting_id
    AND a.capture_until=m.capture_until AND a.stop_valid_from=m.stop_valid_from AND a.stop_until=m.stop_until AND a.original_horizon=m.original_horizon
    AND ARRAY['stop_intent','stop_observed','stop_unknown','status']::text[]<@a.actions
    AND a.valid_from<=clock_timestamp() AND a.expires_at>clock_timestamp() AND a.expires_at>=m.stop_until
    AND h.runtime_hash=a.runtime_hash AND h.registry_hash=a.registry_hash AND runtime.runtime_hash=a.runtime_hash AND runtime.registry_hash=a.registry_hash
    AND h.expires_at>=m.stop_until AND runtime.expires_at>=m.stop_until AND isfinite(h.expires_at) AND isfinite(runtime.expires_at)
    AND role.rolcanlogin AND NOT(role.rolsuper OR role.rolcreatedb OR role.rolcreaterole OR role.rolreplication OR role.rolbypassrls)
    AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_revocations_v1 WHERE admission_id=a.admission_id)
   ORDER BY a.admission_id LIMIT 1 FOR SHARE OF a,h,runtime;
  IF stop_owner.admission_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='current independently installed unattended STOP role required';END IF;
  IF oracle2._meeting_capture_lineage_v1(stop_owner)<m.stop_until THEN RAISE insufficient_privilege USING MESSAGE='rooted STOP authority must cover full original STOP window';END IF;
 END IF;
 IF m.worker_effect='capture-leave' AND m.principal_id::text IS DISTINCT FROM p->>'stop_owner_id' THEN RAISE insufficient_privilege USING MESSAGE='independently appointed exact STOP owner required';END IF;
 RETURN p;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_stop_relation_v1(oracle2.meeting_capture_admissions_v1) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_capture_transition_v1(selected uuid,seal text,expected_head integer,operation uuid,act text,body jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;
 old oracle2.meeting_capture_events_v1%ROWTYPE;proof oracle2.meeting_capture_events_v1%ROWTYPE;supervisor oracle2.meeting_capture_admissions_v1%ROWTYPE;event uuid;hash text;target text;ingress uuid;required text[];field text;terminal_receipt record;
BEGIN
 m:=oracle2._meeting_capture_admission_v1(selected,seal,act,deadline);
 IF operation IS NULL OR expected_head IS NULL OR expected_head<0 OR jsonb_typeof(body) IS DISTINCT FROM 'object'
 OR octet_length(body::text)>1100000 OR act NOT IN('invite','create_intent','create_observed','create_unknown','ingress','final_artifact','normalized','review','cancel','outbox','supervised','stop_intent','stop_observed','stop_unknown','stop_reconciled') THEN
  RAISE EXCEPTION 'closed bounded meeting transition required';END IF;
 required:=CASE act
 WHEN 'invite' THEN ARRAY['consent_packet_sha256'] WHEN 'create_intent' THEN ARRAY['request_sha256','supervisor_event_id','supervisor_event_sha256','supervisor_witness_sha256']
 WHEN 'supervised' THEN ARRAY['scope_sha256','create_operation_id','request_sha256','witness_sha256','witness_object_key','nonce','observed_at','valid_until','scheduler_observation_sha256']
 WHEN 'stop_intent' THEN ARRAY['create_intent_id','bot_id','create_receipt_sha256','stop_mapping_sha256','metadata_sha256']
 WHEN 'stop_observed' THEN ARRAY['stop_intent_id','wire_sha256'] WHEN 'stop_unknown' THEN ARRAY['stop_intent_id','wire_sha256']
 WHEN 'stop_reconciled' THEN ARRAY['stop_intent_id','metadata_sha256','terminal_event_id']
 WHEN 'create_observed' THEN ARRAY['intent_id','receipt_sha256','bot_id'] WHEN 'create_unknown' THEN ARRAY['intent_id','receipt_sha256']
 WHEN 'ingress' THEN ARRAY['bot_id','verifier_secret_sha256','provider_event_id','raw_sha256','byte_count','raw_object_key','event_kind']
 WHEN 'final_artifact' THEN ARRAY['selection_sha256','provider_event_id','raw_sha256','byte_count','raw_object_key','event_kind']
 WHEN 'normalized' THEN ARRAY['ingress_event_id','derivation_sha256','source_id','revision','original_sha256']
 WHEN 'review' THEN ARRAY['normalized_event_id','observation'] WHEN 'outbox' THEN ARRAY['ingress_event_id','observation']
 ELSE ARRAY[]::text[] END;
 IF NOT (body ?& required) OR body-required<>'{}'::jsonb THEN RAISE EXCEPTION 'closed meeting payload required';END IF;
 FOREACH field IN ARRAY required LOOP
  IF field IN('byte_count','revision') THEN
   IF jsonb_typeof(body->field) IS DISTINCT FROM 'number' OR body->>field !~ '^[1-9][0-9]{0,9}$' THEN RAISE EXCEPTION 'strict meeting integer required';END IF;
  ELSE
   IF jsonb_typeof(body->field) IS DISTINCT FROM 'string' OR length(btrim(body->>field)) NOT BETWEEN 1 AND 2048
    OR body->>field<>btrim(body->>field) OR body->>field~'[[:cntrl:]]' THEN RAISE EXCEPTION 'strict meeting string required';END IF;
  END IF;
 END LOOP;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-meeting:'||m.workspace_id::text||':'||m.meeting_id::text));
 hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('action',act,'body',body)),'UTF8')),'hex');
 SELECT * INTO old FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND operation_id=operation;
 IF old.event_id IS NOT NULL THEN
  IF old.payload_sha256<>hash OR old.action<>act OR old.admission_id<>selected OR old.actor_id<>m.principal_id THEN RAISE EXCEPTION 'meeting operation payload collision';END IF;
  SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id;
  RETURN jsonb_build_object('event_id',old.event_id,'version',h.version,'state',h.state,'created',false,'valid_until',m.expires_at,'meeting_id',m.meeting_id,'capture_until',m.capture_until,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
 END IF;
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 IF h.meeting_id IS NULL THEN
  IF act<>'invite' OR expected_head<>0 THEN RAISE EXCEPTION 'invitation must be committed first';END IF;
  INSERT INTO oracle2.meeting_capture_heads_v1(workspace_id,meeting_id,capture_until,version,state) VALUES(m.workspace_id,m.meeting_id,m.capture_until,0,'invited') RETURNING * INTO h;
 END IF;
 IF h.version<>expected_head OR h.version>=16384 THEN RAISE EXCEPTION 'meeting head conflict';END IF;
 IF h.state IN('UNKNOWN','cancelled') AND act NOT IN('cancel','outbox','stop_intent','stop_observed','stop_unknown','stop_reconciled') THEN RAISE EXCEPTION 'terminal meeting cannot resume';END IF;
 target:=h.state;
 CASE act
 WHEN 'invite' THEN
  IF h.version<>0 OR body<>jsonb_build_object('consent_packet_sha256',m.consent_packet_sha256) THEN RAISE EXCEPTION 'exact installed consent required';END IF;
  IF m.stop_valid_from IS NULL OR m.stop_until IS NULL OR m.stop_mapping_sha256 IS NULL
   OR NOT isfinite(m.stop_valid_from) OR NOT isfinite(m.stop_until) OR m.stop_valid_from>clock_timestamp()
   OR m.stop_until<m.capture_until OR m.stop_until>m.original_horizon
   OR m.scheduler_poll_seconds IS NULL OR m.scheduler_poll_seconds NOT BETWEEN 1 AND 30
   OR m.stop_request_seconds IS NULL OR m.stop_request_seconds NOT BETWEEN 1 AND 30
   OR m.safety_allowance_seconds IS NULL OR m.safety_allowance_seconds NOT BETWEEN 1 AND 60
   OR m.stop_margin_seconds IS NULL OR m.stop_margin_seconds NOT BETWEEN 3 AND 120
   OR m.stop_margin_seconds<m.scheduler_poll_seconds+m.stop_request_seconds+m.safety_allowance_seconds
   OR m.capture_until-make_interval(secs=>m.stop_margin_seconds)<=clock_timestamp()
   OR m.capture_until-make_interval(secs=>m.stop_margin_seconds)<=m.stop_valid_from THEN
   RAISE insufficient_privilege USING MESSAGE='preinstalled full STOP-only scheduler margin required before invitation';END IF;
 WHEN 'supervised' THEN
  IF m.supervision_scope_sha256 IS NULL OR body->>'scope_sha256' IS DISTINCT FROM m.supervision_scope_sha256
   OR body->>'request_sha256' !~ '^[a-f0-9]{64}$' OR body->>'witness_sha256' !~ '^[a-f0-9]{64}$' OR body->>'nonce' !~ '^[a-f0-9]{64}$'
   OR body->>'scheduler_observation_sha256' !~ '^[a-f0-9]{64}$'
   OR body->>'witness_object_key' IS DISTINCT FROM 'meeting-supervisor/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||(body->>'witness_sha256')||'.bin'
   OR (body->>'observed_at')::timestamptz>clock_timestamp() OR (body->>'observed_at')::timestamptz<clock_timestamp()-interval '5 seconds'
   OR NOT isfinite((body->>'valid_until')::timestamptz) OR (body->>'valid_until')::timestamptz<=clock_timestamp()
   OR (body->>'valid_until')::timestamptz>least(m.expires_at,m.capture_until,(body->>'observed_at')::timestamptz+interval '5 seconds')
   THEN RAISE insufficient_privilege USING MESSAGE='exact independently observed supervisor required';END IF;
 WHEN 'create_intent' THEN
  SELECT * INTO proof FROM oracle2.meeting_capture_events_v1 WHERE event_id=(body->>'supervisor_event_id')::uuid AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='supervised' FOR SHARE;
  SELECT * INTO supervisor FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=m.supervisor_admission_id FOR SHARE;
  IF supervisor.admission_id IS NULL OR supervisor.principal_id=m.principal_id OR supervisor.supervision_scope_sha256 IS DISTINCT FROM m.supervision_scope_sha256
   OR proof.admission_id IS DISTINCT FROM supervisor.admission_id OR proof.actor_id IS DISTINCT FROM supervisor.principal_id
   OR proof.payload_sha256 IS DISTINCT FROM body->>'supervisor_event_sha256' OR proof.payload->>'witness_sha256' IS DISTINCT FROM body->>'supervisor_witness_sha256'
   OR proof.payload->>'scope_sha256' IS DISTINCT FROM m.supervision_scope_sha256 OR proof.payload->>'create_operation_id' IS DISTINCT FROM operation::text
   OR proof.payload->>'request_sha256' IS DISTINCT FROM body->>'request_sha256' OR (proof.payload->>'valid_until')::timestamptz<=clock_timestamp()
   OR supervisor.valid_from>clock_timestamp() OR supervisor.expires_at<=clock_timestamp() OR supervisor.capture_until IS DISTINCT FROM m.capture_until
   OR EXISTS(SELECT 1 FROM oracle2.meeting_capture_revocations_v1 WHERE admission_id=supervisor.admission_id) THEN
   RAISE insufficient_privilege USING MESSAGE='fresh independently installed supervisor receipt required';END IF;
  IF NOT EXISTS(SELECT 1 FROM oracle2.hosting_request_principal_admissions a JOIN oracle2.hosting_role_runtime_admissions r USING(role_name)
   JOIN pg_roles role ON role.rolname=a.role_name
   WHERE a.role_name=supervisor.role_name AND a.principal_id=supervisor.principal_id AND a.workspace_id=m.workspace_id
   AND a.runtime_hash=supervisor.runtime_hash AND a.registry_hash=supervisor.registry_hash AND r.runtime_hash=a.runtime_hash AND r.registry_hash=a.registry_hash
   AND a.expires_at>clock_timestamp() AND r.expires_at>clock_timestamp() AND isfinite(r.expires_at)
   AND role.rolcanlogin AND NOT(role.rolsuper OR role.rolcreatedb OR role.rolcreaterole OR role.rolreplication OR role.rolbypassrls)) THEN
   RAISE insufficient_privilege USING MESSAGE='current independent supervisor runtime required';END IF;
  supervisor.expires_at:=least(supervisor.expires_at,(proof.payload->>'valid_until')::timestamptz);
  PERFORM oracle2._meeting_capture_lineage_v1(supervisor);
  IF h.state<>'invited' OR h.create_intent_id IS NOT NULL OR NOT(body ? 'request_sha256') OR body-ARRAY['request_sha256','supervisor_event_id','supervisor_event_sha256','supervisor_witness_sha256']<>'{}'::jsonb
  OR body->>'request_sha256' !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'single exact create intent required';END IF;
  target:='joining';h.create_intent_id:=operation;
 WHEN 'create_observed','create_unknown' THEN
  IF h.state<>'joining' OR body->>'intent_id' IS DISTINCT FROM h.create_intent_id::text OR (act='create_unknown' AND body-ARRAY['intent_id','receipt_sha256']<>'{}'::jsonb) OR (act='create_observed' AND (body-ARRAY['intent_id','receipt_sha256','bot_id']<>'{}'::jsonb OR body->>'bot_id' !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'))
  OR body->>'receipt_sha256' !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'exact observed create receipt required';END IF;
  target:=CASE WHEN act='create_unknown' THEN 'UNKNOWN' ELSE 'pending_mapping' END;
 WHEN 'stop_intent' THEN
  SELECT * INTO proof FROM oracle2._meeting_created_bot_v1(m);
  IF m.stop_relation_id IS NOT NULL AND (proof.payload->>'intent_id' IS DISTINCT FROM oracle2._meeting_stop_relation_v1(m)->>'create_operation_id' OR m.bot_id IS NOT NULL AND m.bot_id IS DISTINCT FROM proof.payload->>'bot_id') THEN RAISE insufficient_privilege USING MESSAGE='exact installed operation STOP bot relation required';END IF;
  IF h.stop_intent_id IS NOT NULL OR h.create_intent_id IS NULL OR proof.event_id IS NULL
   OR body->>'create_intent_id' IS DISTINCT FROM h.create_intent_id::text
   OR proof.payload->>'intent_id' IS DISTINCT FROM h.create_intent_id::text
   OR body->>'bot_id' IS DISTINCT FROM proof.payload->>'bot_id'
   OR body->>'create_receipt_sha256' IS DISTINCT FROM proof.payload->>'receipt_sha256'
   OR body->>'stop_mapping_sha256' IS DISTINCT FROM m.stop_mapping_sha256
   OR body->>'metadata_sha256' !~ '^[a-f0-9]{64}$'
   OR clock_timestamp()<m.capture_until-make_interval(secs=>m.stop_margin_seconds) THEN
   RAISE insufficient_privilege USING MESSAGE='single due exact-bot independently mapped STOP intent required';END IF;
  h.stop_intent_id:=operation;h.stop_state:='inflight';h.capture_open:=false;target:=CASE WHEN h.state IN('cancelled','UNKNOWN') THEN h.state ELSE 'capture_ended' END;
 WHEN 'stop_observed','stop_unknown' THEN
  IF h.stop_state<>'inflight' OR h.stop_intent_id IS NULL OR body->>'stop_intent_id' IS DISTINCT FROM h.stop_intent_id::text
   OR body->>'wire_sha256' !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'single exact STOP observation required';END IF;
  h.stop_observation_id:=operation;h.stop_state:=CASE WHEN act='stop_unknown' THEN 'UNKNOWN' ELSE 'observed' END;
  target:=CASE WHEN h.state IN('cancelled','UNKNOWN') THEN h.state ELSE 'capture_status_unknown' END;
 WHEN 'stop_reconciled' THEN
  IF m.stop_relation_id IS NOT NULL THEN
   SELECT * INTO proof FROM oracle2._meeting_created_bot_v1(m);
   IF m.bot_id IS NOT NULL AND m.bot_id IS DISTINCT FROM proof.payload->>'bot_id' THEN RAISE insufficient_privilege USING MESSAGE='exact terminal bot relation required';END IF;
   m.bot_id:=proof.payload->>'bot_id';
  END IF;
  SELECT r.receipt_id,r.observation,c.bot_id,c.stage,c.operation_id,c.intent_event_id,c.original_deadline INTO terminal_receipt
   FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 c USING(claim_id)
   WHERE r.receipt_id=(body->>'terminal_event_id')::uuid AND r.admission_id=selected AND c.admission_id=selected
    AND r.worker_id=m.worker_id AND c.worker_id=m.worker_id AND c.workspace_id=m.workspace_id AND c.meeting_id=m.meeting_id
    AND c.effect='capture-retrieve' AND c.stage='post-stop-terminal' AND c.operation_id=m.worker_retrieve_operation_id
    AND c.intent_event_id=h.create_intent_id AND c.original_deadline>=clock_timestamp();
  IF body-ARRAY['stop_intent_id','metadata_sha256','terminal_event_id']<>'{}'::jsonb
   OR h.stop_intent_id IS NULL OR h.stop_state NOT IN('inflight','observed','UNKNOWN')
   OR body->>'stop_intent_id' IS DISTINCT FROM h.stop_intent_id::text
   OR m.worker_effect IS DISTINCT FROM 'capture-retrieve' OR m.worker_retrieve_stage IS DISTINCT FROM 'post-stop-terminal'
   OR terminal_receipt.receipt_id IS NULL OR terminal_receipt.bot_id::text IS DISTINCT FROM m.bot_id
   OR terminal_receipt.observation->>'kind' IS DISTINCT FROM 'metadata-observed' OR terminal_receipt.observation->'complete' IS DISTINCT FROM 'true'::jsonb
   OR terminal_receipt.observation->>'bot_id' IS DISTINCT FROM m.bot_id
   OR body->>'metadata_sha256' IS DISTINCT FROM terminal_receipt.observation->>'metadata_sha256'
   OR body->>'metadata_sha256' !~ '^[a-f0-9]{64}$'
   OR jsonb_typeof(terminal_receipt.observation->'latest_status') IS DISTINCT FROM 'object'
   OR NOT ((terminal_receipt.observation->'latest_status')?&ARRAY['code','created_at'])
   OR (terminal_receipt.observation->'latest_status')-ARRAY['code','created_at']<>'{}'::jsonb
   OR jsonb_typeof(terminal_receipt.observation->'latest_status'->'code') IS DISTINCT FROM 'string'
   OR jsonb_typeof(terminal_receipt.observation->'latest_status'->'created_at') IS DISTINCT FROM 'string'
   OR terminal_receipt.observation->'latest_status'->>'code' NOT IN('call_ended','done','fatal')
   OR NOT isfinite((terminal_receipt.observation->'latest_status'->>'created_at')::timestamptz)
   OR (terminal_receipt.observation->'latest_status'->>'created_at')::timestamptz>clock_timestamp() THEN
   RAISE insufficient_privilege USING MESSAGE='actual complete current exact post-STOP terminal receipt required';END IF;
  h.stop_state:='terminal_observed';h.capture_open:=false;
 WHEN 'ingress' THEN
  IF m.bot_id IS NULL OR body->>'bot_id' IS DISTINCT FROM m.bot_id OR body->>'verifier_secret_sha256' IS DISTINCT FROM m.verifier_secret_sha256
   OR body-ARRAY['bot_id','verifier_secret_sha256','provider_event_id','raw_sha256','byte_count','raw_object_key','event_kind']<>'{}'::jsonb
   OR jsonb_typeof(body->'provider_event_id') IS DISTINCT FROM 'string' OR length(body->>'provider_event_id') NOT BETWEEN 1 AND 256
   OR body->>'raw_sha256' !~ '^[a-f0-9]{64}$' OR jsonb_typeof(body->'byte_count') IS DISTINCT FROM 'number'
   OR body->>'byte_count' !~ '^[1-9][0-9]{0,6}$' OR (body->>'byte_count')::integer>1048576
   OR body->>'raw_object_key' IS DISTINCT FROM 'meeting-raw/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||(body->>'raw_sha256')||'.bin'
   OR (body->>'event_kind' NOT IN('transcript.data','transcript.partial_data','transcript.done','transcript.failed') AND body->>'event_kind' !~ '^bot\.[a-z_]{1,64}$')
   OR cardinality(h.pending_ingress)+cardinality(h.processed_ingress)>=4096 THEN RAISE EXCEPTION 'exact bounded installed ingress required';END IF;
  SELECT * INTO old FROM oracle2.meeting_capture_events_v1 WHERE provider=m.provider AND provider_account=m.provider_account AND provider_event_id=body->>'provider_event_id';
  IF old.event_id IS NOT NULL THEN RAISE EXCEPTION 'provider identity collision';END IF;
  target:=CASE body->>'event_kind' WHEN 'transcript.failed' THEN 'failed' WHEN 'bot.fatal' THEN 'failed' WHEN 'bot.in_waiting_room' THEN 'waiting_room' WHEN 'bot.joining_call' THEN 'joining' WHEN 'bot.in_call_not_recording' THEN 'recording_permission_pending' WHEN 'bot.recording_permission_denied' THEN 'recording_permission_denied' WHEN 'bot.recording_permission_allowed' THEN 'recording_permission_pending' WHEN 'bot.in_call_recording' THEN 'capturing' WHEN 'transcript.data' THEN 'capturing' WHEN 'transcript.partial_data' THEN 'capturing' WHEN 'bot.call_ended' THEN 'capture_ended' WHEN 'bot.done' THEN 'final_artifact_pending' WHEN 'transcript.done' THEN 'final_artifact_pending' ELSE 'capture_status_unknown' END;
  h.capture_open:=target='capturing';
 WHEN 'final_artifact' THEN
  IF m.final_artifact_sha256 IS NULL OR body->>'selection_sha256' IS DISTINCT FROM m.final_artifact_sha256
   OR body->>'raw_sha256' !~ '^[a-f0-9]{64}$' OR (body->>'byte_count')::numeric NOT BETWEEN 1 AND 1048576
   OR body->>'raw_object_key' IS DISTINCT FROM 'meeting-raw/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||(body->>'raw_sha256')||'.bin'
   OR body->>'event_kind' IS DISTINCT FROM m.provider||'.final' OR length(body->>'provider_event_id')>256
   OR cardinality(h.pending_ingress)+cardinality(h.processed_ingress)>=4096 THEN RAISE EXCEPTION 'exact installed final artifact required';END IF;
  target:='processing';h.capture_open:=false;
 WHEN 'normalized' THEN
  IF body-ARRAY['ingress_event_id','derivation_sha256','source_id','revision','original_sha256']<>'{}'::jsonb
   OR body->>'derivation_sha256' !~ '^[a-f0-9]{64}$' OR body->>'original_sha256' !~ '^[a-f0-9]{64}$'
   OR NOT ((body->>'ingress_event_id')::uuid=ANY(h.pending_ingress)) THEN RAISE EXCEPTION 'exact retained ingress derivation required';END IF;
  ingress:=(body->>'ingress_event_id')::uuid;
  IF NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_events_v1 e WHERE e.event_id=ingress AND e.workspace_id=m.workspace_id AND e.meeting_id=m.meeting_id AND e.action='final_artifact' AND e.payload->>'selection_sha256'=m.final_artifact_sha256 AND e.payload->>'event_kind'=m.provider||'.final') THEN RAISE EXCEPTION 'whole-final selected parent required';END IF;
  IF NOT EXISTS(SELECT 1 FROM oracle2.source_original_revisions o JOIN oracle2.sources s ON s.workspace_id=o.workspace_id AND s.source_id=o.source_id
    WHERE o.workspace_id=m.workspace_id AND o.source_id=(body->>'source_id')::uuid AND o.revision=(body->>'revision')::integer
    AND o.original_sha256=body->>'original_sha256' AND o.media_type='text/plain' AND s.revision=o.revision AND s.status IN('processing','draft','confirmed') AND NOT EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE w.workspace_id=o.workspace_id AND w.source_id=o.source_id AND w.revision=o.revision)) THEN
   RAISE EXCEPTION 'current retained native text required';END IF;
  target:='review';h.pending_ingress:=array_remove(h.pending_ingress,ingress);h.processed_ingress:=array_append(h.processed_ingress,ingress);
 WHEN 'review' THEN
  IF h.state<>'review' OR body-ARRAY['normalized_event_id','observation']<>'{}'::jsonb
   OR body->>'normalized_event_id' IS DISTINCT FROM h.last_normalized_event_id::text OR body->>'observation' NOT IN('reported','needs_correction','unknown') THEN RAISE EXCEPTION 'reported-only meeting review required';END IF;
 WHEN 'cancel' THEN
  IF body<>'{}'::jsonb THEN RAISE EXCEPTION 'closed local cancel required';END IF;target:='cancelled';
 WHEN 'outbox' THEN
  IF body-ARRAY['ingress_event_id','observation']<>'{}'::jsonb
   OR NOT ((body->>'ingress_event_id')::uuid=ANY(h.pending_ingress)) OR body->>'observation' NOT IN('enqueued','enqueue_failed') THEN RAISE EXCEPTION 'exact durable outbox observation required';END IF;
 ELSE RAISE EXCEPTION 'closed meeting transition required';
 END CASE;
 event:=operation;
 INSERT INTO oracle2.meeting_capture_events_v1 VALUES(event,m.workspace_id,m.meeting_id,h.version+1,m.admission_id,m.principal_id,act,hash,body,operation,
 CASE WHEN act IN('ingress','final_artifact') THEN m.provider END,CASE WHEN act IN('ingress','final_artifact') THEN m.provider_account END,CASE WHEN act IN('ingress','final_artifact') THEN body->>'provider_event_id' END,clock_timestamp());
 IF act IN('ingress','final_artifact') THEN h.pending_ingress:=array_append(h.pending_ingress,event);IF h.capture_open THEN h.last_capture_event_id:=event;END IF;END IF;
 IF act='cancel' THEN h.capture_open:=false;END IF;
 IF act='normalized' THEN h.last_normalized_event_id:=event;END IF;
 UPDATE oracle2.meeting_capture_heads_v1 SET version=h.version+1,state=target,pending_ingress=h.pending_ingress,processed_ingress=h.processed_ingress,
 last_event_id=event,last_normalized_event_id=h.last_normalized_event_id,create_intent_id=h.create_intent_id,last_capture_event_id=h.last_capture_event_id,capture_open=h.capture_open,stop_intent_id=h.stop_intent_id,stop_observation_id=h.stop_observation_id,stop_state=h.stop_state WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id;
 -- Reprove original admission after transition and before caller commit.
 PERFORM oracle2._meeting_capture_admission_v1(selected,seal,act,deadline);
 RETURN jsonb_build_object('event_id',event,'version',h.version+1,'state',target,'created',true,'valid_until',m.expires_at,'meeting_id',m.meeting_id,'capture_until',m.capture_until,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_transition_v1(uuid,text,integer,uuid,text,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_transition_v1(uuid,text,integer,uuid,text,jsonb,timestamptz) TO oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_capture_read_v1(selected uuid,seal text,act text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;events jsonb;
BEGIN
 IF act NOT IN('status','process','ingress','final_artifact','supervise') THEN RAISE EXCEPTION 'fixed meeting read required';END IF;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,act,deadline);
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;

 RETURN jsonb_build_object('meeting_id',m.meeting_id,'version',coalesce(h.version,0),'state',coalesce(h.state,'not_invited'),
 'pending_ingress',coalesce(h.pending_ingress,'{}'::uuid[]),'supervision_binding',CASE WHEN act='supervise' THEN jsonb_build_object('scope_sha256',m.supervision_scope_sha256,'stop_relation_sha256',CASE WHEN m.stop_relation_id IS NOT NULL THEN m.stop_mapping_sha256 ELSE NULL END,'capture_until',m.capture_until,'create_operation_id',h.create_intent_id,'create_request_sha256',(SELECT e.payload->>'request_sha256' FROM oracle2.meeting_capture_events_v1 e WHERE e.event_id=h.create_intent_id),'created_bot',(SELECT jsonb_build_object('bot_id',e.payload->>'bot_id','receipt_sha256',e.payload->>'receipt_sha256','event_id',e.event_id) FROM oracle2._meeting_created_bot_v1(m) e)) ELSE NULL END,'capture_until',m.capture_until,'valid_until',m.expires_at,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at),'ingress_binding',CASE WHEN act='ingress' THEN jsonb_build_object('provider',m.provider,'provider_account',m.provider_account,'tenant_id',m.tenant_id,'provider_meeting_id',m.provider_meeting_id,'bot_id',m.bot_id,'verifier_secret_sha256',m.verifier_secret_sha256) ELSE NULL END,'artifact_binding',CASE WHEN act='final_artifact' THEN jsonb_build_object('provider',m.provider,'provider_account',m.provider_account,'tenant_id',m.tenant_id,'provider_meeting_id',m.provider_meeting_id,'bot_id',m.bot_id,'selection_sha256',m.final_artifact_sha256) ELSE NULL END);
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_read_v1(uuid,text,text,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_read_v1(uuid,text,text,timestamptz) TO oracle2_replacement_requester;

-- Ingress provenance and pending work are reopened by opaque identity only.
CREATE FUNCTION oracle2.meeting_capture_receipt_v1(selected uuid,seal text,wanted uuid,act text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;e oracle2.meeting_capture_events_v1%ROWTYPE;
BEGIN
 IF act NOT IN('process','ingress','final_artifact') THEN RAISE EXCEPTION 'fixed receipt purpose required';END IF;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,act,deadline);
 SELECT * INTO e FROM oracle2.meeting_capture_events_v1 WHERE event_id=wanted AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action IN('ingress','final_artifact');
 IF e.event_id IS NULL AND act='process' THEN RAISE insufficient_privilege USING MESSAGE='retained meeting receipt denied';END IF;
 IF e.event_id IS NOT NULL AND (e.provider<>m.provider OR e.provider_account<>m.provider_account) THEN RAISE insufficient_privilege USING MESSAGE='retained meeting receipt denied';END IF;
 RETURN jsonb_build_object('event_id',wanted,'payload',e.payload,'payload_sha256',e.payload_sha256,'action',e.action,'valid_until',m.expires_at,'meeting_id',m.meeting_id,'capture_until',m.capture_until,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_receipt_v1(uuid,text,uuid,text,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_receipt_v1(uuid,text,uuid,text,timestamptz) TO oracle2_replacement_requester;
-- Revocation shares the same workspace serialization as the current runtime owner.
CREATE FUNCTION oracle2._meeting_capture_revoke_lock_v1() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,oracle2 AS $f$
DECLARE workspace uuid;BEGIN
 SELECT workspace_id INTO workspace FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=NEW.admission_id;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));RETURN NEW;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_capture_revoke_lock_v1() FROM PUBLIC;
CREATE TRIGGER meeting_capture_revocation_lock BEFORE INSERT ON oracle2.meeting_capture_revocations_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_capture_revoke_lock_v1();

-- Frozen private consumption boundary for S08; no public EXECUTE grant.
CREATE FUNCTION oracle2._meeting_capture_current_v1(selected uuid,seal text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;e oracle2.meeting_capture_events_v1%ROWTYPE;
BEGIN
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'status',deadline);
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 SELECT * INTO e FROM oracle2.meeting_capture_events_v1 WHERE event_id=h.last_capture_event_id AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id;
 IF m.bot_id IS NULL OR m.verifier_secret_sha256 IS NULL OR h.meeting_id IS NULL OR NOT h.capture_open OR h.state<>'capturing'
 OR m.capture_until<=clock_timestamp() OR e.event_id IS NULL OR e.action<>'ingress' OR e.provider<>m.provider OR e.provider_account<>m.provider_account
 OR e.payload->>'bot_id' IS DISTINCT FROM m.bot_id OR e.payload->>'verifier_secret_sha256' IS DISTINCT FROM m.verifier_secret_sha256 THEN
  RAISE insufficient_privilege USING MESSAGE='current invited capture denied';
 END IF;
 RETURN jsonb_build_object('workspace_id',m.workspace_id,'meeting_id',m.meeting_id,'provider',m.provider,'provider_account',m.provider_account,
  'tenant_id',m.tenant_id,'provider_meeting_id',m.provider_meeting_id,'bot_id',m.bot_id,'admission_id',m.admission_id,'admission_sha256',m.admission_sha256,
  'capture_event_id',e.event_id,'capture_event_sha256',e.payload_sha256,'capture_revision',h.version,'valid_until',least(m.expires_at,m.capture_until));
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_capture_current_v1(uuid,text,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_capture_end_immutable_v1() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,oracle2 AS $f$
BEGIN IF NEW.capture_until IS DISTINCT FROM OLD.capture_until THEN RAISE EXCEPTION 'original capture end immutable';END IF;RETURN NEW;END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_capture_end_immutable_v1() FROM PUBLIC;
CREATE TRIGGER meeting_capture_end_immutable BEFORE UPDATE ON oracle2.meeting_capture_heads_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_capture_end_immutable_v1();

-- Rooted workspace membership only. This never proves employee identity.
CREATE FUNCTION oracle2._meeting_workspace_actor_current_v1(workspace uuid,actor uuid,deadline timestamptz)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;candidate oracle2.appointments%ROWTYPE;p oracle2.appointments%ROWTYPE;
 until timestamptz:=deadline;branch_until timestamptz;seen uuid[];
BEGIN
 FOR a IN SELECT * FROM oracle2.hosting_request_principal_admissions WHERE principal_id=actor FOR SHARE LOOP
  IF a.workspace_id<>workspace OR a.expires_at<=clock_timestamp() OR NOT EXISTS(
   SELECT 1 FROM oracle2.hosting_role_runtime_admissions r JOIN pg_roles role ON role.rolname=r.role_name
   WHERE r.role_name=a.role_name AND r.runtime_hash=a.runtime_hash AND r.registry_hash=a.registry_hash AND isfinite(r.expires_at) AND r.expires_at>clock_timestamp()
   AND role.rolcanlogin AND NOT(role.rolsuper OR role.rolcreatedb OR role.rolcreaterole OR role.rolreplication OR role.rolbypassrls)) THEN
   RAISE insufficient_privilege USING MESSAGE='contradictory current participant principal denied';END IF;
  until:=least(until,a.expires_at,(SELECT r.expires_at FROM oracle2.hosting_role_runtime_admissions r WHERE r.role_name=a.role_name));
 END LOOP;
 <<candidate_loop>>
 FOR candidate IN SELECT * FROM oracle2.appointments WHERE workspace_id=workspace AND actor_id=actor ORDER BY appointment_id FOR SHARE LOOP
  p:=candidate;seen:='{}';branch_until:=until;
  LOOP
   IF p.appointment_id=ANY(seen) OR cardinality(seen)>=16 OR p.workspace_id<>workspace OR p.revoked_at IS NOT NULL
    OR (p.expires_at IS NOT NULL AND (NOT isfinite(p.expires_at) OR p.expires_at<=clock_timestamp())) THEN CONTINUE candidate_loop;END IF;
   seen:=array_append(seen,p.appointment_id);branch_until:=least(branch_until,coalesce(p.expires_at,branch_until));
   IF p.parent_id IS NULL THEN
    IF p.scope='root' AND branch_until>clock_timestamp() THEN RETURN branch_until;END IF;
    CONTINUE candidate_loop;
   END IF;
   SELECT parent.* INTO p FROM oracle2.appointments parent WHERE parent.appointment_id=p.parent_id AND parent.actor_id=p.granted_by FOR SHARE;
   IF p.appointment_id IS NULL THEN CONTINUE candidate_loop;END IF;
  END LOOP;
 END LOOP;
 RAISE insufficient_privilege USING MESSAGE='current rooted workspace participant denied';
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_workspace_actor_current_v1(uuid,uuid,timestamptz) FROM PUBLIC,oracle2_replacement_requester;
CREATE FUNCTION oracle2._meeting_participant_epoch_current_v1(m oracle2.meeting_capture_admissions_v1,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE e oracle2.meeting_participant_epochs_v1%ROWTYPE;p jsonb;link jsonb;until timestamptz;
BEGIN
 SELECT * INTO e FROM oracle2.meeting_participant_epochs_v1 WHERE epoch_id=m.participant_epoch_id FOR SHARE;
 p:=e.epoch_payload;
 IF e.epoch_id IS NULL OR e.epoch_sha256 IS DISTINCT FROM m.participant_epoch_sha256 OR e.workspace_id<>m.workspace_id OR e.meeting_id<>m.meeting_id
  OR p->>'provider' IS DISTINCT FROM m.provider OR p->>'provider_account' IS DISTINCT FROM m.provider_account OR p->>'tenant_id' IS DISTINCT FROM m.tenant_id
  OR p->>'provider_meeting_id' IS DISTINCT FROM m.provider_meeting_id OR p->>'bot_id' IS DISTINCT FROM m.bot_id
  OR (p->>'capture_until')::timestamptz IS DISTINCT FROM m.capture_until
  OR (p->>'issuer_actor')::uuid=m.principal_id OR (p->>'reviewer_actor')::uuid=m.principal_id OR p->>'issuer_actor'=p->>'reviewer_actor'
  OR (p->>'valid_from')::timestamptz>clock_timestamp() OR (p->>'expires_at')::timestamptz<=clock_timestamp()
  OR NOT isfinite((p->>'expires_at')::timestamptz) OR (p->>'expires_at')::timestamptz>m.capture_until
  OR EXISTS(SELECT 1 FROM oracle2.meeting_participant_epoch_revocations_v1 WHERE epoch_id=e.epoch_id)
  OR EXISTS(SELECT 1 FROM oracle2.meeting_participant_epochs_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND epoch_revision>e.epoch_revision)
  OR jsonb_typeof(p->'links') IS DISTINCT FROM 'array' OR jsonb_array_length(p->'links') NOT BETWEEN 1 AND 4096 THEN
  RAISE insufficient_privilege USING MESSAGE='current exact participant epoch denied';END IF;
 until:=least(deadline,m.expires_at,m.capture_until,(p->>'expires_at')::timestamptz);
 FOR link IN SELECT value FROM jsonb_array_elements(p->'links') LOOP
  IF link->>'attribution'='workspace_actor' THEN until:=least(until,oracle2._meeting_workspace_actor_current_v1(m.workspace_id,(link->>'actor_id')::uuid,until));END IF;
 END LOOP;
 RETURN jsonb_build_object('epoch',p,'epoch_sha256',e.epoch_sha256,'valid_until',until);
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participant_epoch_current_v1(oracle2.meeting_capture_admissions_v1,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

-- Meeting-only current finalized utterance consumer. No shared-source or send
-- grant: an independently installed explicit participant_turn action is needed.
CREATE FUNCTION oracle2.meeting_capture_current_turn_v1(selected uuid,seal text,wanted uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;c jsonb;epoch jsonb;e oracle2.meeting_capture_events_v1%ROWTYPE;
BEGIN
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'participant_turn',deadline);
 c:=oracle2._meeting_capture_current_v1(selected,seal,deadline);
 epoch:=oracle2._meeting_participant_epoch_current_v1(m,deadline);
 IF wanted IS NULL OR wanted::text IS DISTINCT FROM c->>'capture_event_id' THEN RAISE insufficient_privilege USING MESSAGE='exact latest current participant turn required';END IF;
 SELECT * INTO e FROM oracle2.meeting_capture_events_v1 WHERE event_id=wanted AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='ingress' FOR SHARE;
 IF e.event_id IS NULL OR e.payload->>'event_kind' IS DISTINCT FROM 'transcript.data' THEN RAISE insufficient_privilege USING MESSAGE='finalized current utterance required';END IF;
 RETURN jsonb_build_object('capture',c,'epoch',epoch->'epoch','epoch_sha256',epoch->>'epoch_sha256','valid_until',epoch->>'valid_until','receipt',jsonb_build_object('event_id',wanted,'payload',e.payload,'payload_sha256',e.payload_sha256,'action',e.action,'valid_until',least(m.expires_at,m.capture_until),'meeting_id',m.meeting_id,'capture_until',m.capture_until,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),least(m.expires_at,m.capture_until))));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_current_turn_v1(uuid,text,uuid,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_current_turn_v1(uuid,text,uuid,timestamptz) TO oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_participant_epoch_change_lock_v1() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,oracle2 AS $f$
DECLARE workspace uuid;BEGIN
 IF TG_TABLE_NAME='meeting_participant_epochs_v1' THEN workspace:=NEW.workspace_id;
 ELSIF TG_TABLE_NAME='meeting_participant_epoch_revocations_v1' THEN SELECT workspace_id INTO workspace FROM oracle2.meeting_participant_epochs_v1 WHERE epoch_id=NEW.epoch_id;
 ELSE RAISE EXCEPTION 'fixed participant epoch installation table required';END IF;
 IF workspace IS NULL THEN RAISE EXCEPTION 'exact participant epoch workspace required';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));RETURN NEW;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participant_epoch_change_lock_v1() FROM PUBLIC;
CREATE TRIGGER participant_epoch_install_lock BEFORE INSERT ON oracle2.meeting_participant_epochs_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_participant_epoch_change_lock_v1();
CREATE TRIGGER participant_epoch_revoke_lock BEFORE INSERT ON oracle2.meeting_participant_epoch_revocations_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_participant_epoch_change_lock_v1();

-- One installed meeting's actual due queue; never a caller-created liveness flag.
CREATE FUNCTION oracle2.meeting_capture_due_stop_v1(selected uuid,seal text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;created oracle2.meeting_capture_events_v1%ROWTYPE;due_at timestamptz;pre_stop jsonb;
BEGIN
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'supervise',deadline);
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 IF h.meeting_id IS NULL OR m.stop_margin_seconds IS NULL OR m.stop_until IS NULL OR m.stop_until>m.original_horizon THEN RAISE insufficient_privilege USING MESSAGE='actual independently installed due-stop queue missing';END IF;
 SELECT * INTO created FROM oracle2._meeting_created_bot_v1(m);
 -- Private descriptive link to an ACTUAL complete independently appointed
 -- pre-stop receipt. No caller metadata, role adaptation or new effect grant.
 SELECT jsonb_build_object('receipt_id',r.receipt_id,'claim_id',c.claim_id,'operation_id',c.operation_id,
  'bot_id',c.bot_id,'metadata_sha256',r.observation->>'metadata_sha256') INTO pre_stop
 FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 c USING(claim_id)
 JOIN oracle2.meeting_capture_admissions_v1 a ON a.admission_id=c.admission_id
 WHERE m.stop_relation_id IS NOT NULL AND c.workspace_id=m.workspace_id AND c.meeting_id=m.meeting_id
  AND c.intent_event_id=h.create_intent_id AND c.effect='capture-retrieve' AND c.stage='pre-stop-consistency'
  AND c.operation_id=a.worker_retrieve_operation_id AND a.worker_retrieve_stage=c.stage AND a.worker_effect=c.effect
  AND c.worker_id=a.worker_id AND r.worker_id=c.worker_id AND r.admission_id=a.admission_id
  AND a.workspace_id=m.workspace_id AND a.meeting_id=m.meeting_id AND a.provider=m.provider AND a.provider_account=m.provider_account
  AND a.tenant_id=m.tenant_id AND a.provider_meeting_id=m.provider_meeting_id
  AND a.stop_relation_id=m.stop_relation_id AND a.stop_mapping_sha256=m.stop_mapping_sha256
  AND c.bot_id::text=created.payload->>'bot_id' AND r.observation->>'bot_id'=c.bot_id::text
  AND r.observation->>'kind'='metadata-observed' AND r.observation->'complete'='true'::jsonb
  AND r.observation->>'metadata_sha256'~'^[a-f0-9]{64}$'
  AND c.original_deadline>clock_timestamp() AND r.created_at<=clock_timestamp()
  AND a.valid_from<=clock_timestamp() AND a.expires_at>clock_timestamp() AND a.original_horizon>=m.capture_until
  AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_revocations_v1 WHERE admission_id=a.admission_id)
  AND oracle2._meeting_capture_lineage_v1(a)>clock_timestamp()
 ORDER BY r.created_at DESC LIMIT 1;
 due_at:=m.capture_until-make_interval(secs=>m.stop_margin_seconds);
 RETURN jsonb_build_object('workspace_id',m.workspace_id,'meeting_id',m.meeting_id,'version',h.version,'capture_until',m.capture_until,'stop_valid_from',m.stop_valid_from,'stop_until',m.stop_until,'original_horizon',m.original_horizon,'due_at',due_at,'due',created.event_id IS NOT NULL AND clock_timestamp()>=due_at,'create_intent_id',h.create_intent_id,'created_bot',created.payload,'pre_stop_observation',pre_stop,'stop_intent_id',h.stop_intent_id,'stop_observation_id',h.stop_observation_id,'stop_state',h.stop_state,'stop_mapping_sha256',m.stop_mapping_sha256,'stop_relation',oracle2._meeting_stop_relation_v1(m),'scheduler_poll_seconds',m.scheduler_poll_seconds,'stop_request_seconds',m.stop_request_seconds,'safety_allowance_seconds',m.safety_allowance_seconds,'stop_margin_seconds',m.stop_margin_seconds,'valid_until',m.expires_at,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_due_stop_v1(uuid,text,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_due_stop_v1(uuid,text,timestamptz) TO oracle2_replacement_requester;

-- Exact selected final raw mapping; same current workspace actor boundary as live.
CREATE FUNCTION oracle2.meeting_capture_current_final_mapping_v1(selected uuid,seal text,wanted uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;row oracle2.meeting_final_mappings_v1%ROWTYPE;e oracle2.meeting_capture_events_v1%ROWTYPE;body jsonb;link jsonb;until timestamptz;actor_end timestamptz;
BEGIN
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'process',deadline);
 SELECT * INTO e FROM oracle2.meeting_capture_events_v1 WHERE event_id=wanted AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='final_artifact' FOR SHARE;
 SELECT * INTO row FROM oracle2.meeting_final_mappings_v1 WHERE mapping_id=m.final_mapping_id AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 IF e.event_id IS NULL OR e.payload->>'selection_sha256' IS DISTINCT FROM m.final_artifact_sha256 OR row.mapping_id IS NULL
  OR row.mapping_sha256 IS DISTINCT FROM m.final_mapping_sha256 OR row.raw_sha256 IS DISTINCT FROM e.payload->>'raw_sha256'
  OR EXISTS(SELECT 1 FROM oracle2.meeting_final_mapping_revocations_v1 WHERE mapping_id=row.mapping_id)
  OR EXISTS(SELECT 1 FROM oracle2.meeting_final_mappings_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND raw_sha256=row.raw_sha256 AND mapping_revision>row.mapping_revision) THEN RAISE insufficient_privilege USING MESSAGE='exact current final mapping denied';END IF;
 body:=row.mapping_payload;
 IF body->>'provider' IS DISTINCT FROM m.provider OR body->>'provider_account' IS DISTINCT FROM m.provider_account OR body->>'tenant_id' IS DISTINCT FROM m.tenant_id OR body->>'provider_meeting_id' IS DISTINCT FROM m.provider_meeting_id
  OR (body->>'issuer_actor')::uuid=(body->>'reviewer_actor')::uuid OR m.principal_id IN((body->>'issuer_actor')::uuid,(body->>'reviewer_actor')::uuid)
  OR NOT isfinite((body->>'expires_at')::timestamptz) OR NOT isfinite((body->>'original_horizon')::timestamptz)
  OR (body->>'valid_from')::timestamptz>clock_timestamp() OR (body->>'expires_at')::timestamptz<=clock_timestamp()
  OR (body->>'expires_at')::timestamptz>(body->>'original_horizon')::timestamptz OR (body->>'original_horizon')::timestamptz>m.original_horizon
  OR jsonb_typeof(body->'links') IS DISTINCT FROM 'array' OR jsonb_array_length(body->'links') NOT BETWEEN 1 AND 4096 THEN RAISE insufficient_privilege USING MESSAGE='independent finite final workspace mapping required';END IF;
 until:=least(m.expires_at,(body->>'expires_at')::timestamptz,(body->>'original_horizon')::timestamptz);
 FOR link IN SELECT value FROM jsonb_array_elements(body->'links') LOOP
  IF link->>'attribution'='workspace_actor' THEN
   actor_end:=oracle2._meeting_workspace_actor_current_v1(m.workspace_id,(link->>'actor_id')::uuid,until);until:=least(until,actor_end);
  ELSIF link->>'attribution' NOT IN('unknown','oracle') OR link->'actor_id'<>'null'::jsonb THEN RAISE insufficient_privilege USING MESSAGE='whole-final employee or guessed actor denied';END IF;
 END LOOP;
 IF until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='final workspace mapping elapsed';END IF;
 RETURN jsonb_build_object('receipt',oracle2.meeting_capture_receipt_v1(selected,seal,wanted,'process',deadline),'mapping',body,'mapping_sha256',row.mapping_sha256,'valid_until',until);
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_current_final_mapping_v1(uuid,text,uuid,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_current_final_mapping_v1(uuid,text,uuid,timestamptz) TO oracle2_replacement_requester;
CREATE FUNCTION oracle2._meeting_final_mapping_lock_v1() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,oracle2 AS $f$
DECLARE workspace uuid;BEGIN
 IF TG_TABLE_NAME='meeting_final_mappings_v1' THEN workspace:=NEW.workspace_id;ELSE SELECT workspace_id INTO workspace FROM oracle2.meeting_final_mappings_v1 WHERE mapping_id=NEW.mapping_id;END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));RETURN NEW;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_final_mapping_lock_v1() FROM PUBLIC;
CREATE TRIGGER meeting_final_mapping_install_lock BEFORE INSERT ON oracle2.meeting_final_mappings_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_final_mapping_lock_v1();
CREATE TRIGGER meeting_final_mapping_revoke_lock BEFORE INSERT ON oracle2.meeting_final_mapping_revocations_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_final_mapping_lock_v1();

-- Worker rows below are delivery custody for EXISTING capture business intents.
-- NULL legacy admissions retain their old APIs and grant no new worker effect.
ALTER TABLE oracle2.meeting_capture_admissions_v1
 ADD COLUMN worker_id uuid, ADD COLUMN worker_effect text,
 ADD COLUMN worker_policy_sha256 text,ADD COLUMN worker_create_operation_id uuid,
 ADD COLUMN worker_create_request_sha256 text,ADD COLUMN worker_retrieve_stage text,
 ADD COLUMN worker_retrieve_operation_id uuid,
 ADD CONSTRAINT meeting_worker_exact_installation_v1 CHECK (
  (worker_id IS NULL AND worker_effect IS NULL AND worker_policy_sha256 IS NULL
   AND worker_create_operation_id IS NULL AND worker_create_request_sha256 IS NULL
   AND worker_retrieve_stage IS NULL AND worker_retrieve_operation_id IS NULL)
  OR (worker_id IS NOT NULL AND worker_effect IS NOT NULL AND worker_effect IN('capture-create','capture-leave','capture-retrieve')
   AND worker_policy_sha256 IS NOT NULL AND worker_policy_sha256~'^[a-f0-9]{64}$'
   AND ((worker_effect='capture-create' AND worker_create_operation_id IS NOT NULL
    AND worker_create_request_sha256 IS NOT NULL AND worker_create_request_sha256~'^[a-f0-9]{64}$')
    OR (worker_effect<>'capture-create' AND worker_create_operation_id IS NULL AND worker_create_request_sha256 IS NULL))
   AND ((worker_effect='capture-retrieve' AND worker_retrieve_stage IS NOT NULL AND worker_retrieve_stage IN('pre-stop-consistency','post-stop-terminal') AND worker_retrieve_operation_id IS NOT NULL)
    OR (worker_effect<>'capture-retrieve' AND worker_retrieve_stage IS NULL AND worker_retrieve_operation_id IS NULL))));
CREATE TABLE oracle2.meeting_capture_worker_claims_v1 (
 claim_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,
 intent_event_id uuid NOT NULL REFERENCES oracle2.meeting_capture_events_v1(event_id),
 effect text NOT NULL CHECK(effect IN('capture-create','capture-leave','capture-retrieve')),
 stage text NOT NULL CHECK(stage IN('-','pre-stop-consistency','post-stop-terminal')),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),worker_id uuid NOT NULL,
 operation_id uuid NOT NULL,request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),bot_id uuid,
 original_deadline timestamptz NOT NULL CHECK(isfinite(original_deadline)),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((effect='capture-create')=(bot_id IS NULL)),CHECK((effect='capture-retrieve')=(stage<>'-')),
 UNIQUE(workspace_id,meeting_id,intent_event_id,effect,stage));
CREATE TABLE oracle2.meeting_capture_worker_receipts_v1 (
 receipt_id uuid PRIMARY KEY,claim_id uuid NOT NULL UNIQUE REFERENCES oracle2.meeting_capture_worker_claims_v1(claim_id),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),worker_id uuid NOT NULL,
 wire_object_key text NOT NULL,wire_sha256 text NOT NULL CHECK(wire_sha256~'^[a-f0-9]{64}$'),
 wire_byte_count integer NOT NULL CHECK(wire_byte_count BETWEEN 0 AND 1064960),
 observation jsonb NOT NULL CHECK(jsonb_typeof(observation)='object' AND octet_length(observation::text)<=16384),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp());
REVOKE ALL ON oracle2.meeting_capture_worker_claims_v1,oracle2.meeting_capture_worker_receipts_v1 FROM PUBLIC,oracle2_replacement_requester;
CREATE TRIGGER immutable_meeting_capture_worker_claims_v1 BEFORE UPDATE OR DELETE ON oracle2.meeting_capture_worker_claims_v1
 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
CREATE TRIGGER immutable_meeting_capture_worker_receipts_v1 BEFORE UPDATE OR DELETE ON oracle2.meeting_capture_worker_receipts_v1
 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();

-- ONE private creation relation owner. STOP retains its own current admission.
-- Forensic after-close facts additionally require their exact immutable delivery
-- claim/receipt; they never reopen the capture head or issue a bot mapping.
CREATE FUNCTION oracle2._meeting_created_bot_v1(m oracle2.meeting_capture_admissions_v1)
 RETURNS oracle2.meeting_capture_events_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE created oracle2.meeting_capture_events_v1%ROWTYPE;BEGIN
 SELECT e.* INTO created FROM oracle2.meeting_capture_events_v1 e
 JOIN oracle2.meeting_capture_heads_v1 h USING(workspace_id,meeting_id)
 JOIN oracle2.meeting_capture_admissions_v1 a ON a.admission_id=e.admission_id
 JOIN oracle2.meeting_capture_events_v1 original ON original.event_id=h.create_intent_id AND original.action='create_intent'
 JOIN oracle2.meeting_capture_admissions_v1 ia ON ia.admission_id=original.admission_id
 WHERE e.workspace_id=m.workspace_id AND e.meeting_id=m.meeting_id
 AND e.payload->>'intent_id'=h.create_intent_id::text
 AND a.provider=m.provider AND a.provider_account=m.provider_account
 AND a.tenant_id=m.tenant_id AND a.provider_meeting_id=m.provider_meeting_id
 AND ia.provider=a.provider AND ia.provider_account=a.provider_account AND ia.tenant_id=a.tenant_id AND ia.provider_meeting_id=a.provider_meeting_id
 AND (e.action='create_observed' OR (e.action='create_observed_after_close' AND EXISTS(
  SELECT 1 FROM oracle2.meeting_capture_worker_claims_v1 c
  JOIN oracle2.meeting_capture_worker_receipts_v1 r ON r.claim_id=c.claim_id
  JOIN oracle2.meeting_capture_events_v1 i ON i.event_id=c.intent_event_id
  WHERE c.workspace_id=e.workspace_id AND c.meeting_id=e.meeting_id AND c.effect='capture-create'
  AND i.action='create_intent' AND i.operation_id=h.create_intent_id AND c.operation_id=i.operation_id
  AND c.request_sha256=i.payload->>'request_sha256' AND c.admission_id=e.admission_id
  AND r.admission_id=c.admission_id AND r.worker_id=c.worker_id
  AND e.payload->>'claim_id'=c.claim_id::text AND e.payload->>'receipt_id'=r.receipt_id::text
  AND e.payload->>'receipt_sha256'=r.wire_sha256 AND e.payload->>'request_sha256'=c.request_sha256
  AND r.observation->>'kind'='create-observed' AND r.observation->'complete'='true'::jsonb
  AND r.observation->>'bot_id'=e.payload->>'bot_id'
  AND e.payload->>'provider_account'=a.provider_account AND e.payload->>'tenant_id'=a.tenant_id
  AND e.payload->>'provider_meeting_id'=a.provider_meeting_id)))
 AND (m.stop_relation_id IS NULL OR EXISTS(
  SELECT 1 FROM oracle2.meeting_capture_worker_claims_v1 c JOIN oracle2.meeting_capture_worker_receipts_v1 r USING(claim_id)
   JOIN oracle2.meeting_create_stop_relations_v1 mapping ON mapping.mapping_id=m.stop_relation_id
   WHERE c.workspace_id=m.workspace_id AND c.meeting_id=m.meeting_id AND c.effect='capture-create' AND c.intent_event_id=(e.payload->>'intent_id')::uuid
    AND c.operation_id::text=mapping.mapping_payload->>'create_operation_id' AND c.request_sha256=mapping.mapping_payload->>'create_request_sha256'
    AND r.receipt_id=e.operation_id AND r.admission_id=e.admission_id AND c.admission_id=e.admission_id
    AND r.observation->>'kind'='create-observed' AND r.observation->'complete'='true'::jsonb
    AND r.observation->>'bot_id'=e.payload->>'bot_id' AND r.wire_sha256=e.payload->>'receipt_sha256'))
 ORDER BY e.version DESC LIMIT 1;
 RETURN created;END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_created_bot_v1(oracle2.meeting_capture_admissions_v1) FROM PUBLIC,oracle2_replacement_requester;

-- Fixed delivery API: no caller-selected effect, stage, worker, body or grant.
CREATE FUNCTION oracle2.meeting_capture_worker_v1(selected uuid,seal text,command text,
 wanted_operation uuid,wanted_claim uuid,body_sha256 text,wire jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;
 intent oracle2.meeting_capture_events_v1%ROWTYPE;proof oracle2.meeting_capture_events_v1%ROWTYPE;
 supervisor oracle2.meeting_capture_admissions_v1%ROWTYPE;claimed oracle2.meeting_capture_worker_claims_v1%ROWTYPE;
 received oracle2.meeting_capture_worker_receipts_v1%ROWTYPE;act text;delivery_stage text;op uuid;bot uuid;hash text;
 state text:='idle';fresh boolean:=false;until timestamptz;expected_key text;semantic jsonb;semantic_hash text;existing_semantic oracle2.meeting_capture_events_v1%ROWTYPE;
BEGIN
 IF command IS NULL OR command NOT IN('prepare','claim','current','observe','status')
 OR (command<>'observe' AND wire IS NOT NULL) OR (command='prepare' AND (wanted_operation IS NOT NULL OR wanted_claim IS NOT NULL))
 OR (command IN('current','observe') AND (wanted_operation IS NULL OR wanted_claim IS NULL))
 OR (command='claim' AND (wanted_operation IS NULL OR wanted_claim IS NOT NULL)) THEN
  RAISE EXCEPTION 'fixed closed worker operation required';END IF;
 SELECT * INTO m FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=selected;
 IF m.worker_id IS NULL OR m.worker_effect IS NULL OR m.worker_policy_sha256 IS NULL THEN
  RAISE insufficient_privilege USING MESSAGE='independently installed worker admission required';END IF;
 act:=CASE WHEN command='status' THEN 'status' WHEN m.worker_effect='capture-create' AND command='observe' THEN 'create_observed'
  WHEN m.worker_effect='capture-create' THEN 'create_intent' WHEN m.worker_effect='capture-leave' AND command='observe' THEN 'stop_observed'
  WHEN m.worker_effect='capture-leave' THEN 'stop_intent' ELSE 'stop_reconciled' END;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,act,deadline);
 IF (m.worker_effect='capture-create' AND NOT ARRAY['create_intent','create_observed','create_unknown','status']::text[]<@m.actions)
  OR (m.worker_effect='capture-leave' AND NOT ARRAY['stop_intent','stop_observed','stop_unknown','status']::text[]<@m.actions)
  OR (m.worker_effect='capture-retrieve' AND NOT ARRAY['stop_reconciled','status']::text[]<@m.actions) THEN
  RAISE insufficient_privilege USING MESSAGE='complete independently installed worker actions required';END IF;
 IF m.worker_effect='capture-create' AND m.stop_relation_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='preinstalled unattended operation STOP relation required';END IF;
 IF m.provider<>'recall' OR m.worker_effect NOT IN('capture-create','capture-leave','capture-retrieve') THEN
  RAISE insufficient_privilege USING MESSAGE='exact installed Recall worker required';END IF;
 delivery_stage:=coalesce(m.worker_retrieve_stage,'-');
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-meeting:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 IF h.meeting_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='existing invitation required';END IF;
 SELECT * INTO intent FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id
  AND operation_id=CASE WHEN m.worker_effect='capture-leave' THEN h.stop_intent_id ELSE h.create_intent_id END
  AND action=CASE WHEN m.worker_effect='capture-leave' THEN 'stop_intent' ELSE 'create_intent' END FOR SHARE;
 IF intent.event_id IS NULL AND command='prepare' AND m.worker_effect='capture-create' THEN
  SELECT * INTO proof FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id
   AND admission_id=m.supervisor_admission_id AND action='supervised'
   AND payload->>'create_operation_id'=m.worker_create_operation_id::text
   AND payload->>'request_sha256'=m.worker_create_request_sha256 ORDER BY version DESC LIMIT 1 FOR SHARE;
  IF proof.event_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='actual independent supervisor receipt required before prepare';END IF;
  PERFORM oracle2.meeting_capture_transition_v1(selected,seal,h.version,m.worker_create_operation_id,'create_intent',
   jsonb_build_object('request_sha256',m.worker_create_request_sha256,'supervisor_event_id',proof.event_id,
    'supervisor_event_sha256',proof.payload_sha256,'supervisor_witness_sha256',proof.payload->>'witness_sha256'),deadline);
  SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
  SELECT * INTO intent FROM oracle2.meeting_capture_events_v1 WHERE event_id=h.create_intent_id AND action='create_intent'
   AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 END IF;
 IF intent.event_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='existing business intent required before delivery';END IF;
 IF NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_admissions_v1 original WHERE original.admission_id=intent.admission_id
  AND original.workspace_id=m.workspace_id AND original.meeting_id=m.meeting_id AND original.provider=m.provider
  AND original.provider_account=m.provider_account AND original.tenant_id=m.tenant_id AND original.provider_meeting_id=m.provider_meeting_id) THEN
  RAISE insufficient_privilege USING MESSAGE='exact existing intent provider scope required';END IF;
 op:=CASE WHEN m.worker_effect='capture-create' THEN m.worker_create_operation_id
  WHEN m.worker_effect='capture-retrieve' THEN m.worker_retrieve_operation_id ELSE intent.operation_id END;
 hash:=CASE WHEN m.worker_effect='capture-create' THEN m.worker_create_request_sha256 ELSE encode(sha256(''::bytea),'hex') END;
 IF op IS NULL OR hash IS NULL OR (body_sha256 IS NOT NULL AND body_sha256 IS DISTINCT FROM hash)
 OR (wanted_operation IS NOT NULL AND wanted_operation IS DISTINCT FROM op) THEN RAISE EXCEPTION 'exact immutable operation and body required';END IF;
 IF m.worker_effect='capture-create' THEN
  IF intent.operation_id IS DISTINCT FROM op OR intent.payload->>'request_sha256' IS DISTINCT FROM hash THEN
   RAISE insufficient_privilege USING MESSAGE='installed create binding differs';END IF;
 ELSE
  SELECT * INTO proof FROM oracle2._meeting_created_bot_v1(m);
  IF m.stop_relation_id IS NOT NULL THEN
   IF proof.payload->>'intent_id' IS DISTINCT FROM oracle2._meeting_stop_relation_v1(m)->>'create_operation_id' THEN RAISE insufficient_privilege USING MESSAGE='immutable mapped Create operation required';END IF;
   IF m.bot_id IS NOT NULL AND m.bot_id IS DISTINCT FROM proof.payload->>'bot_id' THEN RAISE insufficient_privilege USING MESSAGE='explicit bot contradicts immutable operation relation';END IF;
   m.bot_id:=proof.payload->>'bot_id';
  END IF;
  IF proof.event_id IS NULL OR proof.payload->>'bot_id' IS DISTINCT FROM m.bot_id OR m.stop_mapping_sha256 IS NULL
   OR m.bot_id !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' THEN
   RAISE insufficient_privilege USING MESSAGE='exact independently mapped created bot required';END IF;
  bot:=m.bot_id::uuid;
 END IF;
 SELECT * INTO claimed FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id
  AND intent_event_id=intent.event_id AND effect=m.worker_effect AND meeting_capture_worker_claims_v1.stage=delivery_stage;
 IF claimed.claim_id IS NOT NULL THEN
  -- No newly admitted generation can reset or inherit execution authority.
  IF claimed.operation_id IS DISTINCT FROM op OR claimed.request_sha256 IS DISTINCT FROM hash OR claimed.bot_id IS DISTINCT FROM bot THEN
   RAISE EXCEPTION 'retained delivery binding collision';END IF;
  SELECT * INTO received FROM oracle2.meeting_capture_worker_receipts_v1 WHERE claim_id=claimed.claim_id;
  state:=CASE WHEN received.receipt_id IS NOT NULL AND received.observation->>'kind' IN('create-observed','leave-observed','metadata-observed') THEN 'observed' ELSE 'UNKNOWN' END;
 END IF;
 IF command IN('claim','current') THEN
  IF h.state IN('UNKNOWN','cancelled') AND m.worker_effect='capture-create' THEN RAISE insufficient_privilege USING MESSAGE='closed capture cannot create';END IF;
  IF m.worker_effect='capture-create' THEN
   SELECT * INTO proof FROM oracle2.meeting_capture_events_v1 WHERE event_id=(intent.payload->>'supervisor_event_id')::uuid
    AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='supervised' FOR SHARE;
   SELECT * INTO supervisor FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=m.supervisor_admission_id FOR SHARE;
   IF proof.event_id IS NULL OR supervisor.admission_id IS NULL OR supervisor.principal_id=m.principal_id OR proof.admission_id IS DISTINCT FROM supervisor.admission_id
    OR proof.actor_id IS DISTINCT FROM supervisor.principal_id OR proof.payload_sha256 IS DISTINCT FROM intent.payload->>'supervisor_event_sha256'
    OR proof.payload->>'witness_sha256' IS DISTINCT FROM intent.payload->>'supervisor_witness_sha256'
    OR proof.payload->>'request_sha256' IS DISTINCT FROM hash OR proof.payload->>'create_operation_id' IS DISTINCT FROM op::text
    OR proof.payload->>'scope_sha256' IS DISTINCT FROM m.supervision_scope_sha256 OR supervisor.supervision_scope_sha256 IS DISTINCT FROM m.supervision_scope_sha256 THEN
    RAISE insufficient_privilege USING MESSAGE='immutable original independent supervisor intent binding required';END IF;
   -- Preserve that original intent/witness forever. A new independently observed
   -- receipt can prove currentness of ONLY the same operation/scope, never renew
   -- the original claim, windows, STOP relation or capture permission.
   SELECT * INTO proof FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id
    AND admission_id=supervisor.admission_id AND actor_id=supervisor.principal_id AND action='supervised'
    AND payload->>'create_operation_id'=op::text AND payload->>'request_sha256'=hash
    AND payload->>'scope_sha256'=m.supervision_scope_sha256 ORDER BY version DESC LIMIT 1 FOR SHARE;
   IF proof.event_id IS NULL OR supervisor.capture_until IS DISTINCT FROM m.capture_until
    OR supervisor.valid_from>clock_timestamp() OR supervisor.expires_at<=clock_timestamp()
    OR (proof.payload->>'observed_at')::timestamptz>clock_timestamp()
    OR (proof.payload->>'valid_until')::timestamptz<=clock_timestamp() OR m.capture_until<=clock_timestamp()
    OR EXISTS(SELECT 1 FROM oracle2.meeting_capture_revocations_v1 WHERE admission_id=supervisor.admission_id) THEN
    RAISE insufficient_privilege USING MESSAGE='fresh independent actual supervisor required before effect';END IF;
   IF NOT EXISTS(SELECT 1 FROM oracle2.hosting_request_principal_admissions a JOIN oracle2.hosting_role_runtime_admissions r USING(role_name)
    JOIN pg_roles role ON role.rolname=a.role_name WHERE a.role_name=supervisor.role_name AND a.principal_id=supervisor.principal_id
    AND a.workspace_id=m.workspace_id AND a.runtime_hash=supervisor.runtime_hash AND a.registry_hash=supervisor.registry_hash
    AND r.runtime_hash=a.runtime_hash AND r.registry_hash=a.registry_hash AND a.expires_at>clock_timestamp() AND r.expires_at>clock_timestamp()
    AND isfinite(r.expires_at) AND role.rolcanlogin AND NOT(role.rolsuper OR role.rolcreatedb OR role.rolcreaterole OR role.rolreplication OR role.rolbypassrls)) THEN
    RAISE insufficient_privilege USING MESSAGE='current independent supervisor process role required';END IF;
   PERFORM oracle2._meeting_capture_lineage_v1(supervisor);
  ELSIF m.worker_effect='capture-leave' AND h.stop_state<>'inflight' THEN RAISE insufficient_privilege USING MESSAGE='current exact STOP intent required';
  ELSIF m.worker_effect='capture-retrieve' THEN
   IF (delivery_stage='pre-stop-consistency' AND h.stop_intent_id IS NOT NULL)
    OR (delivery_stage='post-stop-terminal' AND h.stop_intent_id IS NULL) THEN RAISE insufficient_privilege USING MESSAGE='fixed retrieval stage differs from current STOP';END IF;
  END IF;
 END IF;
 IF command='claim' AND claimed.claim_id IS NULL THEN
  IF body_sha256 IS DISTINCT FROM hash THEN RAISE EXCEPTION 'actual independently pinned body must be checked before claim';END IF;
  INSERT INTO oracle2.meeting_capture_worker_claims_v1(claim_id,workspace_id,meeting_id,intent_event_id,effect,stage,admission_id,worker_id,operation_id,request_sha256,bot_id,original_deadline)
   VALUES(gen_random_uuid(),m.workspace_id,m.meeting_id,intent.event_id,m.worker_effect,delivery_stage,selected,m.worker_id,op,hash,bot,least(m.expires_at,deadline)) RETURNING * INTO claimed;
  state:='claimed';fresh:=true;
 ELSIF command='prepare' AND claimed.claim_id IS NULL THEN state:='prepared';
 ELSIF command IN('current','observe') THEN
  IF claimed.claim_id IS NULL OR claimed.claim_id IS DISTINCT FROM wanted_claim OR claimed.admission_id<>selected OR claimed.worker_id<>m.worker_id
   OR claimed.original_deadline<=clock_timestamp() OR deadline>claimed.original_deadline THEN RAISE insufficient_privilege USING MESSAGE='current exact own claimed delivery required';END IF;
  IF command='current' THEN
   IF received.receipt_id IS NOT NULL THEN RAISE insufficient_privilege USING MESSAGE='observed delivery cannot execute again';END IF;
   state:='inflight';
  ELSE
   IF jsonb_typeof(wire) IS DISTINCT FROM 'object' OR NOT(wire?&ARRAY['wire_object_key','wire_sha256','wire_byte_count','observation'])
    OR wire-ARRAY['wire_object_key','wire_sha256','wire_byte_count','observation']<>'{}'::jsonb
    OR jsonb_typeof(wire->'wire_sha256') IS DISTINCT FROM 'string' OR wire->>'wire_sha256' !~ '^[a-f0-9]{64}$'
    OR jsonb_typeof(wire->'wire_byte_count') IS DISTINCT FROM 'number' OR wire->>'wire_byte_count' !~ '^(0|[1-9][0-9]{0,6})$'
    OR (wire->>'wire_byte_count')::integer>1064960 OR jsonb_typeof(wire->'observation') IS DISTINCT FROM 'object'
    OR NOT((wire->'observation')?&ARRAY['kind','bot_id','latest_status','complete'])
    OR (wire->'observation')-ARRAY['kind','bot_id','latest_status','complete','metadata_sha256']<>'{}'::jsonb
    OR (wire->'observation'->>'kind'='metadata-observed' AND (jsonb_typeof(wire->'observation'->'metadata_sha256') IS DISTINCT FROM 'string' OR wire->'observation'->>'metadata_sha256' !~ '^[a-f0-9]{64}$'))
    OR (wire->'observation'->>'kind'<>'metadata-observed' AND (wire->'observation')?'metadata_sha256')
    OR jsonb_typeof(wire->'observation'->'kind') IS DISTINCT FROM 'string'
    OR wire->'observation'->>'kind' NOT IN('create-observed','leave-observed','metadata-observed','UNKNOWN')
    OR jsonb_typeof(wire->'observation'->'complete') IS DISTINCT FROM 'boolean'
    OR (wire->'observation'->>'kind'<>'UNKNOWN' AND wire->'observation'->'complete'<>'true'::jsonb) THEN
    RAISE EXCEPTION 'exact retained bounded response custody required';END IF;
   IF wire->'observation'->>'kind'<>'UNKNOWN' AND (
    wire->'observation'->>'kind' IS DISTINCT FROM CASE m.worker_effect WHEN 'capture-create' THEN 'create-observed' WHEN 'capture-leave' THEN 'leave-observed' ELSE 'metadata-observed' END
    OR jsonb_typeof(wire->'observation'->'bot_id') IS DISTINCT FROM 'string'
    OR wire->'observation'->>'bot_id' !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
    OR (m.worker_effect<>'capture-create' AND wire->'observation'->>'bot_id' IS DISTINCT FROM bot::text)
    OR (wire->>'wire_byte_count')::integer<26) THEN RAISE EXCEPTION 'exact complete operation-specific wire observation required';END IF;
   expected_key:='meeting-worker/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||claimed.claim_id::text||'/'||(wire->>'wire_sha256')||'.wire';
   IF wire->>'wire_object_key' IS DISTINCT FROM expected_key THEN RAISE EXCEPTION 'exact own immutable wire key required';END IF;
   IF received.receipt_id IS NULL THEN
    INSERT INTO oracle2.meeting_capture_worker_receipts_v1(receipt_id,claim_id,admission_id,worker_id,wire_object_key,wire_sha256,wire_byte_count,observation)
     VALUES(gen_random_uuid(),claimed.claim_id,selected,m.worker_id,expected_key,wire->>'wire_sha256',(wire->>'wire_byte_count')::integer,wire->'observation') RETURNING * INTO received;
   ELSIF received.wire_object_key IS DISTINCT FROM expected_key OR received.wire_sha256 IS DISTINCT FROM wire->>'wire_sha256'
    OR received.wire_byte_count IS DISTINCT FROM (wire->>'wire_byte_count')::integer OR received.observation IS DISTINCT FROM wire->'observation' THEN
    RAISE EXCEPTION 'immutable delivery receipt collision';END IF;
   IF m.worker_effect='capture-create' THEN
    SELECT * INTO existing_semantic FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND operation_id=received.receipt_id;
    IF existing_semantic.event_id IS NULL AND h.state='joining' THEN
     IF received.observation->>'kind'='create-observed' THEN
      PERFORM oracle2.meeting_capture_transition_v1(selected,seal,h.version,received.receipt_id,'create_observed',
       jsonb_build_object('intent_id',h.create_intent_id,'receipt_sha256',received.wire_sha256,'bot_id',received.observation->>'bot_id'),deadline);
     ELSE
      PERFORM oracle2.meeting_capture_transition_v1(selected,seal,h.version,received.receipt_id,'create_unknown',
       jsonb_build_object('intent_id',h.create_intent_id,'receipt_sha256',received.wire_sha256),deadline);
     END IF;
    ELSIF existing_semantic.event_id IS NULL AND h.state IN('cancelled','UNKNOWN')
     AND received.observation->>'kind'='create-observed' AND received.observation->'complete'='true'::jsonb THEN
     IF h.version>=16384 THEN RAISE EXCEPTION 'bounded forensic capture history required';END IF;
     semantic:=jsonb_build_object('intent_id',h.create_intent_id,'claim_id',claimed.claim_id,'receipt_id',received.receipt_id,
      'request_sha256',claimed.request_sha256,'receipt_sha256',received.wire_sha256,'bot_id',received.observation->>'bot_id',
      'provider_account',m.provider_account,'tenant_id',m.tenant_id,'provider_meeting_id',m.provider_meeting_id);
     semantic_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('action','create_observed_after_close','body',semantic)),'UTF8')),'hex');
     INSERT INTO oracle2.meeting_capture_events_v1(event_id,workspace_id,meeting_id,version,admission_id,actor_id,action,payload_sha256,payload,operation_id,provider,provider_account)
      VALUES(received.receipt_id,m.workspace_id,m.meeting_id,h.version+1,selected,m.principal_id,'create_observed_after_close',semantic_hash,semantic,received.receipt_id,m.provider,m.provider_account);
     UPDATE oracle2.meeting_capture_heads_v1 SET version=h.version+1,last_event_id=received.receipt_id,capture_open=false
      WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id;
    END IF;
   END IF;
   IF m.worker_effect='capture-leave' AND h.stop_state='inflight' THEN
    SELECT * INTO existing_semantic FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND operation_id=received.receipt_id;
    IF existing_semantic.event_id IS NULL THEN
     PERFORM oracle2.meeting_capture_transition_v1(selected,seal,h.version,received.receipt_id,
      CASE WHEN received.observation->>'kind'='leave-observed' THEN 'stop_observed' ELSE 'stop_unknown' END,
      jsonb_build_object('stop_intent_id',h.stop_intent_id,'wire_sha256',received.wire_sha256),deadline);
    END IF;
   ELSIF m.worker_effect='capture-retrieve' AND delivery_stage='post-stop-terminal'
    AND received.observation->>'kind'='metadata-observed' AND received.observation->'latest_status'->>'code' IN('call_ended','done','fatal') THEN
    SELECT * INTO existing_semantic FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND operation_id=received.receipt_id;
    IF existing_semantic.event_id IS NULL THEN
     PERFORM oracle2.meeting_capture_transition_v1(selected,seal,h.version,received.receipt_id,'stop_reconciled',
      jsonb_build_object('stop_intent_id',h.stop_intent_id,'metadata_sha256',received.observation->>'metadata_sha256','terminal_event_id',received.receipt_id),deadline);
    END IF;
   END IF;
   state:=CASE WHEN received.observation->>'kind'='UNKNOWN' THEN 'UNKNOWN' ELSE 'observed' END;
  END IF;
 END IF;
 until:=least(m.expires_at,deadline,CASE WHEN command='status' THEN deadline ELSE coalesce(claimed.original_deadline,deadline) END);
 RETURN jsonb_build_object('meeting_id',m.meeting_id,'capture_until',m.capture_until,'valid_until',until,
  'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),until),'state',state,'fresh_claim',fresh,
  'worker_id',m.worker_id,'stop_mapping_sha256',m.stop_mapping_sha256,'operation_policy_sha256',m.worker_policy_sha256,'effect',m.worker_effect,'stage',delivery_stage,'operation_id',op,'intent_event_id',intent.event_id,
  'claim_id',claimed.claim_id,'claim_admission_id',claimed.admission_id,'claim_worker_id',claimed.worker_id,'claim_original_deadline',claimed.original_deadline,'request_sha256',hash,'bot_id',bot,'receipt_id',received.receipt_id,'observation',received.observation);
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_worker_v1(uuid,text,text,uuid,uuid,text,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_worker_v1(uuid,text,text,uuid,uuid,text,jsonb,timestamptz) TO oracle2_replacement_requester;

-- SAME operational owner: globally spent normalization custody, never truth.
ALTER TABLE oracle2.meeting_capture_admissions_v1
 ADD COLUMN normalization_intake_principal_id uuid,
 ADD COLUMN normalization_intake_config_sha256 text CHECK(normalization_intake_config_sha256~'^[a-f0-9]{64}$'),
 ADD COLUMN normalization_intake_appointment_sha256 text CHECK(normalization_intake_appointment_sha256~'^[a-f0-9]{64}$'),
 ADD CONSTRAINT exact_normalization_intake_pins CHECK(
  (normalization_intake_principal_id IS NULL AND normalization_intake_config_sha256 IS NULL AND normalization_intake_appointment_sha256 IS NULL)
  OR (normalization_intake_principal_id IS NOT NULL AND normalization_intake_config_sha256 IS NOT NULL AND normalization_intake_appointment_sha256 IS NOT NULL));
CREATE TABLE oracle2.meeting_normalization_claims_v1 (
 claim_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,
 ingress_event_id uuid NOT NULL REFERENCES oracle2.meeting_capture_events_v1(event_id),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),principal_id uuid NOT NULL,
 binding jsonb NOT NULL CHECK(jsonb_typeof(binding)='object' AND octet_length(binding::text)<=8192),
 binding_sha256 text NOT NULL CHECK(binding_sha256~'^[a-f0-9]{64}$'),
 original_deadline timestamptz NOT NULL CHECK(isfinite(original_deadline)),original_processing_horizon timestamptz NOT NULL CHECK(isfinite(original_processing_horizon)),
 UNIQUE(workspace_id,meeting_id,ingress_event_id));
CREATE TABLE oracle2.meeting_normalization_intakes_v1 (
 claim_id uuid PRIMARY KEY REFERENCES oracle2.meeting_normalization_claims_v1(claim_id),
 reservation_id uuid NOT NULL REFERENCES oracle2.source_intake_reservations_v1(reservation_id),
 source_id uuid NOT NULL,revision integer NOT NULL CHECK(revision>0),original_sha256 text NOT NULL CHECK(original_sha256~'^[a-f0-9]{64}$'),
 byte_count bigint NOT NULL CHECK(byte_count BETWEEN 1 AND 1048576),custody_seal_sha256 text NOT NULL CHECK(custody_seal_sha256~'^[a-f0-9]{64}$'),
 normalized_event_id uuid NOT NULL REFERENCES oracle2.meeting_capture_events_v1(event_id));
CREATE TRIGGER immutable_meeting_normalization_claims BEFORE UPDATE OR DELETE ON oracle2.meeting_normalization_claims_v1 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
CREATE TRIGGER immutable_meeting_normalization_intakes BEFORE UPDATE OR DELETE ON oracle2.meeting_normalization_intakes_v1 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
REVOKE ALL ON oracle2.meeting_normalization_claims_v1,oracle2.meeting_normalization_intakes_v1 FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_capture_normalization_v1(selected uuid,seal text,command text,wanted uuid,binding jsonb,intake_receipt jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;
 claimed oracle2.meeting_normalization_claims_v1%ROWTYPE;retained oracle2.meeting_normalization_intakes_v1%ROWTYPE;
 reserved oracle2.source_intake_reservations_v1%ROWTYPE;original oracle2.source_original_revisions%ROWTYPE;source oracle2.sources%ROWTYPE;
 mapped jsonb;mapping jsonb;hash text;fresh boolean:=false;field text;state text;source_binding jsonb;published jsonb;expected_idempotency uuid;source_current boolean:=false;
BEGIN
 IF command NOT IN('claim','status','record_intake') OR command IS NULL OR wanted IS NULL
  OR command<>'claim' AND binding IS NOT NULL OR command<>'record_intake' AND intake_receipt IS NOT NULL THEN RAISE EXCEPTION 'closed normalization operation required';END IF;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'process',deadline);
 IF m.normalization_intake_principal_id IS NULL OR NOT ARRAY['process','normalized','status']::text[]<@m.actions THEN
  RAISE insufficient_privilege USING MESSAGE='separately installed exact normalization intake pins required';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-meeting:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 IF h.meeting_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='existing exact capture required';END IF;
 SELECT * INTO claimed FROM oracle2.meeting_normalization_claims_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND ingress_event_id=wanted;
 IF command='claim' THEN
  mapped:=oracle2.meeting_capture_current_final_mapping_v1(selected,seal,wanted,deadline);mapping:=mapped->'mapping';
  expected_idempotency:=encode(substring(sha256(convert_to('oracle2-meeting-normalization-v1/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||wanted::text,'UTF8')) FROM 1 FOR 16),'hex')::uuid;
  IF jsonb_typeof(binding) IS DISTINCT FROM 'object' OR NOT(binding?&ARRAY['raw_sha256','mapping_id','mapping_revision','mapping_sha256','derivation_sha256','original_sha256','byte_count','create_selector','idempotency_key','intake_principal_id','intake_config_sha256','intake_appointment_sha256'])
   OR binding-ARRAY['raw_sha256','mapping_id','mapping_revision','mapping_sha256','derivation_sha256','original_sha256','byte_count','create_selector','idempotency_key','intake_principal_id','intake_config_sha256','intake_appointment_sha256']<>'{}'::jsonb
   OR binding->'create_selector' IS DISTINCT FROM 'null'::jsonb
   OR binding->>'raw_sha256' IS DISTINCT FROM mapped->'receipt'->'payload'->>'raw_sha256'
   OR binding->>'mapping_id' IS DISTINCT FROM mapping->>'mapping_id' OR binding->'mapping_revision' IS DISTINCT FROM mapping->'mapping_revision'
   OR binding->>'mapping_sha256' IS DISTINCT FROM mapped->>'mapping_sha256'
   OR binding->>'intake_principal_id' IS DISTINCT FROM m.normalization_intake_principal_id::text
   OR binding->>'intake_config_sha256' IS DISTINCT FROM m.normalization_intake_config_sha256
   OR binding->>'intake_appointment_sha256' IS DISTINCT FROM m.normalization_intake_appointment_sha256
   OR jsonb_typeof(binding->'byte_count') IS DISTINCT FROM 'number' OR binding->>'byte_count' !~ '^[1-9][0-9]{0,6}$' OR (binding->>'byte_count')::integer>1048576
   OR jsonb_typeof(binding->'idempotency_key') IS DISTINCT FROM 'string' OR binding->>'idempotency_key' IS DISTINCT FROM expected_idempotency::text
   THEN RAISE insufficient_privilege USING MESSAGE='actual exact whole-final normalization binding required';END IF;
  FOREACH field IN ARRAY ARRAY['raw_sha256','mapping_sha256','derivation_sha256','original_sha256','intake_config_sha256','intake_appointment_sha256'] LOOP
   IF jsonb_typeof(binding->field) IS DISTINCT FROM 'string' OR binding->>field !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'canonical normalization hash required';END IF;
  END LOOP;
  hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(binding),'UTF8')),'hex');
  IF claimed.claim_id IS NULL THEN
   IF NOT wanted=ANY(h.pending_ingress) THEN RAISE insufficient_privilege USING MESSAGE='single pending final ingress required';END IF;
   INSERT INTO oracle2.meeting_normalization_claims_v1 VALUES(gen_random_uuid(),m.workspace_id,m.meeting_id,wanted,selected,m.principal_id,binding,hash,least(deadline,m.expires_at),m.original_horizon) RETURNING * INTO claimed;fresh:=true;
  ELSIF claimed.binding_sha256 IS DISTINCT FROM hash OR claimed.binding IS DISTINCT FROM binding THEN RAISE EXCEPTION 'global spent normalization binding collision';END IF;
 END IF;
 IF claimed.claim_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='existing normalization claim required';END IF;
 IF claimed.binding->>'intake_principal_id' IS DISTINCT FROM m.normalization_intake_principal_id::text
  OR claimed.binding->>'intake_config_sha256' IS DISTINCT FROM m.normalization_intake_config_sha256
  OR claimed.binding->>'intake_appointment_sha256' IS DISTINCT FROM m.normalization_intake_appointment_sha256
  OR m.original_horizon IS DISTINCT FROM claimed.original_processing_horizon THEN RAISE insufficient_privilege USING MESSAGE='original normalization scope cannot change';END IF;
 SELECT * INTO retained FROM oracle2.meeting_normalization_intakes_v1 WHERE claim_id=claimed.claim_id;
 IF command='record_intake' THEN
  mapped:=oracle2.meeting_capture_current_final_mapping_v1(selected,seal,wanted,deadline);
  IF mapped->>'mapping_sha256' IS DISTINCT FROM claimed.binding->>'mapping_sha256' OR mapped->'mapping'->>'mapping_id' IS DISTINCT FROM claimed.binding->>'mapping_id' THEN RAISE insufficient_privilege USING MESSAGE='current original final mapping still required';END IF;
  IF jsonb_typeof(intake_receipt) IS DISTINCT FROM 'object' OR NOT(intake_receipt?&ARRAY['source_id','revision','original_sha256','byte_count'])
   OR intake_receipt-ARRAY['source_id','revision','original_sha256','byte_count']<>'{}'::jsonb THEN RAISE EXCEPTION 'closed actual intake observation required';END IF;
  SELECT * INTO reserved FROM oracle2.source_intake_reservations_v1 r WHERE r.workspace_id=m.workspace_id AND r.principal_id=m.normalization_intake_principal_id
   AND r.idempotency_key=(claimed.binding->>'idempotency_key')::uuid FOR SHARE;
  IF reserved.reservation_id IS NULL OR reserved.finalized_at IS NULL OR reserved.media_type<>'text/plain' OR reserved.expected_head<>0 OR reserved.revision<>1
   OR reserved.source_id::text IS DISTINCT FROM intake_receipt->>'source_id' OR to_jsonb(reserved.revision) IS DISTINCT FROM intake_receipt->'revision'
   OR reserved.original_sha256 IS DISTINCT FROM intake_receipt->>'original_sha256' OR to_jsonb(reserved.byte_count) IS DISTINCT FROM intake_receipt->'byte_count'
   OR reserved.original_sha256 IS DISTINCT FROM claimed.binding->>'original_sha256' OR reserved.byte_count IS DISTINCT FROM (claimed.binding->>'byte_count')::bigint THEN
   RAISE insufficient_privilege USING MESSAGE='actual own finalized intake reservation required';END IF;
  SELECT * INTO original FROM oracle2.source_original_revisions WHERE workspace_id=m.workspace_id AND source_id=reserved.source_id AND revision=reserved.revision FOR SHARE;
  SELECT * INTO source FROM oracle2.sources WHERE workspace_id=m.workspace_id AND source_id=reserved.source_id FOR SHARE;
  IF original.source_id IS NULL OR original.original_sha256 IS DISTINCT FROM reserved.original_sha256 OR original.byte_count IS DISTINCT FROM reserved.byte_count
   OR original.custody_locator_seal_sha256 IS DISTINCT FROM reserved.custody_seal_sha256 OR original.media_type<>'text/plain'
   OR source.source_id IS NULL OR source.revision IS DISTINCT FROM reserved.revision OR source.status NOT IN('processing','draft','confirmed')
   OR EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 WHERE workspace_id=m.workspace_id AND source_id=reserved.source_id AND revision=reserved.revision) THEN
   RAISE insufficient_privilege USING MESSAGE='actual current retained original custody required';END IF;
  IF retained.claim_id IS NULL THEN
   published:=oracle2.meeting_capture_transition_v1(selected,seal,h.version,claimed.claim_id,'normalized',jsonb_build_object('ingress_event_id',wanted,'derivation_sha256',claimed.binding->>'derivation_sha256','source_id',reserved.source_id,'revision',reserved.revision,'original_sha256',reserved.original_sha256),deadline);
   INSERT INTO oracle2.meeting_normalization_intakes_v1 VALUES(claimed.claim_id,reserved.reservation_id,reserved.source_id,reserved.revision,reserved.original_sha256,reserved.byte_count,reserved.custody_seal_sha256,(published->>'event_id')::uuid) RETURNING * INTO retained;
  ELSIF retained.reservation_id IS DISTINCT FROM reserved.reservation_id OR retained.source_id IS DISTINCT FROM reserved.source_id OR retained.revision IS DISTINCT FROM reserved.revision OR retained.original_sha256 IS DISTINCT FROM reserved.original_sha256 THEN RAISE EXCEPTION 'immutable normalization intake collision';END IF;
 END IF;
 state:=CASE WHEN retained.claim_id IS NOT NULL THEN 'awaiting_independently_installed_exact_reading_review' WHEN fresh THEN 'intake_claimed' ELSE 'UNKNOWN' END;
 IF retained.claim_id IS NOT NULL THEN
  SELECT EXISTS(SELECT 1 FROM oracle2.sources s JOIN oracle2.source_original_revisions o USING(workspace_id,source_id,revision)
   WHERE s.workspace_id=m.workspace_id AND s.source_id=retained.source_id AND s.revision=retained.revision
    AND s.status IN('processing','draft','confirmed') AND o.original_sha256=retained.original_sha256 AND o.byte_count=retained.byte_count
    AND o.custody_locator_seal_sha256=retained.custody_seal_sha256
    AND NOT EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE w.workspace_id=s.workspace_id AND w.source_id=s.source_id AND w.revision=s.revision)) INTO source_current;
  IF NOT source_current THEN state:='source_unavailable'; END IF;
 END IF;
 IF retained.claim_id IS NOT NULL AND source_current THEN source_binding:=jsonb_build_object('workspace_id',m.workspace_id,'source_id',retained.source_id,'revision',retained.revision,'original_sha256',retained.original_sha256,'byte_count',retained.byte_count,'custody_seal_sha256',retained.custody_seal_sha256,'qualification',false,'source_read_permission',false);END IF;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'process',deadline);
 RETURN jsonb_build_object('meeting_id',m.meeting_id,'capture_until',m.capture_until,'valid_until',least(m.expires_at,deadline),'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),least(m.expires_at,deadline)),
  'claim_id',claimed.claim_id,'ingress_event_id',wanted,'state',state,'fresh_intake_claim',fresh,'binding',claimed.binding,'original_effect_deadline',claimed.original_deadline,'original_processing_horizon',claimed.original_processing_horizon,'source_binding',source_binding);
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_normalization_v1(uuid,text,text,uuid,jsonb,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_normalization_v1(uuid,text,text,uuid,jsonb,jsonb,timestamptz) TO oracle2_replacement_requester;

-- SAME operational owner, source-fixed final fetch and raw-to-final relation.
-- Independently installed descriptor/op pins do not prove custody or issue a
-- grant. Old NULL rows retain their direct APIs and grant no new fetch fence.
ALTER TABLE oracle2.meeting_capture_admissions_v1
 ADD COLUMN final_artifact_descriptor jsonb,
 ADD COLUMN final_artifact_operation_id uuid,
 ADD CONSTRAINT exact_processing_final_descriptor CHECK(
  (final_artifact_descriptor IS NULL AND final_artifact_operation_id IS NULL)
  OR (final_artifact_descriptor IS NOT NULL AND final_artifact_operation_id IS NOT NULL AND final_artifact_sha256 IS NOT NULL
   AND jsonb_typeof(final_artifact_descriptor)='object' AND octet_length(final_artifact_descriptor::text)<=16384
   AND final_artifact_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(final_artifact_descriptor),'UTF8')),'hex')));
ALTER TABLE oracle2.meeting_capture_admissions_v1 DROP CONSTRAINT meeting_capture_admissions_v1_actions_check;
ALTER TABLE oracle2.meeting_capture_admissions_v1 ADD CONSTRAINT meeting_capture_admissions_v1_actions_check
 CHECK(cardinality(actions) BETWEEN 1 AND 16 AND actions<@ARRAY['invite','create_intent','create_observed','create_unknown','ingress','final_artifact','process','normalized','review','cancel','status','outbox','supervised','supervise','stop_intent','stop_observed','stop_unknown','stop_reconciled','participant_turn','process_observe']);
CREATE TABLE oracle2.meeting_capture_final_fetch_claims_v1 (
 fetch_claim_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,
 population_sha256 text NOT NULL CHECK(population_sha256~'^[a-f0-9]{64}$'),
 descriptor_sha256 text NOT NULL CHECK(descriptor_sha256~'^[a-f0-9]{64}$'),
 final_operation_id uuid NOT NULL,initiating_ingress_event_id uuid NOT NULL REFERENCES oracle2.meeting_capture_events_v1(event_id),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),principal_id uuid NOT NULL,
 original_effect_deadline timestamptz NOT NULL CHECK(isfinite(original_effect_deadline)),
 original_processing_horizon timestamptz NOT NULL CHECK(isfinite(original_processing_horizon)),
 claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(workspace_id,meeting_id,population_sha256),
 CHECK(claimed_at<original_effect_deadline AND original_effect_deadline<=original_processing_horizon));
CREATE TABLE oracle2.meeting_capture_processing_links_v1 (
 workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,original_ingress_event_id uuid NOT NULL REFERENCES oracle2.meeting_capture_events_v1(event_id),
 final_event_id uuid NOT NULL REFERENCES oracle2.meeting_capture_events_v1(event_id),
 fetch_claim_id uuid NOT NULL REFERENCES oracle2.meeting_capture_final_fetch_claims_v1(fetch_claim_id),
 descriptor_sha256 text NOT NULL CHECK(descriptor_sha256~'^[a-f0-9]{64}$'),
 observation_admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),
 linked_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(workspace_id,meeting_id,original_ingress_event_id));
CREATE TRIGGER immutable_meeting_final_fetch_claims BEFORE UPDATE OR DELETE ON oracle2.meeting_capture_final_fetch_claims_v1 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
CREATE TRIGGER immutable_meeting_processing_links BEFORE UPDATE OR DELETE ON oracle2.meeting_capture_processing_links_v1 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
REVOKE ALL ON oracle2.meeting_capture_final_fetch_claims_v1,oracle2.meeting_capture_processing_links_v1 FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_processing_descriptor_v1(m oracle2.meeting_capture_admissions_v1)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE p jsonb:=m.final_artifact_descriptor;field text;fields text[]:=ARRAY['schema_version','purpose','workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id','bot_id','recording_id','transcript_id','provider_revision','provider_finality_receipt_sha256','original_sha256','byte_count','media_type','download_url','ca_file','ca_sha256','server_der_sha256','issuer_actor','reviewer_actor','valid_from','expires_at','original_horizon'];
BEGIN
 IF p IS NULL OR m.final_artifact_operation_id IS NULL THEN RETURN NULL;END IF;
 IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR NOT(p?&fields) OR p-fields<>'{}'::jsonb
  OR p->'schema_version' IS DISTINCT FROM '1'::jsonb OR p->>'purpose' IS DISTINCT FROM 'meeting-final-artifact-selection-v1'
  OR m.final_artifact_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(p),'UTF8')),'hex')
  OR p->>'workspace_id' IS DISTINCT FROM m.workspace_id::text OR p->>'meeting_id' IS DISTINCT FROM m.meeting_id::text
  OR p->>'provider' IS DISTINCT FROM m.provider OR p->>'provider_account' IS DISTINCT FROM m.provider_account
  OR p->>'tenant_id' IS DISTINCT FROM m.tenant_id OR p->>'provider_meeting_id' IS DISTINCT FROM m.provider_meeting_id
  OR p->>'bot_id' IS DISTINCT FROM m.bot_id OR (m.bot_id IS NOT NULL AND jsonb_typeof(p->'bot_id') IS DISTINCT FROM 'string') OR (m.bot_id IS NULL AND p->'bot_id' IS DISTINCT FROM 'null'::jsonb) OR jsonb_typeof(p->'media_type') IS DISTINCT FROM 'string' OR p->>'media_type' NOT IN('application/json','text/vtt')
  OR jsonb_typeof(p->'byte_count') IS DISTINCT FROM 'number' OR p->>'byte_count' !~ '^[1-9][0-9]{0,6}$' OR (p->>'byte_count')::integer>1048576
  OR p->>'issuer_actor'=p->>'reviewer_actor' OR m.principal_id::text IN(p->>'issuer_actor',p->>'reviewer_actor')
  THEN RAISE insufficient_privilege USING MESSAGE='exact independently installed whole-final descriptor required';END IF;
 FOREACH field IN ARRAY ARRAY['workspace_id','meeting_id','issuer_actor','reviewer_actor'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR p->>field IS DISTINCT FROM ((p->>field)::uuid)::text THEN RAISE EXCEPTION 'canonical descriptor UUID required';END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['provider','provider_account','tenant_id','provider_meeting_id','recording_id','transcript_id','provider_revision','download_url','ca_file'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR length(p->>field)<1 OR p->>field IS DISTINCT FROM btrim(p->>field) OR p->>field~'[[:cntrl:]]' THEN RAISE EXCEPTION 'canonical bounded final descriptor text required';END IF;
 END LOOP;
 IF length(p->>'provider_account')>256 OR length(p->>'tenant_id')>256 OR length(p->>'provider_meeting_id')>2048 OR length(p->>'recording_id')>1024 OR length(p->>'transcript_id')>1024 OR length(p->>'provider_revision')>256 OR length(p->>'download_url')>8192 OR length(p->>'ca_file')>2048
  OR p->>'download_url' !~ '^https://[^/@#[:space:]]+/' OR p->>'download_url'~'#' OR p->>'ca_file' !~ '^/' OR p->>'ca_file'~'(^|/)[.][.]?(/|$)|//' THEN RAISE EXCEPTION 'bounded exact installed final URL/CA required';END IF;
 FOREACH field IN ARRAY ARRAY['provider_finality_receipt_sha256','original_sha256','ca_sha256','server_der_sha256'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR p->>field !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'canonical descriptor SHA required';END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['valid_from','expires_at','original_horizon'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR NOT isfinite((p->>field)::timestamptz)
   OR p->>field IS DISTINCT FROM to_char((p->>field)::timestamptz AT TIME ZONE 'UTC',CASE WHEN date_trunc('second',(p->>field)::timestamptz)=(p->>field)::timestamptz THEN 'YYYY-MM-DD"T"HH24:MI:SS"Z"' ELSE 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"' END) THEN RAISE EXCEPTION 'canonical finite descriptor instant required';END IF;
 END LOOP;
 IF NOT((p->>'valid_from')::timestamptz<=clock_timestamp() AND clock_timestamp()<(p->>'expires_at')::timestamptz AND (p->>'expires_at')::timestamptz<=(p->>'original_horizon')::timestamptz AND (p->>'original_horizon')::timestamptz<=m.original_horizon) THEN RAISE insufficient_privilege USING MESSAGE='current original descriptor horizon required';END IF;
 RETURN p;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_processing_descriptor_v1(oracle2.meeting_capture_admissions_v1) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_capture_process_ingress_v1(selected uuid,seal text,command text,wanted_ingress uuid,returned_final uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;original oracle2.meeting_capture_events_v1%ROWTYPE;actual oracle2.meeting_capture_events_v1%ROWTYPE;
 claimed oracle2.meeting_capture_final_fetch_claims_v1%ROWTYPE;linked oracle2.meeting_capture_processing_links_v1%ROWTYPE;
 p jsonb;population jsonb;hash text;field text;act text;observe_only boolean:=false;fresh boolean:=false;state text;expected jsonb;
BEGIN
 IF command IS NULL OR command NOT IN('claim_fetch','record_final','status') OR wanted_ingress IS NULL OR command<>'record_final' AND returned_final IS NOT NULL THEN RAISE EXCEPTION 'closed process-ingress operation required';END IF;
 SELECT actions=ARRAY['status','process_observe']::text[] OR actions=ARRAY['process_observe','status']::text[] INTO observe_only FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=selected;
 observe_only:=coalesce(observe_only,false);act:=CASE WHEN observe_only THEN 'process_observe' ELSE 'process' END;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,act,deadline);
 IF observe_only AND command='claim_fetch' OR NOT observe_only AND NOT ARRAY['process','final_artifact','normalized','status']::text[]<@m.actions THEN RAISE insufficient_privilege USING MESSAGE='separate current processing or observation-only purpose required';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-meeting:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 SELECT * INTO original FROM oracle2.meeting_capture_events_v1 WHERE event_id=wanted_ingress AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='ingress' AND provider=m.provider AND provider_account=m.provider_account FOR SHARE;
 IF original.event_id IS NULL OR original.payload->>'bot_id' IS DISTINCT FROM m.bot_id THEN RAISE insufficient_privilege USING MESSAGE='actual same-owner original ingress required';END IF;
 p:=oracle2._meeting_processing_descriptor_v1(m);
 IF p IS NULL THEN state:='final_artifact_pending';
 ELSE
  SELECT jsonb_object_agg(key,value) INTO population FROM jsonb_each(p) WHERE key=ANY(ARRAY['workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id','bot_id','recording_id','transcript_id','provider_revision','provider_finality_receipt_sha256','original_sha256','byte_count','media_type']);
  hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(population),'UTF8')),'hex');
  SELECT * INTO claimed FROM oracle2.meeting_capture_final_fetch_claims_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND population_sha256=hash;
  IF claimed.fetch_claim_id IS NULL AND command='claim_fetch' THEN
   IF NOT wanted_ingress=ANY(h.pending_ingress) THEN RAISE insufficient_privilege USING MESSAGE='actual pending ingress required before fetch';END IF;
   IF (SELECT count(*) FROM oracle2.meeting_capture_final_fetch_claims_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id)>=4096 THEN RAISE EXCEPTION 'bounded final fetch population exhausted';END IF;
   INSERT INTO oracle2.meeting_capture_final_fetch_claims_v1 VALUES(gen_random_uuid(),m.workspace_id,m.meeting_id,hash,m.final_artifact_sha256,m.final_artifact_operation_id,wanted_ingress,selected,m.principal_id,least(m.expires_at,deadline,(p->>'expires_at')::timestamptz),m.original_horizon,clock_timestamp()) RETURNING * INTO claimed;fresh:=true;
  END IF;
  IF claimed.fetch_claim_id IS NOT NULL AND (claimed.descriptor_sha256 IS DISTINCT FROM m.final_artifact_sha256 OR claimed.final_operation_id IS DISTINCT FROM m.final_artifact_operation_id OR claimed.original_processing_horizon IS DISTINCT FROM m.original_horizon) THEN RAISE insufficient_privilege USING MESSAGE='globally spent final population cannot be renewed by metadata/admission';END IF;
  SELECT * INTO linked FROM oracle2.meeting_capture_processing_links_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND original_ingress_event_id=wanted_ingress;
  IF command='record_final' THEN
   IF claimed.fetch_claim_id IS NULL OR returned_final IS NULL THEN RAISE insufficient_privilege USING MESSAGE='original globally spent fetch claim and actual final event required';END IF;
   IF NOT observe_only AND clock_timestamp()>=claimed.original_effect_deadline THEN RAISE insufficient_privilege USING MESSAGE='separate current observation-only purpose required after original fetch deadline';END IF;
   expected:=jsonb_build_object('selection_sha256',claimed.descriptor_sha256,'provider_event_id','final:'||claimed.descriptor_sha256,'raw_sha256',p->>'original_sha256','byte_count',p->'byte_count','raw_object_key','meeting-raw/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||(p->>'original_sha256')||'.bin','event_kind',m.provider||'.final');
   SELECT * INTO actual FROM oracle2.meeting_capture_events_v1 WHERE event_id=returned_final AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='final_artifact'
    AND operation_id=claimed.final_operation_id AND provider=m.provider AND provider_account=m.provider_account AND payload=expected
    AND payload_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('action','final_artifact','body',expected)),'UTF8')),'hex')
    AND created_at>=claimed.claimed_at AND created_at<=claimed.original_effect_deadline FOR SHARE;
   IF actual.event_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='exact originating actual complete final custody event required';END IF;
   IF linked.final_event_id IS NULL THEN
    INSERT INTO oracle2.meeting_capture_processing_links_v1 VALUES(m.workspace_id,m.meeting_id,wanted_ingress,actual.event_id,claimed.fetch_claim_id,claimed.descriptor_sha256,selected,clock_timestamp()) RETURNING * INTO linked;
   ELSIF linked.final_event_id IS DISTINCT FROM actual.event_id OR linked.fetch_claim_id IS DISTINCT FROM claimed.fetch_claim_id THEN RAISE EXCEPTION 'immutable original-to-final link collision';END IF;
  END IF;
  state:=CASE WHEN linked.final_event_id IS NOT NULL THEN 'final_linked' WHEN fresh THEN 'fresh_fetch' ELSE 'UNKNOWN' END;
 END IF;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,act,deadline);
 RETURN jsonb_build_object('schema_version',1,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),least(m.expires_at,deadline)),
  'meeting_id',m.meeting_id,'capture_until',m.capture_until,'valid_until',least(m.expires_at,deadline),'original_ingress_event_id',wanted_ingress,'descriptor_sha256',CASE WHEN p IS NULL THEN NULL ELSE m.final_artifact_sha256 END,'population_sha256',hash,'final_operation_id',m.final_artifact_operation_id,'fetch_claim_id',claimed.fetch_claim_id,'state',state,'fresh_fetch_claim',fresh,'final_event_id',linked.final_event_id,'original_effect_deadline',claimed.original_effect_deadline,'original_processing_horizon',m.original_horizon,'observation_only',observe_only);
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_process_ingress_v1(uuid,text,text,uuid,uuid,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_process_ingress_v1(uuid,text,text,uuid,uuid,timestamptz) TO oracle2_replacement_requester;

-- SAME outbox owner: independently installed queue scope, once effect custody.
ALTER TABLE oracle2.meeting_capture_admissions_v1
 ADD COLUMN queue_project_ref text,
 ADD COLUMN queue_environment_id text,
 ADD COLUMN queue_account_id text,
 ADD COLUMN queue_task_id text,
 ADD COLUMN queue_credential_sha256 text,
 ADD COLUMN queue_installation_receipt_sha256 text,
 ADD COLUMN queue_target_descriptor_sha256 text,
 ADD CONSTRAINT exact_meeting_queue_installation CHECK(
  (queue_project_ref IS NULL AND queue_environment_id IS NULL AND queue_account_id IS NULL AND queue_task_id IS NULL AND queue_credential_sha256 IS NULL AND queue_installation_receipt_sha256 IS NULL AND queue_target_descriptor_sha256 IS NULL)
  OR (queue_project_ref IS NOT NULL AND queue_environment_id IS NOT NULL AND queue_account_id IS NOT NULL AND queue_task_id IS NOT NULL AND queue_task_id='oracle2-meeting-ingress-normalize-v1'
   AND queue_credential_sha256 IS NOT NULL AND queue_installation_receipt_sha256 IS NOT NULL AND queue_target_descriptor_sha256 IS NOT NULL
   AND length(queue_project_ref) BETWEEN 1 AND 256 AND queue_project_ref=btrim(queue_project_ref) AND queue_project_ref!~'[[:cntrl:]]'
   AND length(queue_environment_id) BETWEEN 1 AND 256 AND queue_environment_id=btrim(queue_environment_id) AND queue_environment_id!~'[[:cntrl:]]'
   AND length(queue_account_id) BETWEEN 1 AND 256 AND queue_account_id=btrim(queue_account_id) AND queue_account_id!~'[[:cntrl:]]'
   AND queue_credential_sha256~'^[a-f0-9]{64}$' AND queue_installation_receipt_sha256~'^[a-f0-9]{64}$' AND queue_target_descriptor_sha256~'^[a-f0-9]{64}$'));
CREATE TABLE oracle2.meeting_capture_enqueue_claims_v1 (
 claim_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,
 ingress_event_id uuid NOT NULL REFERENCES oracle2.meeting_capture_events_v1(event_id),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),principal_id uuid NOT NULL,
 queue_pins jsonb NOT NULL,request_body jsonb NOT NULL,request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),
 original_effect_deadline timestamptz NOT NULL CHECK(isfinite(original_effect_deadline)),
 original_processing_horizon timestamptz NOT NULL CHECK(isfinite(original_processing_horizon)),
 claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(workspace_id,meeting_id,ingress_event_id),
 CHECK(claimed_at<original_effect_deadline AND original_effect_deadline<=original_processing_horizon),
 CHECK(jsonb_typeof(queue_pins)='object' AND octet_length(queue_pins::text)<=4096 AND jsonb_typeof(request_body)='object' AND octet_length(request_body::text)<=1024));
CREATE TABLE oracle2.meeting_capture_enqueue_receipts_v1 (
 receipt_id uuid PRIMARY KEY,claim_id uuid NOT NULL UNIQUE REFERENCES oracle2.meeting_capture_enqueue_claims_v1(claim_id),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_capture_admissions_v1(admission_id),
 raw_object_key text NOT NULL CHECK(length(raw_object_key) BETWEEN 1 AND 1024),
 raw_sha256 text NOT NULL CHECK(raw_sha256~'^[a-f0-9]{64}$'),raw_byte_count integer NOT NULL CHECK(raw_byte_count BETWEEN 0 AND 20480),
 observation jsonb NOT NULL CHECK(jsonb_typeof(observation)='object' AND octet_length(observation::text)<=4096),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TRIGGER immutable_meeting_enqueue_claims BEFORE UPDATE OR DELETE ON oracle2.meeting_capture_enqueue_claims_v1 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
CREATE TRIGGER immutable_meeting_enqueue_receipts BEFORE UPDATE OR DELETE ON oracle2.meeting_capture_enqueue_receipts_v1 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
REVOKE ALL ON oracle2.meeting_capture_enqueue_claims_v1,oracle2.meeting_capture_enqueue_receipts_v1 FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_capture_enqueue_v1(selected uuid,seal text,command text,wanted_ingress uuid,wire_receipt jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_capture_admissions_v1%ROWTYPE;h oracle2.meeting_capture_heads_v1%ROWTYPE;
 claimed oracle2.meeting_capture_enqueue_claims_v1%ROWTYPE;receipt oracle2.meeting_capture_enqueue_receipts_v1%ROWTYPE;
 pins jsonb;body jsonb;hash text;expected_key text;observation jsonb;state text;fresh boolean:=false;pending integer;unresolved integer;
BEGIN
 IF command IS NULL OR command NOT IN('pending','claim','current','record','status') OR command='pending' AND wanted_ingress IS NOT NULL OR command<>'pending' AND wanted_ingress IS NULL OR command<>'record' AND wire_receipt IS NOT NULL THEN RAISE EXCEPTION 'closed queue operation required';END IF;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'outbox',deadline);
 IF NOT 'status'=ANY(m.actions) OR m.queue_project_ref IS NULL THEN RAISE insufficient_privilege USING MESSAGE='independently installed exact queue capability required';END IF;
 pins:=jsonb_build_object('queue_project_ref',m.queue_project_ref,'queue_environment_id',m.queue_environment_id,'queue_account_id',m.queue_account_id,'queue_task_id',m.queue_task_id,'queue_credential_sha256',m.queue_credential_sha256,'queue_installation_receipt_sha256',m.queue_installation_receipt_sha256,'queue_target_descriptor_sha256',m.queue_target_descriptor_sha256);
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-meeting:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO h FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 IF h.meeting_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='actual invited capture required for outbox';END IF;
 pending:=cardinality(h.pending_ingress);
 SELECT count(*) INTO unresolved FROM oracle2.meeting_capture_enqueue_claims_v1 q LEFT JOIN oracle2.meeting_capture_enqueue_receipts_v1 r USING(claim_id)
  WHERE q.workspace_id=m.workspace_id AND q.meeting_id=m.meeting_id AND (r.receipt_id IS NULL OR r.observation->>'kind' IS DISTINCT FROM 'enqueue-observed');
 IF command='pending' AND h.state NOT IN('UNKNOWN','cancelled') THEN
  SELECT e.event_id INTO wanted_ingress FROM oracle2.meeting_capture_events_v1 e WHERE e.workspace_id=m.workspace_id AND e.meeting_id=m.meeting_id
   AND e.action='ingress' AND e.event_id=ANY(h.pending_ingress)
   AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_enqueue_claims_v1 q WHERE q.workspace_id=m.workspace_id AND q.meeting_id=m.meeting_id AND q.ingress_event_id=e.event_id)
   ORDER BY e.version LIMIT 1;
 END IF;
 IF wanted_ingress IS NOT NULL THEN
  PERFORM 1 FROM oracle2.meeting_capture_events_v1 WHERE event_id=wanted_ingress AND workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND action='ingress' AND provider=m.provider AND provider_account=m.provider_account;
  IF NOT FOUND THEN RAISE insufficient_privilege USING MESSAGE='exact actual own queued ingress required';END IF;
  SELECT * INTO claimed FROM oracle2.meeting_capture_enqueue_claims_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND ingress_event_id=wanted_ingress;
  IF claimed.claim_id IS NULL AND command='claim' THEN
   IF h.state IN('UNKNOWN','cancelled') OR NOT wanted_ingress=ANY(h.pending_ingress) THEN RAISE insufficient_privilege USING MESSAGE='current pending capture queue required before effect';END IF;
   IF (SELECT count(*) FROM oracle2.meeting_capture_enqueue_claims_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id)>=4096 THEN RAISE EXCEPTION 'bounded queue claim population exhausted';END IF;
   body:=jsonb_build_object('payload',jsonb_build_object('ingress_event_id',wanted_ingress),'options',jsonb_build_object('idempotencyKey','oracle2-meeting-ingress-normalize-v1:'||m.workspace_id::text||':'||m.meeting_id::text||':'||wanted_ingress::text));
   hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(body),'UTF8')),'hex');
   INSERT INTO oracle2.meeting_capture_enqueue_claims_v1 VALUES(gen_random_uuid(),m.workspace_id,m.meeting_id,wanted_ingress,selected,m.principal_id,pins,body,hash,least(m.expires_at,deadline),m.original_horizon,clock_timestamp()) RETURNING * INTO claimed;fresh:=true;
  END IF;
  IF claimed.claim_id IS NOT NULL AND (claimed.queue_pins IS DISTINCT FROM pins OR claimed.original_processing_horizon IS DISTINCT FROM m.original_horizon) THEN RAISE insufficient_privilege USING MESSAGE='original exact queue installation cannot be replaced';END IF;
  SELECT * INTO receipt FROM oracle2.meeting_capture_enqueue_receipts_v1 WHERE claim_id=claimed.claim_id;
  IF command IN('current','record') THEN
   IF claimed.claim_id IS NULL OR claimed.admission_id IS DISTINCT FROM selected OR claimed.principal_id IS DISTINCT FROM m.principal_id OR h.state IN('UNKNOWN','cancelled') OR clock_timestamp()>=claimed.original_effect_deadline OR deadline>claimed.original_effect_deadline THEN RAISE insufficient_privilege USING MESSAGE='original current once queue window required';END IF;
  END IF;
  IF command='record' THEN
   expected_key:='meeting-queue/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||wanted_ingress::text||'/'||claimed.claim_id::text||'/trigger-response.wire';observation:=wire_receipt->'observation';
   IF jsonb_typeof(wire_receipt) IS DISTINCT FROM 'object' OR NOT(wire_receipt?&ARRAY['claim_id','request_sha256','raw_object_key','raw_sha256','raw_byte_count','observation']) OR wire_receipt-ARRAY['claim_id','request_sha256','raw_object_key','raw_sha256','raw_byte_count','observation']<>'{}'::jsonb
    OR jsonb_typeof(wire_receipt->'claim_id') IS DISTINCT FROM 'string' OR jsonb_typeof(wire_receipt->'request_sha256') IS DISTINCT FROM 'string' OR jsonb_typeof(wire_receipt->'raw_object_key') IS DISTINCT FROM 'string'
    OR wire_receipt->>'claim_id' IS DISTINCT FROM claimed.claim_id::text OR wire_receipt->>'request_sha256' IS DISTINCT FROM claimed.request_sha256 OR wire_receipt->>'raw_object_key' IS DISTINCT FROM expected_key
    OR jsonb_typeof(wire_receipt->'raw_sha256') IS DISTINCT FROM 'string' OR wire_receipt->>'raw_sha256' !~ '^[a-f0-9]{64}$'
    OR jsonb_typeof(wire_receipt->'raw_byte_count') IS DISTINCT FROM 'number' OR wire_receipt->>'raw_byte_count' !~ '^(0|[1-9][0-9]{0,6})$' OR (wire_receipt->>'raw_byte_count')::integer>20480
    OR jsonb_typeof(observation) IS DISTINCT FROM 'object' OR NOT(observation?&ARRAY['kind','complete','run_id','body_sha256']) OR observation-ARRAY['kind','complete','run_id','body_sha256']<>'{}'::jsonb
    OR jsonb_typeof(observation->'kind') IS DISTINCT FROM 'string' OR observation->>'kind' NOT IN('UNKNOWN','enqueue-observed') OR jsonb_typeof(observation->'complete') IS DISTINCT FROM 'boolean'
    OR observation->>'kind'='enqueue-observed' AND (observation->'complete' IS DISTINCT FROM 'true'::jsonb OR jsonb_typeof(observation->'run_id') IS DISTINCT FROM 'string' OR (length(observation->>'run_id') NOT BETWEEN 1 AND 256 OR observation->>'run_id' !~ '^[A-Za-z0-9_-]+$') OR jsonb_typeof(observation->'body_sha256') IS DISTINCT FROM 'string' OR observation->>'body_sha256' !~ '^[a-f0-9]{64}$')
    OR observation->>'kind'='UNKNOWN' AND (observation->'run_id' IS DISTINCT FROM 'null'::jsonb OR observation->'body_sha256' IS DISTINCT FROM 'null'::jsonb)
    THEN RAISE EXCEPTION 'actual closed retained full queue wire required';END IF;
   IF receipt.receipt_id IS NULL THEN
    INSERT INTO oracle2.meeting_capture_enqueue_receipts_v1 VALUES(gen_random_uuid(),claimed.claim_id,selected,expected_key,wire_receipt->>'raw_sha256',(wire_receipt->>'raw_byte_count')::integer,observation,clock_timestamp()) RETURNING * INTO receipt;
    IF wanted_ingress=ANY(h.pending_ingress) THEN
     PERFORM oracle2.meeting_capture_transition_v1(selected,seal,h.version,claimed.claim_id,'outbox',jsonb_build_object('ingress_event_id',wanted_ingress,'observation',CASE WHEN observation->>'kind'='enqueue-observed' THEN 'enqueued' ELSE 'enqueue_failed' END),least(deadline,claimed.original_effect_deadline));
    END IF;
   ELSIF receipt.raw_sha256 IS DISTINCT FROM wire_receipt->>'raw_sha256' OR receipt.raw_byte_count IS DISTINCT FROM (wire_receipt->>'raw_byte_count')::integer OR receipt.observation IS DISTINCT FROM observation THEN RAISE EXCEPTION 'immutable once queue wire collision';END IF;
  END IF;
 END IF;
 SELECT count(*) INTO unresolved FROM oracle2.meeting_capture_enqueue_claims_v1 q LEFT JOIN oracle2.meeting_capture_enqueue_receipts_v1 r USING(claim_id) WHERE q.workspace_id=m.workspace_id AND q.meeting_id=m.meeting_id AND (r.receipt_id IS NULL OR r.observation->>'kind' IS DISTINCT FROM 'enqueue-observed');
 state:=CASE WHEN claimed.claim_id IS NULL THEN 'idle' WHEN receipt.observation->>'kind'='enqueue-observed' THEN 'observed' WHEN receipt.receipt_id IS NOT NULL THEN 'UNKNOWN' WHEN fresh THEN 'claimed' WHEN command='current' THEN 'inflight' ELSE 'UNKNOWN' END;
 m:=oracle2._meeting_capture_admission_v1(selected,seal,'outbox',deadline);
 RETURN jsonb_build_object('schema_version',1,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),least(m.expires_at,deadline)),
  'meeting_id',m.meeting_id,'capture_until',m.capture_until,'valid_until',least(m.expires_at,deadline,CASE WHEN command IN('claim','current','record') AND claimed.claim_id IS NOT NULL THEN claimed.original_effect_deadline ELSE deadline END),
  'ingress_event_id',wanted_ingress,'claim_id',claimed.claim_id,'state',state,'fresh_claim',fresh,'request_sha256',claimed.request_sha256,'body',CASE WHEN fresh THEN claimed.request_body ELSE NULL END,'queue_pins',pins,'original_effect_deadline',claimed.original_effect_deadline,'original_processing_horizon',m.original_horizon,
  'run_id',CASE WHEN receipt.observation->>'kind'='enqueue-observed' THEN receipt.observation->>'run_id' END,'pending_count',pending,'unresolved_count',unresolved,'observation_only',true,'remote_stop_proven',false);
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_capture_enqueue_v1(uuid,text,text,uuid,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_capture_enqueue_v1(uuid,text,text,uuid,jsonb,timestamptz) TO oracle2_replacement_requester;
