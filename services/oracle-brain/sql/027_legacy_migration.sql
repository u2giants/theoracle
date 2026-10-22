-- Dedicated Oracle source capability. No actual appointments/LOGINs/grants,
-- legacy writes, source allocation, provider dispatch, cutover or acceptance.
DO $owner$ BEGIN
 IF (SELECT nspowner FROM pg_namespace WHERE nspname='oracle2') IS DISTINCT FROM
 (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER) THEN
  RAISE EXCEPTION 'exact dedicated Oracle schema owner required'; END IF;
 IF to_regprocedure('oracle2.reserve_source_revision_v1(integer,jsonb,uuid)') IS NULL
 OR to_regprocedure('oracle2._replacement_metadata_json(jsonb)') IS NULL THEN
  RAISE EXCEPTION 'canonical original custody prerequisites required'; END IF;
END $owner$;
CREATE TABLE oracle2.migration_admissions_v1 (
 admission_id uuid PRIMARY KEY,role_name name NOT NULL,principal_id uuid NOT NULL,workspace_id uuid NOT NULL,
 origin_system text NOT NULL CHECK(origin_system~'^[a-z][a-z0-9_-]{0,127}$'),
 operation text NOT NULL CHECK(operation IN('snapshot-register','batch-prepare','batch-observe','read','reconcile','citation-read')),
 runtime_sha256 text NOT NULL CHECK(runtime_sha256~'^[a-f0-9]{64}$'),registry_sha256 text NOT NULL CHECK(registry_sha256~'^[a-f0-9]{64}$'),
 config_sha256 text NOT NULL CHECK(config_sha256~'^[a-f0-9]{64}$'),descriptor_sha256 text NOT NULL CHECK(descriptor_sha256~'^[a-f0-9]{64}$'),
 source_program_sha256 text NOT NULL CHECK(source_program_sha256~'^[a-f0-9]{64}$'),
 source_scope jsonb NOT NULL,source_scope_sha256 text NOT NULL CHECK(source_scope_sha256~'^[a-f0-9]{64}$'),
 permission_producer_kind text NOT NULL CHECK(permission_producer_kind IN('unavailable','technical-channel-v1')),
 membership_appointment uuid NOT NULL REFERENCES oracle2.appointments,
 source_export_appointment uuid NOT NULL REFERENCES oracle2.appointments,
 intake_principal_id uuid NOT NULL,intake_config_sha256 text NOT NULL CHECK(intake_config_sha256~'^[a-f0-9]{64}$'),
 max_records integer NOT NULL CHECK(max_records BETWEEN 1 AND 10000),max_batch integer NOT NULL CHECK(max_batch BETWEEN 1 AND 100),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL,valid_from timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,original_horizon timestamptz NOT NULL,
 CHECK(isfinite(valid_from) AND isfinite(expires_at) AND isfinite(original_horizon) AND valid_from<expires_at AND expires_at<=original_horizon),
 CHECK(issuer_actor<>reviewer_actor AND principal_id NOT IN(issuer_actor,reviewer_actor)),
 CHECK(intake_principal_id=principal_id));
CREATE TABLE oracle2.migration_admission_revocations_v1 (
 admission_id uuid PRIMARY KEY REFERENCES oracle2.migration_admissions_v1,revoked_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE oracle2.migration_inventories_v1 (
 inventory_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,origin_system text NOT NULL,principal_id uuid NOT NULL,
 descriptor_sha256 text NOT NULL,source_scope_sha256 text NOT NULL,source_program_sha256 text NOT NULL,
 source_observation_sha256 text NOT NULL CHECK(source_observation_sha256~'^[a-f0-9]{64}$'),
 inventory_sha256 text NOT NULL CHECK(inventory_sha256~'^[a-f0-9]{64}$'),inventory_bytes bytea NOT NULL,
 declared_count integer NOT NULL CHECK(declared_count BETWEEN 0 AND 10000),source_observed_at timestamptz NOT NULL,
 admission_id uuid NOT NULL REFERENCES oracle2.migration_admissions_v1,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 original_operation_valid_until timestamptz NOT NULL,UNIQUE(workspace_id,origin_system,inventory_id));
CREATE TABLE oracle2.migration_inventory_entries_v1 (
 inventory_id uuid NOT NULL REFERENCES oracle2.migration_inventories_v1,sequence integer NOT NULL CHECK(sequence BETWEEN 1 AND 10000),
 legacy_kind text NOT NULL CHECK(legacy_kind IN('message','document')),legacy_id uuid NOT NULL,
 metadata_sha256 text NOT NULL CHECK(metadata_sha256~'^[a-f0-9]{64}$'),permission_sha256 text NOT NULL CHECK(permission_sha256~'^[a-f0-9]{64}$'),
 original_sha256 text CHECK(original_sha256~'^[a-f0-9]{64}$'),byte_count integer CHECK(byte_count BETWEEN 1 AND 26214400),
 media_type text CHECK(media_type IN('text/plain','application/pdf')),
 disposition text NOT NULL CHECK(disposition IN('message-eligible','document-current-capture-eligible','permission-unavailable','document-custody-unavailable','source-bytes-unavailable','missing','excluded-derived','storage-read-unavailable','object-precondition-failed','capture-incomplete','unsupported-document-media','capture-coverage-gap')),
 PRIMARY KEY(inventory_id,sequence),UNIQUE(inventory_id,legacy_kind,legacy_id),
 CHECK((disposition IN('message-eligible','document-current-capture-eligible'))=(original_sha256 IS NOT NULL AND byte_count IS NOT NULL AND media_type IS NOT NULL)),
 CHECK(disposition IN('message-eligible','document-current-capture-eligible') OR(original_sha256 IS NULL AND byte_count IS NULL AND media_type IS NULL)),
 CHECK(disposition<>'message-eligible' OR(legacy_kind='message' AND media_type='text/plain' AND byte_count<=1048576)),
 CHECK(disposition<>'document-current-capture-eligible' OR(legacy_kind='document' AND media_type='application/pdf')));
CREATE TABLE oracle2.migration_source_bindings_v1 (
 binding_id uuid PRIMARY KEY,origin_system text NOT NULL,workspace_id uuid NOT NULL,legacy_kind text NOT NULL,legacy_id uuid NOT NULL,
 target_source_uuid uuid,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(origin_system,workspace_id,legacy_kind,legacy_id),UNIQUE(workspace_id,target_source_uuid));
CREATE TABLE oracle2.migration_source_versions_v1 (
 version_id uuid PRIMARY KEY,binding_id uuid NOT NULL REFERENCES oracle2.migration_source_bindings_v1,
 original_identity_sha256 text NOT NULL CHECK(original_identity_sha256~'^[a-f0-9]{64}$'),
 original_sha256 text NOT NULL CHECK(original_sha256~'^[a-f0-9]{64}$'),byte_count integer NOT NULL CHECK(byte_count BETWEEN 1 AND 26214400),
 media_type text NOT NULL CHECK(media_type IN('text/plain','application/pdf')),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(binding_id,original_identity_sha256));
CREATE TABLE oracle2.migration_heads_v1 (
 inventory_id uuid PRIMARY KEY REFERENCES oracle2.migration_inventories_v1,revision integer NOT NULL DEFAULT 0,
 read_sequence integer NOT NULL DEFAULT 0,applied_sequence integer NOT NULL DEFAULT 0,
 CHECK(revision>=0 AND read_sequence>=applied_sequence AND applied_sequence>=0));
CREATE TABLE oracle2.migration_intents_v1 (
 intent_id uuid PRIMARY KEY,inventory_id uuid NOT NULL REFERENCES oracle2.migration_inventories_v1,
 entry_sequence integer NOT NULL,binding_id uuid NOT NULL REFERENCES oracle2.migration_source_bindings_v1,
 version_id uuid NOT NULL UNIQUE REFERENCES oracle2.migration_source_versions_v1,
 intake_idempotency uuid UNIQUE,reuses_intent_id uuid REFERENCES oracle2.migration_intents_v1,intake_principal_id uuid NOT NULL,intake_config_sha256 text NOT NULL,
 expected_target_head integer NOT NULL CHECK(expected_target_head>=0),
 original_dispatch_deadline timestamptz NOT NULL CHECK(isfinite(original_dispatch_deadline)),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(inventory_id,entry_sequence) REFERENCES oracle2.migration_inventory_entries_v1,
 CHECK((intake_idempotency IS NULL)=(reuses_intent_id IS NOT NULL)));
CREATE UNIQUE INDEX migration_first_intake_once_v1 ON oracle2.migration_intents_v1(binding_id) WHERE expected_target_head=0 AND reuses_intent_id IS NULL;
CREATE TABLE oracle2.migration_events_v1 (
 event_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,origin_system text NOT NULL,principal_id uuid NOT NULL,
 inventory_id uuid NOT NULL REFERENCES oracle2.migration_inventories_v1,sequence integer NOT NULL CHECK(sequence>0),
 command_id uuid NOT NULL,command_sha256 text NOT NULL CHECK(command_sha256~'^[a-f0-9]{64}$'),command_bytes bytea NOT NULL,
 kind text NOT NULL CHECK(kind IN('inventory-recorded','batch-prepared','intake-observed','resolution-observed')),
 admission_id uuid NOT NULL REFERENCES oracle2.migration_admissions_v1,payload jsonb NOT NULL,
 original_operation_valid_until timestamptz NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,origin_system,command_id),UNIQUE(inventory_id,sequence));
CREATE TABLE oracle2.migration_intent_observations_v1 (
 observation_id uuid PRIMARY KEY,intent_id uuid NOT NULL REFERENCES oracle2.migration_intents_v1,
 event_id uuid NOT NULL REFERENCES oracle2.migration_events_v1,
 state text NOT NULL CHECK(state IN('custody-observed','UNKNOWN','quarantined','metadata-only')),
 reservation_id uuid,source_uuid uuid,target_revision integer,original_sha256 text,byte_count integer,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE oracle2.migration_resolution_events_v1 (
 resolution_id uuid PRIMARY KEY,failure_event uuid NOT NULL REFERENCES oracle2.migration_events_v1,
 evidence_receipt uuid NOT NULL REFERENCES oracle2.migration_intent_observations_v1,event_id uuid NOT NULL REFERENCES oracle2.migration_events_v1,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(failure_event,evidence_receipt));
CREATE TABLE oracle2.migration_citation_bindings_v1 (
 inventory_id uuid NOT NULL REFERENCES oracle2.migration_inventories_v1,legacy_citation_id text NOT NULL,
 binding_id uuid NOT NULL REFERENCES oracle2.migration_source_bindings_v1,target_revision integer NOT NULL,
 original_sha256 text NOT NULL CHECK(original_sha256~'^[a-f0-9]{64}$'),observation_id uuid NOT NULL REFERENCES oracle2.migration_intent_observations_v1,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(inventory_id,legacy_citation_id));
-- Documentary current-capture provenance only; no historical/read grant.
CREATE TABLE oracle2.migration_capture_observations_v1 (
 capture_id uuid PRIMARY KEY,inventory_id uuid NOT NULL,entry_sequence integer NOT NULL,
 workspace_id uuid NOT NULL,origin_system text NOT NULL,legacy_kind text NOT NULL CHECK(legacy_kind='document'),legacy_id uuid NOT NULL,
 source_projection_sha256 text NOT NULL CHECK(source_projection_sha256~'^[a-f0-9]{64}$'),
 permission_sha256 text NOT NULL CHECK(permission_sha256~'^[a-f0-9]{64}$'),metadata_sha256 text NOT NULL CHECK(metadata_sha256~'^[a-f0-9]{64}$'),
 producer_program_sha256 text NOT NULL,producer_profile_sha256 text NOT NULL CHECK(producer_profile_sha256~'^[a-f0-9]{64}$'),auth_subject uuid NOT NULL,
 etag text NOT NULL CHECK(length(etag) BETWEEN 2 AND 512),
 original_sha256 text NOT NULL,byte_count integer NOT NULL CHECK(byte_count BETWEEN 1 AND 26214400),media_type text NOT NULL CHECK(media_type='application/pdf'),
 private_receipt_key text NOT NULL,receipt_sha256 text NOT NULL,receipt_byte_count integer NOT NULL CHECK(receipt_byte_count BETWEEN 1 AND 65536),
 capture jsonb NOT NULL,original_deadline timestamptz NOT NULL,recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(inventory_id,entry_sequence) REFERENCES oracle2.migration_inventory_entries_v1,
 UNIQUE(inventory_id,entry_sequence,capture_id));
CREATE FUNCTION oracle2._migration_binding_once_v1() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,oracle2 AS $$
BEGIN
 IF TG_OP<>'UPDATE' OR OLD.target_source_uuid IS NOT NULL OR NEW.target_source_uuid IS NULL
 OR (to_jsonb(OLD)-'target_source_uuid') IS DISTINCT FROM (to_jsonb(NEW)-'target_source_uuid') THEN
  RAISE insufficient_privilege USING MESSAGE='stable origin source binding is immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER migration_binding_once_v1 BEFORE UPDATE OR DELETE ON oracle2.migration_source_bindings_v1
 FOR EACH ROW EXECUTE FUNCTION oracle2._migration_binding_once_v1();
DO $private$ DECLARE n text; granted record; BEGIN
 FOREACH n IN ARRAY ARRAY['migration_admissions_v1','migration_admission_revocations_v1','migration_inventories_v1',
 'migration_inventory_entries_v1','migration_source_versions_v1','migration_intents_v1','migration_events_v1',
 'migration_intent_observations_v1','migration_resolution_events_v1','migration_citation_bindings_v1','migration_capture_observations_v1'] LOOP
  EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()','immutable_'||n,n);
 END LOOP;
 FOREACH n IN ARRAY ARRAY['migration_admissions_v1','migration_admission_revocations_v1','migration_inventories_v1',
 'migration_inventory_entries_v1','migration_source_bindings_v1','migration_source_versions_v1','migration_heads_v1',
 'migration_intents_v1','migration_events_v1','migration_intent_observations_v1','migration_resolution_events_v1','migration_citation_bindings_v1','migration_capture_observations_v1'] LOOP
  EXECUTE format('ALTER TABLE oracle2.%I ENABLE ROW LEVEL SECURITY',n);
  EXECUTE format('REVOKE ALL ON oracle2.%I FROM PUBLIC',n);
  -- Close only this newly created exact table, including inherited default
  -- ACL grantees not named by the historical runtime role inventory.
  FOR granted IN SELECT DISTINCT x.grantee FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
   CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) x
   WHERE ns.nspname='oracle2' AND c.relname=n AND x.grantee NOT IN(0,c.relowner) LOOP
   EXECUTE format('REVOKE ALL ON oracle2.%I FROM %I',n,pg_get_userbyid(granted.grantee));
  END LOOP;
 END LOOP;
END $private$;
CREATE FUNCTION oracle2._migration_named_path_v1(selected uuid,w uuid,actor uuid,wanted_scope text)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE p oracle2.appointments%ROWTYPE;seen uuid[]:='{}';until_at timestamptz:='infinity';
BEGIN
 SELECT * INTO p FROM oracle2.appointments WHERE appointment_id=selected FOR SHARE;
 IF p.appointment_id IS NULL OR (p.workspace_id,p.actor_id,p.scope) IS DISTINCT FROM(w,actor,wanted_scope) THEN RAISE insufficient_privilege; END IF;
 LOOP
  IF p.appointment_id=ANY(seen) OR cardinality(seen)>=16 OR p.workspace_id<>w OR p.revoked_at IS NOT NULL
  OR (p.expires_at IS NOT NULL AND(NOT isfinite(p.expires_at) OR p.expires_at<=clock_timestamp())) THEN RAISE insufficient_privilege; END IF;
  seen:=array_append(seen,p.appointment_id);until_at:=least(until_at,coalesce(p.expires_at,until_at));
  IF p.parent_id IS NULL THEN IF p.scope<>'root' THEN RAISE insufficient_privilege; END IF;RETURN until_at;END IF;
  SELECT * INTO p FROM oracle2.appointments WHERE appointment_id=p.parent_id AND actor_id=p.granted_by
   AND scope IN(wanted_scope,'root') FOR SHARE;
  IF p.appointment_id IS NULL THEN RAISE insufficient_privilege; END IF;
 END LOOP;
END $$;
CREATE FUNCTION oracle2._migration_scope_valid_v1(scope jsonb,maximum integer)
 RETURNS boolean LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE key text;value text;seen text[]:='{}';total integer:=0;
BEGIN
 IF jsonb_typeof(scope) IS DISTINCT FROM 'object' OR NOT scope ?& ARRAY['source_database_identity','employee_id','auth_user_id','auth_provider','channel_id','message_ids','document_ids']
 OR scope-ARRAY['source_database_identity','employee_id','auth_user_id','auth_provider','channel_id','message_ids','document_ids']<>'{}'::jsonb THEN RETURN false;END IF;
 FOREACH key IN ARRAY ARRAY['source_database_identity','employee_id','auth_user_id','channel_id'] LOOP
  IF jsonb_typeof(scope->key) IS DISTINCT FROM 'string' OR scope->>key IS DISTINCT FROM ((scope->>key)::uuid)::text THEN RETURN false;END IF;
 END LOOP;
 IF jsonb_typeof(scope->'auth_provider') IS DISTINCT FROM 'string' OR scope->>'auth_provider' NOT IN('microsoft','google','authentik','magic_link_dev') THEN RETURN false;END IF;
 FOREACH key IN ARRAY ARRAY['message_ids','document_ids'] LOOP
  IF jsonb_typeof(scope->key) IS DISTINCT FROM 'array' THEN RETURN false;END IF;
  seen:='{}';
  FOR value IN SELECT jsonb_array_elements_text(scope->key) LOOP
   IF value IS NULL OR value IS DISTINCT FROM (value::uuid)::text OR value=ANY(seen) THEN RETURN false;END IF;
   seen:=array_append(seen,value);total:=total+1;
   IF total>maximum THEN RETURN false;END IF;
  END LOOP;
  IF seen IS DISTINCT FROM ARRAY(SELECT x FROM unnest(seen) x ORDER BY x) THEN RETURN false;END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation THEN RETURN false;
END $$;
CREATE FUNCTION oracle2._migration_context_v1(appointment uuid,wanted text,runtime text,registry text,config text,deadline timestamptz,mutation boolean DEFAULT false)
 RETURNS oracle2.migration_admissions_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;login oid;until_at timestamptz;
BEGIN
 SELECT oid INTO login FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin AND NOT(rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
 IF login IS NULL OR current_setting('role') NOT IN('none',SESSION_USER::text)
 OR (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER) IS DISTINCT FROM(SELECT nspowner FROM pg_namespace WHERE nspname='oracle2')
 OR pg_has_role(login,(SELECT nspowner FROM pg_namespace WHERE nspname='oracle2'),'MEMBER')
 OR EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid<>login AND(pg_has_role(login,r.oid,'MEMBER') OR pg_has_role(login,r.oid,'SET') OR pg_has_role(login,r.oid,'USAGE')))
 OR NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl)
 OR deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() OR deadline>clock_timestamp()+interval '30 seconds' THEN RAISE insufficient_privilege; END IF;
 SELECT * INTO a FROM oracle2.migration_admissions_v1 WHERE admission_id=appointment FOR SHARE;
 IF a.admission_id IS NULL OR a.role_name IS DISTINCT FROM SESSION_USER OR a.operation IS DISTINCT FROM wanted
 OR(a.runtime_sha256,a.registry_sha256,a.config_sha256) IS DISTINCT FROM(runtime,registry,config)
 OR a.valid_from>clock_timestamp() OR a.expires_at<=clock_timestamp() OR a.original_horizon<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.migration_admission_revocations_v1 WHERE admission_id=appointment)
 OR NOT oracle2._migration_scope_valid_v1(a.source_scope,a.max_records)
 OR a.source_scope_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(a.source_scope),'UTF8')),'hex')
 THEN RAISE insufficient_privilege; END IF;
 IF mutation THEN PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||a.workspace_id::text));END IF;
 until_at:=oracle2._migration_named_path_v1(a.membership_appointment,a.workspace_id,a.principal_id,'migration-'||wanted||':'||a.origin_system);
 IF wanted<>'reconcile' THEN
  until_at:=least(until_at,oracle2._migration_named_path_v1(a.source_export_appointment,a.workspace_id,a.principal_id,'migration-source-export:'||a.origin_system));
 END IF;
 a.expires_at:=least(a.expires_at,a.original_horizon,until_at,deadline);
 IF NOT isfinite(a.expires_at) OR a.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege;END IF;
 RETURN a;
END $$;
CREATE FUNCTION oracle2._migration_json_v1(raw bytea,maximum integer)
 RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE q jsonb;
BEGIN
 IF raw IS NULL OR octet_length(raw) NOT BETWEEN 1 AND maximum THEN RAISE invalid_parameter_value;END IF;
 q:=convert_from(raw,'UTF8')::jsonb;
 IF jsonb_typeof(q)<>'object' OR convert_to(oracle2._replacement_metadata_json(q),'UTF8')<>raw THEN RAISE invalid_parameter_value;END IF;
 RETURN q;
END $$;
CREATE FUNCTION oracle2._migration_flags_v1()
 RETURNS jsonb LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT jsonb_build_object('qualification',false,'source_read_authorized',false,'viewer_authorized',false,
 'dispatch_authorized',false,'consistent_boundary_proven',false,'serving_switch_authorized',false,
 'shadow_comparison_accepted',false,'company_acceptance',false);
$$;
CREATE FUNCTION oracle2._migration_command_v1(a oracle2.migration_admissions_v1,inventory uuid,command uuid,raw bytea,kind text,payload jsonb)
 RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE prior oracle2.migration_events_v1;event uuid:=gen_random_uuid();head integer;
BEGIN
 IF command IS NULL THEN RAISE invalid_parameter_value;END IF;
 SELECT * INTO prior FROM oracle2.migration_events_v1 WHERE workspace_id=a.workspace_id AND origin_system=a.origin_system AND command_id=command;
 IF prior.event_id IS NOT NULL THEN
  IF prior.principal_id<>a.principal_id OR prior.command_bytes<>raw OR prior.kind<>kind OR prior.inventory_id<>inventory THEN RAISE unique_violation;END IF;
  RETURN prior.event_id;
 END IF;
 SELECT revision INTO head FROM oracle2.migration_heads_v1 WHERE inventory_id=inventory FOR UPDATE;
 IF head IS NULL THEN RAISE insufficient_privilege;END IF;
 INSERT INTO oracle2.migration_events_v1(event_id,workspace_id,origin_system,principal_id,inventory_id,sequence,command_id,command_sha256,command_bytes,kind,admission_id,payload,original_operation_valid_until)
 VALUES(event,a.workspace_id,a.origin_system,a.principal_id,inventory,head+1,command,encode(sha256(raw),'hex'),raw,kind,a.admission_id,payload,a.expires_at);
 UPDATE oracle2.migration_heads_v1 SET revision=head+1 WHERE inventory_id=inventory;
 RETURN event;
END $$;
CREATE FUNCTION oracle2._migration_inventory_v1(a oracle2.migration_admissions_v1,wanted uuid)
 RETURNS oracle2.migration_inventories_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE i oracle2.migration_inventories_v1;
BEGIN
 SELECT * INTO i FROM oracle2.migration_inventories_v1 WHERE inventory_id=wanted FOR SHARE;
 IF i.inventory_id IS NULL OR(i.workspace_id,i.origin_system,i.principal_id,i.descriptor_sha256,i.source_scope_sha256,i.source_program_sha256)
 IS DISTINCT FROM(a.workspace_id,a.origin_system,a.principal_id,a.descriptor_sha256,a.source_scope_sha256,a.source_program_sha256) THEN RAISE insufficient_privilege;END IF;
 RETURN i;
END $$;
CREATE FUNCTION oracle2._migration_writer_scope_current_v1(selected uuid)
 RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;until_at timestamptz;
BEGIN
 SELECT * INTO a FROM oracle2.migration_admissions_v1 WHERE admission_id=selected FOR SHARE;
 IF a.admission_id IS NULL OR a.valid_from>clock_timestamp() OR least(a.expires_at,a.original_horizon)<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.migration_admission_revocations_v1 WHERE admission_id=selected)
 OR NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=a.role_name AND rolcanlogin AND NOT(rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN RETURN false;END IF;
 until_at:=oracle2._migration_named_path_v1(a.membership_appointment,a.workspace_id,a.principal_id,'migration-'||a.operation||':'||a.origin_system);
 IF a.operation<>'reconcile' THEN until_at:=least(until_at,oracle2._migration_named_path_v1(a.source_export_appointment,a.workspace_id,a.principal_id,'migration-source-export:'||a.origin_system));END IF;
 RETURN least(until_at,a.expires_at,a.original_horizon)>clock_timestamp();
EXCEPTION WHEN insufficient_privilege THEN RETURN false;
END $$;
CREATE FUNCTION oracle2._migration_receipt_v1(a oracle2.migration_admissions_v1,wanted uuid,readonly boolean)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE e oracle2.migration_events_v1;
BEGIN
 SELECT * INTO e FROM oracle2.migration_events_v1 WHERE command_id=wanted AND workspace_id=a.workspace_id
  AND origin_system=a.origin_system AND principal_id=a.principal_id;
 IF e.event_id IS NULL THEN RAISE insufficient_privilege;END IF;
 RETURN oracle2._migration_flags_v1()||jsonb_build_object('schema_version',1,'command_id',e.command_id,'event_id',e.event_id,
 'inventory_id',e.inventory_id,'sequence',e.sequence,'kind',e.kind,'recorded_at',e.recorded_at,
 'original_operation_valid_until',e.original_operation_valid_until,
 'original_operation_window_unexpired',e.original_operation_valid_until>clock_timestamp(),
 'original_writer_scope_current',oracle2._migration_writer_scope_current_v1(e.admission_id),
 'valid_until',a.expires_at,'receipt_read_only',readonly,'observation_only',NOT readonly,
 'write_authorized',false,'resend_authorized',false);
END $$;
CREATE FUNCTION oracle2._migration_advance_v1(wanted uuid)
 RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE h oracle2.migration_heads_v1;e oracle2.migration_inventory_entries_v1;done boolean;
BEGIN
 SELECT * INTO h FROM oracle2.migration_heads_v1 WHERE inventory_id=wanted FOR UPDATE;
 FOR e IN SELECT * FROM oracle2.migration_inventory_entries_v1 WHERE inventory_id=wanted AND sequence>h.applied_sequence ORDER BY sequence LOOP
  IF e.disposition='excluded-derived' THEN done:=true;
  ELSE
   SELECT EXISTS(SELECT 1 FROM oracle2.migration_inventories_v1 inv
    JOIN oracle2.migration_source_bindings_v1 b ON b.workspace_id=inv.workspace_id AND b.origin_system=inv.origin_system AND b.legacy_kind=e.legacy_kind AND b.legacy_id=e.legacy_id
    JOIN oracle2.migration_source_versions_v1 v ON v.binding_id=b.binding_id AND v.original_identity_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('original_sha256',e.original_sha256,'byte_count',e.byte_count,'media_type',e.media_type)),'UTF8')),'hex')
    JOIN oracle2.migration_intents_v1 i ON i.version_id=v.version_id JOIN oracle2.migration_intent_observations_v1 o USING(intent_id)
    JOIN oracle2.sources src ON src.workspace_id=b.workspace_id AND src.source_id=b.target_source_uuid AND src.revision=o.target_revision
    WHERE inv.inventory_id=wanted AND o.state IN('custody-observed','metadata-only') AND NOT EXISTS(SELECT 1 FROM oracle2.migration_intent_observations_v1 bad WHERE bad.intent_id=i.intent_id AND bad.state='UNKNOWN' AND NOT EXISTS(SELECT 1 FROM oracle2.migration_resolution_events_v1 fixed WHERE fixed.failure_event=bad.event_id)) AND NOT EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE w.workspace_id=b.workspace_id AND w.source_id=b.target_source_uuid AND w.revision=o.target_revision)) INTO done;
  END IF;
  IF NOT done THEN EXIT;END IF;
  h.applied_sequence:=e.sequence;
 END LOOP;
 UPDATE oracle2.migration_heads_v1 SET applied_sequence=h.applied_sequence WHERE inventory_id=wanted;
END $$;
CREATE FUNCTION oracle2.register_migration_inventory_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz,inventory_bytes bytea,command uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;q jsonb;row jsonb;id uuid;mark integer:=0;counted integer;expected jsonb;actual jsonb;
 prior oracle2.migration_events_v1;event uuid;raw bytea;capture jsonb;observation jsonb;observation_number integer;
BEGIN
 a:=oracle2._migration_context_v1(appointment,'snapshot-register',runtime,registry,config,deadline,true);
 q:=oracle2._migration_json_v1(inventory_bytes,67108864);
 IF NOT q ?& ARRAY['schema_version','inventory_id','descriptor_sha256','source_scope_sha256','source_program_sha256','source_observation_sha256','source_observed_at','declared_count','entries']
 OR q-ARRAY['schema_version','inventory_id','descriptor_sha256','source_scope_sha256','source_program_sha256','source_observation_sha256','source_observed_at','declared_count','entries']<>'{}'::jsonb
 OR q->'schema_version' IS DISTINCT FROM '1'::jsonb OR(q->>'descriptor_sha256',q->>'source_scope_sha256',q->>'source_program_sha256') IS DISTINCT FROM(a.descriptor_sha256,a.source_scope_sha256,a.source_program_sha256)
 OR jsonb_typeof(q->'source_observation_sha256') IS DISTINCT FROM 'string' OR q->>'source_observation_sha256'!~'^[a-f0-9]{64}$'
 OR jsonb_typeof(q->'source_observed_at') IS DISTINCT FROM 'string' OR q->>'source_observed_at'!~'(Z|[+]00:00)$' OR jsonb_typeof(q->'entries')<>'array'
 OR jsonb_typeof(q->'declared_count')<>'number' OR q->>'declared_count'!~'^(0|[1-9][0-9]*)$'
 OR (q->>'declared_count')::integer<>jsonb_array_length(q->'entries') OR jsonb_array_length(q->'entries')>a.max_records
 OR (q->>'source_observed_at')::timestamptz>clock_timestamp() OR (q->>'source_observed_at')::timestamptz<clock_timestamp()-interval '30 seconds'
 OR q->>'inventory_id' IS DISTINCT FROM ((q->>'inventory_id')::uuid)::text THEN RAISE invalid_parameter_value;END IF;
 id:=(q->>'inventory_id')::uuid;
 raw:=convert_to(oracle2._replacement_metadata_json(jsonb_build_object('operation','register','inventory',q)),'UTF8');
 SELECT * INTO prior FROM oracle2.migration_events_v1 WHERE workspace_id=a.workspace_id AND origin_system=a.origin_system AND command_id=command;
 IF prior.event_id IS NOT NULL THEN
  IF prior.principal_id<>a.principal_id OR prior.command_bytes<>raw THEN RAISE unique_violation;END IF;
  RETURN oracle2._migration_receipt_v1(a,command,true);
 END IF;
 -- Exact finite installed source set, never caller count/wildcard authority.
 SELECT coalesce(jsonb_agg(jsonb_build_array(kind,key) ORDER BY kind,key),'[]') INTO expected FROM(
  SELECT 'message' AS kind,value AS key FROM jsonb_array_elements_text(a.source_scope->'message_ids')
  UNION ALL SELECT 'document',value FROM jsonb_array_elements_text(a.source_scope->'document_ids')) s;
 SELECT coalesce(jsonb_agg(jsonb_build_array(x->>'legacy_kind',x->>'legacy_id') ORDER BY x->>'legacy_kind',x->>'legacy_id'),'[]') INTO actual FROM jsonb_array_elements(q->'entries') x;
 IF expected IS DISTINCT FROM actual OR jsonb_array_length(expected)<>(q->>'declared_count')::integer THEN RAISE insufficient_privilege;END IF;
 INSERT INTO oracle2.migration_inventories_v1(inventory_id,workspace_id,origin_system,principal_id,descriptor_sha256,source_scope_sha256,source_program_sha256,
 source_observation_sha256,inventory_sha256,inventory_bytes,declared_count,source_observed_at,admission_id,original_operation_valid_until)
 VALUES(id,a.workspace_id,a.origin_system,a.principal_id,a.descriptor_sha256,a.source_scope_sha256,a.source_program_sha256,q->>'source_observation_sha256',
 encode(sha256(inventory_bytes),'hex'),inventory_bytes,(q->>'declared_count')::integer,(q->>'source_observed_at')::timestamptz,a.admission_id,a.expires_at);
 FOR row IN SELECT value FROM jsonb_array_elements(q->'entries') ORDER BY value->>'legacy_kind',value->>'legacy_id' LOOP
  mark:=mark+1;
  IF NOT row ?& ARRAY['legacy_kind','legacy_id','metadata_sha256','permission_sha256','original_sha256','byte_count','media_type','capture','disposition']
  OR row-ARRAY['legacy_kind','legacy_id','metadata_sha256','permission_sha256','original_sha256','byte_count','media_type','capture','disposition']<>'{}'::jsonb
  OR jsonb_typeof(row->'legacy_kind') IS DISTINCT FROM 'string' OR jsonb_typeof(row->'legacy_id') IS DISTINCT FROM 'string'
  OR jsonb_typeof(row->'metadata_sha256') IS DISTINCT FROM 'string' OR jsonb_typeof(row->'permission_sha256') IS DISTINCT FROM 'string'
  OR jsonb_typeof(row->'disposition') IS DISTINCT FROM 'string'
  OR (row->'byte_count'<>'null'::jsonb AND(jsonb_typeof(row->'byte_count') IS DISTINCT FROM 'number' OR row->>'byte_count'!~'^[1-9][0-9]*$'))
  OR (row->'original_sha256'<>'null'::jsonb AND jsonb_typeof(row->'original_sha256') IS DISTINCT FROM 'string')
  OR row->>'legacy_id' IS DISTINCT FROM ((row->>'legacy_id')::uuid)::text
  OR(a.permission_producer_kind='unavailable' AND row->>'disposition' IN('message-eligible','document-current-capture-eligible')) THEN RAISE invalid_parameter_value;END IF;
  INSERT INTO oracle2.migration_inventory_entries_v1 VALUES(id,mark,row->>'legacy_kind',(row->>'legacy_id')::uuid,
   row->>'metadata_sha256',row->>'permission_sha256',row->>'original_sha256',(row->>'byte_count')::integer,row->>'media_type',row->>'disposition');
  IF row->>'disposition'='document-current-capture-eligible' THEN
   -- Installed source program is the sole normalized/custody producer. SQL
   -- validates its closed documentary receipt, never claims raw hashes alone
   -- independently authenticate Auth identity, Storage RLS or original bytes.
   capture:=row->'capture';
   IF jsonb_typeof(capture) IS DISTINCT FROM 'object'
    OR NOT capture ?& ARRAY['schema_version','purpose','capture_id','legacy_id','source_projection_sha256','producer_profile_sha256','auth_subject','etag','original_sha256','byte_count','media_type','private_body_key','observations','original_deadline','historical_original_proven','qualification','company_acceptance','private_receipt_key','receipt_sha256','receipt_byte_count']
    OR capture-ARRAY['schema_version','purpose','capture_id','legacy_id','source_projection_sha256','producer_profile_sha256','auth_subject','etag','original_sha256','byte_count','media_type','private_body_key','observations','original_deadline','historical_original_proven','qualification','company_acceptance','private_receipt_key','receipt_sha256','receipt_byte_count']<>'{}'::jsonb
    OR EXISTS(SELECT 1 FROM unnest(ARRAY['purpose','capture_id','legacy_id','source_projection_sha256','producer_profile_sha256','auth_subject','etag','original_sha256','media_type','private_body_key','original_deadline','private_receipt_key','receipt_sha256']) required WHERE jsonb_typeof(capture->required) IS DISTINCT FROM 'string')
    OR jsonb_typeof(capture->'byte_count') IS DISTINCT FROM 'number' OR jsonb_typeof(capture->'receipt_byte_count') IS DISTINCT FROM 'number'
    OR capture->'schema_version' IS DISTINCT FROM '1'::jsonb OR capture->>'purpose'<>'legacy-current-original-capture-v1'
    OR capture->>'legacy_id' IS DISTINCT FROM row->>'legacy_id'
    OR(capture->>'original_sha256',capture->>'byte_count',capture->>'media_type') IS DISTINCT FROM(row->>'original_sha256',row->>'byte_count',row->>'media_type')
    OR capture->'historical_original_proven' IS DISTINCT FROM 'false'::jsonb OR capture->'qualification' IS DISTINCT FROM 'false'::jsonb OR capture->'company_acceptance' IS DISTINCT FROM 'false'::jsonb
    OR capture->>'capture_id' IS DISTINCT FROM ((capture->>'capture_id')::uuid)::text
    OR capture->>'auth_subject' IS DISTINCT FROM ((capture->>'auth_subject')::uuid)::text
    OR capture->>'source_projection_sha256'!~'^[a-f0-9]{64}$' OR capture->>'producer_profile_sha256'!~'^[a-f0-9]{64}$'
    OR capture->>'etag'!~'^"[!#-~]*"$' OR char_length(capture->>'etag')>512
    OR capture->>'private_body_key' IS DISTINCT FROM 'legacy-original-captures/'||a.workspace_id::text||'/'||(capture->>'capture_id')||'/original.pdf'
    OR capture->>'private_receipt_key' IS DISTINCT FROM 'legacy-original-captures/'||a.workspace_id::text||'/'||(capture->>'capture_id')||'/receipt.json'
    OR capture->>'receipt_sha256' IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(capture-ARRAY['private_receipt_key','receipt_sha256','receipt_byte_count']),'UTF8')),'hex')
    OR capture->>'receipt_byte_count' IS DISTINCT FROM octet_length(convert_to(oracle2._replacement_metadata_json(capture-ARRAY['private_receipt_key','receipt_sha256','receipt_byte_count']),'UTF8'))::text
    OR jsonb_typeof(capture->'observations') IS DISTINCT FROM 'array' OR jsonb_array_length(capture->'observations')<>5
    OR capture->>'original_deadline'!~'(Z|[+]00:00)$' OR NOT isfinite((capture->>'original_deadline')::timestamptz)
    OR (capture->>'original_deadline')::timestamptz>deadline OR (capture->>'original_deadline')::timestamptz<=clock_timestamp()
    THEN RAISE invalid_parameter_value;END IF;
   observation_number:=0;
   FOR observation IN SELECT value FROM jsonb_array_elements(capture->'observations') LOOP
    IF NOT observation ?& ARRAY['http_status','header_sha256','header_byte_count','wire_sha256','wire_byte_count','private_wire_key','observed_at']
     OR observation-ARRAY['http_status','header_sha256','header_byte_count','wire_sha256','wire_byte_count','private_wire_key','observed_at']<>'{}'::jsonb
     OR jsonb_typeof(observation->'header_sha256') IS DISTINCT FROM 'string' OR observation->>'header_sha256'!~'^[a-f0-9]{64}$'
     OR jsonb_typeof(observation->'header_byte_count') IS DISTINCT FROM 'number' OR observation->>'header_byte_count'!~'^[1-9][0-9]*$'
     OR (observation->>'header_byte_count')::integer NOT BETWEEN 4 AND 16384
     OR jsonb_typeof(observation->'wire_sha256') IS DISTINCT FROM 'string' OR jsonb_typeof(observation->'wire_byte_count') IS DISTINCT FROM 'number'
     OR jsonb_typeof(observation->'private_wire_key') IS DISTINCT FROM 'string' OR jsonb_typeof(observation->'observed_at') IS DISTINCT FROM 'string'
     OR observation->>'private_wire_key' IS DISTINCT FROM 'legacy-original-captures/'||a.workspace_id::text||'/'||(capture->>'capture_id')||'/'||observation_number::text||'.wire'
     OR observation->'http_status' IS DISTINCT FROM '200'::jsonb OR observation->>'wire_sha256'!~'^[a-f0-9]{64}$'
     OR observation->>'wire_byte_count'!~'^[1-9][0-9]*$' OR(observation->>'wire_byte_count')::bigint>26230784
     OR observation->>'observed_at'!~'(Z|[+]00:00)$' OR NOT isfinite((observation->>'observed_at')::timestamptz)
     OR(observation->>'observed_at')::timestamptz>clock_timestamp() OR(observation->>'observed_at')::timestamptz<clock_timestamp()-interval '30 seconds'
     THEN RAISE invalid_parameter_value;END IF;
    observation_number:=observation_number+1;
   END LOOP;
   INSERT INTO oracle2.migration_capture_observations_v1 VALUES((capture->>'capture_id')::uuid,id,mark,a.workspace_id,a.origin_system,'document',(row->>'legacy_id')::uuid,
    capture->>'source_projection_sha256',row->>'permission_sha256',row->>'metadata_sha256',a.source_program_sha256,capture->>'producer_profile_sha256',(capture->>'auth_subject')::uuid,
    capture->>'etag',row->>'original_sha256',(row->>'byte_count')::integer,row->>'media_type',capture->>'private_receipt_key',capture->>'receipt_sha256',(capture->>'receipt_byte_count')::integer,
    capture,(capture->>'original_deadline')::timestamptz,clock_timestamp());
  ELSIF row->'capture' IS DISTINCT FROM 'null'::jsonb THEN RAISE invalid_parameter_value;END IF;
 END LOOP;
 IF (SELECT coalesce(sum(byte_count),0) FROM oracle2.migration_inventory_entries_v1 WHERE inventory_id=id)>67108864 THEN RAISE invalid_parameter_value;END IF;
 INSERT INTO oracle2.migration_heads_v1(inventory_id,read_sequence) VALUES(id,mark);
 event:=oracle2._migration_command_v1(a,id,command,raw,'inventory-recorded',jsonb_build_object('count',mark));
 a:=oracle2._migration_context_v1(appointment,'snapshot-register',runtime,registry,config,deadline);
 RETURN oracle2._migration_receipt_v1(a,command,false);
END $$;
CREATE FUNCTION oracle2.prepare_migration_batch_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz,inventory uuid,expected_head integer,command uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;i oracle2.migration_inventories_v1;h oracle2.migration_heads_v1;e oracle2.migration_inventory_entries_v1;
 b oracle2.migration_source_bindings_v1;v oracle2.migration_source_versions_v1;t oracle2.migration_intents_v1;
 prior oracle2.migration_events_v1;event uuid;raw bytea;instructions jsonb:='[]';observations jsonb:='[]';target_head integer;new_version uuid;new_intent uuid;reuse uuid;original_deadline timestamptz;
BEGIN
 a:=oracle2._migration_context_v1(appointment,'batch-prepare',runtime,registry,config,deadline,true);
 i:=oracle2._migration_inventory_v1(a,inventory);
 raw:=convert_to(oracle2._replacement_metadata_json(jsonb_build_object('operation','prepare','inventory',inventory,'expected_head',expected_head)),'UTF8');
 SELECT * INTO prior FROM oracle2.migration_events_v1 WHERE workspace_id=a.workspace_id AND origin_system=a.origin_system AND command_id=command;
 IF prior.event_id IS NOT NULL THEN
  IF prior.principal_id<>a.principal_id OR prior.command_bytes<>raw THEN RAISE unique_violation;END IF;
  RETURN oracle2._migration_receipt_v1(a,command,true)||jsonb_build_object('intake_instructions','[]'::jsonb,'state','UNKNOWN');
 END IF;
 SELECT * INTO h FROM oracle2.migration_heads_v1 WHERE inventory_id=inventory FOR UPDATE;
 IF expected_head IS NULL OR expected_head<0 OR h.revision<>expected_head THEN RAISE serialization_failure;END IF;
 FOR e IN SELECT * FROM oracle2.migration_inventory_entries_v1 WHERE inventory_id=inventory AND sequence>h.applied_sequence ORDER BY sequence LIMIT a.max_batch LOOP
  IF e.disposition='excluded-derived' THEN CONTINUE;END IF;
  IF e.disposition NOT IN('message-eligible','document-current-capture-eligible') THEN EXIT;END IF;
  SELECT * INTO b FROM oracle2.migration_source_bindings_v1 WHERE origin_system=a.origin_system AND workspace_id=a.workspace_id AND legacy_kind=e.legacy_kind AND legacy_id=e.legacy_id FOR UPDATE;
  IF b.binding_id IS NULL THEN
   INSERT INTO oracle2.migration_source_bindings_v1(binding_id,origin_system,workspace_id,legacy_kind,legacy_id)
   VALUES(gen_random_uuid(),a.origin_system,a.workspace_id,e.legacy_kind,e.legacy_id) RETURNING * INTO b;
  END IF;
  SELECT * INTO v FROM oracle2.migration_source_versions_v1 WHERE binding_id=b.binding_id AND original_identity_sha256=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('original_sha256',e.original_sha256,'byte_count',e.byte_count,'media_type',e.media_type)),'UTF8')),'hex');
  IF v.version_id IS NOT NULL THEN
   IF EXISTS(SELECT 1 FROM oracle2.migration_intents_v1 x JOIN oracle2.migration_intent_observations_v1 o USING(intent_id) WHERE x.version_id=v.version_id AND o.state IN('custody-observed','metadata-only') AND NOT EXISTS(SELECT 1 FROM oracle2.migration_intent_observations_v1 bad WHERE bad.intent_id=x.intent_id AND bad.state='UNKNOWN' AND NOT EXISTS(SELECT 1 FROM oracle2.migration_resolution_events_v1 fixed WHERE fixed.failure_event=bad.event_id))) THEN CONTINUE; END IF;
   EXIT; -- Existing UNKNOWN intent never resends.
  END IF;
  IF EXISTS(SELECT 1 FROM oracle2.migration_intents_v1 x WHERE x.binding_id=b.binding_id AND NOT EXISTS(
   SELECT 1 FROM oracle2.migration_intent_observations_v1 o WHERE o.intent_id=x.intent_id AND o.state IN('custody-observed','metadata-only'))) THEN EXIT;END IF;
  target_head:=0;reuse:=NULL;original_deadline:=a.expires_at;
  IF b.target_source_uuid IS NOT NULL THEN
   PERFORM oracle2._replacement_scope(a.workspace_id,a.principal_id,'source-read:'||b.target_source_uuid::text);
   SELECT revision INTO target_head FROM oracle2.sources WHERE workspace_id=a.workspace_id AND source_id=b.target_source_uuid FOR SHARE;
   IF target_head IS NULL THEN RAISE insufficient_privilege;END IF;
   SELECT x.intent_id,x.original_dispatch_deadline INTO reuse,original_deadline FROM oracle2.migration_intents_v1 x
    JOIN oracle2.migration_source_versions_v1 oldv ON oldv.version_id=x.version_id
    JOIN oracle2.migration_intent_observations_v1 o ON o.intent_id=x.intent_id
    WHERE x.binding_id=b.binding_id AND x.reuses_intent_id IS NULL AND o.state='custody-observed'
     AND o.target_revision=target_head AND oldv.original_sha256=e.original_sha256 AND oldv.byte_count=e.byte_count AND oldv.media_type=e.media_type LIMIT 1;
   IF reuse IS NULL THEN original_deadline:=a.expires_at;END IF;
  END IF;
  new_version:=gen_random_uuid();new_intent:=gen_random_uuid();
  INSERT INTO oracle2.migration_source_versions_v1 VALUES(new_version,b.binding_id,encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('original_sha256',e.original_sha256,'byte_count',e.byte_count,'media_type',e.media_type)),'UTF8')),'hex'),e.original_sha256,e.byte_count,e.media_type,clock_timestamp());
  INSERT INTO oracle2.migration_intents_v1(intent_id,inventory_id,entry_sequence,binding_id,version_id,intake_idempotency,reuses_intent_id,intake_principal_id,intake_config_sha256,expected_target_head,original_dispatch_deadline)
  VALUES(new_intent,inventory,e.sequence,b.binding_id,new_version,CASE WHEN reuse IS NULL THEN gen_random_uuid() ELSE NULL END,reuse,a.intake_principal_id,a.intake_config_sha256,target_head,original_deadline) RETURNING * INTO t;
  IF reuse IS NOT NULL THEN observations:=observations||jsonb_build_array(t.intent_id);CONTINUE;END IF;
  instructions:=instructions||jsonb_build_array(jsonb_build_object('intent_id',t.intent_id,'legacy_id',e.legacy_id,'legacy_kind',e.legacy_kind,'media_type',e.media_type,'metadata_sha256',e.metadata_sha256,
   'source_id',b.target_source_uuid,'expected_head',target_head,'idempotency_key',t.intake_idempotency,'original_sha256',e.original_sha256,'byte_count',e.byte_count,'original_dispatch_deadline',t.original_dispatch_deadline));
 END LOOP;
 event:=oracle2._migration_command_v1(a,inventory,command,raw,'batch-prepared',jsonb_build_object('intent_ids',(SELECT coalesce(jsonb_agg(x->'intent_id'),'[]') FROM jsonb_array_elements(instructions) x)));
 PERFORM oracle2._migration_advance_v1(inventory);
 a:=oracle2._migration_context_v1(appointment,'batch-prepare',runtime,registry,config,deadline);
 RETURN oracle2._migration_receipt_v1(a,command,false)||jsonb_build_object('intake_instructions',instructions,'observation_instructions',observations,'state',CASE WHEN instructions='[]'::jsonb THEN 'blocked' ELSE 'prepared' END);
END $$;
CREATE FUNCTION oracle2._migration_iso_v1(value timestamptz)
 RETURNS text LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT to_char(value AT TIME ZONE 'UTC',CASE WHEN date_trunc('second',value)=value THEN 'YYYY-MM-DD"T"HH24:MI:SS' ELSE 'YYYY-MM-DD"T"HH24:MI:SS.US' END)||'+00:00';
$$;
CREATE FUNCTION oracle2.observe_migration_intake_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz,intent uuid,canonical_intake_receipt_bytes bytea,command uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;t oracle2.migration_intents_v1;base oracle2.migration_intents_v1;
 b oracle2.migration_source_bindings_v1;v oracle2.migration_source_versions_v1;r oracle2.source_intake_reservations_v1;
 o oracle2.source_original_revisions;q jsonb;raw bytea;event uuid;observation uuid;state text:='UNKNOWN';prior oracle2.migration_events_v1;
 expected_request text;expected_source uuid;known_revision integer;existing_observation uuid;
BEGIN
 a:=oracle2._migration_context_v1(appointment,'batch-observe',runtime,registry,config,deadline,true);
 q:=oracle2._migration_json_v1(canonical_intake_receipt_bytes,4096);
 IF q->'schema_version' IS DISTINCT FROM '1'::jsonb OR NOT q ?& ARRAY['schema_version','intake_config_sha256']
 OR q-ARRAY['schema_version','intake_config_sha256']<>'{}'::jsonb THEN RAISE invalid_parameter_value;END IF;
 SELECT * INTO t FROM oracle2.migration_intents_v1 WHERE intent_id=intent FOR SHARE;
 SELECT * INTO b FROM oracle2.migration_source_bindings_v1 WHERE binding_id=t.binding_id FOR UPDATE;
 SELECT * INTO v FROM oracle2.migration_source_versions_v1 WHERE version_id=t.version_id;
 IF t.intent_id IS NULL OR(b.workspace_id,b.origin_system,t.intake_principal_id,t.intake_config_sha256)
 IS DISTINCT FROM(a.workspace_id,a.origin_system,a.intake_principal_id,a.intake_config_sha256)
 OR q->>'intake_config_sha256' IS DISTINCT FROM t.intake_config_sha256 THEN RAISE insufficient_privilege;END IF;
 PERFORM oracle2._migration_inventory_v1(a,t.inventory_id);
 raw:=convert_to(oracle2._replacement_metadata_json(jsonb_build_object('operation','observe','intent',intent,'receipt',q)),'UTF8');
 SELECT * INTO prior FROM oracle2.migration_events_v1 WHERE workspace_id=a.workspace_id AND origin_system=a.origin_system AND command_id=command;
 IF prior.event_id IS NOT NULL THEN
  IF prior.principal_id<>a.principal_id OR prior.command_bytes<>raw THEN RAISE unique_violation;END IF;
  RETURN oracle2._migration_receipt_v1(a,command,true);
 END IF;
 base:=t;
 IF t.reuses_intent_id IS NOT NULL THEN
  SELECT * INTO base FROM oracle2.migration_intents_v1 WHERE intent_id=t.reuses_intent_id FOR SHARE;
  IF base.binding_id<>t.binding_id OR base.reuses_intent_id IS NOT NULL THEN RAISE insufficient_privilege;END IF;
 END IF;
 SELECT * INTO r FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=a.workspace_id AND principal_id=t.intake_principal_id AND idempotency_key=base.intake_idempotency FOR SHARE;
 IF r.reservation_id IS NOT NULL THEN
  expected_source:=CASE WHEN base.expected_target_head=0 THEN NULL ELSE b.target_source_uuid END;
  expected_request:=oracle2._replacement_metadata_json(jsonb_build_object('expected_head',base.expected_target_head,
   'intake',jsonb_build_object('source_id',expected_source,'filename','legacy_'||b.legacy_id::text||CASE WHEN v.media_type='application/pdf' THEN '.pdf' ELSE '.txt' END,'media_type',v.media_type,
   'byte_count',v.byte_count,'caller_deadline',oracle2._migration_iso_v1(base.original_dispatch_deadline))));
  IF r.request_sha256 IS DISTINCT FROM encode(sha256(convert_to(expected_request,'UTF8')),'hex')
   OR r.expected_head<>base.expected_target_head OR r.byte_count<>v.byte_count OR r.media_type<>v.media_type
   OR (b.target_source_uuid IS NOT NULL AND b.target_source_uuid<>r.source_id) THEN RAISE insufficient_privilege;END IF;
  IF b.target_source_uuid IS NULL THEN
   UPDATE oracle2.migration_source_bindings_v1 SET target_source_uuid=r.source_id WHERE binding_id=b.binding_id;
   b.target_source_uuid:=r.source_id;
  END IF;
  IF r.finalized_at IS NOT NULL THEN
   SELECT * INTO o FROM oracle2.source_original_revisions WHERE workspace_id=a.workspace_id AND source_id=r.source_id AND revision=r.revision;
   IF(o.original_sha256,o.byte_count,r.original_sha256) IS DISTINCT FROM(v.original_sha256,v.byte_count::bigint,v.original_sha256)
   OR o.custody_locator_seal_sha256 IS DISTINCT FROM r.custody_seal_sha256 THEN RAISE insufficient_privilege;END IF;
   known_revision:=r.revision;
   -- A truthful own forensic observation survives source denial. It is not a
   -- positive active import, body permission, viewer or qualified SourceRef.
   state:=CASE WHEN t.reuses_intent_id IS NULL THEN 'custody-observed' ELSE 'metadata-only' END;
   IF t.reuses_intent_id IS NOT NULL AND r.revision<>t.expected_target_head THEN RAISE insufficient_privilege;END IF;
  END IF;
 END IF;
 event:=oracle2._migration_command_v1(a,t.inventory_id,command,raw,'intake-observed',jsonb_build_object('intent_id',intent,'state',state));
 observation:=gen_random_uuid();
 INSERT INTO oracle2.migration_intent_observations_v1(observation_id,intent_id,event_id,state,reservation_id,source_uuid,target_revision,original_sha256,byte_count)
 VALUES(observation,intent,event,state,r.reservation_id,r.source_id,known_revision,CASE WHEN known_revision IS NOT NULL THEN o.original_sha256 END,CASE WHEN known_revision IS NOT NULL THEN o.byte_count END);
 IF state IN('custody-observed','metadata-only') THEN
  INSERT INTO oracle2.migration_citation_bindings_v1(inventory_id,legacy_citation_id,binding_id,target_revision,original_sha256,observation_id)
   VALUES(t.inventory_id,b.legacy_kind||':'||b.legacy_id::text,b.binding_id,known_revision,o.original_sha256,observation)
   ON CONFLICT DO NOTHING;
 END IF;
 -- Explicit UNKNOWN history is never erased by a later observation. Its safe
 -- cursor needs separately evidenced resolution, not a delivery retry.
 IF NOT EXISTS(SELECT 1 FROM oracle2.migration_intent_observations_v1 old WHERE old.intent_id=intent AND old.state='UNKNOWN') THEN
  PERFORM oracle2._migration_advance_v1(t.inventory_id);
 END IF;
 a:=oracle2._migration_context_v1(appointment,'batch-observe',runtime,registry,config,deadline);
 RETURN oracle2._migration_receipt_v1(a,command,false)||jsonb_build_object('observation_id',observation,'intent_id',intent,'state',state,
  'source_id',r.source_id,'revision',known_revision,'original_sha256',CASE WHEN known_revision IS NOT NULL THEN o.original_sha256 END,
  'byte_count',CASE WHEN known_revision IS NOT NULL THEN o.byte_count END,'observation_only',true,'receipt_read_only',false,'active_import_proven',false);
END $$;
CREATE FUNCTION oracle2.record_migration_resolution_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz,failure_event uuid,evidence_receipt uuid,expected_head integer,command uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;f oracle2.migration_events_v1;o oracle2.migration_intent_observations_v1;t oracle2.migration_intents_v1;
 raw bytea;event uuid;prior oracle2.migration_events_v1;head integer;
BEGIN
 a:=oracle2._migration_context_v1(appointment,'batch-observe',runtime,registry,config,deadline,true);
 SELECT * INTO f FROM oracle2.migration_events_v1 WHERE event_id=failure_event;
 SELECT * INTO o FROM oracle2.migration_intent_observations_v1 WHERE observation_id=evidence_receipt;
 SELECT * INTO t FROM oracle2.migration_intents_v1 WHERE intent_id=o.intent_id;
 IF f.event_id IS NULL OR o.observation_id IS NULL OR(f.workspace_id,f.origin_system,f.principal_id)
 IS DISTINCT FROM(a.workspace_id,a.origin_system,a.principal_id) OR f.inventory_id<>t.inventory_id
 OR f.kind<>'intake-observed' OR f.payload->>'state'<>'UNKNOWN' OR f.payload->>'intent_id' IS DISTINCT FROM t.intent_id::text
 OR o.state NOT IN('custody-observed','metadata-only')
 OR f.sequence>=(SELECT sequence FROM oracle2.migration_events_v1 WHERE event_id=o.event_id) THEN RAISE insufficient_privilege;END IF;
 PERFORM oracle2._migration_inventory_v1(a,t.inventory_id);
 raw:=convert_to(oracle2._replacement_metadata_json(jsonb_build_object('operation','resolve','failure_event',failure_event,'evidence_receipt',evidence_receipt,'expected_head',expected_head)),'UTF8');
 SELECT * INTO prior FROM oracle2.migration_events_v1 WHERE workspace_id=a.workspace_id AND origin_system=a.origin_system AND command_id=command;
 IF prior.event_id IS NOT NULL THEN
  IF prior.principal_id<>a.principal_id OR prior.command_bytes<>raw THEN RAISE unique_violation;END IF;
  RETURN oracle2._migration_receipt_v1(a,command,true);
 END IF;
 SELECT revision INTO head FROM oracle2.migration_heads_v1 WHERE inventory_id=t.inventory_id FOR UPDATE;
 IF expected_head IS NULL OR expected_head<0 OR head<>expected_head THEN RAISE serialization_failure;END IF;
 event:=oracle2._migration_command_v1(a,t.inventory_id,command,raw,'resolution-observed',jsonb_build_object('failure_event',failure_event,'evidence_receipt',evidence_receipt));
 INSERT INTO oracle2.migration_resolution_events_v1 VALUES(gen_random_uuid(),failure_event,evidence_receipt,event,clock_timestamp());
 PERFORM oracle2._migration_advance_v1(t.inventory_id);
 a:=oracle2._migration_context_v1(appointment,'batch-observe',runtime,registry,config,deadline);
 RETURN oracle2._migration_receipt_v1(a,command,false);
END $$;
CREATE FUNCTION oracle2.current_migration_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz,inventory uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;i oracle2.migration_inventories_v1;h oracle2.migration_heads_v1;counts jsonb;entry_sha text;
BEGIN
 IF inventory IS NULL THEN
  a:=oracle2._migration_context_v1(appointment,'snapshot-register',runtime,registry,config,deadline);
  RETURN oracle2._migration_flags_v1()||jsonb_build_object('schema_version',1,'operation','source-export-context','principal_id',a.principal_id,
   'workspace_id',a.workspace_id,'origin_system',a.origin_system,'descriptor_sha256',a.descriptor_sha256,'source_scope_sha256',a.source_scope_sha256,
   'source_program_sha256',a.source_program_sha256,'intake_principal_id',a.intake_principal_id,'intake_config_sha256',a.intake_config_sha256,'permission_producer_kind',a.permission_producer_kind,'valid_until',a.expires_at);
 END IF;
 a:=oracle2._migration_context_v1(appointment,'read',runtime,registry,config,deadline);
 i:=oracle2._migration_inventory_v1(a,inventory);
 SELECT * INTO h FROM oracle2.migration_heads_v1 WHERE inventory_id=inventory;
 SELECT jsonb_build_object('inventory',count(*),'eligible_metadata',count(*) FILTER(WHERE disposition IN('message-eligible','document-current-capture-eligible')),
  'quarantined',count(*) FILTER(WHERE disposition NOT IN('message-eligible','document-current-capture-eligible','excluded-derived')),
  'intentionally_excluded',count(*) FILTER(WHERE disposition='excluded-derived')) INTO counts
 FROM oracle2.migration_inventory_entries_v1 WHERE inventory_id=inventory;
 SELECT encode(sha256(convert_to(oracle2._replacement_metadata_json(coalesce(jsonb_agg(jsonb_build_object(
  'legacy_kind',e.legacy_kind,'legacy_id',e.legacy_id,'metadata_sha256',e.metadata_sha256,'permission_sha256',e.permission_sha256,
  'original_sha256',e.original_sha256,'byte_count',e.byte_count,'media_type',e.media_type,'disposition',e.disposition) ORDER BY e.sequence),'[]'::jsonb)),'UTF8')),'hex')
  INTO entry_sha FROM oracle2.migration_inventory_entries_v1 e WHERE e.inventory_id=inventory;
 a:=oracle2._migration_context_v1(appointment,'read',runtime,registry,config,deadline);
 RETURN oracle2._migration_flags_v1()||jsonb_build_object('schema_version',1,'operation','inventory-status','inventory_id',inventory,
  'inventory_entries_sha256',entry_sha,'revision',h.revision,'read_sequence',h.read_sequence,'applied_sequence',h.applied_sequence,'counts',counts,
  'declared_finite_inventory_shape_complete',true,'actual_target_effects_complete',h.applied_sequence=h.read_sequence,
  'valid_until',a.expires_at,'body_available',false);
END $$;
CREATE FUNCTION oracle2.reconcile_migration_command_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz,command uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;
BEGIN
 a:=oracle2._migration_context_v1(appointment,'reconcile',runtime,registry,config,deadline);
 IF command IS NULL THEN RAISE invalid_parameter_value;END IF;
 -- Read-only immutable receipt. Never allocate, bind source UUID, observe
 -- intake, advance cursor, retry a command or renew original dispatch window.
 RETURN oracle2._migration_receipt_v1(a,command,true);
END $$;
CREATE FUNCTION oracle2.resolve_migration_citation_v1(appointment uuid,runtime text,registry text,config text,deadline timestamptz,legacy_citation_id text,inventory uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.migration_admissions_v1;c oracle2.migration_citation_bindings_v1;b oracle2.migration_source_bindings_v1;head integer;denied boolean;
BEGIN
 a:=oracle2._migration_context_v1(appointment,'citation-read',runtime,registry,config,deadline);
 PERFORM oracle2._migration_inventory_v1(a,inventory);
 IF legacy_citation_id IS NULL OR length(legacy_citation_id) NOT BETWEEN 1 AND 256 THEN RAISE invalid_parameter_value;END IF;
 SELECT * INTO c FROM oracle2.migration_citation_bindings_v1 x WHERE x.inventory_id=inventory AND x.legacy_citation_id=resolve_migration_citation_v1.legacy_citation_id;
 SELECT * INTO b FROM oracle2.migration_source_bindings_v1 WHERE binding_id=c.binding_id;
 SELECT revision INTO head FROM oracle2.sources WHERE workspace_id=a.workspace_id AND source_id=b.target_source_uuid;
 denied:=c.binding_id IS NULL OR head IS DISTINCT FROM c.target_revision OR EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE w.workspace_id=a.workspace_id AND w.source_id=b.target_source_uuid AND w.revision=c.target_revision);
 a:=oracle2._migration_context_v1(appointment,'citation-read',runtime,registry,config,deadline);
 -- Mapping metadata only. A second independently installed actual viewer role
 -- is mandatory before the caller can emit a same-origin original link/body.
 RETURN oracle2._migration_flags_v1()||jsonb_build_object('schema_version',1,'operation','citation-mapping','inventory_id',inventory,
  'redacted',denied,'source_id',CASE WHEN NOT denied THEN b.target_source_uuid END,'revision',CASE WHEN NOT denied THEN c.target_revision END,
  'original_sha256',CASE WHEN NOT denied THEN c.original_sha256 END,'independent_viewer_check_required',true,'valid_until',a.expires_at);
END $$;
-- No runtime grant/role/appointment installation. Every public operation needs
-- separately reviewed installation; all owner-private helpers remain ungranted.
DO $acl$ DECLARE target_function record; granted record; BEGIN
 FOR target_function IN SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='oracle2' AND p.oid=ANY(ARRAY[
  to_regprocedure('oracle2.register_migration_inventory_v1(uuid,text,text,text,timestamptz,bytea,uuid)'),
  to_regprocedure('oracle2.prepare_migration_batch_v1(uuid,text,text,text,timestamptz,uuid,integer,uuid)'),
  to_regprocedure('oracle2.observe_migration_intake_v1(uuid,text,text,text,timestamptz,uuid,bytea,uuid)'),
  to_regprocedure('oracle2.record_migration_resolution_v1(uuid,text,text,text,timestamptz,uuid,uuid,integer,uuid)'),
  to_regprocedure('oracle2.current_migration_v1(uuid,text,text,text,timestamptz,uuid)'),
  to_regprocedure('oracle2.reconcile_migration_command_v1(uuid,text,text,text,timestamptz,uuid)'),
  to_regprocedure('oracle2.resolve_migration_citation_v1(uuid,text,text,text,timestamptz,text,uuid)'),
  to_regprocedure('oracle2._migration_binding_once_v1()'),
  to_regprocedure('oracle2._migration_named_path_v1(uuid,uuid,uuid,text)'),
  to_regprocedure('oracle2._migration_scope_valid_v1(jsonb,integer)'),
  to_regprocedure('oracle2._migration_context_v1(uuid,text,text,text,text,timestamptz,boolean)'),
  to_regprocedure('oracle2._migration_json_v1(bytea,integer)'),
  to_regprocedure('oracle2._migration_flags_v1()'),
  to_regprocedure('oracle2._migration_command_v1(oracle2.migration_admissions_v1,uuid,uuid,bytea,text,jsonb)'),
  to_regprocedure('oracle2._migration_inventory_v1(oracle2.migration_admissions_v1,uuid)'),
  to_regprocedure('oracle2._migration_writer_scope_current_v1(uuid)'),
  to_regprocedure('oracle2._migration_receipt_v1(oracle2.migration_admissions_v1,uuid,boolean)'),
  to_regprocedure('oracle2._migration_advance_v1(uuid)'),
  to_regprocedure('oracle2._migration_iso_v1(timestamptz)')]::oid[]) LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',target_function.oid::regprocedure);
  FOR granted IN SELECT DISTINCT x.grantee FROM pg_proc own
   CROSS JOIN LATERAL aclexplode(coalesce(own.proacl,acldefault('f',own.proowner))) x
   WHERE own.oid=target_function.oid AND x.grantee NOT IN(0,own.proowner) LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',target_function.oid::regprocedure,pg_get_userbyid(granted.grantee));
  END LOOP;
 END LOOP;
END $acl$;
