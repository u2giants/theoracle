-- Dedicated Oracle quarantined operational recovery. SOURCE ONLY.
-- No role/grant/admission issuance, positive permission, spend allowance or serving activation.
-- The immutable phase master lives ONLY on the intact original control plane.
DO $owner$ BEGIN
 IF (SELECT nspowner FROM pg_namespace WHERE nspname='oracle2') IS DISTINCT FROM
 (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER) THEN RAISE EXCEPTION 'dedicated canonical recovery owner required'; END IF;
END $owner$;
CREATE TABLE oracle2.recovery_operation_admissions_v1 (
 admission_id uuid PRIMARY KEY,operation_id uuid NOT NULL,role_name name NOT NULL,principal_id uuid NOT NULL,
 phase_authority text NOT NULL CHECK(phase_authority IN('capture','current-denials','deny-only-target','observe')),
 runtime_hash text NOT NULL CHECK(runtime_hash~'^[a-f0-9]{64}$'),registry_hash text NOT NULL CHECK(registry_hash~'^[a-f0-9]{64}$'),
 descriptor_bytes bytea NOT NULL CHECK(octet_length(descriptor_bytes) BETWEEN 1 AND 65536),
 descriptor_sha256 text NOT NULL CHECK(descriptor_sha256=encode(sha256(descriptor_bytes),'hex')),
 postrestore_binding_bytes bytea CHECK(octet_length(postrestore_binding_bytes) BETWEEN 1 AND 65536),
 postrestore_binding_sha256 text CHECK(postrestore_binding_sha256=encode(sha256(postrestore_binding_bytes),'hex')),
 backup_custody_sha256 text CHECK(backup_custody_sha256~'^[a-f0-9]{64}$'),
 catalog jsonb NOT NULL CHECK(jsonb_typeof(catalog)='object'),
 scope_coverage jsonb NOT NULL CHECK(jsonb_typeof(scope_coverage)='array' AND jsonb_array_length(scope_coverage) BETWEEN 1 AND 1024),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL,issued_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,original_horizon timestamptz NOT NULL,
 CHECK((postrestore_binding_bytes IS NULL)=(postrestore_binding_sha256 IS NULL)),
 CHECK(isfinite(issued_at) AND isfinite(expires_at) AND isfinite(original_horizon)
 AND issued_at<expires_at AND expires_at<=original_horizon AND expires_at<=issued_at+interval '3600 seconds'),
 CHECK(issuer_actor<>reviewer_actor AND principal_id NOT IN(issuer_actor,reviewer_actor)));
CREATE TABLE oracle2.recovery_admission_revocations_v1 (
 admission_id uuid PRIMARY KEY REFERENCES oracle2.recovery_operation_admissions_v1,
 revoked_at timestamptz NOT NULL CHECK(isfinite(revoked_at)));
CREATE TABLE oracle2.recovery_phase_claims_v1 (
 operation_id uuid NOT NULL,phase text NOT NULL CHECK(phase IN('capture','restore','deny-import','rebuild-verify','resume-observe')),
 admission_id uuid NOT NULL REFERENCES oracle2.recovery_operation_admissions_v1,
 descriptor_sha256 text NOT NULL CHECK(descriptor_sha256~'^[a-f0-9]{64}$'),
 claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),original_phase_deadline timestamptz NOT NULL,
 PRIMARY KEY(operation_id,phase),CHECK(isfinite(original_phase_deadline) AND claimed_at<original_phase_deadline
 AND original_phase_deadline<=claimed_at+interval '3600 seconds'));
-- A new admission/operation cannot reset a possibly effected physical target.
CREATE TABLE oracle2.recovery_target_reservations_v1 (
 resource_kind text NOT NULL CHECK(resource_kind IN('database','private-root')),resource_sha256 text NOT NULL CHECK(resource_sha256~'^[a-f0-9]{64}$'),
 operation_id uuid NOT NULL,phase text NOT NULL CHECK(phase='restore'),PRIMARY KEY(resource_kind,resource_sha256),
 FOREIGN KEY(operation_id,phase) REFERENCES oracle2.recovery_phase_claims_v1);
CREATE TABLE oracle2.recovery_phase_observations_v1 (
 observation_id uuid PRIMARY KEY,operation_id uuid NOT NULL,claimed_phase text,attempted_phase text NOT NULL,
 observation_bytes bytea NOT NULL CHECK(octet_length(observation_bytes) BETWEEN 1 AND 65536),
 observation_sha256 text NOT NULL CHECK(observation_sha256=encode(sha256(observation_bytes),'hex')),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(operation_id,claimed_phase) REFERENCES oracle2.recovery_phase_claims_v1,
 UNIQUE(operation_id,observation_sha256));
CREATE TABLE oracle2.recovery_denial_imports_v1 (
 operation_id uuid NOT NULL,census_sha256 text NOT NULL CHECK(census_sha256~'^[a-f0-9]{64}$'),
 admission_id uuid NOT NULL REFERENCES oracle2.recovery_operation_admissions_v1,
 census_bytes bytea NOT NULL CHECK(octet_length(census_bytes) BETWEEN 1 AND 1048576),
 imported_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(operation_id,census_sha256),
 CHECK(census_sha256=encode(sha256(census_bytes),'hex')));
-- Additive target quarantine overlay only. It never grants access or replaces
-- canonical source/appointment/history facts. Restored application LOGINs must
-- remain NOLOGIN/passwordless under the separately admitted restore executor.
CREATE TABLE oracle2.recovery_deny_overlay_v1 (
 operation_id uuid NOT NULL,deny_sha256 text NOT NULL CHECK(deny_sha256~'^[a-f0-9]{64}$'),
 census_sha256 text NOT NULL,deny_kind text NOT NULL CHECK(deny_kind IN('source','withdrawal','authority','operational')),
 deny_metadata jsonb NOT NULL CHECK(jsonb_typeof(deny_metadata)='object'),
 PRIMARY KEY(operation_id,deny_sha256),
 FOREIGN KEY(operation_id,census_sha256) REFERENCES oracle2.recovery_denial_imports_v1);
DO $immutable$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['recovery_operation_admissions_v1','recovery_admission_revocations_v1','recovery_phase_claims_v1','recovery_target_reservations_v1','recovery_phase_observations_v1','recovery_denial_imports_v1','recovery_deny_overlay_v1'] LOOP
 EXECUTE format('REVOKE ALL ON oracle2.%I FROM PUBLIC,oracle2_source_reader,oracle2_replacement_requester,oracle2_candidate_compiler,oracle2_gateway_metadata,oracle2_documentary_executor,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer',t);
 EXECUTE format('CREATE TRIGGER immutable_%I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()',t,t);
 END LOOP;
END $immutable$;

CREATE FUNCTION oracle2._recovery_json_v1(raw bytea,maximum integer)
 RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE j jsonb;BEGIN
 IF maximum NOT IN(65536,1048576) OR raw IS NULL OR octet_length(raw) NOT BETWEEN 1 AND maximum THEN RAISE invalid_parameter_value;END IF;
 j:=convert_from(raw,'UTF8')::jsonb;
 IF jsonb_typeof(j)<>'object' OR convert_to(oracle2._replacement_metadata_json(j),'UTF8')<>raw
 OR j->'schema_version' IS DISTINCT FROM '1'::jsonb THEN RAISE invalid_parameter_value USING MESSAGE='exact canonical recovery bytes required';END IF;
 RETURN j;
END $f$;


CREATE FUNCTION oracle2._recovery_operational_denials_v1(workspaces uuid[],observed_at timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE result jsonb;BEGIN
 IF workspaces IS NULL OR cardinality(workspaces) NOT BETWEEN 1 AND 256 OR observed_at IS NULL OR NOT isfinite(observed_at) THEN RAISE insufficient_privilege;END IF;
 -- No incomplete or ambiguous joins may disappear behind an inner join.
 IF EXISTS(SELECT 1 FROM oracle2.meeting_participation_heads_v1 h WHERE h.workspace_id=ANY(workspaces) AND h.last_event_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_participation_events_v1 e WHERE e.event_id=h.last_event_id AND(e.workspace_id,e.meeting_id)=(h.workspace_id,h.meeting_id)))
 OR EXISTS(SELECT 1 FROM oracle2.meeting_participation_delivery_heads_v1 h JOIN oracle2.meeting_participation_intents_v1 i USING(intent_id) WHERE i.workspace_id=ANY(workspaces) AND h.last_event_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_participation_delivery_events_v1 e WHERE e.event_id=h.last_event_id AND e.intent_id=h.intent_id))
 OR EXISTS(SELECT 1 FROM oracle2.research_state_v1 WHERE workspace_id=ANY(workspaces) AND next_due>observed_at AND NOT isfinite(next_due))
 OR EXISTS(SELECT 1 FROM oracle2.recommendation_registrations_v1 r WHERE r.workspace_id=ANY(workspaces) AND r.version<(SELECT max(x.version) FROM oracle2.recommendation_registrations_v1 x WHERE(x.workspace_id,x.artifact_id)=(r.workspace_id,r.artifact_id)) AND r.parent_version=(SELECT max(x.version) FROM oracle2.processing_model_revisions_v1 x WHERE(x.workspace_id,x.artifact_id)=(r.workspace_id,r.parent_model)))
 THEN RAISE insufficient_privilege USING MESSAGE='unmapped or ambiguous operational denial; recovery quarantined';END IF;
 -- Historical custody checks deliberately do NOT invoke the old current/expiry
 -- parser: retained valid links survive capture expiry without renewing it.
 IF EXISTS(SELECT 1 FROM oracle2.meeting_capture_final_fetch_claims_v1 q
 LEFT JOIN oracle2.meeting_capture_admissions_v1 m ON m.admission_id=q.admission_id
 LEFT JOIN oracle2.meeting_capture_events_v1 e ON e.event_id=q.initiating_ingress_event_id
 WHERE q.workspace_id=ANY(workspaces) AND (m.admission_id IS NULL OR e.event_id IS NULL
 OR (m.workspace_id,m.meeting_id,m.principal_id) IS DISTINCT FROM(q.workspace_id,q.meeting_id,q.principal_id)
 OR (e.workspace_id,e.meeting_id,e.action,e.provider,e.provider_account) IS DISTINCT FROM(q.workspace_id,q.meeting_id,'ingress',m.provider,m.provider_account)
 OR e.payload->>'bot_id' IS DISTINCT FROM m.bot_id
 OR q.descriptor_sha256 IS DISTINCT FROM m.final_artifact_sha256
 OR q.final_operation_id IS DISTINCT FROM m.final_artifact_operation_id
 OR q.original_processing_horizon IS DISTINCT FROM m.original_horizon
 OR q.descriptor_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(m.final_artifact_descriptor),'UTF8')),'hex')
 OR q.population_sha256 IS DISTINCT FROM(SELECT encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_object_agg(key,value)),'UTF8')),'hex') FROM jsonb_each(m.final_artifact_descriptor) WHERE key=ANY(ARRAY['workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id','bot_id','recording_id','transcript_id','provider_revision','provider_finality_receipt_sha256','original_sha256','byte_count','media_type']))))
 OR EXISTS(SELECT 1 FROM oracle2.meeting_capture_processing_links_v1 l
 LEFT JOIN oracle2.meeting_capture_final_fetch_claims_v1 q ON q.fetch_claim_id=l.fetch_claim_id
 LEFT JOIN oracle2.meeting_capture_admissions_v1 m ON m.admission_id=l.observation_admission_id
 LEFT JOIN oracle2.meeting_capture_events_v1 ingress ON ingress.event_id=l.original_ingress_event_id
 LEFT JOIN oracle2.meeting_capture_events_v1 final ON final.event_id=l.final_event_id
 WHERE l.workspace_id=ANY(workspaces) AND(q.fetch_claim_id IS NULL OR m.admission_id IS NULL OR ingress.event_id IS NULL OR final.event_id IS NULL
 OR(q.workspace_id,q.meeting_id,q.descriptor_sha256) IS DISTINCT FROM(l.workspace_id,l.meeting_id,l.descriptor_sha256)
 OR(m.workspace_id,m.meeting_id,m.final_artifact_sha256,m.final_artifact_operation_id,m.original_horizon) IS DISTINCT FROM(l.workspace_id,l.meeting_id,q.descriptor_sha256,q.final_operation_id,q.original_processing_horizon)
 OR(ingress.workspace_id,ingress.meeting_id,ingress.action,ingress.provider,ingress.provider_account) IS DISTINCT FROM(l.workspace_id,l.meeting_id,'ingress',m.provider,m.provider_account)
 OR ingress.payload->>'bot_id' IS DISTINCT FROM m.bot_id
 OR(final.workspace_id,final.meeting_id,final.action,final.operation_id,final.provider,final.provider_account) IS DISTINCT FROM(l.workspace_id,l.meeting_id,'final_artifact',q.final_operation_id,m.provider,m.provider_account)
 OR final.created_at<q.claimed_at OR final.created_at>q.original_effect_deadline
 OR final.payload IS DISTINCT FROM jsonb_build_object('selection_sha256',q.descriptor_sha256,'provider_event_id','final:'||q.descriptor_sha256,'raw_sha256',m.final_artifact_descriptor->>'original_sha256','byte_count',m.final_artifact_descriptor->'byte_count','raw_object_key','meeting-raw/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||(m.final_artifact_descriptor->>'original_sha256')||'.bin','event_kind',m.provider||'.final')
 OR final.payload_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('action','final_artifact','body',final.payload)),'UTF8')),'hex')))
 OR EXISTS(SELECT 1 FROM oracle2.meeting_capture_enqueue_claims_v1 q
 LEFT JOIN oracle2.meeting_capture_admissions_v1 m ON m.admission_id=q.admission_id
 LEFT JOIN oracle2.meeting_capture_events_v1 e ON e.event_id=q.ingress_event_id
 WHERE q.workspace_id=ANY(workspaces) AND(m.admission_id IS NULL OR e.event_id IS NULL
 OR(m.workspace_id,m.meeting_id,m.principal_id,m.original_horizon) IS DISTINCT FROM(q.workspace_id,q.meeting_id,q.principal_id,q.original_processing_horizon)
 OR(e.workspace_id,e.meeting_id,e.action,e.provider,e.provider_account) IS DISTINCT FROM(q.workspace_id,q.meeting_id,'ingress',m.provider,m.provider_account)
 OR q.queue_pins IS DISTINCT FROM jsonb_build_object('queue_project_ref',m.queue_project_ref,'queue_environment_id',m.queue_environment_id,'queue_account_id',m.queue_account_id,'queue_task_id',m.queue_task_id,'queue_credential_sha256',m.queue_credential_sha256,'queue_installation_receipt_sha256',m.queue_installation_receipt_sha256,'queue_target_descriptor_sha256',m.queue_target_descriptor_sha256)
 OR q.request_body IS DISTINCT FROM jsonb_build_object('payload',jsonb_build_object('ingress_event_id',q.ingress_event_id),'options',jsonb_build_object('idempotencyKey','oracle2-meeting-ingress-normalize-v1:'||q.workspace_id::text||':'||q.meeting_id::text||':'||q.ingress_event_id::text))
 OR q.request_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(q.request_body),'UTF8')),'hex')))
 OR EXISTS(SELECT 1 FROM oracle2.meeting_capture_enqueue_receipts_v1 r
 LEFT JOIN oracle2.meeting_capture_enqueue_claims_v1 q ON q.claim_id=r.claim_id
 LEFT JOIN oracle2.meeting_capture_admissions_v1 m ON m.admission_id=r.admission_id
 WHERE (q.workspace_id=ANY(workspaces) OR m.workspace_id=ANY(workspaces)) AND(q.claim_id IS NULL OR m.admission_id IS NULL
 OR r.admission_id IS DISTINCT FROM q.admission_id
 OR(m.workspace_id,m.meeting_id,m.principal_id) IS DISTINCT FROM(q.workspace_id,q.meeting_id,q.principal_id)
 OR r.raw_object_key IS DISTINCT FROM 'meeting-queue/'||q.workspace_id::text||'/'||q.meeting_id::text||'/'||q.ingress_event_id::text||'/'||q.claim_id::text||'/trigger-response.wire'
 OR jsonb_typeof(r.observation) IS DISTINCT FROM 'object' OR NOT(r.observation?&ARRAY['kind','complete','run_id','body_sha256']) OR r.observation-ARRAY['kind','complete','run_id','body_sha256']<>'{}'::jsonb
 OR jsonb_typeof(r.observation->'kind') IS DISTINCT FROM 'string' OR r.observation->>'kind' NOT IN('UNKNOWN','enqueue-observed') OR jsonb_typeof(r.observation->'complete') IS DISTINCT FROM 'boolean'
 OR r.observation->>'kind'='UNKNOWN' AND(r.observation->'run_id' IS DISTINCT FROM 'null'::jsonb OR r.observation->'body_sha256' IS DISTINCT FROM 'null'::jsonb)
 OR r.observation->>'kind'='enqueue-observed' AND(r.observation->'complete' IS DISTINCT FROM 'true'::jsonb OR jsonb_typeof(r.observation->'run_id') IS DISTINCT FROM 'string' OR (r.observation->>'run_id'!~'^[A-Za-z0-9_-]+$' OR char_length(r.observation->>'run_id') NOT BETWEEN 1 AND 256) OR jsonb_typeof(r.observation->'body_sha256') IS DISTINCT FROM 'string' OR r.observation->>'body_sha256'!~'^[a-f0-9]{64}$')))
 THEN RAISE insufficient_privilege USING MESSAGE='missing foreign or malformed complete meeting processing custody; recovery quarantined';END IF;
 -- Exact frozen027 retained joins. Never call its current/expiry/context getters
 -- under recovery's role or turn historical custody into renewed permission.
 IF EXISTS(SELECT 1 FROM oracle2.migration_admission_revocations_v1 x LEFT JOIN oracle2.migration_admissions_v1 a USING(admission_id) WHERE a.admission_id IS NULL)
 OR EXISTS(SELECT 1 FROM oracle2.migration_inventory_entries_v1 e LEFT JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.inventory_id IS NULL)
 OR EXISTS(SELECT 1 FROM oracle2.migration_heads_v1 h LEFT JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.inventory_id IS NULL)
 OR EXISTS(SELECT 1 FROM oracle2.migration_source_versions_v1 v LEFT JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) WHERE b.binding_id IS NULL)
 OR EXISTS(SELECT 1 FROM oracle2.migration_inventories_v1 i LEFT JOIN oracle2.migration_admissions_v1 a USING(admission_id)
 WHERE i.workspace_id=ANY(workspaces) AND(a.admission_id IS NULL OR(i.workspace_id,i.origin_system,i.principal_id,i.descriptor_sha256,i.source_scope_sha256,i.source_program_sha256) IS DISTINCT FROM(a.workspace_id,a.origin_system,a.principal_id,a.descriptor_sha256,a.source_scope_sha256,a.source_program_sha256)
 OR i.inventory_sha256 IS DISTINCT FROM encode(sha256(i.inventory_bytes),'hex') OR i.declared_count<>(SELECT count(*) FROM oracle2.migration_inventory_entries_v1 e WHERE e.inventory_id=i.inventory_id)
 OR NOT EXISTS(SELECT 1 FROM oracle2.migration_heads_v1 h WHERE h.inventory_id=i.inventory_id)
 OR (SELECT array_agg(e.sequence ORDER BY e.sequence) FROM oracle2.migration_inventory_entries_v1 e WHERE e.inventory_id=i.inventory_id) IS DISTINCT FROM(SELECT array_agg(n ORDER BY n) FROM generate_series(1,i.declared_count) n)))
 OR EXISTS(SELECT 1 FROM oracle2.migration_heads_v1 h JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.workspace_id=ANY(workspaces) AND(h.read_sequence<>i.declared_count OR h.revision<>(SELECT count(*) FROM oracle2.migration_events_v1 e WHERE e.inventory_id=i.inventory_id)))
 OR EXISTS(SELECT 1 FROM oracle2.migration_source_versions_v1 v JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) WHERE b.workspace_id=ANY(workspaces) AND v.original_identity_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('original_sha256',v.original_sha256,'byte_count',v.byte_count,'media_type',v.media_type)),'UTF8')),'hex'))
 OR EXISTS(SELECT 1 FROM oracle2.migration_intents_v1 t LEFT JOIN oracle2.migration_inventories_v1 i USING(inventory_id)
 LEFT JOIN oracle2.migration_inventory_entries_v1 e ON(e.inventory_id,e.sequence)=(t.inventory_id,t.entry_sequence)
 LEFT JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) LEFT JOIN oracle2.migration_source_versions_v1 v USING(version_id)
 WHERE(i.workspace_id=ANY(workspaces) OR b.workspace_id=ANY(workspaces) OR i.inventory_id IS NULL) AND(i.inventory_id IS NULL OR e.inventory_id IS NULL OR b.binding_id IS NULL OR v.version_id IS NULL
 OR(b.workspace_id,b.origin_system,b.legacy_kind,b.legacy_id) IS DISTINCT FROM(i.workspace_id,i.origin_system,e.legacy_kind,e.legacy_id)
 OR(v.binding_id,v.original_sha256,v.byte_count,v.media_type) IS DISTINCT FROM(t.binding_id,e.original_sha256,e.byte_count,e.media_type)
 OR e.disposition NOT IN('message-eligible','document-current-capture-eligible')
 OR t.reuses_intent_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM oracle2.migration_intents_v1 base WHERE base.intent_id=t.reuses_intent_id AND base.binding_id=t.binding_id AND base.reuses_intent_id IS NULL AND base.intake_idempotency IS NOT NULL)))
 OR EXISTS(SELECT 1 FROM oracle2.migration_events_v1 e LEFT JOIN oracle2.migration_inventories_v1 i USING(inventory_id) LEFT JOIN oracle2.migration_admissions_v1 a ON a.admission_id=e.admission_id
 WHERE e.workspace_id=ANY(workspaces) AND(i.inventory_id IS NULL OR a.admission_id IS NULL OR(e.workspace_id,e.origin_system,e.principal_id) IS DISTINCT FROM(i.workspace_id,i.origin_system,i.principal_id)
 OR(e.workspace_id,e.origin_system,e.principal_id) IS DISTINCT FROM(a.workspace_id,a.origin_system,a.principal_id) OR e.command_sha256 IS DISTINCT FROM encode(sha256(e.command_bytes),'hex') OR e.sequence>(SELECT revision FROM oracle2.migration_heads_v1 h WHERE h.inventory_id=e.inventory_id)))
 OR EXISTS(SELECT 1 FROM oracle2.migration_intent_observations_v1 o LEFT JOIN oracle2.migration_intents_v1 t USING(intent_id)
 LEFT JOIN oracle2.migration_inventories_v1 i ON i.inventory_id=t.inventory_id LEFT JOIN oracle2.migration_events_v1 e ON e.event_id=o.event_id
 LEFT JOIN oracle2.migration_source_bindings_v1 b ON b.binding_id=t.binding_id LEFT JOIN oracle2.migration_source_versions_v1 v ON v.version_id=t.version_id
 WHERE(i.workspace_id=ANY(workspaces) OR i.inventory_id IS NULL) AND(t.intent_id IS NULL OR i.inventory_id IS NULL OR e.event_id IS NULL OR b.binding_id IS NULL OR v.version_id IS NULL
 OR e.inventory_id<>t.inventory_id OR e.kind<>'intake-observed' OR e.payload->>'intent_id' IS DISTINCT FROM t.intent_id::text OR e.payload->>'state' IS DISTINCT FROM o.state
 OR o.state NOT IN('UNKNOWN','custody-observed','metadata-only')
 OR o.state IN('custody-observed','metadata-only') AND(o.reservation_id IS NULL OR NOT EXISTS(
 SELECT 1 FROM oracle2.source_intake_reservations_v1 r JOIN oracle2.source_original_revisions src ON(src.workspace_id,src.source_id,src.revision)=(r.workspace_id,r.source_id,r.revision)
 WHERE r.reservation_id=o.reservation_id AND r.workspace_id=i.workspace_id AND r.principal_id=t.intake_principal_id AND r.finalized_at IS NOT NULL
 AND(r.source_id,r.revision,r.original_sha256,r.byte_count,r.media_type)=(o.source_uuid,o.target_revision,v.original_sha256,v.byte_count,v.media_type)
 AND(src.original_sha256,src.byte_count,src.custody_locator_seal_sha256)=(v.original_sha256,v.byte_count::bigint,r.custody_seal_sha256)
 AND(o.original_sha256,o.byte_count)=(v.original_sha256,v.byte_count) AND b.target_source_uuid=r.source_id))
 OR o.state='metadata-only' AND t.reuses_intent_id IS NULL OR o.state='custody-observed' AND t.reuses_intent_id IS NOT NULL))

 OR EXISTS(SELECT 1 FROM oracle2.migration_intent_observations_v1 o
 JOIN oracle2.migration_intents_v1 t USING(intent_id) JOIN oracle2.migration_inventories_v1 i USING(inventory_id)
 JOIN oracle2.migration_source_bindings_v1 b ON b.binding_id=t.binding_id JOIN oracle2.migration_source_versions_v1 v ON v.version_id=t.version_id
 LEFT JOIN oracle2.migration_intents_v1 base ON base.intent_id=coalesce(t.reuses_intent_id,t.intent_id)
 LEFT JOIN oracle2.source_intake_reservations_v1 r ON r.reservation_id=o.reservation_id
 WHERE i.workspace_id=ANY(workspaces) AND(
 o.reservation_id IS NULL AND(o.source_uuid IS NOT NULL OR o.target_revision IS NOT NULL OR o.original_sha256 IS NOT NULL OR o.byte_count IS NOT NULL)
 OR o.reservation_id IS NOT NULL AND(r.reservation_id IS NULL OR base.intent_id IS NULL
 OR(r.workspace_id,r.principal_id,r.idempotency_key,r.source_id,r.byte_count,r.media_type,r.expected_head) IS DISTINCT FROM(i.workspace_id,t.intake_principal_id,base.intake_idempotency,o.source_uuid,v.byte_count::bigint,v.media_type,base.expected_target_head)
 OR b.target_source_uuid IS DISTINCT FROM r.source_id
 OR r.request_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('expected_head',base.expected_target_head,
 'intake',jsonb_build_object('source_id',CASE WHEN base.expected_target_head=0 THEN NULL ELSE b.target_source_uuid END,
 'filename','legacy_'||b.legacy_id::text||CASE WHEN v.media_type='application/pdf' THEN '.pdf' ELSE '.txt' END,
 'media_type',v.media_type,'byte_count',v.byte_count,'caller_deadline',oracle2._migration_iso_v1(base.original_dispatch_deadline)))),'UTF8')),'hex'))))
 OR EXISTS(SELECT 1 FROM oracle2.migration_resolution_events_v1 x LEFT JOIN oracle2.migration_events_v1 f ON f.event_id=x.failure_event
 LEFT JOIN oracle2.migration_intent_observations_v1 o ON o.observation_id=x.evidence_receipt LEFT JOIN oracle2.migration_events_v1 e ON e.event_id=x.event_id
 LEFT JOIN oracle2.migration_events_v1 proof ON proof.event_id=o.event_id LEFT JOIN oracle2.migration_intents_v1 t ON t.intent_id=o.intent_id
 WHERE(e.workspace_id=ANY(workspaces) OR f.workspace_id=ANY(workspaces) OR e.event_id IS NULL) AND(f.event_id IS NULL OR o.observation_id IS NULL OR e.event_id IS NULL OR proof.event_id IS NULL OR t.intent_id IS NULL
 OR f.kind<>'intake-observed' OR f.payload->>'state'<>'UNKNOWN' OR f.payload->>'intent_id' IS DISTINCT FROM t.intent_id::text
 OR o.state NOT IN('custody-observed','metadata-only') OR f.sequence>=proof.sequence OR proof.sequence>=e.sequence OR e.kind<>'resolution-observed'
 OR(f.workspace_id,f.origin_system,f.principal_id,f.inventory_id) IS DISTINCT FROM(e.workspace_id,e.origin_system,e.principal_id,e.inventory_id)
 OR e.inventory_id<>t.inventory_id OR e.payload->>'failure_event' IS DISTINCT FROM x.failure_event::text OR e.payload->>'evidence_receipt' IS DISTINCT FROM x.evidence_receipt::text))
 OR EXISTS(SELECT 1 FROM oracle2.migration_citation_bindings_v1 c LEFT JOIN oracle2.migration_inventories_v1 i USING(inventory_id)
 LEFT JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) LEFT JOIN oracle2.migration_intent_observations_v1 o USING(observation_id)
 LEFT JOIN oracle2.migration_intents_v1 t ON t.intent_id=o.intent_id
 WHERE(i.workspace_id=ANY(workspaces) OR b.workspace_id=ANY(workspaces) OR i.inventory_id IS NULL) AND(i.inventory_id IS NULL OR b.binding_id IS NULL OR o.observation_id IS NULL OR t.intent_id IS NULL
 OR(i.workspace_id,i.origin_system) IS DISTINCT FROM(b.workspace_id,b.origin_system) OR(t.inventory_id,t.binding_id) IS DISTINCT FROM(c.inventory_id,c.binding_id)
 OR c.legacy_citation_id IS DISTINCT FROM b.legacy_kind||':'||b.legacy_id::text OR(c.target_revision,c.original_sha256) IS DISTINCT FROM(o.target_revision,o.original_sha256)
 OR o.state NOT IN('custody-observed','metadata-only')))
 OR EXISTS(SELECT 1 FROM oracle2.migration_capture_observations_v1 c LEFT JOIN oracle2.migration_inventories_v1 i USING(inventory_id)
 LEFT JOIN oracle2.migration_inventory_entries_v1 e ON(e.inventory_id,e.sequence)=(c.inventory_id,c.entry_sequence)
 WHERE c.workspace_id=ANY(workspaces) AND(i.inventory_id IS NULL OR e.inventory_id IS NULL OR(c.workspace_id,c.origin_system,c.legacy_kind,c.legacy_id,c.original_sha256,c.byte_count,c.media_type,c.permission_sha256,c.metadata_sha256)
 IS DISTINCT FROM(i.workspace_id,i.origin_system,e.legacy_kind,e.legacy_id,e.original_sha256,e.byte_count,e.media_type,e.permission_sha256,e.metadata_sha256)
 OR e.disposition<>'document-current-capture-eligible' OR c.producer_program_sha256<>i.source_program_sha256
 OR(c.capture->>'capture_id',c.capture->>'legacy_id',c.capture->>'source_projection_sha256',c.capture->>'producer_profile_sha256',c.capture->>'auth_subject',c.capture->>'etag',c.capture->>'original_sha256',c.capture->>'byte_count',c.capture->>'media_type',c.capture->>'private_receipt_key',c.capture->>'receipt_sha256',c.capture->>'receipt_byte_count')
 IS DISTINCT FROM(c.capture_id::text,c.legacy_id::text,c.source_projection_sha256,c.producer_profile_sha256,c.auth_subject::text,c.etag,c.original_sha256,c.byte_count::text,c.media_type,c.private_receipt_key,c.receipt_sha256,c.receipt_byte_count::text)
 OR c.private_receipt_key IS DISTINCT FROM 'legacy-original-captures/'||c.workspace_id::text||'/'||c.capture_id::text||'/receipt.json'
 OR c.capture->>'private_body_key' IS DISTINCT FROM 'legacy-original-captures/'||c.workspace_id::text||'/'||c.capture_id::text||'/original.pdf'
 OR c.capture->'historical_original_proven' IS DISTINCT FROM 'false'::jsonb OR c.capture->'qualification' IS DISTINCT FROM 'false'::jsonb OR c.capture->'company_acceptance' IS DISTINCT FROM 'false'::jsonb
 OR c.receipt_sha256 IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(c.capture-ARRAY['private_receipt_key','receipt_sha256','receipt_byte_count']),'UTF8')),'hex')
 OR c.receipt_byte_count IS DISTINCT FROM octet_length(convert_to(oracle2._replacement_metadata_json(c.capture-ARRAY['private_receipt_key','receipt_sha256','receipt_byte_count']),'UTF8'))
 OR (c.capture->>'original_deadline')::timestamptz IS DISTINCT FROM c.original_deadline))
 THEN RAISE insufficient_privilege USING MESSAGE='missing foreign malformed or unknown complete migration custody; recovery quarantined';END IF;
 SELECT coalesce(jsonb_agg(value ORDER BY oracle2._replacement_metadata_json(value)),'[]') INTO result FROM (
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_final_fetch_claims_v1','record_kind','final-fetch-claim','record_key',jsonb_build_object('schema_version',1,'fetch_claim_id',t.fetch_claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.original_effect_deadline) value FROM oracle2.meeting_capture_final_fetch_claims_v1 t WHERE t.workspace_id=ANY(workspaces) AND t.original_effect_deadline<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_final_fetch_claims_v1','record_kind','final-fetch-claim','record_key',jsonb_build_object('schema_version',1,'fetch_claim_id',t.fetch_claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',NULL::timestamptz) value FROM oracle2.meeting_capture_final_fetch_claims_v1 t WHERE t.workspace_id=ANY(workspaces) AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_processing_links_v1 r WHERE r.fetch_claim_id=t.fetch_claim_id)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_enqueue_claims_v1','record_kind','enqueue-claim','record_key',jsonb_build_object('schema_version',1,'claim_id',t.claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.original_effect_deadline) value FROM oracle2.meeting_capture_enqueue_claims_v1 t WHERE t.workspace_id=ANY(workspaces) AND t.original_effect_deadline<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_enqueue_claims_v1','record_kind','enqueue-claim','record_key',jsonb_build_object('schema_version',1,'claim_id',t.claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',NULL::timestamptz) value FROM oracle2.meeting_capture_enqueue_claims_v1 t WHERE t.workspace_id=ANY(workspaces) AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_enqueue_receipts_v1 r WHERE r.claim_id=t.claim_id AND r.observation->>'kind'='enqueue-observed')
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_revocations_v1','record_kind','capture-admission-revocation','record_key',jsonb_build_object('schema_version',1,'revocation_id',t.revocation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-revoked','effective_at',t.revoked_at) value FROM oracle2.meeting_capture_revocations_v1 t JOIN oracle2.meeting_capture_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participant_epoch_revocations_v1','record_kind','participant-epoch-revocation','record_key',jsonb_build_object('schema_version',1,'revocation_id',t.revocation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','participant-epoch-revoked','effective_at',t.revoked_at) value FROM oracle2.meeting_participant_epoch_revocations_v1 t JOIN oracle2.meeting_participant_epochs_v1 own USING(epoch_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_final_mapping_revocations_v1','record_kind','final-mapping-revocation','record_key',jsonb_build_object('schema_version',1,'revocation_id',t.revocation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','final-mapping-revoked','effective_at',t.revoked_at) value FROM oracle2.meeting_final_mapping_revocations_v1 t JOIN oracle2.meeting_final_mappings_v1 own USING(mapping_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_create_stop_relation_revocations_v1','record_kind','create-stop-relation-revocation','record_key',jsonb_build_object('schema_version',1,'revocation_id',t.revocation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','create-stop-relation-revoked','effective_at',t.revoked_at) value FROM oracle2.meeting_create_stop_relation_revocations_v1 t JOIN oracle2.meeting_create_stop_relations_v1 own USING(mapping_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_revocations_v1','record_kind','participation-admission-revocation','record_key',jsonb_build_object('schema_version',1,'revocation_id',t.revocation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-revoked','effective_at',t.revoked_at) value FROM oracle2.meeting_participation_revocations_v1 t JOIN oracle2.meeting_participation_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_admission_revocations_v1','record_kind','research-admission-revocation','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-revoked','effective_at',t.revoked_at) value FROM oracle2.research_admission_revocations_v1 t JOIN oracle2.research_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','question_effect_admission_revocations_v1','record_kind','question-admission-revocation','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-revoked','effective_at',t.revoked_at) value FROM oracle2.question_effect_admission_revocations_v1 t JOIN oracle2.question_effect_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','recommendation_action_revocations_v1','record_kind','recommendation-admission-revocation','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-revoked','effective_at',t.revoked_at) value FROM oracle2.recommendation_action_revocations_v1 t JOIN oracle2.recommendation_action_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_admissions_v1','record_kind','capture-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-expired','effective_at',least(t.expires_at,t.original_horizon)) value FROM oracle2.meeting_capture_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND least(t.expires_at,t.original_horizon)<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_admissions_v1','record_kind','capture-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-not-effective','effective_at',t.valid_from) value FROM oracle2.meeting_capture_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.valid_from>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_admissions_v1','record_kind','participation-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-expired','effective_at',least(t.expires_at,t.original_horizon)) value FROM oracle2.meeting_participation_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND least(t.expires_at,t.original_horizon)<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_admissions_v1','record_kind','participation-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-not-effective','effective_at',t.valid_from) value FROM oracle2.meeting_participation_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.valid_from>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_admissions_v1','record_kind','research-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-expired','effective_at',least(t.expires_at,t.original_horizon)) value FROM oracle2.research_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND least(t.expires_at,t.original_horizon)<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_admissions_v1','record_kind','research-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-not-effective','effective_at',t.issued_at) value FROM oracle2.research_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.issued_at>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','question_effect_admissions_v1','record_kind','question-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-expired','effective_at',least(t.expires_at,t.original_horizon)) value FROM oracle2.question_effect_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND least(t.expires_at,t.original_horizon)<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','question_effect_admissions_v1','record_kind','question-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-not-effective','effective_at',t.issued_at) value FROM oracle2.question_effect_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.issued_at>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','recommendation_action_admissions_v1','record_kind','recommendation-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-expired','effective_at',least(t.expires_at,t.original_horizon)) value FROM oracle2.recommendation_action_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND least(t.expires_at,t.original_horizon)<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','recommendation_action_admissions_v1','record_kind','recommendation-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-not-effective','effective_at',t.issued_at) value FROM oracle2.recommendation_action_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.issued_at>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_admissions_v1','record_kind','capture-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',CASE WHEN t.worker_effect='capture-leave' THEN t.stop_until ELSE t.capture_until END) value FROM oracle2.meeting_capture_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND ((t.worker_effect='capture-leave' AND t.stop_until<=observed_at) OR (t.worker_effect='capture-create' AND t.capture_until<=observed_at))
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_heads_v1','record_kind','capture-head','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'meeting_id',t.meeting_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','capture-closed','effective_at',CASE WHEN t.capture_until<=observed_at THEN t.capture_until ELSE NULL END) value FROM oracle2.meeting_capture_heads_v1 t  WHERE t.workspace_id=ANY(workspaces) AND (NOT t.capture_open OR t.capture_until<=observed_at OR t.state IN('cancelled','failed','capture_ended'))
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_heads_v1','record_kind','capture-head','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'meeting_id',t.meeting_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-UNKNOWN','effective_at',NULL::timestamptz) value FROM oracle2.meeting_capture_heads_v1 t  WHERE t.workspace_id=ANY(workspaces) AND (t.state IN('UNKNOWN','capture_status_unknown') OR t.stop_state='UNKNOWN')
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_worker_claims_v1','record_kind','capture-worker-claim','record_key',jsonb_build_object('schema_version',1,'claim_id',t.claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.original_deadline) value FROM oracle2.meeting_capture_worker_claims_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.original_deadline<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_capture_worker_claims_v1','record_kind','capture-worker-claim','record_key',jsonb_build_object('schema_version',1,'claim_id',t.claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',t.created_at) value FROM oracle2.meeting_capture_worker_claims_v1 t  WHERE t.workspace_id=ANY(workspaces) AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_capture_worker_receipts_v1 r WHERE r.claim_id=t.claim_id)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_normalization_claims_v1','record_kind','normalization-claim','record_key',jsonb_build_object('schema_version',1,'claim_id',t.claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',least(t.original_deadline,t.original_processing_horizon)) value FROM oracle2.meeting_normalization_claims_v1 t  WHERE t.workspace_id=ANY(workspaces) AND least(t.original_deadline,t.original_processing_horizon)<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_normalization_claims_v1','record_kind','normalization-claim','record_key',jsonb_build_object('schema_version',1,'claim_id',t.claim_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',NULL::timestamptz) value FROM oracle2.meeting_normalization_claims_v1 t  WHERE t.workspace_id=ANY(workspaces) AND NOT EXISTS(SELECT 1 FROM oracle2.meeting_normalization_intakes_v1 r WHERE r.claim_id=t.claim_id)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_heads_v1','record_kind','participation-head','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'meeting_id',t.meeting_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','host-disabled','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_heads_v1 t  WHERE t.workspace_id=ANY(workspaces) AND NOT t.enabled
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_heads_v1','record_kind','participation-head','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'meeting_id',t.meeting_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','proactive-disabled','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_heads_v1 t  WHERE t.workspace_id=ANY(workspaces) AND NOT t.proactive_enabled
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_heads_v1','record_kind','participation-head','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'meeting_id',t.meeting_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','proactive-limit-reached','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_heads_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.proactive_count>=t.max_proactive
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_heads_v1','record_kind','participation-head','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'meeting_id',t.meeting_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','proactive-cooldown','effective_at',t.last_proactive_at+make_interval(secs=>t.cooldown_seconds)) value FROM oracle2.meeting_participation_heads_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.last_proactive_at+make_interval(secs=>t.cooldown_seconds)>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_heads_v1','record_kind','participation-head','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'meeting_id',t.meeting_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','active-intent-present','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_heads_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.active_intent_id IS NOT NULL
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_observations_v1','record_kind','participant-observation','record_key',jsonb_build_object('schema_version',1,'observation_id',t.observation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.valid_until) value FROM oracle2.meeting_participation_observations_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.valid_until<=observed_at AND (EXISTS(SELECT 1 FROM oracle2.meeting_participation_audience_heads_v1 h WHERE h.observation_id=t.observation_id) OR EXISTS(SELECT 1 FROM oracle2.meeting_participation_intents_v1 i JOIN oracle2.meeting_participation_heads_v1 h ON(h.workspace_id,h.meeting_id)=(i.workspace_id,i.meeting_id) JOIN oracle2.meeting_participation_delivery_heads_v1 delivery ON delivery.intent_id=i.intent_id WHERE i.observation_id=t.observation_id AND i.generation=h.generation AND delivery.state IN('intent','inflight','UNKNOWN')))
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_delivery_heads_v1','record_kind','participation-delivery','record_key',jsonb_build_object('schema_version',1,'intent_id',t.intent_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-UNKNOWN','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_delivery_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_delivery_heads_v1 t JOIN oracle2.meeting_participation_intents_v1 own USING(intent_id) WHERE own.workspace_id=ANY(workspaces) AND t.state='UNKNOWN'
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_delivery_heads_v1','record_kind','participation-delivery','record_key',jsonb_build_object('schema_version',1,'intent_id',t.intent_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_delivery_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_delivery_heads_v1 t JOIN oracle2.meeting_participation_intents_v1 own USING(intent_id) WHERE own.workspace_id=ANY(workspaces) AND t.state='inflight'
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_delivery_heads_v1','record_kind','participation-delivery','record_key',jsonb_build_object('schema_version',1,'intent_id',t.intent_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-suppressed','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_delivery_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_delivery_heads_v1 t JOIN oracle2.meeting_participation_intents_v1 own USING(intent_id) WHERE own.workspace_id=ANY(workspaces) AND t.state='suppressed'
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_delivery_heads_v1','record_kind','participation-delivery','record_key',jsonb_build_object('schema_version',1,'intent_id',t.intent_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','effect-already-observed','effective_at',(SELECT e.created_at FROM oracle2.meeting_participation_delivery_events_v1 e WHERE e.event_id=t.last_event_id)) value FROM oracle2.meeting_participation_delivery_heads_v1 t JOIN oracle2.meeting_participation_intents_v1 own USING(intent_id) WHERE own.workspace_id=ANY(workspaces) AND t.state='provider-response-observed'
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','meeting_participation_delivery_heads_v1','record_kind','participation-delivery','record_key',jsonb_build_object('schema_version',1,'intent_id',t.intent_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.claim_deadline) value FROM oracle2.meeting_participation_delivery_heads_v1 t JOIN oracle2.meeting_participation_intents_v1 own USING(intent_id) WHERE own.workspace_id=ANY(workspaces) AND t.state IN('inflight','UNKNOWN') AND t.claim_deadline<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_registrations_v1','record_kind','research-registration','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'source_id',t.source_id,'revision',t.revision),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','source-disabled','effective_at',t.registered_at) value FROM oracle2.research_registrations_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.revision=(SELECT max(r.revision) FROM oracle2.research_registrations_v1 r WHERE(r.workspace_id,r.source_id)=(t.workspace_id,t.source_id)) AND t.definition->'enabled'='false'::jsonb
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_registrations_v1','record_kind','research-registration','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'source_id',t.source_id,'revision',t.revision),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','source-rights-unconfirmed','effective_at',t.registered_at) value FROM oracle2.research_registrations_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.revision=(SELECT max(r.revision) FROM oracle2.research_registrations_v1 r WHERE(r.workspace_id,r.source_id)=(t.workspace_id,t.source_id)) AND t.definition->>'access'<>'public' AND t.definition->'rights_confirmed'='false'::jsonb
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_registrations_v1','record_kind','research-registration','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'source_id',t.source_id,'revision',t.revision),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','registration-superseded','effective_at',(SELECT min(r.registered_at) FROM oracle2.research_registrations_v1 r WHERE(r.workspace_id,r.source_id)=(t.workspace_id,t.source_id) AND r.revision>t.revision)) value FROM oracle2.research_registrations_v1 t  WHERE t.workspace_id=ANY(workspaces) AND NOT t.revision=(SELECT max(r.revision) FROM oracle2.research_registrations_v1 r WHERE(r.workspace_id,r.source_id)=(t.workspace_id,t.source_id))
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_state_v1','record_kind','research-state','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'source_id',t.source_id,'revision',t.revision),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','refresh-exhausted','effective_at',NULL::timestamptz) value FROM oracle2.research_state_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.exhausted
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_state_v1','record_kind','research-state','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'source_id',t.source_id,'revision',t.revision),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','refresh-not-due','effective_at',t.next_due) value FROM oracle2.research_state_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.next_due>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_state_v1','record_kind','research-state','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'source_id',t.source_id,'revision',t.revision),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','active-intent-present','effective_at',NULL::timestamptz) value FROM oracle2.research_state_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.inflight IS NOT NULL
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_run_heads_v1','record_kind','research-run','record_key',jsonb_build_object('schema_version',1,'run_id',t.run_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-UNKNOWN','effective_at',(SELECT max(e.recorded_at) FROM oracle2.research_events_v1 e WHERE e.run_id=t.run_id)) value FROM oracle2.research_run_heads_v1 t JOIN oracle2.research_attempts_v1 own USING(run_id) WHERE own.workspace_id=ANY(workspaces) AND t.state='UNKNOWN'
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_run_heads_v1','record_kind','research-run','record_key',jsonb_build_object('schema_version',1,'run_id',t.run_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',(SELECT max(e.recorded_at) FROM oracle2.research_events_v1 e WHERE e.run_id=t.run_id)) value FROM oracle2.research_run_heads_v1 t JOIN oracle2.research_attempts_v1 own USING(run_id) WHERE own.workspace_id=ANY(workspaces) AND t.state='INFLIGHT'
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_run_heads_v1','record_kind','research-run','record_key',jsonb_build_object('schema_version',1,'run_id',t.run_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','effect-already-observed','effective_at',(SELECT max(e.recorded_at) FROM oracle2.research_events_v1 e WHERE e.run_id=t.run_id)) value FROM oracle2.research_run_heads_v1 t JOIN oracle2.research_attempts_v1 own USING(run_id) WHERE own.workspace_id=ANY(workspaces) AND t.state='observed'
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','research_run_heads_v1','record_kind','research-run','record_key',jsonb_build_object('schema_version',1,'run_id',t.run_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.claim_deadline) value FROM oracle2.research_run_heads_v1 t JOIN oracle2.research_attempts_v1 own USING(run_id) WHERE own.workspace_id=ANY(workspaces) AND t.state IN('INFLIGHT','UNKNOWN') AND t.claim_deadline<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','question_effect_operations_v1','record_kind','question-operation','record_key',jsonb_build_object('schema_version',1,'operation_id',t.operation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.operation_deadline) value FROM oracle2.question_effect_operations_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.operation_deadline<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','question_effect_operations_v1','record_kind','question-operation','record_key',jsonb_build_object('schema_version',1,'operation_id',t.operation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',t.created_at) value FROM oracle2.question_effect_operations_v1 t  WHERE t.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','recommendation_registrations_v1','record_kind','recommendation-registration','record_key',jsonb_build_object('schema_version',1,'workspace_id',t.workspace_id,'artifact_id',t.artifact_id,'version',t.version),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','parent-model-superseded','effective_at',(SELECT min(r.recorded_at) FROM oracle2.processing_model_revisions_v1 r WHERE(r.workspace_id,r.artifact_id)=(t.workspace_id,t.parent_model) AND r.version>t.parent_version)) value FROM oracle2.recommendation_registrations_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.parent_version<(SELECT max(r.version) FROM oracle2.processing_model_revisions_v1 r WHERE(r.workspace_id,r.artifact_id)=(t.workspace_id,t.parent_model))
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_admissions_v1','record_kind','migration-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-expired','effective_at',least(t.expires_at,t.original_horizon)) value FROM oracle2.migration_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND least(t.expires_at,t.original_horizon)<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_admissions_v1','record_kind','migration-admission','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-not-effective','effective_at',t.valid_from) value FROM oracle2.migration_admissions_v1 t  WHERE t.workspace_id=ANY(workspaces) AND t.valid_from>observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_admission_revocations_v1','record_kind','migration-admission-revocation','record_key',jsonb_build_object('schema_version',1,'admission_id',t.admission_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','admission-revoked','effective_at',t.revoked_at) value FROM oracle2.migration_admission_revocations_v1 t JOIN oracle2.migration_admissions_v1 a USING(admission_id) WHERE a.workspace_id=ANY(workspaces)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_intents_v1','record_kind','migration-intent','record_key',jsonb_build_object('schema_version',1,'intent_id',t.intent_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','operation-window-ended','effective_at',t.original_dispatch_deadline) value FROM oracle2.migration_intents_v1 t JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.workspace_id=ANY(workspaces) AND t.original_dispatch_deadline<=observed_at
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_intents_v1','record_kind','migration-intent','record_key',jsonb_build_object('schema_version',1,'intent_id',t.intent_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',NULL::timestamptz) value FROM oracle2.migration_intents_v1 t JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.workspace_id=ANY(workspaces) AND(NOT EXISTS(SELECT 1 FROM oracle2.migration_intent_observations_v1 o WHERE o.intent_id=t.intent_id AND o.state IN('custody-observed','metadata-only')) OR EXISTS(SELECT 1 FROM oracle2.migration_intent_observations_v1 bad WHERE bad.intent_id=t.intent_id AND bad.state='UNKNOWN' AND NOT EXISTS(SELECT 1 FROM oracle2.migration_resolution_events_v1 fixed WHERE fixed.failure_event=bad.event_id)))
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_intent_observations_v1','record_kind','migration-observation','record_key',jsonb_build_object('schema_version',1,'observation_id',t.observation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','possible-effect-unreconciled','effective_at',NULL::timestamptz) value FROM oracle2.migration_intent_observations_v1 t JOIN oracle2.migration_intents_v1 claim USING(intent_id) JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.workspace_id=ANY(workspaces) AND t.state='UNKNOWN' AND NOT EXISTS(SELECT 1 FROM oracle2.migration_resolution_events_v1 fixed WHERE fixed.failure_event=t.event_id)
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_inventory_entries_v1','record_kind','migration-entry','record_key',jsonb_build_object('schema_version',1,'inventory_id',t.inventory_id,'sequence',t.sequence),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason',CASE t.disposition WHEN 'permission-unavailable' THEN 'source-rights-unconfirmed' WHEN 'document-custody-unavailable' THEN 'legacy-document-custody-unavailable' WHEN 'source-bytes-unavailable' THEN 'legacy-source-bytes-unavailable' WHEN 'missing' THEN 'legacy-original-missing' WHEN 'storage-read-unavailable' THEN 'legacy-storage-read-unavailable' WHEN 'object-precondition-failed' THEN 'legacy-object-precondition-failed' WHEN 'capture-incomplete' THEN 'legacy-capture-incomplete' WHEN 'unsupported-document-media' THEN 'legacy-unsupported-document-media' WHEN 'capture-coverage-gap' THEN 'legacy-capture-coverage-gap' END,'effective_at',NULL::timestamptz) value FROM oracle2.migration_inventory_entries_v1 t JOIN oracle2.migration_inventories_v1 i USING(inventory_id) WHERE i.workspace_id=ANY(workspaces) AND t.disposition IN('permission-unavailable','document-custody-unavailable','source-bytes-unavailable','missing','storage-read-unavailable','object-precondition-failed','capture-incomplete','unsupported-document-media','capture-coverage-gap')
 UNION
SELECT jsonb_build_object('schema_version',1,'owner_table','migration_citation_bindings_v1','record_kind','migration-citation','record_key',jsonb_build_object('schema_version',1,'inventory_id',t.inventory_id,'legacy_citation_id',t.legacy_citation_id),'record_row_sha256',encode(sha256(convert_to(oracle2._replacement_metadata_json(to_jsonb(t)),'UTF8')),'hex'),'reason','legacy-citation-revision-changed','effective_at',NULL::timestamptz) value FROM oracle2.migration_citation_bindings_v1 t JOIN oracle2.migration_inventories_v1 i USING(inventory_id) JOIN oracle2.migration_source_bindings_v1 b USING(binding_id) WHERE i.workspace_id=ANY(workspaces) AND t.target_revision IS DISTINCT FROM(SELECT current_source.revision FROM oracle2.sources current_source WHERE current_source.workspace_id=i.workspace_id AND current_source.source_id=b.target_source_uuid)
 ) actual_closed_denials;
 IF jsonb_array_length(result)>32768 THEN RAISE program_limit_exceeded USING MESSAGE='complete operational denial quota exceeded';END IF;
 RETURN result;
END $f$;

CREATE FUNCTION oracle2._recovery_context_v1(wanted uuid,deadline timestamptz)
 RETURNS oracle2.recovery_operation_admissions_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE admission_row oracle2.recovery_operation_admissions_v1;r oracle2.hosting_role_runtime_admissions;
 d jsonb;b jsonb;profile jsonb;physical jsonb;cap record;f oid;login oid;owner_oid oid;scope jsonb;appointment_row oracle2.appointments;seen uuid[];bound timestamptz;rooted boolean;own_scope boolean:=false;phase_scope text;actual_catalog_sha256 text;
BEGIN
 IF deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() OR deadline>clock_timestamp()+interval '30 seconds'
 OR NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl) THEN RAISE insufficient_privilege USING MESSAGE='original finite TLS recovery window required';END IF;
 SELECT oid INTO login FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin AND NOT(rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication);
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF login IS NULL OR owner_oid IS DISTINCT FROM(SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR current_setting('role') NOT IN('none',SESSION_USER::text)
 OR EXISTS(SELECT 1 FROM pg_roles x WHERE x.oid<>login AND(pg_has_role(login,x.oid,'MEMBER') OR pg_has_role(login,x.oid,'SET') OR pg_has_role(login,x.oid,'USAGE')))
 THEN RAISE insufficient_privilege USING MESSAGE='distinct direct own recovery LOGIN required';END IF;
 -- Canonicalization must not authenticate its own changed implementation.
 -- Exact retained014 source body pin, checked BEFORE _recovery_json_v1.
 IF NOT EXISTS(SELECT 1 FROM pg_proc canonical WHERE canonical.oid=to_regprocedure('oracle2._replacement_metadata_json(jsonb)')
 AND canonical.proowner=owner_oid AND canonical.prosecdef AND canonical.provolatile='i'
 AND canonical.proconfig=ARRAY['search_path=pg_catalog, oracle2']
 AND encode(sha256(convert_to(canonical.prosrc,'UTF8')),'hex')='339e50e2b6636942c90dcdc8b2d0d3ad6c643e68bac3627959df6f840a62b8f2') THEN
 RAISE insufficient_privilege USING MESSAGE='exact independent retained canonicalizer body required';END IF;
 SELECT count(*) INTO f FROM oracle2.recovery_operation_admissions_v1 x WHERE x.operation_id=wanted AND x.role_name=SESSION_USER
 AND x.issued_at<=clock_timestamp() AND x.expires_at>clock_timestamp()
 AND NOT EXISTS(SELECT 1 FROM oracle2.recovery_admission_revocations_v1 v WHERE v.admission_id=x.admission_id);
 IF f<>1 THEN RAISE insufficient_privilege USING MESSAGE='unambiguous independently installed recovery purpose required';END IF;
 SELECT * INTO admission_row FROM oracle2.recovery_operation_admissions_v1 x WHERE x.operation_id=wanted AND x.role_name=SESSION_USER
 AND x.issued_at<=clock_timestamp() AND x.expires_at>clock_timestamp()
 AND NOT EXISTS(SELECT 1 FROM oracle2.recovery_admission_revocations_v1 v WHERE v.admission_id=x.admission_id) FOR SHARE;
 SELECT * INTO r FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 IF r.role_name IS NULL OR (r.runtime_hash,r.registry_hash) IS DISTINCT FROM(admission_row.runtime_hash,admission_row.registry_hash)
 OR NOT isfinite(r.expires_at) OR r.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='current independently installed recovery runtime required';END IF;
 d:=oracle2._recovery_json_v1(admission_row.descriptor_bytes,65536);
 IF NOT d ?& ARRAY['schema_version','protocol','kind','operation_id','original_capture_operation_id','backup_manifest_sha256','source_head','runtime_sha256','registry_sha256','workspace_ids','scope_coverage','current_control_source','purpose_bindings','databases','covered_ledgers','private_roots','migrations','accepted_graphs','archive_limits','issued_at','expires_at','original_horizon'] OR d-ARRAY['schema_version','protocol','kind','operation_id','original_capture_operation_id','backup_manifest_sha256','source_head','runtime_sha256','registry_sha256','workspace_ids','scope_coverage','current_control_source','purpose_bindings','databases','covered_ledgers','private_roots','migrations','accepted_graphs','archive_limits','issued_at','expires_at','original_horizon']<>'{}'::jsonb OR d->>'protocol'<>'oracle-replacement-recovery-descriptor-v1' OR d->>'operation_id'<>wanted::text
 OR d->>'runtime_sha256'<>admission_row.runtime_hash OR d->>'registry_sha256'<>admission_row.registry_hash
 OR d->>'kind' NOT IN('capture','restore') OR (d->>'issued_at')::timestamptz>clock_timestamp()
 OR (d->>'expires_at')::timestamptz<clock_timestamp()
 OR (d->>'original_horizon')::timestamptz<admission_row.original_horizon
 OR jsonb_typeof(d->'workspace_ids')<>'array' OR jsonb_array_length(d->'workspace_ids') NOT BETWEEN 1 AND 256
 OR jsonb_typeof(d->'scope_coverage')<>'array' OR jsonb_array_length(d->'scope_coverage') NOT BETWEEN 1 AND 1024 THEN RAISE insufficient_privilege;END IF;

 -- New operations require exact installed027 tail; retained26 is descriptive
 -- backup metadata ONLY, never a current capture/restore admission.
 IF jsonb_typeof(d->'migrations') IS DISTINCT FROM 'array'
 OR (SELECT array_agg(m->>'name' ORDER BY ordinal) FROM jsonb_array_elements(d->'migrations') WITH ORDINALITY x(m,ordinal)) IS DISTINCT FROM ARRAY['001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql','006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql','008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql','010_hosting_job_permissions.sql','011_hosting_source_processing_permissions.sql','012_processing_compiler_capabilities.sql','013_processing_purpose_permissions.sql','014_replacement_source_custody.sql','017_processing_model_history.sql','018_original_review_reading_input.sql','019_employee_conversations.sql','020_meeting_capture.sql','021_meeting_participation.sql','022_consolidated_answer_delivery.sql','023_maintained_research.sql','024_question_effects.sql','025_recommendation_actions.sql','026_operational_recovery.sql','027_legacy_migration.sql']::text[]
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(d->'migrations') m WHERE NOT(m?&ARRAY['schema_version','name','sha256']) OR m-ARRAY['schema_version','name','sha256']<>'{}'::jsonb OR m->'schema_version' IS DISTINCT FROM '1'::jsonb OR jsonb_typeof(m->'name') IS DISTINCT FROM 'string' OR jsonb_typeof(m->'sha256') IS DISTINCT FROM 'string' OR m->>'sha256'!~'^[a-f0-9]{64}$')
 OR EXISTS(SELECT 1 FROM(VALUES ('020_meeting_capture.sql','79c6d0c28c91c337d88ab3680de7c83deb79700d4cd69441107479fc5a23ed7e'),('021_meeting_participation.sql','959a77553849616eee1d7b4eba4ed8a3bc146aaa432b7e0e2ca8d83ff17b2f7c'),('023_maintained_research.sql','4cec9e3111318197566a77099d234fac2229e02805d88f82a26053194b36cc66'),('024_question_effects.sql','e6f956c47842e81237f24519f27f06ea644b265b086309753e412b6c5eaf91aa'),('025_recommendation_actions.sql','59471db44be8c27ba2c3564d2732fb5081b5d79ceff8d0d53591855f0ac51b2b'),('027_legacy_migration.sql','034d60c201b100acf22d0eafac5a9b623dfc14b053140a514d57da048f091143')) pin(name,sha) WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(d->'migrations') m WHERE m->>'name'=pin.name AND m->>'sha256'=pin.sha))
 THEN RAISE insufficient_privilege USING MESSAGE='complete exact current027 operational tail and owner source pins required';END IF;
 IF admission_row.postrestore_binding_bytes IS NULL AND (SELECT count(*) FROM jsonb_array_elements(d->'purpose_bindings') x WHERE x->>'phase_authority'=admission_row.phase_authority AND x->>'principal_id'=admission_row.principal_id::text AND x->'sql_identity'->>'session_role'=SESSION_USER::text)<>1 THEN RAISE insufficient_privilege;END IF;
 IF admission_row.postrestore_binding_bytes IS NULL THEN
 IF admission_row.scope_coverage IS DISTINCT FROM d->'scope_coverage' THEN RAISE insufficient_privilege;END IF;
 SELECT value->'sql_identity' INTO b FROM jsonb_array_elements(d->'purpose_bindings') WHERE value->>'phase_authority'=admission_row.phase_authority;
 IF (b->>'system_identifier',b->>'database_oid',b->>'database_name') IS DISTINCT FROM
 (d->'current_control_source'->>'system_identifier',d->'current_control_source'->>'database_oid',d->'current_control_source'->>'database_name') THEN RAISE insufficient_privilege;END IF;
 ELSE
 IF admission_row.phase_authority NOT IN('deny-only-target','observe') OR d->>'kind'<>'restore' THEN RAISE insufficient_privilege;END IF;
 profile:=oracle2._recovery_json_v1(admission_row.postrestore_binding_bytes,65536);
 IF NOT profile ?& ARRAY['schema_version','protocol','restore_operation_id','original_capture_operation_id','backup_manifest_sha256','descriptor_sha256','master_phase','master_claimed_at','original_phase_deadline','target_physical_identity','actual_postrestore_catalog_sha256','purpose_bindings','issuer_actor','reviewer_actor','issued_at','expires_at','original_horizon'] OR profile-ARRAY['schema_version','protocol','restore_operation_id','original_capture_operation_id','backup_manifest_sha256','descriptor_sha256','master_phase','master_claimed_at','original_phase_deadline','target_physical_identity','actual_postrestore_catalog_sha256','purpose_bindings','issuer_actor','reviewer_actor','issued_at','expires_at','original_horizon']<>'{}'::jsonb OR profile->>'protocol'<>'oracle-replacement-post-restore-binding-v1' OR profile->>'restore_operation_id'<>wanted::text
 OR profile->>'original_capture_operation_id'<>d->>'original_capture_operation_id' OR profile->>'backup_manifest_sha256'<>d->>'backup_manifest_sha256'
 OR profile->>'descriptor_sha256'<>admission_row.descriptor_sha256 OR profile->>'master_phase'<>'restore'
 OR (profile->>'expires_at')::timestamptz<clock_timestamp() OR (profile->>'issued_at')::timestamptz>clock_timestamp()
 OR (profile->>'original_phase_deadline')::timestamptz<admission_row.original_horizon
 OR (profile->>'expires_at')::timestamptz>(profile->>'original_phase_deadline')::timestamptz
 OR (SELECT count(*) FROM jsonb_array_elements(profile->'purpose_bindings') x WHERE x->>'phase_authority'=admission_row.phase_authority AND x->>'principal_id'=admission_row.principal_id::text AND x->'sql_identity'->>'session_role'=SESSION_USER::text)<>1 THEN RAISE insufficient_privilege;END IF;
 SELECT value->'sql_identity' INTO b FROM jsonb_array_elements(profile->'purpose_bindings') WHERE value->>'phase_authority'=admission_row.phase_authority;
 IF (b->>'system_identifier',b->>'database_oid',b->>'database_name') IS DISTINCT FROM
 (profile->'target_physical_identity'->>'system_identifier',profile->'target_physical_identity'->>'database_oid',profile->'target_physical_identity'->>'database_name') THEN RAISE insufficient_privilege;END IF;
 END IF;
 IF b IS NULL OR b->>'system_identifier'<>(SELECT system_identifier::text FROM pg_control_system())
 OR (b->>'database_oid')::oid<>(SELECT oid FROM pg_database WHERE datname=current_database()) OR b->>'database_name'<>current_database()
 OR b->>'database_owner'<>(SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()) THEN RAISE insufficient_privilege USING MESSAGE='actual pinned recovery physical plane required';END IF;
 -- SAME existing recovery_catalog_fingerprint_v1 expression/digest semantics.
 -- Source equality is tested; not migration-file SHA metadata or native DDL hash.
 -- BEGIN SAME_RECOVERY_CATALOG_SQL_V1
 SELECT encode(sha256(convert_to(oracle2._replacement_metadata_json((
SELECT jsonb_build_object(
 'tables',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',c.oid,'name',c.relname,'owner',c.relowner,'kind',c.relkind,'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'acl',c.relacl::text,
 'columns',(SELECT coalesce(jsonb_agg(jsonb_build_object('number',a.attnum,'name',a.attname,'type',a.atttypid,'modifier',a.atttypmod,'not_null',a.attnotnull,'acl',a.attacl::text,'default',pg_get_expr(ad.adbin,ad.adrelid)) ORDER BY a.attnum),'[]') FROM pg_attribute a LEFT JOIN pg_attrdef ad ON(ad.adrelid,ad.adnum)=(a.attrelid,a.attnum) WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
 'constraints',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',k.oid,'name',k.conname,'definition',pg_get_constraintdef(k.oid),'validated',k.convalidated) ORDER BY k.oid),'[]') FROM pg_constraint k WHERE k.conrelid=c.oid),
 'triggers',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',t.oid,'definition',pg_get_triggerdef(t.oid),'enabled',t.tgenabled) ORDER BY t.oid),'[]') FROM pg_trigger t WHERE t.tgrelid=c.oid),
 'policies',(SELECT coalesce(jsonb_agg(to_jsonb(p) ORDER BY p.oid),'[]') FROM pg_policy p WHERE p.polrelid=c.oid)) ORDER BY c.oid),'[]') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='oracle2'),
 'functions',(SELECT coalesce(jsonb_agg(jsonb_build_object('oid',p.oid,'name',p.proname,'owner',p.proowner,'kind',p.prokind,'language',p.prolang,'arguments',p.proargtypes::text,'result',p.prorettype,'security_definer',p.prosecdef,'config',p.proconfig,'volatility',p.provolatile,'acl',p.proacl::text,'body_sha256',encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')) ORDER BY p.oid),'[]') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='oracle2'),
 'enums',(SELECT coalesce(jsonb_agg(jsonb_build_object('type',t.oid,'label',e.enumlabel,'order',e.enumsortorder) ORDER BY t.oid,e.enumsortorder),'[]') FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace JOIN pg_enum e ON e.enumtypid=t.oid WHERE n.nspname='oracle2'))
 )),'UTF8')),'hex') INTO actual_catalog_sha256;
 -- END SAME_RECOVERY_CATALOG_SQL_V1
 IF actual_catalog_sha256 IS DISTINCT FROM b->>'schema_catalog_sha256' THEN
 RAISE insufficient_privilege USING MESSAGE='actual complete recovery catalog differs from installed binding';END IF;
 IF admission_row.postrestore_binding_bytes IS NOT NULL THEN
 -- This quarantined variant admits only the two independently installed target
 -- recovery LOGINs. Every role referenced by restored operational/source
 -- admissions must remain NOLOGIN/passwordless; no password value is returned.
 IF EXISTS(WITH application_roles AS (
 SELECT role_name FROM oracle2.hosting_role_runtime_admissions
 UNION SELECT role_name FROM oracle2.hosting_role_source_admissions
 UNION SELECT role_name FROM oracle2.hosting_request_principal_admissions
 UNION SELECT role_name FROM oracle2.hosting_original_source_admissions
 UNION SELECT role_name FROM oracle2.hosting_original_population_admissions_v1
 UNION SELECT role_name FROM oracle2.processing_model_admissions_v1
 UNION SELECT role_name FROM oracle2.conversation_processing_admissions_v1
 UNION SELECT role_name FROM oracle2.meeting_capture_admissions_v1
 UNION SELECT role_name FROM oracle2.meeting_participation_admissions_v1
 UNION SELECT role_name FROM oracle2.research_admissions_v1
 UNION SELECT role_name FROM oracle2.question_effect_admissions_v1
 UNION SELECT role_name FROM oracle2.recommendation_action_admissions_v1
 UNION SELECT role_name FROM oracle2.migration_admissions_v1
 UNION SELECT role_name FROM oracle2.recovery_operation_admissions_v1)
 SELECT 1 FROM application_roles app JOIN pg_authid old ON old.rolname=app.role_name
 WHERE (old.rolcanlogin OR old.rolpassword IS NOT NULL)
 AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(profile->'purpose_bindings') target WHERE target->'sql_identity'->>'session_role'=old.rolname::text))
 THEN RAISE insufficient_privilege USING MESSAGE='restored application LOGIN/password forbidden; target remains quarantined';END IF;
 END IF;
 -- Unknown successor custody/once tables must not disappear from an old
 -- static union, even if someone supplies a new aggregate catalog pin.
 IF (SELECT array_agg(c.relname::text ORDER BY c.relname) FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
 WHERE ns.nspname='oracle2' AND c.relkind IN('r','p') AND
 (c.relname LIKE 'meeting_capture_%' OR c.relname LIKE 'meeting_participant_%' OR c.relname LIKE 'meeting_final_%'
 OR c.relname LIKE 'meeting_create_stop_%' OR c.relname LIKE 'meeting_normalization_%' OR c.relname LIKE 'meeting_participation_%'
 OR c.relname LIKE 'research_%' OR c.relname LIKE 'question_effect_%' OR c.relname LIKE 'recommendation_%' OR c.relname LIKE 'migration_%')) IS DISTINCT FROM ARRAY['meeting_capture_admissions_v1','meeting_capture_enqueue_claims_v1','meeting_capture_enqueue_receipts_v1','meeting_capture_events_v1','meeting_capture_final_fetch_claims_v1','meeting_capture_heads_v1','meeting_capture_processing_links_v1','meeting_capture_revocations_v1','meeting_capture_worker_claims_v1','meeting_capture_worker_receipts_v1','meeting_create_stop_relation_revocations_v1','meeting_create_stop_relations_v1','meeting_final_mapping_revocations_v1','meeting_final_mappings_v1','meeting_normalization_claims_v1','meeting_normalization_intakes_v1','meeting_participant_epoch_revocations_v1','meeting_participant_epochs_v1','meeting_participation_admissions_v1','meeting_participation_audience_heads_v1','meeting_participation_delivery_events_v1','meeting_participation_delivery_heads_v1','meeting_participation_events_v1','meeting_participation_heads_v1','meeting_participation_intents_v1','meeting_participation_observations_v1','meeting_participation_revocations_v1','migration_admission_revocations_v1','migration_admissions_v1','migration_capture_observations_v1','migration_citation_bindings_v1','migration_events_v1','migration_heads_v1','migration_intent_observations_v1','migration_intents_v1','migration_inventories_v1','migration_inventory_entries_v1','migration_resolution_events_v1','migration_source_bindings_v1','migration_source_versions_v1','question_effect_admission_revocations_v1','question_effect_admissions_v1','question_effect_observations_v1','question_effect_operations_v1','recommendation_action_admissions_v1','recommendation_action_events_v1','recommendation_action_revocations_v1','recommendation_registrations_v1','recommendation_repairs_v1','research_admission_revocations_v1','research_admissions_v1','research_attempts_v1','research_events_v1','research_registrations_v1','research_run_heads_v1','research_state_v1']::text[] THEN
 RAISE insufficient_privilege USING MESSAGE='operational source table union changed; recovery quarantined';END IF;
 -- Complete installed function body/OID/owner/ACL tuple, no wildcard exclusions.
 IF (SELECT count(*) FROM jsonb_object_keys(admission_row.catalog))<>8 THEN RAISE insufficient_privilege;END IF;
 FOR cap IN SELECT * FROM jsonb_each(admission_row.catalog) LOOP
 IF NOT cap.value ?& ARRAY['oid','body_sha256'] OR cap.value-ARRAY['oid','body_sha256']<>'{}'::jsonb OR cap.key NOT IN('oracle2.recovery_current_v1(uuid,timestamptz)','oracle2.claim_recovery_phase_v1(uuid,text,timestamptz)','oracle2.observe_recovery_phase_v1(uuid,text,bytea,timestamptz)','oracle2.import_recovery_denials_v1(uuid,bytea,timestamptz)','oracle2._recovery_context_v1(uuid,timestamptz)','oracle2._recovery_json_v1(bytea,integer)','oracle2._recovery_census_v1(uuid,timestamptz)','oracle2._recovery_operational_denials_v1(uuid[],timestamptz)') THEN RAISE insufficient_privilege;END IF;
 f:=to_regprocedure(cap.key);
 IF NOT EXISTS(SELECT 1 FROM pg_proc x WHERE x.oid=f AND x.oid=(cap.value->>'oid')::oid AND x.proowner=owner_oid AND x.prosecdef
 AND x.proconfig=ARRAY['search_path=pg_catalog, oracle2'] AND encode(sha256(convert_to(x.prosrc,'UTF8')),'hex')=cap.value->>'body_sha256') THEN RAISE insufficient_privilege USING MESSAGE='current exact recovery function catalog denied';END IF;
 IF cap.key LIKE 'oracle2._recovery%' THEN
 IF EXISTS(SELECT 1 FROM pg_proc x CROSS JOIN LATERAL aclexplode(coalesce(x.proacl,acldefault('f',x.proowner))) g WHERE x.oid=f AND g.grantee<>x.proowner) THEN RAISE insufficient_privilege;END IF;
 ELSE
 IF (cap.key='oracle2.recovery_current_v1(uuid,timestamptz)' AND NOT EXISTS(SELECT 1 FROM pg_proc x CROSS JOIN LATERAL aclexplode(coalesce(x.proacl,acldefault('f',x.proowner))) g WHERE x.oid=f AND g.grantee=login AND g.privilege_type='EXECUTE' AND NOT g.is_grantable))
 OR EXISTS(SELECT 1 FROM pg_proc x CROSS JOIN LATERAL aclexplode(coalesce(x.proacl,acldefault('f',x.proowner))) g LEFT JOIN pg_roles gr ON gr.oid=g.grantee WHERE x.oid=f AND g.grantee<>x.proowner AND(g.is_grantable OR gr.oid IS NULL OR NOT gr.rolcanlogin OR gr.rolsuper OR gr.rolbypassrls OR gr.rolcreatedb OR gr.rolcreaterole OR gr.rolreplication OR EXISTS(SELECT 1 FROM pg_roles other WHERE other.oid<>gr.oid AND(pg_has_role(gr.oid,other.oid,'MEMBER') OR pg_has_role(gr.oid,other.oid,'SET') OR pg_has_role(gr.oid,other.oid,'USAGE'))))) THEN RAISE insufficient_privilege;END IF;
 END IF;
 END LOOP;
 phase_scope:=CASE admission_row.phase_authority WHEN 'capture' THEN 'recovery-capture:' WHEN 'current-denials' THEN 'recovery-deny-census:' WHEN 'deny-only-target' THEN 'recovery-deny-import:' ELSE 'recovery-observe:' END||wanted::text;
 bound:=least(deadline,admission_row.expires_at,admission_row.original_horizon,r.expires_at,(d->>'expires_at')::timestamptz);
 FOR scope IN SELECT value FROM jsonb_array_elements(admission_row.scope_coverage) LOOP
 SELECT * INTO appointment_row FROM oracle2.appointments WHERE appointment_id=(scope->>'appointment_id')::uuid FOR SHARE;
 IF appointment_row.appointment_id IS NULL OR appointment_row.workspace_id<>(scope->>'workspace_id')::uuid OR appointment_row.scope<>scope->>'scope' THEN RAISE insufficient_privilege;END IF;
 IF appointment_row.actor_id=admission_row.principal_id AND appointment_row.scope=phase_scope THEN own_scope:=true;END IF;
 seen:='{}';rooted:=false;
 LOOP
 IF appointment_row.appointment_id=ANY(seen) OR cardinality(seen)>=16 OR appointment_row.workspace_id<>(scope->>'workspace_id')::uuid OR appointment_row.revoked_at IS NOT NULL OR appointment_row.expires_at IS NOT NULL AND(NOT isfinite(appointment_row.expires_at) OR appointment_row.expires_at<=clock_timestamp()) THEN RAISE insufficient_privilege USING MESSAGE='actual current rooted recovery coverage required';END IF;
 seen:=array_append(seen,appointment_row.appointment_id);bound:=least(bound,coalesce(appointment_row.expires_at,bound));
 IF appointment_row.parent_id IS NULL THEN rooted:=appointment_row.scope='root' AND appointment_row.appointment_id=(scope->>'root_appointment_id')::uuid;EXIT;END IF;
 SELECT parent.* INTO appointment_row FROM oracle2.appointments parent WHERE parent.appointment_id=appointment_row.parent_id AND parent.actor_id=appointment_row.granted_by AND parent.workspace_id=(scope->>'workspace_id')::uuid AND parent.scope IN(scope->>'scope','root') FOR SHARE;
 IF appointment_row.appointment_id IS NULL THEN RAISE insufficient_privilege;END IF;
 END LOOP;
 IF NOT rooted THEN RAISE insufficient_privilege;END IF;
 END LOOP;
 IF NOT own_scope OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(d->'workspace_ids') w WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(admission_row.scope_coverage) s JOIN oracle2.appointments p ON p.appointment_id=(s->>'appointment_id')::uuid WHERE s->>'workspace_id'=w AND p.actor_id=admission_row.principal_id AND p.scope=phase_scope)) THEN RAISE insufficient_privilege;END IF;
 IF admission_row.phase_authority='capture' AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(d->'workspace_ids') w WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(admission_row.scope_coverage) s JOIN oracle2.appointments p ON p.appointment_id=(s->>'appointment_id')::uuid WHERE s->>'workspace_id'=w AND p.actor_id=admission_row.principal_id AND p.scope='recovery-deny-census:'||wanted::text)) THEN RAISE insufficient_privilege;END IF;
 admission_row.expires_at:=bound;
 IF admission_row.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege;END IF;
 RETURN admission_row;
END $f$;

-- This private getter reads actual current SQL, never a supplied census/hash.
-- All declared policy tables are SHARE locked in the same bounded transaction;
-- caller closes it before private bytes/network or any target mutation.
CREATE FUNCTION oracle2._recovery_census_v1(wanted uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.recovery_operation_admissions_v1;d jsonb;workspaces uuid[];table_name text;query text;n bigint;h text;
 watermarks jsonb:='[]';sources jsonb;withdrawals jsonb;denials jsonb;result jsonb;stamp timestamptz:=clock_timestamp();snapshot text;owner_oid oid;
BEGIN
 a:=oracle2._recovery_context_v1(wanted,deadline);d:=convert_from(a.descriptor_bytes,'UTF8')::jsonb;
 IF a.phase_authority NOT IN('capture','current-denials') OR a.postrestore_binding_bytes IS NOT NULL THEN RAISE insufficient_privilege;END IF;
 SELECT array_agg(value::uuid ORDER BY value) INTO workspaces FROM jsonb_array_elements_text(d->'workspace_ids');
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 LOCK TABLE oracle2.appointments,oracle2.artifact_invalidations,oracle2.conversation_processing_admissions_v1,oracle2.hosting_original_population_admissions_v1,oracle2.hosting_original_source_admissions,oracle2.hosting_request_principal_admissions,oracle2.hosting_role_runtime_admissions,oracle2.hosting_role_source_admissions,oracle2.meeting_capture_admissions_v1,oracle2.meeting_capture_enqueue_claims_v1,oracle2.meeting_capture_enqueue_receipts_v1,oracle2.meeting_capture_events_v1,oracle2.meeting_capture_final_fetch_claims_v1,oracle2.meeting_capture_heads_v1,oracle2.meeting_capture_processing_links_v1,oracle2.meeting_capture_revocations_v1,oracle2.meeting_capture_worker_claims_v1,oracle2.meeting_capture_worker_receipts_v1,oracle2.meeting_create_stop_relation_revocations_v1,oracle2.meeting_create_stop_relations_v1,oracle2.meeting_final_mapping_revocations_v1,oracle2.meeting_final_mappings_v1,oracle2.meeting_normalization_claims_v1,oracle2.meeting_normalization_intakes_v1,oracle2.meeting_participant_epoch_revocations_v1,oracle2.meeting_participant_epochs_v1,oracle2.meeting_participation_admissions_v1,oracle2.meeting_participation_audience_heads_v1,oracle2.meeting_participation_delivery_events_v1,oracle2.meeting_participation_delivery_heads_v1,oracle2.meeting_participation_events_v1,oracle2.meeting_participation_heads_v1,oracle2.meeting_participation_intents_v1,oracle2.meeting_participation_observations_v1,oracle2.meeting_participation_revocations_v1,oracle2.migration_admission_revocations_v1,oracle2.migration_admissions_v1,oracle2.migration_capture_observations_v1,oracle2.migration_citation_bindings_v1,oracle2.migration_events_v1,oracle2.migration_heads_v1,oracle2.migration_intent_observations_v1,oracle2.migration_intents_v1,oracle2.migration_inventories_v1,oracle2.migration_inventory_entries_v1,oracle2.migration_resolution_events_v1,oracle2.migration_source_bindings_v1,oracle2.migration_source_versions_v1,oracle2.original_source_population_members_v1,oracle2.original_source_populations_v1,oracle2.processing_model_admission_revocations_v1,oracle2.processing_model_admissions_v1,oracle2.question_effect_admission_revocations_v1,oracle2.question_effect_admissions_v1,oracle2.question_effect_observations_v1,oracle2.question_effect_operations_v1,oracle2.recommendation_action_admissions_v1,oracle2.recommendation_action_events_v1,oracle2.recommendation_action_revocations_v1,oracle2.recommendation_registrations_v1,oracle2.recommendation_repairs_v1,oracle2.recovery_admission_revocations_v1,oracle2.recovery_operation_admissions_v1,oracle2.research_admission_revocations_v1,oracle2.research_admissions_v1,oracle2.research_attempts_v1,oracle2.research_events_v1,oracle2.research_registrations_v1,oracle2.research_run_heads_v1,oracle2.research_state_v1,oracle2.source_blocks,oracle2.source_original_revisions,oracle2.source_original_withdrawals_v1,oracle2.source_reading_qualifications,oracle2.sources IN SHARE MODE;
 snapshot:=txid_current_snapshot()::text;
 FOREACH table_name IN ARRAY ARRAY['appointments','artifact_invalidations','conversation_processing_admissions_v1','hosting_original_population_admissions_v1','hosting_original_source_admissions','hosting_request_principal_admissions','hosting_role_runtime_admissions','hosting_role_source_admissions','meeting_capture_admissions_v1','meeting_capture_enqueue_claims_v1','meeting_capture_enqueue_receipts_v1','meeting_capture_events_v1','meeting_capture_final_fetch_claims_v1','meeting_capture_heads_v1','meeting_capture_processing_links_v1','meeting_capture_revocations_v1','meeting_capture_worker_claims_v1','meeting_capture_worker_receipts_v1','meeting_create_stop_relation_revocations_v1','meeting_create_stop_relations_v1','meeting_final_mapping_revocations_v1','meeting_final_mappings_v1','meeting_normalization_claims_v1','meeting_normalization_intakes_v1','meeting_participant_epoch_revocations_v1','meeting_participant_epochs_v1','meeting_participation_admissions_v1','meeting_participation_audience_heads_v1','meeting_participation_delivery_events_v1','meeting_participation_delivery_heads_v1','meeting_participation_events_v1','meeting_participation_heads_v1','meeting_participation_intents_v1','meeting_participation_observations_v1','meeting_participation_revocations_v1','migration_admission_revocations_v1','migration_admissions_v1','migration_capture_observations_v1','migration_citation_bindings_v1','migration_events_v1','migration_heads_v1','migration_intent_observations_v1','migration_intents_v1','migration_inventories_v1','migration_inventory_entries_v1','migration_resolution_events_v1','migration_source_bindings_v1','migration_source_versions_v1','original_source_population_members_v1','original_source_populations_v1','processing_model_admission_revocations_v1','processing_model_admissions_v1','question_effect_admission_revocations_v1','question_effect_admissions_v1','question_effect_observations_v1','question_effect_operations_v1','recommendation_action_admissions_v1','recommendation_action_events_v1','recommendation_action_revocations_v1','recommendation_registrations_v1','recommendation_repairs_v1','recovery_admission_revocations_v1','recovery_operation_admissions_v1','research_admission_revocations_v1','research_admissions_v1','research_attempts_v1','research_events_v1','research_registrations_v1','research_run_heads_v1','research_state_v1','source_blocks','source_original_revisions','source_original_withdrawals_v1','source_reading_qualifications','sources'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace WHERE ns.nspname='oracle2' AND c.relname=table_name AND c.relkind='r' AND c.relowner=owner_oid) THEN RAISE insufficient_privilege USING MESSAGE='complete exact current policy owners required';END IF;
 CASE table_name
 WHEN 'appointments' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.appointments t WHERE t.workspace_id=ANY($1)';
 WHEN 'artifact_invalidations' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.artifact_invalidations t WHERE t.workspace_id=ANY($1)';
 WHEN 'conversation_processing_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.conversation_processing_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'hosting_original_population_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.hosting_original_population_admissions_v1 t JOIN oracle2.original_source_populations_v1 own ON own.population_id=t.population_id WHERE own.workspace_id=ANY($1)';
 WHEN 'hosting_original_source_admissions' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.hosting_original_source_admissions t WHERE t.workspace_id=ANY($1)';
 WHEN 'hosting_request_principal_admissions' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.hosting_request_principal_admissions t WHERE t.workspace_id=ANY($1)';
 WHEN 'hosting_role_runtime_admissions' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.hosting_role_runtime_admissions t WHERE EXISTS(SELECT 1 FROM oracle2.hosting_role_source_admissions own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.hosting_request_principal_admissions own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.processing_model_admissions_v1 own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.recovery_operation_admissions_v1 own CROSS JOIN LATERAL jsonb_array_elements_text(convert_from(own.descriptor_bytes,''UTF8'')::jsonb->''workspace_ids'') w WHERE own.role_name=t.role_name AND w::uuid=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.meeting_capture_admissions_v1 own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.meeting_participation_admissions_v1 own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.research_admissions_v1 own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.question_effect_admissions_v1 own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.recommendation_action_admissions_v1 own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1)) OR EXISTS(SELECT 1 FROM oracle2.migration_admissions_v1 own WHERE own.role_name=t.role_name AND own.workspace_id=ANY($1))';
 WHEN 'hosting_role_source_admissions' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.hosting_role_source_admissions t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_final_fetch_claims_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_final_fetch_claims_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_processing_links_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_processing_links_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_enqueue_claims_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_enqueue_claims_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_enqueue_receipts_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_enqueue_receipts_v1 t JOIN oracle2.meeting_capture_enqueue_claims_v1 own USING(claim_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_capture_events_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_events_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_heads_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_heads_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_revocations_v1 t JOIN oracle2.meeting_capture_admissions_v1 own ON own.admission_id=t.admission_id WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_capture_worker_claims_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_worker_claims_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_capture_worker_receipts_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_capture_worker_receipts_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_create_stop_relation_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_create_stop_relation_revocations_v1 t JOIN oracle2.meeting_create_stop_relations_v1 own ON own.mapping_id=t.mapping_id WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_create_stop_relations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_create_stop_relations_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_final_mapping_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_final_mapping_revocations_v1 t JOIN oracle2.meeting_final_mappings_v1 own ON own.mapping_id=t.mapping_id WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_final_mappings_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_final_mappings_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_normalization_claims_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_normalization_claims_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_normalization_intakes_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_normalization_intakes_v1 t JOIN oracle2.meeting_normalization_claims_v1 own ON own.claim_id=t.claim_id WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_participant_epoch_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participant_epoch_revocations_v1 t JOIN oracle2.meeting_participant_epochs_v1 own ON own.epoch_id=t.epoch_id WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_participant_epochs_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participant_epochs_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_participation_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_participation_audience_heads_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_audience_heads_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_participation_delivery_events_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_delivery_events_v1 t JOIN oracle2.meeting_participation_intents_v1 own ON own.intent_id=t.intent_id WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_participation_delivery_heads_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_delivery_heads_v1 t JOIN oracle2.meeting_participation_intents_v1 own ON own.intent_id=t.intent_id WHERE own.workspace_id=ANY($1)';
 WHEN 'meeting_participation_events_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_events_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_participation_heads_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_heads_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_participation_intents_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_intents_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_participation_observations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_observations_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'meeting_participation_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.meeting_participation_revocations_v1 t JOIN oracle2.meeting_participation_admissions_v1 own ON own.admission_id=t.admission_id WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_admission_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_admission_revocations_v1 t JOIN oracle2.migration_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'migration_capture_observations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_capture_observations_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'migration_citation_bindings_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_citation_bindings_v1 t JOIN oracle2.migration_inventories_v1 own USING(inventory_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_events_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_events_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'migration_heads_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_heads_v1 t JOIN oracle2.migration_inventories_v1 own USING(inventory_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_intent_observations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_intent_observations_v1 t JOIN oracle2.migration_intents_v1 i USING(intent_id) JOIN oracle2.migration_inventories_v1 own USING(inventory_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_intents_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_intents_v1 t JOIN oracle2.migration_inventories_v1 own USING(inventory_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_inventories_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_inventories_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'migration_inventory_entries_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_inventory_entries_v1 t JOIN oracle2.migration_inventories_v1 own USING(inventory_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_resolution_events_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_resolution_events_v1 t JOIN oracle2.migration_events_v1 own ON own.event_id=t.event_id WHERE own.workspace_id=ANY($1)';
 WHEN 'migration_source_bindings_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_source_bindings_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'migration_source_versions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.migration_source_versions_v1 t JOIN oracle2.migration_source_bindings_v1 own USING(binding_id) WHERE own.workspace_id=ANY($1)';
 WHEN 'original_source_population_members_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.original_source_population_members_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'original_source_populations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.original_source_populations_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'processing_model_admission_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.processing_model_admission_revocations_v1 t JOIN oracle2.processing_model_admissions_v1 own ON own.admission_id=t.admission_id WHERE own.workspace_id=ANY($1)';
 WHEN 'processing_model_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.processing_model_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'question_effect_admission_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.question_effect_admission_revocations_v1 t JOIN oracle2.question_effect_admissions_v1 own ON own.admission_id=t.admission_id WHERE own.workspace_id=ANY($1)';
 WHEN 'question_effect_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.question_effect_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'question_effect_observations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.question_effect_observations_v1 t JOIN oracle2.question_effect_operations_v1 own ON own.operation_id=t.operation_id WHERE own.workspace_id=ANY($1)';
 WHEN 'question_effect_operations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.question_effect_operations_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'recommendation_action_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.recommendation_action_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'recommendation_action_events_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.recommendation_action_events_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'recommendation_action_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.recommendation_action_revocations_v1 t JOIN oracle2.recommendation_action_admissions_v1 own ON own.admission_id=t.admission_id WHERE own.workspace_id=ANY($1)';
 WHEN 'recommendation_registrations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.recommendation_registrations_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'recommendation_repairs_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.recommendation_repairs_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'recovery_admission_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.recovery_admission_revocations_v1 t JOIN oracle2.recovery_operation_admissions_v1 own USING(admission_id) WHERE EXISTS(SELECT 1 FROM jsonb_array_elements_text(convert_from(own.descriptor_bytes,''UTF8'')::jsonb->''workspace_ids'') w WHERE w::uuid=ANY($1))';
 WHEN 'recovery_operation_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.recovery_operation_admissions_v1 t WHERE EXISTS(SELECT 1 FROM jsonb_array_elements_text(convert_from(t.descriptor_bytes,''UTF8'')::jsonb->''workspace_ids'') w WHERE w::uuid=ANY($1))';
 WHEN 'research_admission_revocations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.research_admission_revocations_v1 t JOIN oracle2.research_admissions_v1 own ON own.admission_id=t.admission_id WHERE own.workspace_id=ANY($1)';
 WHEN 'research_admissions_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.research_admissions_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'research_attempts_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.research_attempts_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'research_events_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.research_events_v1 t JOIN oracle2.research_attempts_v1 own ON own.run_id=t.run_id WHERE own.workspace_id=ANY($1)';
 WHEN 'research_registrations_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.research_registrations_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'research_run_heads_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.research_run_heads_v1 t JOIN oracle2.research_attempts_v1 own ON own.run_id=t.run_id WHERE own.workspace_id=ANY($1)';
 WHEN 'research_state_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.research_state_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'source_blocks' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.source_blocks t WHERE t.workspace_id=ANY($1)';
 WHEN 'source_original_revisions' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.source_original_revisions t WHERE t.workspace_id=ANY($1)';
 WHEN 'source_original_withdrawals_v1' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.source_original_withdrawals_v1 t WHERE t.workspace_id=ANY($1)';
 WHEN 'source_reading_qualifications' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.source_reading_qualifications t WHERE t.workspace_id=ANY($1)';
 WHEN 'sources' THEN query:='SELECT to_jsonb(t) AS row FROM oracle2.sources t WHERE t.workspace_id=ANY($1)';
 ELSE RAISE insufficient_privilege USING MESSAGE='unknown current policy table refused';END CASE;
 -- Whole-row digests only: no private payload/question text crosses this boundary.
 EXECUTE 'SELECT count(*),encode(sha256(convert_to(coalesce(string_agg(row_sha,'''' ORDER BY row_sha),''''),''UTF8'')),''hex'') FROM (SELECT encode(sha256(convert_to(oracle2._replacement_metadata_json(row),''UTF8'')),''hex'') row_sha FROM ('||query||') owned LIMIT 100001) bounded'
 INTO n,h USING workspaces;
 IF n>100000 THEN RAISE program_limit_exceeded USING MESSAGE='complete census table bound exceeded';END IF;
 watermarks:=watermarks||jsonb_build_array(jsonb_build_object('schema_version',1,'table',table_name,'row_count',n,'canonical_rows_sha256',h));
 END LOOP;
 SELECT coalesce(jsonb_agg(jsonb_build_object('schema_version',1,'workspace_id',s.workspace_id,'source_id',s.source_id,'current_revision',s.revision,
 'original_sha256',o.original_sha256,'status',s.status,'denied',s.status NOT IN('draft','confirmed') OR o.source_id IS NULL OR q.source_id IS NULL OR EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 w WHERE(w.workspace_id,w.source_id,w.revision)=(s.workspace_id,s.source_id,s.revision))) ORDER BY s.workspace_id,s.source_id),'[]')
 INTO sources FROM oracle2.sources s LEFT JOIN oracle2.source_original_revisions o ON(o.workspace_id,o.source_id,o.revision)=(s.workspace_id,s.source_id,s.revision)
 LEFT JOIN oracle2.source_reading_qualifications q ON(q.workspace_id,q.source_id,q.revision)=(s.workspace_id,s.source_id,s.revision)
 WHERE s.workspace_id=ANY(workspaces);
 IF jsonb_array_length(sources)>4096 OR EXISTS(SELECT 1 FROM oracle2.sources WHERE workspace_id=ANY(workspaces) AND status NOT IN('processing','draft','confirmed','error')) THEN RAISE program_limit_exceeded;END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('schema_version',1,'event_id',event_id,'workspace_id',workspace_id,'source_id',source_id,'revision',revision,'original_sha256',original_sha256,'recorded_at',created_at) ORDER BY workspace_id,source_id,revision,event_id),'[]') INTO withdrawals FROM oracle2.source_original_withdrawals_v1 WHERE workspace_id=ANY(workspaces);
 WITH RECURSIVE lineage AS (
 SELECT p.appointment_id leaf_id,p.workspace_id,p.actor_id,p.scope leaf_scope,p.appointment_id,p.parent_id,p.scope,p.granted_by,
 p.revoked_at,p.expires_at,ARRAY[p.appointment_id] seen,1 depth
 FROM oracle2.appointments p WHERE p.workspace_id=ANY(workspaces)
 UNION ALL SELECT l.leaf_id,l.workspace_id,l.actor_id,l.leaf_scope,p.appointment_id,p.parent_id,p.scope,p.granted_by,p.revoked_at,p.expires_at,l.seen||p.appointment_id,l.depth+1
 FROM lineage l JOIN oracle2.appointments p ON p.appointment_id=l.parent_id AND p.workspace_id=l.workspace_id AND p.actor_id=l.granted_by AND p.scope IN(l.leaf_scope,'root')
 WHERE l.depth<16 AND NOT p.appointment_id=ANY(l.seen)
 ), classified AS (
 SELECT leaf_id,workspace_id,actor_id,leaf_scope,
 min(appointment_id::text) FILTER(WHERE scope='root' AND parent_id IS NULL)::uuid root_id,
 bool_or(revoked_at IS NOT NULL) revoked,bool_or(expires_at<=stamp) expired,
 min(revoked_at) revoked_at,min(expires_at) expires_at,
 bool_or(scope='root' AND parent_id IS NULL) rooted
 FROM lineage GROUP BY leaf_id,workspace_id,actor_id,leaf_scope
 ), revoked_admissions AS (
 SELECT own.workspace_id,own.principal_id,own.role_name,own.leaf_appointment_id leaf_id,v.revoked_at FROM oracle2.meeting_capture_revocations_v1 v JOIN oracle2.meeting_capture_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION ALL SELECT own.workspace_id,own.principal_id,own.role_name,own.leaf_appointment_id,v.revoked_at FROM oracle2.meeting_participation_revocations_v1 v JOIN oracle2.meeting_participation_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION ALL SELECT own.workspace_id,own.principal_id,own.role_name,own.membership_appointment,v.revoked_at FROM oracle2.research_admission_revocations_v1 v JOIN oracle2.research_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION ALL SELECT own.workspace_id,own.principal_id,own.role_name,own.membership_appointment,v.revoked_at FROM oracle2.processing_model_admission_revocations_v1 v JOIN oracle2.processing_model_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION ALL SELECT own.workspace_id,own.principal_id,own.role_name,own.membership_appointment,v.revoked_at FROM oracle2.recommendation_action_revocations_v1 v JOIN oracle2.recommendation_action_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION ALL SELECT own.workspace_id,own.worker_principal_id,own.role_name,NULL::uuid,v.revoked_at FROM oracle2.question_effect_admission_revocations_v1 v JOIN oracle2.question_effect_admissions_v1 own USING(admission_id) WHERE own.workspace_id=ANY(workspaces)
 UNION ALL SELECT (scope->>'workspace_id')::uuid,own.principal_id,own.role_name,(scope->>'appointment_id')::uuid,v.revoked_at FROM oracle2.recovery_admission_revocations_v1 v JOIN oracle2.recovery_operation_admissions_v1 own USING(admission_id) CROSS JOIN LATERAL jsonb_array_elements(own.scope_coverage) scope WHERE (scope->>'workspace_id')::uuid=ANY(workspaces)
 ), actual_denials AS (
 SELECT jsonb_build_object('schema_version',1,'workspace_id',v.workspace_id,'principal_id',v.principal_id,'session_role',v.role_name,
 'appointment_id',v.leaf_id,'root_appointment_id',c.root_id,'scope',c.leaf_scope,'reason','revoked','effective_at',v.revoked_at) value
 FROM revoked_admissions v LEFT JOIN classified c ON c.leaf_id=v.leaf_id
 UNION
 SELECT jsonb_build_object('schema_version',1,'workspace_id',workspace_id,'principal_id',actor_id,'session_role',NULL,
 'appointment_id',leaf_id,'root_appointment_id',root_id,'scope',leaf_scope,
 'reason',CASE WHEN revoked THEN 'revoked' WHEN expired THEN 'expired' ELSE 'missing-current-root' END,
 'effective_at',CASE WHEN revoked THEN revoked_at WHEN expired THEN expires_at ELSE NULL END) value
 FROM classified WHERE revoked OR expired OR NOT rooted
 UNION
 SELECT jsonb_build_object('schema_version',1,'workspace_id',own.workspace_id,'principal_id',own.principal_id,'session_role',own.role_name,
 'appointment_id',NULL,'root_appointment_id',NULL,'scope',NULL,'reason',CASE WHEN runtime.role_name IS NULL THEN 'host-disabled' ELSE 'runtime-revoked' END,'effective_at',runtime.expires_at)
 FROM (
 SELECT workspace_id,principal_id,role_name FROM oracle2.hosting_role_source_admissions WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.hosting_request_principal_admissions WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.hosting_original_source_admissions WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.processing_model_admissions_v1 WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.conversation_processing_admissions_v1 WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.meeting_capture_admissions_v1 WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.meeting_participation_admissions_v1 WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.research_admissions_v1 WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,worker_principal_id,role_name FROM oracle2.question_effect_admissions_v1 WHERE workspace_id=ANY(workspaces)
 UNION SELECT workspace_id,principal_id,role_name FROM oracle2.recommendation_action_admissions_v1 WHERE workspace_id=ANY(workspaces)
 ) own LEFT JOIN oracle2.hosting_role_runtime_admissions runtime ON runtime.role_name=own.role_name
 WHERE runtime.role_name IS NULL OR runtime.expires_at<=stamp
 ) SELECT coalesce(jsonb_agg(value ORDER BY oracle2._replacement_metadata_json(value)),'[]') INTO denials FROM actual_denials;
 IF jsonb_array_length(withdrawals)>16384 OR jsonb_array_length(denials)>16384 THEN RAISE program_limit_exceeded;END IF;
 -- No policy payload/receipt is issued by completeness or snapshot metadata.
 a:=oracle2._recovery_context_v1(wanted,deadline);
 result:=jsonb_build_object('schema_version',1,'protocol',CASE WHEN a.phase_authority='capture' THEN 'oracle-replacement-capture-denials-v1' ELSE 'oracle-replacement-current-denials-v1' END,CASE WHEN a.phase_authority='capture' THEN 'capture_operation_id' ELSE 'restore_operation_id' END,wanted,'descriptor_sha256',a.descriptor_sha256,
 'source_system_identifier',(SELECT system_identifier::text FROM pg_control_system()),'source_database_oid',(SELECT oid FROM pg_database WHERE datname=current_database()),'source_database_name',current_database(),
 'source_session_role',SESSION_USER,'source_principal_id',a.principal_id,'runtime_sha256',a.runtime_hash,'registry_sha256',a.registry_hash,
 'workspace_ids',d->'workspace_ids','coverage',d->'scope_coverage','source_snapshot',snapshot,'watermarks',watermarks,'sources',sources,'withdrawals',withdrawals,'authority_denials',denials,'operational_denials',oracle2._recovery_operational_denials_v1(workspaces,stamp),
 'checked_at',stamp,'valid_until',a.expires_at,'complete',true,'serving_authorized',false,'dispatch_authorized',false);
 IF octet_length(convert_to(oracle2._replacement_metadata_json(result),'UTF8'))>1048576 THEN RAISE program_limit_exceeded;END IF;
 RETURN result;
END $f$;

CREATE FUNCTION oracle2.recovery_current_v1(wanted uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.recovery_operation_admissions_v1;census jsonb;result jsonb;BEGIN
 a:=oracle2._recovery_context_v1(wanted,deadline);
 IF (SELECT count(*) FROM oracle2.recovery_phase_observations_v1 o WHERE o.operation_id=(convert_from(a.descriptor_bytes,'UTF8')::jsonb->>'original_capture_operation_id')::uuid AND o.claimed_phase='capture')>64 THEN RAISE insufficient_privilege USING MESSAGE='complete retained capture observation quota exceeded';END IF;
 IF a.phase_authority IN('capture','current-denials') THEN census:=oracle2._recovery_census_v1(wanted,deadline);END IF;
 result:=jsonb_build_object('schema_version',1,'protocol','oracle-replacement-recovery-current-v1',
 'admission_id',a.admission_id,'operation_id',a.operation_id,'phase_authority',a.phase_authority,
 'principal_id',a.principal_id,'session_role',SESSION_USER,'descriptor_bytes_hex',encode(a.descriptor_bytes,'hex'),
 'descriptor_sha256',a.descriptor_sha256,'postrestore_binding_bytes_hex',encode(a.postrestore_binding_bytes,'hex'),
 'postrestore_binding_sha256',a.postrestore_binding_sha256,'backup_custody_sha256',a.backup_custody_sha256,'checked_at',clock_timestamp(),'valid_until',a.expires_at,
 'original_horizon',a.original_horizon,'census',census,
 'original_capture_claim',(SELECT jsonb_build_object('schema_version',1,'operation_id',c.operation_id,'phase',c.phase,'descriptor_sha256',c.descriptor_sha256,'original_phase_deadline',c.original_phase_deadline,'claimed_at',c.claimed_at,'fresh',false,'serving_authorized',false,'dispatch_authorized',false,'automatic_retry_allowed',false) FROM oracle2.recovery_phase_claims_v1 c WHERE c.operation_id=(convert_from(a.descriptor_bytes,'UTF8')::jsonb->>'original_capture_operation_id')::uuid AND c.phase='capture'),
 'original_capture_observations',(SELECT coalesce(jsonb_agg(convert_from(o.observation_bytes,'UTF8')::jsonb ORDER BY o.observation_id),'[]') FROM oracle2.recovery_phase_observations_v1 o WHERE o.operation_id=(convert_from(a.descriptor_bytes,'UTF8')::jsonb->>'original_capture_operation_id')::uuid AND o.claimed_phase='capture' AND convert_from(o.observation_bytes,'UTF8')::jsonb->>'backup_manifest_sha256'=convert_from(a.descriptor_bytes,'UTF8')::jsonb->>'backup_manifest_sha256'),
 'retained_claims',(SELECT coalesce(jsonb_agg(jsonb_build_object('schema_version',1,'operation_id',c.operation_id,'phase',c.phase,'descriptor_sha256',c.descriptor_sha256,'original_phase_deadline',c.original_phase_deadline,'claimed_at',c.claimed_at,'fresh',false,'serving_authorized',false,'dispatch_authorized',false,'automatic_retry_allowed',false) ORDER BY c.phase),'[]') FROM oracle2.recovery_phase_claims_v1 c WHERE c.operation_id=wanted),
 'imported_census_sha256s',(SELECT coalesce(jsonb_agg(i.census_sha256 ORDER BY i.census_sha256),'[]') FROM oracle2.recovery_denial_imports_v1 i WHERE i.operation_id=wanted AND a.postrestore_binding_bytes IS NOT NULL),'serving_authorized',false,'dispatch_authorized',false);
 PERFORM oracle2._recovery_context_v1(wanted,deadline);RETURN result;
END $f$;

CREATE FUNCTION oracle2.claim_recovery_phase_v1(wanted uuid,wanted_phase text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.recovery_operation_admissions_v1;d jsonb;c oracle2.recovery_phase_claims_v1;item jsonb;
 phase_until timestamptz;fresh boolean:=false;resource_hash text;BEGIN
 a:=oracle2._recovery_context_v1(wanted,deadline);d:=convert_from(a.descriptor_bytes,'UTF8')::jsonb;
 IF a.postrestore_binding_bytes IS NOT NULL OR wanted_phase IS NULL
 OR NOT ((a.phase_authority='capture' AND d->>'kind'='capture' AND wanted_phase='capture')
 OR (a.phase_authority='deny-only-target' AND d->>'kind'='restore' AND wanted_phase IN('restore','deny-import','rebuild-verify','resume-observe')))
 THEN RAISE insufficient_privilege USING MESSAGE='original control master own exact recovery phase required';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('oracle-recovery-master:'||wanted::text,0));
 SELECT * INTO c FROM oracle2.recovery_phase_claims_v1 WHERE operation_id=wanted AND phase=wanted_phase;
 IF c.operation_id IS NOT NULL THEN
 IF c.descriptor_sha256<>a.descriptor_sha256 THEN RAISE unique_violation USING MESSAGE='recovery phase identity collision';END IF;
 ELSE
 -- Original phase horizon is selected once from ACTUAL installed metadata;
 -- the independent <=30s current request neither renews nor replaces it.
 WITH RECURSIVE ancestors AS (
 SELECT p.appointment_id,p.parent_id,p.granted_by,p.workspace_id,p.scope leaf_scope,p.expires_at,ARRAY[p.appointment_id] seen FROM oracle2.appointments p
 JOIN jsonb_array_elements(a.scope_coverage) scope ON p.appointment_id=(scope->>'appointment_id')::uuid
 UNION ALL SELECT p.appointment_id,p.parent_id,p.granted_by,p.workspace_id,x.leaf_scope,p.expires_at,x.seen||p.appointment_id FROM oracle2.appointments p
 JOIN ancestors x ON x.parent_id=p.appointment_id AND p.actor_id=x.granted_by AND p.workspace_id=x.workspace_id AND p.scope IN(x.leaf_scope,'root') WHERE cardinality(x.seen)<16 AND NOT p.appointment_id=ANY(x.seen))
 SELECT least((SELECT expires_at FROM oracle2.recovery_operation_admissions_v1 WHERE admission_id=a.admission_id),
 a.original_horizon,(d->>'expires_at')::timestamptz,(SELECT expires_at FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER),min(expires_at)) INTO phase_until FROM ancestors;
 IF phase_until<=clock_timestamp() THEN RAISE insufficient_privilege;END IF;
 INSERT INTO oracle2.recovery_phase_claims_v1(operation_id,phase,admission_id,descriptor_sha256,original_phase_deadline)
 VALUES(wanted,wanted_phase,a.admission_id,a.descriptor_sha256,phase_until) RETURNING * INTO c;fresh:=true;
 IF wanted_phase='restore' THEN
 FOR item IN SELECT value->'target' FROM jsonb_array_elements(d->'databases') LOOP
 resource_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('system_identifier',item->>'system_identifier','database_oid',item->'database_oid')),'UTF8')),'hex');
 INSERT INTO oracle2.recovery_target_reservations_v1 VALUES('database',resource_hash,wanted,'restore');
 END LOOP;
 FOR item IN SELECT value->'target' FROM jsonb_array_elements(d->'private_roots') LOOP
 resource_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('device',item->'device','inode',item->'inode','uid',item->'uid')),'UTF8')),'hex');
 INSERT INTO oracle2.recovery_target_reservations_v1 VALUES('private-root',resource_hash,wanted,'restore');
 END LOOP;
 END IF;
 END IF;
 PERFORM oracle2._recovery_context_v1(wanted,deadline);
 RETURN jsonb_build_object('schema_version',1,'operation_id',c.operation_id,'phase',c.phase,'descriptor_sha256',c.descriptor_sha256,
 'original_phase_deadline',c.original_phase_deadline,'claimed_at',c.claimed_at,'fresh',fresh,
 'serving_authorized',false,'dispatch_authorized',false,'automatic_retry_allowed',false);
END $f$;

CREATE FUNCTION oracle2.observe_recovery_phase_v1(wanted uuid,wanted_phase text,raw bytea,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.recovery_operation_admissions_v1;j jsonb;c oracle2.recovery_phase_claims_v1;prior oracle2.recovery_phase_observations_v1;hash text;claimed text;BEGIN
 a:=oracle2._recovery_context_v1(wanted,deadline);
 IF a.phase_authority<>'observe' THEN RAISE insufficient_privilege USING MESSAGE='separately current metadata observation required';END IF;
 j:=oracle2._recovery_json_v1(raw,65536);hash:=encode(sha256(raw),'hex');
 IF j->>'operation_id'<>wanted::text OR wanted_phase NOT IN('capture','restore','deny-import','rebuild-verify','resume-observe')
 OR j->'observation_only' IS DISTINCT FROM 'true'::jsonb OR j->'serving_authorized' IS DISTINCT FROM 'false'::jsonb
 OR j->'dispatch_authorized' IS DISTINCT FROM 'false'::jsonb OR j->'automatic_retry_allowed' IS DISTINCT FROM 'false'::jsonb
 OR jsonb_typeof(j->'quarantine_reasons')<>'array' THEN RAISE invalid_parameter_value;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('oracle-recovery-master:'||wanted::text,0));
 SELECT * INTO c FROM oracle2.recovery_phase_claims_v1 WHERE operation_id=wanted AND phase=wanted_phase;
 IF j->>'claim_state'='claimed' THEN
 IF NOT j ?& ARRAY['schema_version','protocol','claim_state','observation_id','operation_id','phase','status','original_phase_deadline','phase_started_at','observed_at','backup_manifest_sha256','source_census_sha256','observed_result_sha256','observed_file_count','observed_bytes','quarantine_reasons','observation_only','serving_authorized','dispatch_authorized','automatic_retry_allowed'] OR j-ARRAY['schema_version','protocol','claim_state','observation_id','operation_id','phase','status','original_phase_deadline','phase_started_at','observed_at','backup_manifest_sha256','source_census_sha256','observed_result_sha256','observed_file_count','observed_bytes','quarantine_reasons','observation_only','serving_authorized','dispatch_authorized','automatic_retry_allowed']<>'{}'::jsonb OR j->>'protocol'<>'oracle-replacement-recovery-observation-v1' OR j->>'phase'<>wanted_phase OR c.operation_id IS NULL
 OR c.descriptor_sha256<>a.descriptor_sha256 OR j->>'status' NOT IN('complete','UNKNOWN','refused')
 OR NOT isfinite((j->>'original_phase_deadline')::timestamptz) OR NOT isfinite((j->>'phase_started_at')::timestamptz) OR NOT isfinite((j->>'observed_at')::timestamptz) OR (j->>'original_phase_deadline')::timestamptz<>c.original_phase_deadline OR (j->>'phase_started_at')::timestamptz<>c.claimed_at
 OR (j->>'observed_at')::timestamptz<c.claimed_at OR (j->>'observed_at')::timestamptz>clock_timestamp()
 OR j-ARRAY['schema_version','protocol','claim_state','observation_id','operation_id','phase','status','original_phase_deadline','phase_started_at','observed_at','backup_manifest_sha256','source_census_sha256','observed_result_sha256','observed_file_count','observed_bytes','quarantine_reasons','observation_only','serving_authorized','dispatch_authorized','automatic_retry_allowed']<>'{}'::jsonb
 THEN RAISE invalid_parameter_value USING MESSAGE='actual retained original claim observation required';END IF;
 claimed:=wanted_phase;
 ELSIF j->>'claim_state'='not-claimed' THEN
 IF NOT j ?& ARRAY['schema_version','protocol','claim_state','observation_id','operation_id','attempted_phase','descriptor_sha256','status','refused_at','quarantine_reasons','observation_only','serving_authorized','dispatch_authorized','automatic_retry_allowed'] OR j-ARRAY['schema_version','protocol','claim_state','observation_id','operation_id','attempted_phase','descriptor_sha256','status','refused_at','quarantine_reasons','observation_only','serving_authorized','dispatch_authorized','automatic_retry_allowed']<>'{}'::jsonb OR j->>'protocol'<>'oracle-replacement-recovery-preclaim-refusal-v1' OR j->>'attempted_phase'<>wanted_phase OR c.operation_id IS NOT NULL
 OR j->>'status'<>'refused' OR j->>'descriptor_sha256'<>a.descriptor_sha256
 OR NOT isfinite((j->>'refused_at')::timestamptz) OR (j->>'refused_at')::timestamptz>clock_timestamp() OR jsonb_array_length(j->'quarantine_reasons')=0
 OR j-ARRAY['schema_version','protocol','claim_state','observation_id','operation_id','attempted_phase','descriptor_sha256','status','refused_at','quarantine_reasons','observation_only','serving_authorized','dispatch_authorized','automatic_retry_allowed']<>'{}'::jsonb
 THEN RAISE invalid_parameter_value USING MESSAGE='preclaim refusal cannot fabricate an effect or deadline';END IF;
 ELSE RAISE invalid_parameter_value;END IF;
 SELECT * INTO prior FROM oracle2.recovery_phase_observations_v1 WHERE observation_id=(j->>'observation_id')::uuid;
 IF prior.observation_id IS NOT NULL THEN
 IF prior.operation_id<>wanted OR prior.attempted_phase<>wanted_phase OR prior.observation_bytes<>raw THEN RAISE unique_violation;END IF;
 ELSE
 INSERT INTO oracle2.recovery_phase_observations_v1(observation_id,operation_id,claimed_phase,attempted_phase,observation_bytes,observation_sha256)
 VALUES((j->>'observation_id')::uuid,wanted,claimed,wanted_phase,raw,hash);
 END IF;
 PERFORM oracle2._recovery_context_v1(wanted,deadline);
 RETURN jsonb_build_object('schema_version',1,'observation_id',j->>'observation_id','observation_sha256',hash,'observation_only',true,'serving_authorized',false,'dispatch_authorized',false,'automatic_retry_allowed',false);
END $f$;

CREATE FUNCTION oracle2.import_recovery_denials_v1(wanted uuid,raw bytea,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.recovery_operation_admissions_v1;j jsonb;d jsonb;item jsonb;hash text;kind text;field text;deny_hash text;BEGIN
 a:=oracle2._recovery_context_v1(wanted,deadline);
 IF a.phase_authority<>'deny-only-target' OR a.postrestore_binding_bytes IS NULL THEN RAISE insufficient_privilege USING MESSAGE='separately installed postrestore target deny-only purpose required';END IF;
 j:=oracle2._recovery_json_v1(raw,1048576);d:=convert_from(a.descriptor_bytes,'UTF8')::jsonb;hash:=encode(sha256(raw),'hex');
 IF NOT j ?& ARRAY['schema_version','protocol','restore_operation_id','descriptor_sha256','source_system_identifier','source_database_oid','source_database_name','source_session_role','source_principal_id','runtime_sha256','registry_sha256','workspace_ids','coverage','source_snapshot','watermarks','sources','withdrawals','authority_denials','operational_denials','checked_at','valid_until','complete','serving_authorized','dispatch_authorized'] OR j-ARRAY['schema_version','protocol','restore_operation_id','descriptor_sha256','source_system_identifier','source_database_oid','source_database_name','source_session_role','source_principal_id','runtime_sha256','registry_sha256','workspace_ids','coverage','source_snapshot','watermarks','sources','withdrawals','authority_denials','operational_denials','checked_at','valid_until','complete','serving_authorized','dispatch_authorized']<>'{}'::jsonb OR j->>'protocol'<>'oracle-replacement-current-denials-v1' OR j->>'restore_operation_id'<>wanted::text OR j->>'descriptor_sha256'<>a.descriptor_sha256
 OR j->'workspace_ids' IS DISTINCT FROM d->'workspace_ids' OR j->'coverage' IS DISTINCT FROM d->'scope_coverage'
 OR (j->>'source_system_identifier',j->>'source_database_oid',j->>'source_database_name') IS DISTINCT FROM
 (d->'current_control_source'->>'system_identifier',d->'current_control_source'->>'database_oid',d->'current_control_source'->>'database_name')
 OR j->'complete' IS DISTINCT FROM 'true'::jsonb OR j->'serving_authorized' IS DISTINCT FROM 'false'::jsonb OR j->'dispatch_authorized' IS DISTINCT FROM 'false'::jsonb
 OR NOT isfinite((j->>'checked_at')::timestamptz) OR NOT isfinite((j->>'valid_until')::timestamptz) OR (j->>'checked_at')::timestamptz>clock_timestamp() OR (j->>'valid_until')::timestamptz<=clock_timestamp()
 OR (j->>'valid_until')::timestamptz>(j->>'checked_at')::timestamptz+interval '30 seconds'
 THEN RAISE invalid_parameter_value USING MESSAGE='complete descriptive current-denials population required';END IF;
 -- These bytes do NOT authenticate original-control provenance. The concrete
 -- protected factory must read actual own fixed TLS source before AND after.
 INSERT INTO oracle2.recovery_denial_imports_v1 VALUES(wanted,hash,a.admission_id,raw,clock_timestamp()) ON CONFLICT DO NOTHING;
 FOR field,kind IN SELECT * FROM(VALUES('sources','source'),('withdrawals','withdrawal'),('authority_denials','authority'),('operational_denials','operational')) mapping LOOP
 IF jsonb_typeof(j->field)<>'array' THEN RAISE invalid_parameter_value;END IF;
 FOR item IN SELECT value FROM jsonb_array_elements(j->field) LOOP
 IF kind<>'operational' AND NOT d->'workspace_ids' @> jsonb_build_array(item->'workspace_id') THEN RAISE invalid_parameter_value;END IF;
 IF kind='source' AND item->'denied' IS DISTINCT FROM 'true'::jsonb THEN CONTINUE;END IF;
 deny_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('kind',kind,'metadata',item)),'UTF8')),'hex');
 INSERT INTO oracle2.recovery_deny_overlay_v1 VALUES(wanted,deny_hash,hash,kind,item) ON CONFLICT DO NOTHING;
 END LOOP;END LOOP;
 PERFORM oracle2._recovery_context_v1(wanted,deadline);
 RETURN jsonb_build_object('schema_version',1,'operation_id',wanted,'census_sha256',hash,'quarantined',true,'serving_authorized',false,'dispatch_authorized',false,'automatic_retry_allowed',false);
END $f$;
DO $private$ DECLARE signature text;BEGIN
 FOREACH signature IN ARRAY ARRAY['oracle2._recovery_json_v1(bytea,integer)','oracle2._recovery_context_v1(uuid,timestamptz)','oracle2._recovery_census_v1(uuid,timestamptz)','oracle2._recovery_operational_denials_v1(uuid[],timestamptz)','oracle2.recovery_current_v1(uuid,timestamptz)','oracle2.claim_recovery_phase_v1(uuid,text,timestamptz)','oracle2.observe_recovery_phase_v1(uuid,text,bytea,timestamptz)','oracle2.import_recovery_denials_v1(uuid,bytea,timestamptz)'] LOOP
 EXECUTE 'REVOKE ALL ON FUNCTION '||signature||' FROM PUBLIC,oracle2_source_reader,oracle2_replacement_requester,oracle2_candidate_compiler,oracle2_gateway_metadata,oracle2_documentary_executor,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer';
 END LOOP;
END $private$;
