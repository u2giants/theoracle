-- Canonical Oracle operational question-effects owner. SOURCE ONLY.
-- No installed role/admission/grant, provider dispatch, model truth or cost ledger.
DO $owner$ BEGIN
 IF (SELECT nspowner FROM pg_namespace WHERE nspname='oracle2') IS DISTINCT FROM
 (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER) THEN RAISE EXCEPTION 'dedicated canonical owner required'; END IF;
END $owner$;
CREATE TABLE oracle2.question_effect_admissions_v1 (
 admission_id uuid PRIMARY KEY,role_name name NOT NULL,worker_principal_id uuid NOT NULL,
 enduser_role name NOT NULL,enduser_principal_id uuid NOT NULL,workspace_id uuid NOT NULL,
 thread_id uuid NOT NULL REFERENCES oracle2.conversation_threads_v1,model_id uuid NOT NULL,
 worker_history_admission uuid NOT NULL REFERENCES oracle2.processing_model_admissions_v1,
 enduser_history_admission uuid NOT NULL REFERENCES oracle2.processing_model_admissions_v1,
 effect_purpose text NOT NULL CHECK(effect_purpose IN('qualified-query-embedding-v1','qualified-answer-synthesis-v1')),
 provider_model text NOT NULL CHECK(provider_model IN('openai/text-embedding-3-small','openai/gpt-6.1-sol','openai/gpt-6-astra')),
 runtime_hash text NOT NULL,registry_hash text NOT NULL,config_sha256 text NOT NULL,catalog jsonb NOT NULL CHECK(jsonb_typeof(catalog)='object'),
 account text NOT NULL,key_fingerprint text NOT NULL,ledger_registry_hash text NOT NULL,terms_hash text NOT NULL,
 register_hash text NOT NULL,billing_bounds_sha256 text NOT NULL,pricing_sha256 text NOT NULL,
 approval_packet_sha256 text NOT NULL,source_export_scope_sha256 text NOT NULL,
 allocation_batch uuid NOT NULL,allocation_hash text NOT NULL,allocation_receipt_hash text NOT NULL,
 cost_settlement_sha256 text CHECK(cost_settlement_sha256 ~ '^[0-9a-f]{64}$'),cost_settlement_expires_at timestamptz,
 CHECK((cost_settlement_sha256 IS NULL)=(cost_settlement_expires_at IS NULL)),
 CHECK(cost_settlement_expires_at IS NULL OR isfinite(cost_settlement_expires_at) AND issued_at<cost_settlement_expires_at AND cost_settlement_expires_at<=original_horizon),
 allocation_ceiling_usd numeric NOT NULL CHECK(allocation_ceiling_usd>0 AND allocation_ceiling_usd::text NOT IN('NaN','Infinity','-Infinity')),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL,issued_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL,original_horizon timestamptz NOT NULL,
 CHECK(isfinite(issued_at) AND isfinite(expires_at) AND isfinite(original_horizon) AND issued_at<expires_at AND expires_at<=original_horizon),
 CHECK(issuer_actor<>reviewer_actor AND worker_principal_id NOT IN(issuer_actor,reviewer_actor)),
 CHECK(account='key-sha256:'||key_fingerprint),
 CHECK((effect_purpose='qualified-query-embedding-v1')=(provider_model='openai/text-embedding-3-small')),
 CHECK(runtime_hash ~ '^[0-9a-f]{64}$' AND registry_hash ~ '^[0-9a-f]{64}$' AND config_sha256 ~ '^[0-9a-f]{64}$'
 AND key_fingerprint ~ '^[0-9a-f]{64}$' AND ledger_registry_hash ~ '^[0-9a-f]{64}$' AND terms_hash ~ '^[0-9a-f]{64}$'
 AND register_hash ~ '^[0-9a-f]{64}$' AND billing_bounds_sha256 ~ '^[0-9a-f]{64}$' AND pricing_sha256 ~ '^[0-9a-f]{64}$'
 AND approval_packet_sha256 ~ '^[0-9a-f]{64}$' AND source_export_scope_sha256 ~ '^[0-9a-f]{64}$'
 AND allocation_hash ~ '^[0-9a-f]{64}$' AND allocation_receipt_hash ~ '^[0-9a-f]{64}$'));
CREATE TABLE oracle2.question_effect_admission_revocations_v1 (
 admission_id uuid PRIMARY KEY REFERENCES oracle2.question_effect_admissions_v1,
 revoked_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE oracle2.question_effect_operations_v1 (
 operation_id uuid PRIMARY KEY,admission_id uuid NOT NULL REFERENCES oracle2.question_effect_admissions_v1,
 workspace_id uuid NOT NULL,thread_id uuid NOT NULL,employee_event_id uuid NOT NULL REFERENCES oracle2.conversation_events_v1,
 effect_purpose text NOT NULL,query_sha256 text NOT NULL,model_id uuid NOT NULL,model_version integer NOT NULL CHECK(model_version>0),
 model_content_hash text NOT NULL,accepted_projection_event_id uuid NOT NULL,accepted_receipt_body_sha256 text NOT NULL,
 valid_at timestamptz,known_at timestamptz,job_bytes bytea NOT NULL CHECK(octet_length(job_bytes) BETWEEN 1 AND 262144),
 job_sha256 text NOT NULL CHECK(job_sha256=encode(sha256(job_bytes),'hex')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 operation_deadline timestamptz NOT NULL CHECK(isfinite(operation_deadline) AND created_at<operation_deadline),
 UNIQUE(workspace_id,thread_id,employee_event_id,effect_purpose,query_sha256,model_id,model_version,model_content_hash,accepted_projection_event_id,accepted_receipt_body_sha256),
 CHECK((valid_at IS NULL)=(known_at IS NULL)));
CREATE TABLE oracle2.question_effect_observations_v1 (
 observation_id uuid PRIMARY KEY,operation_id uuid NOT NULL REFERENCES oracle2.question_effect_operations_v1,
 observation_bytes bytea NOT NULL CHECK(octet_length(observation_bytes) BETWEEN 1 AND 65536),
 observation_sha256 text NOT NULL CHECK(observation_sha256=encode(sha256(observation_bytes),'hex')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(operation_id,observation_sha256));
DO $immutable$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['question_effect_admissions_v1','question_effect_admission_revocations_v1','question_effect_operations_v1','question_effect_observations_v1'] LOOP
 EXECUTE format('REVOKE ALL ON oracle2.%I FROM PUBLIC,oracle2_source_reader,oracle2_replacement_requester,oracle2_candidate_compiler,oracle2_gateway_metadata,oracle2_documentary_executor,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer',t);
 EXECUTE format('CREATE TRIGGER immutable_%I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()',t,t);
 END LOOP;
END $immutable$;

-- Private current context derives the original only after independently
-- installed own-worker and enduser/thread mapping. Never SET ROLE/impersonation.
CREATE FUNCTION oracle2._question_effect_input_v1(wanted_admission uuid,wanted_employee_event uuid,
 valid_at timestamptz,known_at timestamptz,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.question_effect_admissions_v1;worker oracle2.processing_model_admissions_v1;employee oracle2.processing_model_admissions_v1;
 t oracle2.conversation_threads_v1;e oracle2.conversation_events_v1;u oracle2.hosting_request_principal_admissions;
 run oracle2.hosting_role_runtime_admissions;employee_run oracle2.hosting_role_runtime_admissions;cap record;function_oid oid;
 m jsonb;delivery jsonb;employee_metadata jsonb;until_at timestamptz;login oid;owner_oid oid;ref jsonb;query_hash text;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 IF deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp()
 OR (valid_at IS NULL) IS DISTINCT FROM(known_at IS NULL)
 OR known_at IS NOT NULL AND(NOT isfinite(known_at) OR NOT isfinite(valid_at) OR known_at>clock_timestamp())
 OR NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl) THEN RAISE insufficient_privilege; END IF;
 SELECT oid INTO login FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin AND NOT(rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication);
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF login IS NULL OR owner_oid IS DISTINCT FROM(SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR current_setting('role') NOT IN('none',SESSION_USER::text)
 OR EXISTS(SELECT 1 FROM pg_roles r WHERE r.oid<>login AND(pg_has_role(login,r.oid,'MEMBER') OR pg_has_role(login,r.oid,'SET') OR pg_has_role(login,r.oid,'USAGE')))
 THEN RAISE insufficient_privilege USING MESSAGE='distinct no-membership actual question worker required'; END IF;
 SELECT * INTO a FROM oracle2.question_effect_admissions_v1 WHERE admission_id=wanted_admission AND role_name=SESSION_USER;
 IF a.admission_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='separate installed question-purpose admission required'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(a.catalog))<>6 THEN RAISE insufficient_privilege; END IF;
 FOR cap IN SELECT * FROM jsonb_each_text(a.catalog) LOOP
 IF cap.key NOT IN('oracle2.question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz)',
 'oracle2.claim_question_effect_v1(uuid,uuid,timestamptz,timestamptz,bytea,timestamptz)',
 'oracle2.question_effect_status_v1(uuid,timestamptz)',
 'oracle2.record_question_effect_observation_v1(uuid,bytea,timestamptz)',
 'oracle2._question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz)',
 'oracle2._question_effect_cost_context_v1(uuid,timestamptz)') OR cap.value !~ '^[0-9a-f]{64}$' THEN RAISE insufficient_privilege; END IF;
 function_oid:=to_regprocedure(cap.key);
 IF NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=function_oid AND p.proowner=owner_oid AND p.prosecdef
 AND p.provolatile='v' AND p.proconfig=ARRAY['search_path=pg_catalog, oracle2']
 AND encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')=cap.value) THEN RAISE insufficient_privilege USING MESSAGE='exact current question catalog denied'; END IF;
 IF cap.key LIKE 'oracle2._question%' THEN
  IF EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
  WHERE p.oid=function_oid AND x.grantee<>p.proowner) THEN RAISE insufficient_privilege USING MESSAGE='private question helper owner-only'; END IF;
 ELSE
  IF NOT EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
  WHERE p.oid=function_oid AND x.grantee=login AND x.privilege_type='EXECUTE' AND NOT x.is_grantable)
  OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
  LEFT JOIN pg_roles r ON r.oid=x.grantee WHERE p.oid=function_oid AND x.grantee<>p.proowner
  AND (x.is_grantable OR r.oid IS NULL OR NOT r.rolcanlogin OR r.rolsuper OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
  OR EXISTS(SELECT 1 FROM pg_roles other WHERE other.oid<>r.oid AND(pg_has_role(r.oid,other.oid,'MEMBER') OR pg_has_role(r.oid,other.oid,'SET') OR pg_has_role(r.oid,other.oid,'USAGE')))))
  THEN RAISE insufficient_privilege USING MESSAGE='only complete direct lowpriv question LOGIN grants allowed'; END IF;
 END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x
 WHERE p.oid=to_regprocedure('oracle2.hosting_consolidated_projection_delivery_v1(uuid,integer,timestamptz,timestamptz,uuid,text,text,text,timestamptz)')
 AND x.grantee=login AND x.privilege_type='EXECUTE' AND NOT x.is_grantable) THEN RAISE insufficient_privilege USING MESSAGE='separate direct current delivery capability required'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||a.workspace_id::text));
 SELECT * INTO a FROM oracle2.question_effect_admissions_v1 WHERE admission_id=wanted_admission AND role_name=SESSION_USER FOR SHARE;
 SELECT * INTO run FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 IF a.issued_at>clock_timestamp() OR least(a.expires_at,a.original_horizon)<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.question_effect_admission_revocations_v1 WHERE admission_id=a.admission_id)
 OR run.role_name IS NULL OR (run.runtime_hash,run.registry_hash) IS DISTINCT FROM(a.runtime_hash,a.registry_hash)
 OR NOT isfinite(run.expires_at) OR run.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='current question worker runtime denied'; END IF;
 until_at:=least(deadline,a.expires_at,a.original_horizon,run.expires_at,
 oracle2._replacement_scope(a.workspace_id,a.worker_principal_id,'question-effect-thread:'||a.thread_id::text||':'||a.effect_purpose));
 -- Existing 017 own-history guard is unchanged and re-proves actual SESSION_USER.
 SELECT * INTO worker FROM oracle2.processing_model_admissions_v1 WHERE admission_id=a.worker_history_admission;
 worker:=oracle2._processing_model_admission_v1(a.worker_history_admission,'history-read',a.runtime_hash,a.registry_hash,worker.config_hash,until_at);
 IF (worker.workspace_id,worker.principal_id,worker.model_id) IS DISTINCT FROM(a.workspace_id,a.worker_principal_id,a.model_id)
 THEN RAISE insufficient_privilege USING MESSAGE='separate exact worker history admission required'; END IF;
 SELECT * INTO t FROM oracle2.conversation_threads_v1 WHERE thread_id=a.thread_id AND workspace_id=a.workspace_id AND principal_id=a.enduser_principal_id FOR SHARE;
 SELECT * INTO e FROM oracle2.conversation_events_v1 WHERE event_id=wanted_employee_event AND thread_id=a.thread_id
 AND workspace_id=a.workspace_id AND principal_id=a.enduser_principal_id AND origin='employee';
 IF t.thread_id IS NULL OR t.state<>'active' OR t.segment_deadline<=clock_timestamp()
 OR e.event_id IS NULL OR e.original_text IS NULL OR e.original_sha256 IS NULL
 OR octet_length(convert_to(e.original_text,'UTF8')) NOT BETWEEN 1 AND 16384 OR length(e.original_text)>4096
 OR e.original_sha256<>encode(sha256(convert_to(e.original_text,'UTF8')),'hex')
 OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 newer WHERE newer.thread_id=t.thread_id AND newer.origin='employee' AND newer.sequence>e.sequence)
 OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 corrected WHERE corrected.corrects_event_id=e.event_id)
 THEN RAISE insufficient_privilege USING MESSAGE='exact current immutable employee question required'; END IF;
 SELECT * INTO u FROM oracle2.hosting_request_principal_admissions WHERE role_name=a.enduser_role AND workspace_id=a.workspace_id AND principal_id=a.enduser_principal_id FOR SHARE;
 SELECT * INTO employee_run FROM oracle2.hosting_role_runtime_admissions WHERE role_name=a.enduser_role FOR SHARE;
 IF u.role_name IS NULL OR employee_run.role_name IS NULL OR u.expires_at<=clock_timestamp() OR employee_run.expires_at<=clock_timestamp()
 OR(u.runtime_hash,u.registry_hash) IS DISTINCT FROM(employee_run.runtime_hash,employee_run.registry_hash)
 THEN RAISE insufficient_privilege USING MESSAGE='same independently current authenticated employee required'; END IF;
 until_at:=least(until_at,t.segment_deadline,u.expires_at,employee_run.expires_at,
 oracle2._replacement_scope(a.workspace_id,a.enduser_principal_id,'conversation-self'));
 SELECT * INTO employee FROM oracle2.processing_model_admissions_v1 WHERE admission_id=a.enduser_history_admission FOR SHARE;
 IF employee.admission_id IS NULL OR employee.operation<>'history-read' OR employee.workspace_id<>a.workspace_id
 OR employee.principal_id<>a.enduser_principal_id OR employee.model_id<>a.model_id
 OR employee.issued_at>clock_timestamp() OR employee.expires_at<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.processing_model_admission_revocations_v1 WHERE admission_id=employee.admission_id)
 THEN RAISE insufficient_privilege USING MESSAGE='actual selected employee history access required'; END IF;
 -- Private 017 metadata validator has no SESSION_USER mutation/claim. It is
 -- reached ONLY after the installed exact employee admission above, and keeps
 -- its complete original qualification/history/root checks unchanged.
 employee.expires_at:=least(employee.expires_at,until_at,
 oracle2._replacement_scope(a.workspace_id,a.enduser_principal_id,'processing-history'));
 IF known_at IS NULL THEN m:=oracle2.hosting_current_consolidated_model_v1(a.model_id,a.worker_history_admission,a.runtime_hash,a.registry_hash,worker.config_hash,until_at);
 ELSE m:=oracle2.hosting_historical_consolidated_model_v1(a.model_id,valid_at,known_at,a.worker_history_admission,a.runtime_hash,a.registry_hash,worker.config_hash,until_at); END IF;
 employee_metadata:=oracle2._processing_history_metadata_v1(employee,a.model_id,(m->'manifest'->>'version')::integer);
 IF employee_metadata->'manifest' IS DISTINCT FROM m->'manifest' OR employee_metadata->'sourceRefs' IS DISTINCT FROM m->'sourceRefs'
 THEN RAISE insufficient_privilege USING MESSAGE='complete worker employee source/model intersection differs'; END IF;
 delivery:=oracle2.hosting_consolidated_projection_delivery_v1(a.model_id,(m->'manifest'->>'version')::integer,
 valid_at,known_at,a.worker_history_admission,a.runtime_hash,a.registry_hash,worker.config_hash,until_at);
 until_at:=least(until_at,(m->>'validUntil')::timestamptz,(employee_metadata->>'validUntil')::timestamptz,(delivery->>'valid_until')::timestamptz);
 -- Distinct per-source export-purpose leaves are mandatory; history read alone
 -- never becomes permission to send these originals to another processing use.
 FOR ref IN SELECT value FROM jsonb_array_elements(m->'sourceRefs') LOOP
 until_at:=least(until_at,oracle2._replacement_scope(a.workspace_id,a.worker_principal_id,a.effect_purpose||':'||(ref->>'source_id')));
 END LOOP;
 IF until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 query_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('schema_version',1,'protocol','qualified-natural-question-v1','question',e.original_text)),'UTF8')),'hex');
 RETURN jsonb_build_object('schema_version',1,'purpose','question-effect-input-v1','admission_id',a.admission_id,'effect_purpose',a.effect_purpose,
 'worker_principal_id',a.worker_principal_id,'enduser_principal_id',a.enduser_principal_id,'workspace_id',a.workspace_id,
 'thread_id',a.thread_id,'thread_revision',t.revision,'thread_mode',t.mode,'pending_question_id',t.pending_question,
 'employee_event_id',e.event_id,'original_text',e.original_text,'original_language',e.original_language,'original_sha256',e.original_sha256,'query_sha256',query_hash,
 'model_id',a.model_id,'model_version',(m->'manifest'->>'version')::integer,'model_content_hash',m->'manifest'->>'content_hash',
 'source_refs',m->'sourceRefs','delivery',delivery,'admission',to_jsonb(a),'checked_at',clock_timestamp(),'valid_until',until_at,'original_horizon',a.original_horizon);
END $$;
REVOKE ALL ON FUNCTION oracle2._question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.question_effect_input_v1(wanted_admission uuid,wanted_employee_event uuid,valid_at timestamptz,known_at timestamptz,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
BEGIN RETURN oracle2._question_effect_input_v1(wanted_admission,wanted_employee_event,valid_at,known_at,deadline); END $$;
REVOKE ALL ON FUNCTION oracle2.question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.claim_question_effect_v1(wanted_admission uuid,wanted_employee_event uuid,
 valid_at timestamptz,known_at timestamptz,job_bytes bytea,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE context jsonb;again jsonb;j jsonb;a oracle2.question_effect_admissions_v1;o oracle2.question_effect_operations_v1;
 supplied_id uuid;job_hash text;accepted uuid;receipt_hash text;existing_id uuid;scope_hash text;
BEGIN
 context:=oracle2._question_effect_input_v1(wanted_admission,wanted_employee_event,valid_at,known_at,deadline);
 SELECT * INTO a FROM oracle2.question_effect_admissions_v1 WHERE admission_id=wanted_admission;
 IF octet_length(job_bytes) NOT BETWEEN 1 AND 262144 THEN RAISE insufficient_privilege; END IF;
 j:=convert_from(job_bytes,'UTF8')::jsonb;
 IF convert_to(oracle2._replacement_metadata_json(j),'UTF8') IS DISTINCT FROM job_bytes
 OR jsonb_typeof(j)<>'object' OR NOT j ?& ARRAY['schema_version','job_schema','dispatch_id','workspace_id','artifact_id','batch_id','purpose','attempt','request','request_hash','permission_hash','processing_request','approvals','pricing','register_hash','input_tokens_upper_bound','admission_id','thread_id','thread_revision','employee_event_id','original_sha256','query_sha256','qualified_model_id','model_version','model_content_hash','accepted_projection_event_id','accepted_receipt_body_sha256','qualified_population','qualified_population_sha256','billing_bounds_sha256','approval_packet_sha256','source_export_scope_sha256','grounding_sha256']
 OR j-ARRAY['schema_version','job_schema','dispatch_id','workspace_id','artifact_id','batch_id','purpose','attempt','request','request_hash','permission_hash','processing_request','approvals','pricing','register_hash','input_tokens_upper_bound','admission_id','thread_id','thread_revision','employee_event_id','original_sha256','query_sha256','qualified_model_id','model_version','model_content_hash','accepted_projection_event_id','accepted_receipt_body_sha256','qualified_population','qualified_population_sha256','billing_bounds_sha256','approval_packet_sha256','source_export_scope_sha256','grounding_sha256']<>'{}'::jsonb
 OR j->'schema_version'<>'1'::jsonb OR j->'attempt'<>'1'::jsonb
 OR j->>'job_schema' IS DISTINCT FROM(CASE WHEN a.effect_purpose='qualified-query-embedding-v1' THEN 'qualified-query-embedding-dispatch-v1' ELSE 'qualified-answer-synthesis-dispatch-v1' END)
 OR j->>'purpose' IS DISTINCT FROM a.effect_purpose OR j->'processing_request'->>'purpose' IS DISTINCT FROM a.effect_purpose
 OR j->'request'->>'model' IS DISTINCT FROM a.provider_model OR j->'pricing'->>'model' IS DISTINCT FROM a.provider_model
 OR j->>'workspace_id' IS DISTINCT FROM a.workspace_id::text OR j->>'admission_id' IS DISTINCT FROM a.admission_id::text
 OR j->>'thread_id' IS DISTINCT FROM a.thread_id::text OR j->'thread_revision' IS DISTINCT FROM context->'thread_revision'
 OR j->>'employee_event_id' IS DISTINCT FROM wanted_employee_event::text OR j->'original_sha256' IS DISTINCT FROM context->'original_sha256'
 OR j->'query_sha256' IS DISTINCT FROM context->'query_sha256'
 OR j->>'qualified_model_id' IS DISTINCT FROM a.model_id::text OR j->'model_version' IS DISTINCT FROM context->'model_version'
 OR j->'model_content_hash' IS DISTINCT FROM context->'model_content_hash'
 OR j->'qualified_population' IS DISTINCT FROM context->'source_refs'
 OR j->>'qualified_population_sha256' IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('source_refs',context->'source_refs')),'UTF8')),'hex')
 OR j->>'batch_id' IS DISTINCT FROM a.allocation_batch::text OR j->>'register_hash' IS DISTINCT FROM a.register_hash
 OR j->>'billing_bounds_sha256' IS DISTINCT FROM a.billing_bounds_sha256
 OR j->>'approval_packet_sha256' IS DISTINCT FROM a.approval_packet_sha256
 OR j->>'source_export_scope_sha256' IS DISTINCT FROM a.source_export_scope_sha256
 OR j->'processing_request'->>'account' IS DISTINCT FROM a.account OR j->'processing_request'->>'terms_hash' IS DISTINCT FROM a.terms_hash
 OR encode(sha256(convert_to(oracle2._replacement_metadata_json(j->'pricing'),'UTF8')),'hex') IS DISTINCT FROM a.pricing_sha256
 OR encode(sha256(convert_to(oracle2._replacement_metadata_json(j->'approvals'),'UTF8')),'hex') IS DISTINCT FROM a.approval_packet_sha256
 OR j->>'request_hash' IS DISTINCT FROM encode(sha256(convert_to(oracle2._replacement_metadata_json(j->'request'),'UTF8')),'hex')
 OR jsonb_typeof(j->'permission_hash') IS DISTINCT FROM 'string' OR jsonb_typeof(j->'grounding_sha256') IS DISTINCT FROM 'string'
 OR j->>'permission_hash' !~ '^[0-9a-f]{64}$' OR j->>'grounding_sha256' !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(j->'input_tokens_upper_bound') IS DISTINCT FROM 'number' OR j->>'input_tokens_upper_bound' !~ '^[1-9][0-9]{0,8}$'
 THEN RAISE insufficient_privilege USING MESSAGE='exact fixed current derived question job required'; END IF;
 IF a.effect_purpose='qualified-query-embedding-v1' AND(j->'request'->'input' IS DISTINCT FROM jsonb_build_array(context->>'original_text')
 OR j->'request'->'dimensions'<>'256'::jsonb OR j->'request'->>'encoding_format'<>'float')
 THEN RAISE insufficient_privilege USING MESSAGE='one exact original query embedding required'; END IF;
 supplied_id:=(j->>'dispatch_id')::uuid;
 IF j->>'dispatch_id' IS DISTINCT FROM supplied_id::text OR j->>'artifact_id' IS DISTINCT FROM supplied_id::text THEN RAISE insufficient_privilege; END IF;
 accepted:=(context->'delivery'->'retained_receipt'->>'event_id')::uuid;
 receipt_hash:=context->'delivery'->>'retained_receipt_body_sha256';
 IF j->>'accepted_projection_event_id' IS DISTINCT FROM accepted::text OR j->>'accepted_receipt_body_sha256' IS DISTINCT FROM receipt_hash
 THEN RAISE insufficient_privilege USING MESSAGE='actual retained accepted ACK differs'; END IF;
 -- GLOBAL identity excludes admission/runtime/batch/allocation generations.
 scope_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_array(a.workspace_id,a.thread_id,wanted_employee_event,a.effect_purpose,
 context->>'query_sha256',a.model_id,context->'model_version',context->>'model_content_hash',accepted,receipt_hash)),'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('oracle-question-effect:'||scope_hash,0));
 SELECT * INTO o FROM oracle2.question_effect_operations_v1 WHERE workspace_id=a.workspace_id AND thread_id=a.thread_id
 AND employee_event_id=wanted_employee_event AND effect_purpose=a.effect_purpose AND query_sha256=context->>'query_sha256'
 AND model_id=a.model_id AND model_version=(context->>'model_version')::integer AND model_content_hash=context->>'model_content_hash'
 AND accepted_projection_event_id=accepted AND accepted_receipt_body_sha256=receipt_hash;
 job_hash:=encode(sha256(job_bytes),'hex');
 IF o.operation_id IS NOT NULL THEN
  IF o.job_bytes IS DISTINCT FROM job_bytes THEN RAISE unique_violation USING MESSAGE='global question effect already claimed; changed job cannot reset UNKNOWN'; END IF;
  RETURN jsonb_build_object('schema_version',1,'operation_id',o.operation_id,'dispatch_allowed',false,'state','unknown','job_sha256',o.job_sha256,'operation_deadline',o.operation_deadline);
 END IF;
 INSERT INTO oracle2.question_effect_operations_v1(operation_id,admission_id,workspace_id,thread_id,employee_event_id,effect_purpose,query_sha256,
 model_id,model_version,model_content_hash,accepted_projection_event_id,accepted_receipt_body_sha256,valid_at,known_at,job_bytes,job_sha256,operation_deadline)
 VALUES(supplied_id,a.admission_id,a.workspace_id,a.thread_id,wanted_employee_event,a.effect_purpose,context->>'query_sha256',a.model_id,
 (context->>'model_version')::integer,context->>'model_content_hash',accepted,receipt_hash,valid_at,known_at,job_bytes,job_hash,(context->>'valid_until')::timestamptz);
 again:=oracle2._question_effect_input_v1(wanted_admission,wanted_employee_event,valid_at,known_at,deadline);
 IF ((again-'checked_at'-'valid_until'-'delivery')||jsonb_build_object('delivery',(again->'delivery')-'checked_at'-'valid_until')) IS DISTINCT FROM((context-'checked_at'-'valid_until'-'delivery')||jsonb_build_object('delivery',(context->'delivery')-'checked_at'-'valid_until')) THEN RAISE serialization_failure USING MESSAGE='question authority changed during claim'; END IF;
 RETURN jsonb_build_object('schema_version',1,'operation_id',supplied_id,'dispatch_allowed',true,'state','claimed','job_sha256',job_hash,'operation_deadline',(context->>'valid_until')::timestamptz);
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE insufficient_privilege USING MESSAGE='invalid bounded question job';
END $$;
REVOKE ALL ON FUNCTION oracle2.claim_question_effect_v1(uuid,uuid,timestamptz,timestamptz,bytea,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.question_effect_status_v1(wanted_operation uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE o oracle2.question_effect_operations_v1;context jsonb;observations jsonb;
BEGIN
 SELECT * INTO o FROM oracle2.question_effect_operations_v1 WHERE operation_id=wanted_operation;
 IF o.operation_id IS NULL OR deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 context:=oracle2._question_effect_input_v1(o.admission_id,o.employee_event_id,o.valid_at,o.known_at,least(deadline,o.operation_deadline));
 IF context->>'model_content_hash' IS DISTINCT FROM o.model_content_hash OR context->>'model_version' IS DISTINCT FROM o.model_version::text
 OR context->'delivery'->>'retained_receipt_body_sha256' IS DISTINCT FROM o.accepted_receipt_body_sha256
 THEN RAISE insufficient_privilege USING MESSAGE='question model/ACK changed'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('observation_id',observation_id,'observation_utf8',convert_from(observation_bytes,'UTF8'),
 'observation_sha256',observation_sha256,'recorded_at',created_at) ORDER BY created_at,observation_id),'[]'::jsonb)
 INTO observations FROM oracle2.question_effect_observations_v1 WHERE operation_id=o.operation_id;
 RETURN jsonb_build_object('schema_version',1,'operation_id',o.operation_id,'state','unknown','dispatch_allowed',false,
 'job_utf8',convert_from(o.job_bytes,'UTF8'),'job_sha256',o.job_sha256,'operation_deadline',o.operation_deadline,'observations',observations,'context',context);
END $$;
REVOKE ALL ON FUNCTION oracle2.question_effect_status_v1(uuid,timestamptz) FROM PUBLIC;

-- Independent ORIGINAL cost scope. No source/question/body is returned or
-- reauthorized, even after source/recipient/thread/read appointment expiry.
CREATE FUNCTION oracle2._question_effect_cost_context_v1(wanted_operation uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE o oracle2.question_effect_operations_v1;a oracle2.question_effect_admissions_v1;
 r oracle2.hosting_role_runtime_admissions;login oid;owner_oid oid;until_at timestamptz;cap record;function_oid oid;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 IF deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp()
 OR NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl) THEN RAISE insufficient_privilege; END IF;
 SELECT oid INTO login FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin AND NOT(rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication);
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 IF login IS NULL OR owner_oid IS DISTINCT FROM(SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR current_setting('role') NOT IN('none',SESSION_USER::text)
 OR EXISTS(SELECT 1 FROM pg_roles role WHERE role.oid<>login AND(pg_has_role(login,role.oid,'MEMBER') OR pg_has_role(login,role.oid,'SET') OR pg_has_role(login,role.oid,'USAGE')))
 THEN RAISE insufficient_privilege USING MESSAGE='actual separate original cost worker required'; END IF;
 SELECT * INTO o FROM oracle2.question_effect_operations_v1 WHERE operation_id=wanted_operation;
 SELECT * INTO a FROM oracle2.question_effect_admissions_v1 WHERE admission_id=o.admission_id AND role_name=SESSION_USER FOR SHARE;
 SELECT * INTO r FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 IF o.operation_id IS NULL OR a.admission_id IS NULL OR a.cost_settlement_sha256 IS NULL OR a.cost_settlement_expires_at IS NULL
 OR least(a.cost_settlement_expires_at,a.original_horizon)<=clock_timestamp() OR a.issued_at>clock_timestamp()
 OR r.role_name IS NULL OR(r.runtime_hash,r.registry_hash) IS DISTINCT FROM(a.runtime_hash,a.registry_hash)
 OR r.expires_at<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='separately installed current ORIGINAL settlement authority required'; END IF;
 until_at:=least(deadline,a.cost_settlement_expires_at,a.original_horizon,r.expires_at,
 oracle2._replacement_scope(a.workspace_id,a.worker_principal_id,'question-effect-cost-settlement:'||a.admission_id::text));
 IF (SELECT count(*) FROM jsonb_object_keys(a.catalog))<>6 THEN RAISE insufficient_privilege; END IF;
 FOR cap IN SELECT * FROM jsonb_each_text(a.catalog) LOOP
 IF cap.key NOT IN('oracle2.question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz)',
 'oracle2.claim_question_effect_v1(uuid,uuid,timestamptz,timestamptz,bytea,timestamptz)',
 'oracle2.question_effect_status_v1(uuid,timestamptz)',
 'oracle2.record_question_effect_observation_v1(uuid,bytea,timestamptz)',
 'oracle2._question_effect_input_v1(uuid,uuid,timestamptz,timestamptz,timestamptz)',
 'oracle2._question_effect_cost_context_v1(uuid,timestamptz)') OR cap.value !~ '^[0-9a-f]{64}$' THEN RAISE insufficient_privilege; END IF;
 function_oid:=to_regprocedure(cap.key);
 IF NOT EXISTS(SELECT 1 FROM pg_proc p WHERE p.oid=function_oid AND p.proowner=owner_oid AND p.prosecdef
 AND p.provolatile='v' AND p.proconfig=ARRAY['search_path=pg_catalog, oracle2']
 AND encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')=cap.value) THEN RAISE insufficient_privilege USING MESSAGE='current exact cost capability catalog required'; END IF;
 IF cap.key LIKE 'oracle2._question%' THEN
 IF EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x WHERE p.oid=function_oid AND x.grantee<>p.proowner) THEN RAISE insufficient_privilege; END IF;
 ELSE
 IF NOT EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x WHERE p.oid=function_oid AND x.grantee=login AND x.privilege_type='EXECUTE' AND NOT x.is_grantable)
 OR EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x LEFT JOIN pg_roles role ON role.oid=x.grantee WHERE p.oid=function_oid AND x.grantee<>p.proowner
 AND(x.is_grantable OR role.oid IS NULL OR NOT role.rolcanlogin OR role.rolsuper OR role.rolbypassrls OR role.rolcreatedb OR role.rolcreaterole OR role.rolreplication
 OR EXISTS(SELECT 1 FROM pg_roles other WHERE other.oid<>role.oid AND(pg_has_role(role.oid,other.oid,'MEMBER') OR pg_has_role(role.oid,other.oid,'SET') OR pg_has_role(role.oid,other.oid,'USAGE'))))) THEN RAISE insufficient_privilege; END IF;
 END IF;
 END LOOP;
 IF until_at<=clock_timestamp() THEN RAISE insufficient_privilege; END IF;
 RETURN jsonb_build_object('schema_version',1,'purpose','question-effect-cost-context-v1','operation_id',o.operation_id,'admission_id',a.admission_id,
 'workspace_id',a.workspace_id,'effect_purpose',a.effect_purpose,'worker_principal_id',a.worker_principal_id,'config_sha256',a.config_sha256,
 'account',a.account,'key_fingerprint',a.key_fingerprint,'ledger_registry_hash',a.ledger_registry_hash,'terms_hash',a.terms_hash,
 'allocation_batch',a.allocation_batch,'allocation_hash',a.allocation_hash,'allocation_receipt_hash',a.allocation_receipt_hash,
 'job_sha256',o.job_sha256,'original_operation_deadline',o.operation_deadline,'cost_settlement_sha256',a.cost_settlement_sha256,'original_horizon',a.original_horizon,
 'cost_settlement_expires_at',a.cost_settlement_expires_at,'checked_at',clock_timestamp(),'valid_until',until_at);
END $$;
REVOKE ALL ON FUNCTION oracle2._question_effect_cost_context_v1(uuid,timestamptz) FROM PUBLIC;

CREATE FUNCTION oracle2.record_question_effect_observation_v1(wanted_operation uuid,observation_bytes bytea,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE status jsonb;q jsonb;prior oracle2.question_effect_observations_v1;sha text;identifier uuid;
BEGIN
 status:=oracle2._question_effect_cost_context_v1(wanted_operation,deadline);
 IF octet_length(observation_bytes) NOT BETWEEN 1 AND 65536 THEN RAISE insufficient_privilege; END IF;
 q:=convert_from(observation_bytes,'UTF8')::jsonb;
 IF convert_to(oracle2._replacement_metadata_json(q),'UTF8')=observation_bytes
 AND q ?& ARRAY['schema_version','protocol','operation_id']
 AND q-ARRAY['schema_version','protocol','operation_id']='{}'::jsonb
 AND q->'schema_version'='1'::jsonb AND q->>'protocol'='question-effect-cost-check-v1'
 AND q->>'operation_id'=wanted_operation::text THEN
 RETURN jsonb_build_object('schema_version',1,'operation_id',wanted_operation,'dispatch_allowed',false,'state','unknown','cost_context',status);
 END IF;
 IF convert_to(oracle2._replacement_metadata_json(q),'UTF8') IS DISTINCT FROM observation_bytes
 OR NOT q ?& ARRAY['schema_version','protocol','observation_id','operation_id','outcome','reservation_id','wire_sha256','native_receipt_sha256','settled_response_sha256']
 OR q-ARRAY['schema_version','protocol','observation_id','operation_id','outcome','reservation_id','wire_sha256','native_receipt_sha256','settled_response_sha256']<>'{}'::jsonb
 OR q->'schema_version'<>'1'::jsonb OR q->>'protocol'<>'question-effect-observation-v1' OR q->>'operation_id' IS DISTINCT FROM wanted_operation::text
 OR jsonb_typeof(q->'observation_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'reservation_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(q->'outcome') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'wire_sha256') IS DISTINCT FROM 'string'
 OR jsonb_typeof(q->'native_receipt_sha256') IS DISTINCT FROM 'string'
 OR q->>'outcome' NOT IN('observed-settlement','unknown')
 OR q->>'wire_sha256' !~ '^[0-9a-f]{64}$' OR q->>'native_receipt_sha256' !~ '^[0-9a-f]{64}$'
 OR NOT(q->'settled_response_sha256'='null'::jsonb OR q->>'settled_response_sha256' ~ '^[0-9a-f]{64}$')
 OR q->>'outcome'='unknown' AND q->'settled_response_sha256'<>'null'::jsonb
 THEN RAISE insufficient_privilege USING MESSAGE='closed actual custody observation required; metadata is not paid-wire authority'; END IF;
 identifier:=(q->>'observation_id')::uuid;PERFORM(q->>'reservation_id')::uuid;
 sha:=encode(sha256(observation_bytes),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('oracle-question-observation:'||wanted_operation::text,0));
 SELECT * INTO prior FROM oracle2.question_effect_observations_v1 WHERE observation_id=identifier;
 IF prior.observation_id IS NOT NULL THEN
  IF(prior.operation_id,prior.observation_bytes) IS DISTINCT FROM(wanted_operation,observation_bytes) THEN RAISE unique_violation; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM oracle2.question_effect_observations_v1 WHERE operation_id=wanted_operation AND observation_sha256=sha) THEN RAISE unique_violation; END IF;
  INSERT INTO oracle2.question_effect_observations_v1 VALUES(identifier,wanted_operation,observation_bytes,sha,clock_timestamp());
 END IF;
 PERFORM oracle2._question_effect_cost_context_v1(wanted_operation,deadline);
 RETURN jsonb_build_object('schema_version',1,'observation_id',identifier,'operation_id',wanted_operation,'dispatch_allowed',false,'state','unknown','cost_context',status);
END $$;
REVOKE ALL ON FUNCTION oracle2.record_question_effect_observation_v1(uuid,bytea,timestamptz) FROM PUBLIC;
-- Exact independently installed direct LOGIN EXECUTE only; none installed here.
