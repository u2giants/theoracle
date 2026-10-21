-- Dedicated Oracle operational conversation owner. No installed appointment or truth grant.
DO $owner$ BEGIN
 IF (SELECT nspowner FROM pg_namespace WHERE nspname='oracle2') IS DISTINCT FROM
 (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER) THEN RAISE EXCEPTION 'dedicated schema owner required'; END IF;
END $owner$;
CREATE TABLE oracle2.conversation_threads_v1 (
 thread_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, principal_id uuid NOT NULL,
 mode text NOT NULL CHECK(mode IN ('ordinary','interview')), revision integer NOT NULL CHECK(revision>0),
 topic text NOT NULL CHECK(length(topic) BETWEEN 1 AND 1000), language text NOT NULL,
 state text NOT NULL CHECK(state IN ('active','paused','recap','stopped')),
 question_count integer NOT NULL CHECK(question_count BETWEEN 0 AND 8), pending_question uuid,
 segment_started_at timestamptz NOT NULL, segment_deadline timestamptz NOT NULL,
 reviewed_revision integer, reviewed_sha256 text,
 CHECK(segment_deadline=segment_started_at+interval '10 minutes'),
 CHECK((reviewed_revision IS NULL)=(reviewed_sha256 IS NULL)));
CREATE TABLE oracle2.conversation_events_v1 (
 event_id uuid PRIMARY KEY, thread_id uuid NOT NULL REFERENCES oracle2.conversation_threads_v1,
 workspace_id uuid NOT NULL, principal_id uuid NOT NULL, sequence integer NOT NULL CHECK(sequence>0),
 command_id uuid NOT NULL, command_sha256 text NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{64}$'),
 command_bytes bytea NOT NULL CHECK(octet_length(command_bytes) BETWEEN 1 AND 65536),
 operation text NOT NULL, origin text NOT NULL CHECK(origin IN ('employee','control','display')),
 turn_id uuid, original_text text, original_language text, original_sha256 text,
 corrects_event_id uuid REFERENCES oracle2.conversation_events_v1, corrects_original_sha256 text,
 question_id uuid, need text, response_kind text, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(thread_id,sequence), UNIQUE(workspace_id,principal_id,command_id), UNIQUE(thread_id,turn_id),
 CHECK((original_text IS NULL)=(original_sha256 IS NULL)),
 CHECK(original_sha256 IS NULL OR original_sha256=encode(sha256(convert_to(original_text,'UTF8')),'hex')));
CREATE TRIGGER immutable_conversation_events_v1 BEFORE UPDATE OR DELETE ON oracle2.conversation_events_v1
 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
REVOKE ALL ON oracle2.conversation_threads_v1,oracle2.conversation_events_v1 FROM PUBLIC,
 oracle2_replacement_requester,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,
 oracle2_gateway_metadata,oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer;
CREATE FUNCTION oracle2._conversation_context_v1(deadline timestamptz)
 RETURNS oracle2.hosting_request_principal_admissions LANGUAGE plpgsql VOLATILE SECURITY DEFINER
 SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE; until timestamptz;
BEGIN
 a:=oracle2._replacement_request_context();
 IF deadline IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() OR NOT EXISTS(
 SELECT 1 FROM oracle2.appointments WHERE workspace_id=a.workspace_id AND actor_id=a.principal_id
 AND scope='conversation-self' AND revoked_at IS NULL AND expires_at>clock_timestamp()) THEN
 RAISE insufficient_privilege USING MESSAGE='separate current conversation appointment required'; END IF;
 until:=oracle2._replacement_scope(a.workspace_id,a.principal_id,'conversation-self');
 a.expires_at:=least(a.expires_at,deadline,until); RETURN a;
END $fn$;
CREATE FUNCTION oracle2._conversation_request_v1(raw bytea)
 RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE q jsonb;
BEGIN
 IF raw IS NULL OR octet_length(raw) NOT BETWEEN 1 AND 65536 THEN RAISE invalid_parameter_value USING MESSAGE='bounded conversation command required'; END IF;
 q:=convert_from(raw,'UTF8')::jsonb;
 IF jsonb_typeof(q)<>'object' OR convert_to(oracle2._replacement_metadata_json(q),'UTF8')<>raw
 OR q->'schema_version' IS DISTINCT FROM '1'::jsonb OR jsonb_typeof(q->'command_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(q->'caller_deadline') IS DISTINCT FROM 'string' OR q->>'caller_deadline' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
 THEN RAISE invalid_parameter_value USING MESSAGE='exact canonical conversation command required'; END IF;
 PERFORM (q->>'command_id')::uuid; RETURN q;
END $fn$;
CREATE FUNCTION oracle2._conversation_result_v1(t oracle2.conversation_threads_v1)
 RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE events jsonb; recap jsonb; recap_hash text;
BEGIN
 SELECT coalesce(jsonb_agg(jsonb_build_object('event_id',e.event_id,'sequence',e.sequence,'operation',e.operation,
 'origin',e.origin,'turn_id',e.turn_id,'original_text',e.original_text,'original_language',e.original_language,
 'original_sha256',e.original_sha256,'corrects_event_id',e.corrects_event_id,'question_id',e.question_id,
 'need',e.need,'response_kind',e.response_kind,'payload',e.payload,'created_at',e.created_at) ORDER BY e.sequence),'[]'::jsonb)
 INTO events FROM oracle2.conversation_events_v1 e WHERE e.thread_id=t.thread_id;
 recap:=jsonb_build_object('thread_id',t.thread_id,'revision',t.revision,'events',events,
 'reported',true,'confirmed',false,'company_policy_confirmed',false,'policy_authority',false);
 recap_hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(recap),'UTF8')),'hex');
 RETURN jsonb_build_object('schema_version',1,'thread_id',t.thread_id,'workspace_id',t.workspace_id,
 'principal_id',t.principal_id,'mode',t.mode,'revision',t.revision,'topic',t.topic,'language',t.language,
 'state',t.state,'question_count',t.question_count,'pending_question_id',t.pending_question,
 'segment_started_at',t.segment_started_at,'segment_deadline',t.segment_deadline,'events',events,
 'recap',recap,'recap_sha256',recap_hash,'reviewed_revision',t.reviewed_revision,
 'reviewed_sha256',t.reviewed_sha256,'company_policy_confirmed',false,'source_qualified',false);
END $fn$;
CREATE FUNCTION oracle2.create_conversation_v1(command_bytes bytea)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE q jsonb; a oracle2.hosting_request_principal_admissions%ROWTYPE; t oracle2.conversation_threads_v1%ROWTYPE;
 prior oracle2.conversation_events_v1%ROWTYPE; id uuid; question uuid; stamp timestamptz:=clock_timestamp();
BEGIN
 q:=oracle2._conversation_request_v1(command_bytes); a:=oracle2._conversation_context_v1((q->>'caller_deadline')::timestamptz);
 IF NOT q ?& ARRAY['schema_version','command_id','caller_deadline','mode','topic','language'] OR
 q-ARRAY['schema_version','command_id','caller_deadline','mode','topic','language']<>'{}'::jsonb OR
 jsonb_typeof(q->'mode') IS DISTINCT FROM 'string' OR q->>'mode' NOT IN ('ordinary','interview') OR
 jsonb_typeof(q->'topic') IS DISTINCT FROM 'string' OR length(btrim(q->>'topic')) NOT BETWEEN 1 AND 1000 OR
 jsonb_typeof(q->'language') IS DISTINCT FROM 'string' OR q->>'language' !~ '^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$' OR length(q->>'language')>40 THEN
 RAISE invalid_parameter_value USING MESSAGE='strict conversation creation required'; END IF;
 -- Existing requester auth lock serializes per-workspace idempotency before inserting.
 SELECT * INTO prior FROM oracle2.conversation_events_v1 WHERE workspace_id=a.workspace_id AND principal_id=a.principal_id AND command_id=(q->>'command_id')::uuid;
 IF FOUND THEN
 IF prior.command_bytes<>command_bytes THEN RAISE unique_violation USING MESSAGE='conversation command collision'; END IF;
 SELECT * INTO t FROM oracle2.conversation_threads_v1 WHERE thread_id=prior.thread_id;
 RETURN oracle2._conversation_result_v1(t); END IF;
 id:=gen_random_uuid(); IF q->>'mode'='interview' THEN question:=gen_random_uuid(); END IF;
 INSERT INTO oracle2.conversation_threads_v1 VALUES(id,a.workspace_id,a.principal_id,q->>'mode',1,q->>'topic',q->>'language',
 'active',CASE WHEN question IS NULL THEN 0 ELSE 1 END,question,stamp,stamp+interval '10 minutes',NULL,NULL) RETURNING * INTO t;
 INSERT INTO oracle2.conversation_events_v1(event_id,thread_id,workspace_id,principal_id,sequence,command_id,command_sha256,command_bytes,operation,origin,question_id,need,payload)
 VALUES(gen_random_uuid(),id,a.workspace_id,a.principal_id,1,(q->>'command_id')::uuid,encode(sha256(command_bytes),'hex'),command_bytes,'create','control',question,
 CASE WHEN question IS NULL THEN NULL ELSE 'recent-example' END,jsonb_build_object('explicit_interview_consent',q->>'mode'='interview'));
 PERFORM oracle2._conversation_context_v1(a.expires_at);
 -- Store exact response for uncertain acknowledgement readback; payload is append-only below.
 RETURN oracle2._conversation_result_v1(t);
END $fn$;
CREATE FUNCTION oracle2.apply_conversation_command_v1(command_bytes bytea)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE q jsonb; a oracle2.hosting_request_principal_admissions%ROWTYPE; t oracle2.conversation_threads_v1%ROWTYPE;
 prior oracle2.conversation_events_v1%ROWTYPE; target oracle2.conversation_events_v1%ROWTYPE;
 op text; fields text[]; id uuid:=gen_random_uuid(); question uuid; selected text; original text; lang text; turn uuid;
 target_id uuid; target_hash text; response text; payload jsonb:='{}'; stamp timestamptz:=clock_timestamp();
 snapshot jsonb; selected_index integer; allowed text[]:=ARRAY['recent-example','trigger','steps','handoffs','result','exceptions','decision-criteria','conflicts'];
BEGIN
 q:=oracle2._conversation_request_v1(command_bytes); a:=oracle2._conversation_context_v1((q->>'caller_deadline')::timestamptz);
 IF jsonb_typeof(q->'thread_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'expected_revision') IS DISTINCT FROM 'number'
 OR q->>'expected_revision' !~ '^[1-9][0-9]{0,8}$' OR jsonb_typeof(q->'operation') IS DISTINCT FROM 'string' THEN
 RAISE invalid_parameter_value USING MESSAGE='strict conversation selector required'; END IF;
 SELECT * INTO t FROM oracle2.conversation_threads_v1 WHERE thread_id=(q->>'thread_id')::uuid
 AND workspace_id=a.workspace_id AND principal_id=a.principal_id FOR UPDATE;
 IF NOT FOUND THEN RAISE insufficient_privilege USING MESSAGE='own conversation unavailable'; END IF;
 SELECT * INTO prior FROM oracle2.conversation_events_v1 WHERE workspace_id=a.workspace_id AND principal_id=a.principal_id AND command_id=(q->>'command_id')::uuid;
 IF FOUND THEN
 IF prior.command_bytes<>command_bytes THEN RAISE unique_violation USING MESSAGE='conversation command collision'; END IF;
 RETURN oracle2._conversation_result_v1(t); END IF;
 IF t.revision<>(q->>'expected_revision')::integer THEN RAISE serialization_failure USING MESSAGE='conversation CAS conflict'; END IF;
 IF t.revision>=1024 OR (SELECT coalesce(sum(octet_length(e.command_bytes)),0) FROM oracle2.conversation_events_v1 e WHERE e.thread_id=t.thread_id)+octet_length(command_bytes)>1048576 THEN RAISE program_limit_exceeded USING MESSAGE='conversation history capacity reached; retained history unchanged'; END IF;
 fields:=ARRAY['schema_version','command_id','caller_deadline','thread_id','expected_revision','operation']; op:=q->>'operation';
 IF op IN ('employee_turn','correct','skip','unknown','referral') THEN
 fields:=fields||ARRAY['turn_id','text','language'];
 IF jsonb_typeof(q->'turn_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'text') IS DISTINCT FROM 'string'
 OR octet_length(q->>'text') NOT BETWEEN 1 AND 32768 OR length(btrim(q->>'text'))<1
 OR jsonb_typeof(q->'language') IS DISTINCT FROM 'string' OR q->>'language' !~ '^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$' OR length(q->>'language')>40 THEN
 RAISE invalid_parameter_value USING MESSAGE='exact original employee turn required'; END IF;
 turn:=(q->>'turn_id')::uuid; original:=q->>'text';lang:=q->>'language';
 response:=CASE WHEN op IN ('skip','unknown','referral') THEN op ELSE 'reported' END;
 IF op='correct' THEN
 fields:=fields||ARRAY['corrects_event_id','corrects_original_sha256'];
 IF jsonb_typeof(q->'corrects_event_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'corrects_original_sha256') IS DISTINCT FROM 'string' THEN
 RAISE invalid_parameter_value USING MESSAGE='exact correction ancestry required'; END IF;
 target_id:=(q->>'corrects_event_id')::uuid;target_hash:=q->>'corrects_original_sha256';
 SELECT * INTO target FROM oracle2.conversation_events_v1 WHERE event_id=target_id AND thread_id=t.thread_id AND origin='employee';
 IF NOT FOUND OR target.original_sha256 IS DISTINCT FROM target_hash OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 WHERE corrects_event_id=target_id) THEN
 RAISE serialization_failure USING MESSAGE='foreign stale or changed correction original'; END IF;
 selected:=target.need;question:=target.question_id;
 ELSE
 IF t.state<>'active' THEN RAISE object_not_in_prerequisite_state USING MESSAGE='conversation is not active'; END IF;
 question:=t.pending_question;
 SELECT CASE WHEN e.payload->>'next_question_id'=question::text THEN e.payload->>'next_need' ELSE e.need END INTO selected FROM oracle2.conversation_events_v1 e WHERE e.thread_id=t.thread_id AND (e.question_id=question OR e.payload->>'next_question_id'=question::text) ORDER BY e.sequence DESC LIMIT 1;
 END IF;
 payload:=jsonb_build_object('reported',response='reported','confirmed',false,'policy_authority',false,'qualification_state','pending',
 'proposal_text',CASE WHEN response='reported' THEN original ELSE NULL END,'missing_reason',CASE WHEN response<>'reported' THEN response ELSE NULL END,
 'direct_question_answer',CASE WHEN position('?' in original)>0 OR position('？' in original)>0 THEN 'No qualified answer is available for this question yet.' ELSE NULL END);
 t.reviewed_revision:=NULL;t.reviewed_sha256:=NULL;
 IF op<>'correct' AND t.mode='interview' AND position('?' in original)=0 AND position('？' in original)=0 THEN
 IF t.question_count>=8 OR stamp>=t.segment_deadline THEN t.state:='recap';t.pending_question:=NULL;
 ELSE
 selected_index:=t.question_count+1;t.question_count:=selected_index;t.pending_question:=gen_random_uuid();
 END IF;
 END IF;
 ELSIF op='pause' THEN IF t.state<>'active' THEN RAISE object_not_in_prerequisite_state USING MESSAGE='only active conversation can pause'; END IF;t.state:='paused';
 ELSIF op='resume' THEN
 IF t.state<>'paused' THEN RAISE object_not_in_prerequisite_state USING MESSAGE='only paused conversation can resume'; END IF;
 t.segment_started_at:=stamp;t.segment_deadline:=stamp+interval '10 minutes';
 IF t.mode='interview' AND t.question_count>=8 AND t.pending_question IS NULL THEN t.state:='recap'; ELSE t.state:='active'; END IF;
 ELSIF op IN ('stop','review_recap') THEN
 IF op='review_recap' THEN
 fields:=fields||ARRAY['recap_revision','recap_sha256'];snapshot:=oracle2._conversation_result_v1(t);
 IF q->'recap_revision' IS DISTINCT FROM to_jsonb(t.revision) OR q->>'recap_sha256' IS DISTINCT FROM snapshot->>'recap_sha256' THEN
 RAISE serialization_failure USING MESSAGE='review exact current recap first'; END IF;
 t.reviewed_revision:=t.revision;t.reviewed_sha256:=q->>'recap_sha256';
 payload:=jsonb_build_object('own_account_acknowledged',true,'company_policy_confirmed',false,'account_acknowledgement_only',true);
 END IF;
 t.state:=CASE WHEN op='stop' THEN 'stopped' ELSE 'recap' END;t.pending_question:=NULL;
 ELSIF op='claim_response' THEN
 fields:=fields||ARRAY['event_id','dispatch_id','job_sha256','request_sha256'];
 IF jsonb_typeof(q->'event_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'dispatch_id') IS DISTINCT FROM 'string'
 OR q->>'job_sha256' !~ '^[0-9a-f]{64}$' OR q->>'request_sha256' !~ '^[0-9a-f]{64}$' THEN RAISE invalid_parameter_value USING MESSAGE='fixed observed conversation job required'; END IF;
 SELECT * INTO target FROM oracle2.conversation_events_v1 WHERE event_id=(q->>'event_id')::uuid AND thread_id=t.thread_id AND origin='employee';
 IF NOT FOUND OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 e WHERE e.thread_id=t.thread_id AND e.operation='claim_response'
 AND (e.payload->>'event_id'=q->>'event_id' OR e.payload->>'dispatch_id'=q->>'dispatch_id')) THEN RAISE unique_violation USING MESSAGE='conversation operation already retained; outcome UNKNOWN; no resend'; END IF;
 payload:=jsonb_build_object('event_id',q->>'event_id','dispatch_id',(q->>'dispatch_id')::uuid,'job_sha256',q->>'job_sha256',
 'request_sha256',q->>'request_sha256','base_revision',t.revision,'state','UNKNOWN','resend_authorized',false);
 ELSIF op='complete_response' THEN
 fields:=fields||ARRAY['dispatch_id','response_text','native_receipt_sha256'];
 IF jsonb_typeof(q->'dispatch_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'response_text') IS DISTINCT FROM 'string'
 OR octet_length(q->>'response_text') NOT BETWEEN 1 AND 32768 OR q->>'native_receipt_sha256' !~ '^[0-9a-f]{64}$' THEN RAISE invalid_parameter_value USING MESSAGE='fixed retained display response required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 e WHERE e.thread_id=t.thread_id AND e.operation='claim_response' AND e.payload->>'dispatch_id'=q->>'dispatch_id')
 OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 e WHERE e.thread_id=t.thread_id AND e.operation='complete_response' AND e.payload->>'dispatch_id'=q->>'dispatch_id') THEN
 RAISE unique_violation USING MESSAGE='single retained conversation response required'; END IF;
 payload:=jsonb_build_object('dispatch_id',q->>'dispatch_id','display_text',q->>'response_text','native_receipt_sha256',q->>'native_receipt_sha256',
 'display_only',true,'source_qualified',false,'company_policy_confirmed',false);
 ELSIF op='claim_original' THEN
 fields:=fields||ARRAY['event_id'];
 IF jsonb_typeof(q->'event_id') IS DISTINCT FROM 'string' THEN RAISE invalid_parameter_value USING MESSAGE='exact retained employee original required'; END IF;
 SELECT * INTO target FROM oracle2.conversation_events_v1 WHERE event_id=(q->>'event_id')::uuid AND thread_id=t.thread_id AND origin='employee' AND response_kind='reported';
 IF NOT FOUND OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 correction WHERE correction.corrects_event_id=target.event_id)
 OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 e WHERE e.thread_id=t.thread_id AND e.operation='claim_original' AND e.payload->>'event_id'=q->>'event_id') THEN
 RAISE unique_violation USING MESSAGE='original registration retained UNKNOWN; no automatic resubmit'; END IF;
 payload:=jsonb_build_object('event_id',target.event_id,'original_sha256',target.original_sha256,'state','UNKNOWN','resend_authorized',false);
 ELSIF op='link_original' THEN
 fields:=fields||ARRAY['event_id','source_id','source_revision'];
 IF jsonb_typeof(q->'event_id') IS DISTINCT FROM 'string' OR jsonb_typeof(q->'source_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(q->'source_revision') IS DISTINCT FROM 'number' OR q->>'source_revision' !~ '^[1-9][0-9]{0,8}$' THEN RAISE invalid_parameter_value USING MESSAGE='strict actual custody selector required'; END IF;
 SELECT * INTO target FROM oracle2.conversation_events_v1 WHERE event_id=(q->>'event_id')::uuid AND thread_id=t.thread_id
 AND workspace_id=a.workspace_id AND principal_id=a.principal_id AND origin='employee' AND response_kind='reported';
 IF NOT FOUND OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 correction WHERE correction.corrects_event_id=target.event_id)
 OR NOT EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 claim WHERE claim.thread_id=t.thread_id AND claim.operation='claim_original' AND claim.payload->>'event_id'=target.event_id::text)
 OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 link WHERE link.thread_id=t.thread_id AND link.operation='link_original' AND link.payload->>'event_id'=target.event_id::text)
 OR NOT EXISTS(SELECT 1 FROM oracle2.source_original_revisions s JOIN oracle2.source_intake_reservations_v1 r
 ON r.workspace_id=s.workspace_id AND r.source_id=s.source_id AND r.revision=s.revision
 WHERE s.workspace_id=a.workspace_id AND s.source_id=(q->>'source_id')::uuid AND s.revision=(q->>'source_revision')::integer
 AND s.media_type='text/plain' AND r.media_type=s.media_type AND r.principal_id=a.principal_id AND r.finalized_at IS NOT NULL
 AND r.filename=target.event_id::text||'.txt' AND r.original_sha256=s.original_sha256 AND r.byte_count=s.byte_count
 AND s.uploaded_by=a.principal_id AND s.original_sha256=target.original_sha256 AND s.byte_count=octet_length(target.original_text)
 AND r.custody_seal_sha256=s.custody_locator_seal_sha256) THEN
 RAISE insufficient_privilege USING MESSAGE='exact finalized own original metadata linkage required'; END IF;
 -- Metadata-only own creation linkage. This checks intake and conversation-self;
 -- it never grants or borrows source-read, private bytes, or qualification.
 PERFORM oracle2._replacement_scope(a.workspace_id,a.principal_id,'intake');
 payload:=jsonb_build_object('event_id',target.event_id,'source_id',q->>'source_id','source_revision',(q->>'source_revision')::integer,
 'original_sha256',target.original_sha256,'source_read_granted',false,'qualification_authorized',false);
 ELSE RAISE invalid_parameter_value USING MESSAGE='fixed conversation operation required'; END IF;
 IF NOT q ?& fields OR q-fields<>'{}'::jsonb THEN RAISE invalid_parameter_value USING MESSAGE='closed conversation command required'; END IF;
 IF selected_index IS NOT NULL THEN payload:=payload||jsonb_build_object('next_question_id',t.pending_question,'next_need',allowed[selected_index]); END IF;
 t.revision:=t.revision+1;
 UPDATE oracle2.conversation_threads_v1 SET revision=t.revision,state=t.state,question_count=t.question_count,pending_question=t.pending_question,
 segment_started_at=t.segment_started_at,segment_deadline=t.segment_deadline,reviewed_revision=t.reviewed_revision,reviewed_sha256=t.reviewed_sha256 WHERE thread_id=t.thread_id;
 INSERT INTO oracle2.conversation_events_v1(event_id,thread_id,workspace_id,principal_id,sequence,command_id,command_sha256,command_bytes,
 operation,origin,turn_id,original_text,original_language,original_sha256,corrects_event_id,corrects_original_sha256,question_id,need,response_kind,payload)
 VALUES(id,t.thread_id,a.workspace_id,a.principal_id,t.revision,(q->>'command_id')::uuid,encode(sha256(command_bytes),'hex'),command_bytes,
 op,CASE WHEN op='complete_response' THEN 'display' WHEN original IS NULL THEN 'control' ELSE 'employee' END,turn,original,lang,
 CASE WHEN original IS NULL THEN NULL ELSE encode(sha256(convert_to(original,'UTF8')),'hex') END,target_id,target_hash,question,selected,response,payload);
 PERFORM oracle2._conversation_context_v1(a.expires_at); RETURN oracle2._conversation_result_v1(t);
END $fn$;
CREATE FUNCTION oracle2.conversation_snapshot_v1(wanted_thread uuid,after_sequence bigint,caller_deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;t oracle2.conversation_threads_v1%ROWTYPE; result jsonb;
BEGIN
 a:=oracle2._conversation_context_v1(caller_deadline);
 IF after_sequence IS NULL OR after_sequence<0 OR after_sequence>10000 THEN RAISE invalid_parameter_value USING MESSAGE='bounded conversation page required'; END IF;
 IF wanted_thread IS NULL THEN
 SELECT jsonb_build_object('schema_version',1,'state','index','principal_id',a.principal_id,'workspace_id',a.workspace_id,
 'company_policy_confirmed',false,'source_qualified',false,'threads',coalesce(jsonb_agg(item),'[]'::jsonb)) INTO result FROM (
 SELECT jsonb_build_object('thread_id',v.thread_id,'topic',v.topic,'mode',v.mode,'state',v.state,'revision',v.revision,'language',v.language) item
 FROM oracle2.conversation_threads_v1 v WHERE v.workspace_id=a.workspace_id AND v.principal_id=a.principal_id ORDER BY v.thread_id LIMIT 20 OFFSET after_sequence) page;
 PERFORM oracle2._conversation_context_v1(a.expires_at); RETURN result;
 END IF;
 SELECT * INTO t FROM oracle2.conversation_threads_v1 WHERE thread_id=wanted_thread AND workspace_id=a.workspace_id AND principal_id=a.principal_id;
 IF NOT FOUND THEN RAISE insufficient_privilege USING MESSAGE='own conversation unavailable'; END IF;
 result:=oracle2._conversation_result_v1(t);
 PERFORM oracle2._conversation_context_v1(a.expires_at); RETURN result;
END $fn$;
CREATE FUNCTION oracle2.conversation_command_status_v1(wanted_command uuid,caller_deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;e oracle2.conversation_events_v1%ROWTYPE;
BEGIN
 a:=oracle2._conversation_context_v1(caller_deadline);
 SELECT * INTO e FROM oracle2.conversation_events_v1 WHERE workspace_id=a.workspace_id AND principal_id=a.principal_id AND command_id=wanted_command;
 PERFORM oracle2._conversation_context_v1(a.expires_at);
 IF e.event_id IS NULL THEN RETURN jsonb_build_object('schema_version',1,'state','UNKNOWN','resend_authorized',false); END IF;
 RETURN jsonb_build_object('schema_version',1,'state','committed','thread_id',e.thread_id,'sequence',e.sequence,'command_sha256',e.command_sha256,'resend_authorized',false);
END $fn$;
DO $acl$ DECLARE signature text; BEGIN
 FOREACH signature IN ARRAY ARRAY['_conversation_context_v1(timestamptz)','_conversation_request_v1(bytea)',
 '_conversation_result_v1(oracle2.conversation_threads_v1)','create_conversation_v1(bytea)','apply_conversation_command_v1(bytea)',
 'conversation_snapshot_v1(uuid,bigint,timestamptz)','conversation_command_status_v1(uuid,timestamptz)'] LOOP
 EXECUTE 'REVOKE ALL ON FUNCTION oracle2.'||signature||' FROM PUBLIC,oracle2_replacement_requester'; END LOOP;
END $acl$;
GRANT EXECUTE ON FUNCTION oracle2.create_conversation_v1(bytea),oracle2.apply_conversation_command_v1(bytea),
 oracle2.conversation_snapshot_v1(uuid,bigint,timestamptz),oracle2.conversation_command_status_v1(uuid,timestamptz) TO oracle2_replacement_requester;

-- Root-ratified additive processing purpose. Existing purpose/role behavior is retained.
CREATE OR REPLACE FUNCTION oracle2._purpose_source_v2(
 workspace uuid, source uuid, principal uuid, expected_runtime text, expected_registry text, purpose text, want_raw boolean)
 RETURNS TABLE(revision integer, original_hash text, reading_hash text, parser_id text, original_reading text, provenance text, valid_until timestamptz, checked_at timestamptz)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE a oracle2.hosting_role_source_admissions%ROWTYPE;
 r oracle2.hosting_role_runtime_admissions%ROWTYPE; owner_oid oid; login_oid oid;
 kinds text[]; kind text; reading text; metadata jsonb; n bigint; source_revision integer; source_status text;
 scope_name text; permitted boolean; deadline timestamptz; scope_deadline timestamptz;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 -- Use the SAME connection as an enclosing ledger transaction; never a nested lock connection.
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||workspace::text));
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 SELECT oid INTO login_oid FROM pg_roles WHERE rolname=SESSION_USER
 AND rolcanlogin AND NOT (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication);
 IF login_oid IS NULL OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR pg_has_role(login_oid,owner_oid,'MEMBER') THEN RAISE insufficient_privilege USING MESSAGE='processing owner/session denied'; END IF;
 SELECT array_agg(rolname::text ORDER BY rolname) INTO kinds FROM pg_roles
 WHERE rolname IN ('oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor','oracle2_gateway_metadata')
 AND pg_has_role(login_oid,oid,'MEMBER');
 IF coalesce(cardinality(kinds),0)<>1 THEN RAISE insufficient_privilege USING MESSAGE='exclusive processing role required'; END IF;
 kind:=kinds[1];
 -- PG16 MEMBER, SET and inherited USAGE have different option semantics.
 -- The new processing issuer permits no other reachable role, even harmless
 -- intermediate/monitor membership. Legacy SourceRoleBinding is unchanged.
 IF EXISTS(SELECT 1 FROM pg_roles x WHERE x.rolname NOT IN (SESSION_USER::text,kind)
 AND (pg_has_role(login_oid,x.oid,'MEMBER') OR pg_has_role(login_oid,x.oid,'SET') OR pg_has_role(login_oid,x.oid,'USAGE')))
 OR EXISTS(SELECT 1 FROM pg_roles x WHERE x.rolname=kind AND (x.rolcanlogin OR x.rolinherit OR x.rolsuper OR x.rolbypassrls OR x.rolcreaterole OR x.rolcreatedb OR x.rolreplication))
 OR current_setting('role') NOT IN ('none',SESSION_USER::text,kind) THEN
 RAISE insufficient_privilege USING MESSAGE='exact processing role/SET membership required'; END IF;
 IF purpose IS NULL OR purpose NOT IN ('source-census','operating-audit','independent-source-semantic-acceptance','source-extraction','employee-conversation')
 OR kind NOT IN ('oracle2_source_reader','oracle2_gateway_metadata')
 OR (purpose='employee-conversation' AND kind<>'oracle2_source_reader')
 OR (want_raw AND (kind<>'oracle2_source_reader' OR purpose='source-extraction'))
 OR (purpose='source-extraction' AND kind<>'oracle2_gateway_metadata') THEN
  RAISE insufficient_privilege USING MESSAGE='fixed purpose V2 role/operation denied';
 END IF;
 SELECT * INTO r FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 SELECT c.* INTO a FROM oracle2.hosting_role_source_admissions c
 JOIN oracle2.sources s ON s.workspace_id=c.workspace_id AND s.source_id=c.source_id AND s.revision=c.revision
 WHERE c.role_name=SESSION_USER AND c.workspace_id=workspace AND c.source_id=source
 AND c.runtime_hash=expected_runtime AND c.registry_hash=expected_registry
 AND c.principal_id=principal FOR SHARE OF c;
 IF r.role_name IS NULL OR a.role_name IS NULL OR expected_runtime !~ '^[0-9a-f]{64}$'
 OR expected_registry !~ '^[0-9a-f]{64}$' OR r.runtime_hash IS DISTINCT FROM expected_runtime
 OR r.registry_hash IS DISTINCT FROM expected_registry OR a.expires_at<=clock_timestamp()
 OR r.expires_at<=clock_timestamp() OR NOT isfinite(r.expires_at) OR NOT isfinite(a.expires_at) THEN RAISE insufficient_privilege USING MESSAGE='current processing admission denied'; END IF;
 deadline:=least(a.expires_at,r.expires_at);
 SELECT s.revision,s.status INTO source_revision,source_status FROM oracle2.sources s
 WHERE s.workspace_id=workspace AND s.source_id=source FOR SHARE;
 IF source_revision IS DISTINCT FROM a.revision OR source_status NOT IN ('draft','confirmed') OR source_status IS NULL THEN
  RAISE insufficient_privilege USING MESSAGE='current processing source denied';
 END IF;
 -- SHARE also prevents new duplicate draft/original rows (row locks alone allow phantoms).
 LOCK TABLE oracle2.drafts,oracle2.source_blocks IN SHARE MODE;
 -- drafts.status is the current schema's withdrawal marker; its CONTENT is never accepted as truth.
 PERFORM 1 FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source ORDER BY d.draft_id FOR SHARE;
 SELECT count(*) INTO n FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source;
 IF n<>1 OR NOT EXISTS(SELECT 1 FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source AND d.status IN ('draft','confirmed')) THEN
  RAISE insufficient_privilege USING MESSAGE='processing source withdrawn or ambiguous';
 END IF;
 PERFORM 1 FROM oracle2.source_blocks b WHERE b.workspace_id=workspace AND b.source_id=source
 AND b.kind IN ('original','original-metadata') ORDER BY b.block_id FOR SHARE;
 SELECT count(*),min(b.text) INTO n,reading FROM oracle2.source_blocks b
 WHERE b.workspace_id=workspace AND b.source_id=source AND b.kind='original';
 IF n<>1 THEN RAISE insufficient_privilege USING MESSAGE='unique processing original required'; END IF;
 SELECT count(*),min(b.text)::jsonb INTO n,metadata FROM oracle2.source_blocks b
 WHERE b.workspace_id=workspace AND b.source_id=source AND b.kind='original-metadata';
 IF n<>1 OR jsonb_typeof(metadata) IS DISTINCT FROM 'object'
 OR NOT metadata ?& ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt']
 OR (metadata-ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt'])<>'{}'::jsonb
 OR EXISTS(SELECT 1 FROM unnest(ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','review_receipt']) k
 WHERE jsonb_typeof(metadata->k) IS DISTINCT FROM 'string')
 OR metadata->>'evidence_kind' NOT IN ('native_text','visual_transcription')
 OR metadata->>'parser_identity' !~ '^[0-9a-f]{64}$' OR metadata->>'review_receipt' !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(metadata->'page_count') IS DISTINCT FROM 'number' OR (metadata->>'page_count')::numeric NOT BETWEEN 1 AND 40
 OR (metadata->>'page_count')::numeric<>trunc((metadata->>'page_count')::numeric)
 OR metadata->>'original_hash' IS DISTINCT FROM a.original_hash
 OR metadata->>'content_hash' IS DISTINCT FROM a.reading_hash
 OR metadata->>'parser_identity' IS DISTINCT FROM a.parser_id
 OR encode(sha256(convert_to(reading,'UTF8')),'hex') IS DISTINCT FROM a.reading_hash THEN
  RAISE insufficient_privilege USING MESSAGE='processing original provenance denied';
 END IF;
 IF EXISTS(SELECT 1 FROM oracle2.operating_model_source_receipts q WHERE q.workspace_id=workspace
 AND q.source_id=source AND q.revision=a.revision
 AND (q.original_hash,q.reading_hash,q.parser_id) IS DISTINCT FROM (a.original_hash,a.reading_hash,a.parser_id)) THEN
  RAISE insufficient_privilege USING MESSAGE='processing receipt identity differs';
 END IF;
 IF purpose='employee-conversation' AND (NOT EXISTS(
 SELECT 1 FROM oracle2.source_original_revisions original JOIN oracle2.source_reading_qualifications qualified
 USING(workspace_id,source_id,revision) WHERE original.workspace_id=workspace AND original.source_id=source
 AND original.revision=a.revision AND original.original_sha256=a.original_hash
 AND qualified.original_sha256=a.original_hash AND qualified.reading_sha256=a.reading_hash AND qualified.parser_id=a.parser_id)
 OR EXISTS(SELECT 1 FROM oracle2.source_original_withdrawals_v1 withdrawn WHERE withdrawn.workspace_id=workspace
 AND withdrawn.source_id=source AND withdrawn.revision=a.revision)) THEN
 RAISE insufficient_privilege USING MESSAGE='actual current SQL014 original qualification required'; END IF;
 PERFORM 1 FROM oracle2.appointments p WHERE p.workspace_id=workspace ORDER BY p.appointment_id FOR SHARE;
 FOREACH scope_name IN ARRAY ARRAY['source-read:'||source::text,purpose||':'||source::text] LOOP
  WITH RECURSIVE lineage AS (
   SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.actor_id,p.granted_by,
    ARRAY[p.appointment_id] seen, true valid,1 depth
   FROM oracle2.appointments p WHERE p.workspace_id=workspace AND p.actor_id=principal AND p.scope=scope_name
   UNION ALL
   SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.actor_id,p.granted_by,
    l.seen||p.appointment_id,l.valid AND p.actor_id=l.granted_by AND p.scope IN (scope_name,'root'),l.depth+1
   FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id
   WHERE p.workspace_id=workspace AND l.depth<16 AND NOT p.appointment_id=ANY(l.seen))
  , valid_paths AS (SELECT min(expires_at) expiry FROM lineage GROUP BY start_id HAVING
   bool_and(valid AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp()))
   AND bool_or(scope='root' AND parent_id IS NULL))
  SELECT EXISTS(SELECT 1 FROM valid_paths),max(coalesce(expiry,'infinity'::timestamptz))
  INTO permitted,scope_deadline FROM valid_paths;
  IF NOT permitted THEN RAISE insufficient_privilege USING MESSAGE='current processing scope lineage denied'; END IF;
  deadline:=least(deadline,scope_deadline);
 END LOOP;
 IF deadline<=clock_timestamp() OR a.expires_at<=clock_timestamp() OR r.expires_at<=clock_timestamp() OR NOT isfinite(r.expires_at) OR NOT isfinite(a.expires_at) THEN
  RAISE insufficient_privilege USING MESSAGE='processing admission expired during qualification';
 END IF;
 RETURN QUERY SELECT a.revision,a.original_hash,a.reading_hash,a.parser_id,
 CASE WHEN want_raw THEN reading ELSE NULL::text END,
 CASE WHEN want_raw THEN metadata::text ELSE NULL::text END,deadline,clock_timestamp();
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='invalid processing provenance';
END $body$;
REVOKE ALL ON FUNCTION oracle2._purpose_source_v2(uuid,uuid,uuid,text,text,text,boolean) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;

CREATE OR REPLACE FUNCTION oracle2.hosting_employee_conversation_receipt_v1(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,original_reading text,provenance text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT * FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'employee-conversation',true)
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_employee_conversation_receipt_v1(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_employee_conversation_receipt_v1(uuid,uuid,uuid,text,text) TO oracle2_source_reader;

CREATE OR REPLACE FUNCTION oracle2.hosting_employee_conversation_identity_v1(
 workspace uuid,source uuid,principal uuid,expected_runtime text,expected_registry text)
 RETURNS TABLE(revision integer,original_hash text,reading_hash text,parser_id text,valid_until timestamptz,checked_at timestamptz)
 LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT q.revision,q.original_hash,q.reading_hash,q.parser_id,q.valid_until,q.checked_at
 FROM oracle2._purpose_source_v2(workspace,source,principal,expected_runtime,expected_registry,'employee-conversation',false) q
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_employee_conversation_identity_v1(uuid,uuid,uuid,text,text) FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.hosting_employee_conversation_identity_v1(uuid,uuid,uuid,text,text) TO oracle2_source_reader;


CREATE TABLE oracle2.conversation_processing_admissions_v1 (
 admission_id uuid PRIMARY KEY,role_name name NOT NULL,principal_id uuid NOT NULL,workspace_id uuid NOT NULL,
 thread_id uuid NOT NULL REFERENCES oracle2.conversation_threads_v1,thread_revision integer NOT NULL CHECK(thread_revision>0),
 employee_event_id uuid NOT NULL REFERENCES oracle2.conversation_events_v1,enduser_principal_id uuid NOT NULL,enduser_role name NOT NULL,
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),registry_hash text NOT NULL CHECK(registry_hash ~ '^[0-9a-f]{64}$'),
 config_sha256 text NOT NULL CHECK(config_sha256 ~ '^[0-9a-f]{64}$'),dispatch_id uuid NOT NULL UNIQUE,
 model_id text NOT NULL CHECK(model_id IN ('openai/gpt-6.1-sol','openai/gpt-6-astra')),
 qualified_population jsonb NOT NULL CHECK(jsonb_typeof(qualified_population)='array' AND jsonb_array_length(qualified_population)<=64),
 qualified_population_sha256 text NOT NULL CHECK(qualified_population_sha256 ~ '^[0-9a-f]{64}$'),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL,original_horizon timestamptz NOT NULL,expires_at timestamptz NOT NULL,
 CHECK(principal_id<>issuer_actor AND principal_id<>reviewer_actor AND issuer_actor<>reviewer_actor),
 CHECK(isfinite(original_horizon) AND isfinite(expires_at) AND expires_at<=original_horizon));
CREATE TRIGGER immutable_conversation_processing_admissions_v1 BEFORE UPDATE OR DELETE ON oracle2.conversation_processing_admissions_v1
 FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
REVOKE ALL ON oracle2.conversation_processing_admissions_v1 FROM PUBLIC,oracle2_replacement_requester,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_gateway_metadata,oracle2_documentary_executor,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer;
CREATE FUNCTION oracle2.conversation_model_input_v1(wanted_admission uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE a oracle2.conversation_processing_admissions_v1%ROWTYPE;r oracle2.hosting_role_runtime_admissions%ROWTYPE;
 t oracle2.conversation_threads_v1%ROWTYPE;e oracle2.conversation_events_v1%ROWTYPE;owner_oid oid;login_oid oid;group_oid oid;
 until timestamptz;ref jsonb;receipt record;readings jsonb:='[]';source_refs uuid[]:='{}';claim oracle2.conversation_events_v1%ROWTYPE;result jsonb;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 IF NOT EXISTS(SELECT 1 FROM pg_stat_ssl WHERE pid=pg_backend_pid() AND ssl) THEN RAISE insufficient_privilege USING MESSAGE='actual TLS conversation worker required'; END IF;
 SELECT nspowner INTO owner_oid FROM pg_namespace WHERE nspname='oracle2';
 SELECT oid INTO login_oid FROM pg_roles WHERE rolname=SESSION_USER AND rolcanlogin AND NOT(rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication);
 SELECT oid INTO group_oid FROM pg_roles WHERE rolname='oracle2_source_reader' AND NOT(rolcanlogin OR rolinherit OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication);
 IF login_oid IS NULL OR group_oid IS NULL OR owner_oid IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR NOT pg_has_role(login_oid,group_oid,'MEMBER') OR current_setting('role') NOT IN ('none',SESSION_USER::text,'oracle2_source_reader')
 OR EXISTS(SELECT 1 FROM pg_roles x WHERE x.oid NOT IN(login_oid,group_oid) AND (pg_has_role(login_oid,x.oid,'MEMBER') OR pg_has_role(login_oid,x.oid,'SET') OR pg_has_role(login_oid,x.oid,'USAGE'))) THEN
 RAISE insufficient_privilege USING MESSAGE='exclusive actual conversation worker denied'; END IF;
 SELECT * INTO a FROM oracle2.conversation_processing_admissions_v1 WHERE admission_id=wanted_admission AND role_name=SESSION_USER;
 IF NOT FOUND THEN RAISE insufficient_privilege USING MESSAGE='independent actual conversation worker appointment required'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||a.workspace_id::text));
 SELECT * INTO a FROM oracle2.conversation_processing_admissions_v1 WHERE admission_id=wanted_admission AND role_name=SESSION_USER FOR SHARE;
 SELECT * INTO r FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 IF r.role_name IS NULL OR r.runtime_hash IS DISTINCT FROM a.runtime_hash OR r.registry_hash IS DISTINCT FROM a.registry_hash
 OR NOT isfinite(r.expires_at) OR least(a.expires_at,a.original_horizon,r.expires_at)<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='current conversation worker runtime denied'; END IF;
 IF NOT EXISTS(SELECT 1 FROM oracle2.appointments WHERE workspace_id=a.workspace_id AND actor_id=a.principal_id
 AND scope='employee-conversation-thread:'||a.thread_id::text AND revoked_at IS NULL AND expires_at>clock_timestamp()) THEN RAISE insufficient_privilege USING MESSAGE='separate rooted conversation thread purpose required'; END IF;
 until:=least(a.expires_at,a.original_horizon,r.expires_at,oracle2._replacement_scope(a.workspace_id,a.principal_id,'employee-conversation-thread:'||a.thread_id::text));
 SELECT * INTO t FROM oracle2.conversation_threads_v1 WHERE thread_id=a.thread_id AND workspace_id=a.workspace_id AND principal_id=a.enduser_principal_id FOR SHARE;
 SELECT * INTO e FROM oracle2.conversation_events_v1 WHERE event_id=a.employee_event_id AND thread_id=a.thread_id AND principal_id=a.enduser_principal_id AND origin='employee';
 IF t.thread_id IS NULL OR e.event_id IS NULL
 OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 newer WHERE newer.thread_id=a.thread_id AND newer.origin='employee' AND newer.sequence>e.sequence)
 OR EXISTS(SELECT 1 FROM oracle2.conversation_events_v1 correction WHERE correction.corrects_event_id=e.event_id)
 OR t.state<>'active' OR t.mode<>'ordinary'
 OR NOT EXISTS(SELECT 1 FROM oracle2.hosting_request_principal_admissions u JOIN oracle2.hosting_role_runtime_admissions v USING(role_name)
 WHERE u.role_name=a.enduser_role AND u.workspace_id=a.workspace_id AND u.principal_id=a.enduser_principal_id
 AND u.expires_at>clock_timestamp() AND v.expires_at>clock_timestamp() AND u.runtime_hash=v.runtime_hash AND u.registry_hash=v.registry_hash)
 OR NOT EXISTS(SELECT 1 FROM oracle2.appointments WHERE workspace_id=a.workspace_id AND actor_id=a.enduser_principal_id
 AND scope='conversation-self' AND revoked_at IS NULL AND expires_at>clock_timestamp()) THEN RAISE insufficient_privilege USING MESSAGE='actual current employee conversation context denied'; END IF;
 until:=least(until,oracle2._replacement_scope(a.workspace_id,a.enduser_principal_id,'conversation-self'));
 PERFORM 1 FROM oracle2.hosting_request_principal_admissions u JOIN oracle2.hosting_role_runtime_admissions v USING(role_name) WHERE u.role_name=a.enduser_role FOR SHARE OF u,v;
 until:=least(until,(SELECT least(u.expires_at,v.expires_at) FROM oracle2.hosting_request_principal_admissions u JOIN oracle2.hosting_role_runtime_admissions v USING(role_name) WHERE u.role_name=a.enduser_role));
 IF t.revision<>a.thread_revision THEN
 SELECT * INTO claim FROM oracle2.conversation_events_v1 WHERE thread_id=t.thread_id AND sequence=t.revision AND operation='claim_response';
 IF t.revision<>a.thread_revision+1 OR claim.event_id IS NULL OR claim.payload->>'dispatch_id'<>a.dispatch_id::text
 OR claim.payload->>'event_id'<>a.employee_event_id::text THEN RAISE serialization_failure USING MESSAGE='current conversation worker revision differs'; END IF;
 END IF;
 IF encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('source_refs',a.qualified_population)),'UTF8')),'hex')<>a.qualified_population_sha256 THEN
 RAISE insufficient_privilege USING MESSAGE='complete conversation population commitment differs'; END IF;
 FOR ref IN SELECT value FROM jsonb_array_elements(a.qualified_population) LOOP
 IF jsonb_typeof(ref)<>'object' OR NOT ref ?& ARRAY['schema_version','workspace_id','source_id','revision','original_sha256','reading_sha256','parser_id']
 OR ref-ARRAY['schema_version','workspace_id','source_id','revision','original_sha256','reading_sha256','parser_id']<>'{}'::jsonb
 OR ref->'schema_version'<>'1'::jsonb OR jsonb_typeof(ref->'revision') IS DISTINCT FROM 'number' OR ref->>'revision' !~ '^[1-9][0-9]{0,8}$'
 OR EXISTS(SELECT 1 FROM unnest(ARRAY['workspace_id','source_id','original_sha256','reading_sha256','parser_id']) k WHERE jsonb_typeof(ref->k) IS DISTINCT FROM 'string')
 OR ref->>'original_sha256' !~ '^[0-9a-f]{64}$' OR ref->>'reading_sha256' !~ '^[0-9a-f]{64}$' OR ref->>'parser_id' !~ '^[0-9a-f]{64}$'
 OR ref->>'workspace_id'<>a.workspace_id::text
 OR (ref->>'source_id')::uuid=ANY(source_refs) THEN RAISE insufficient_privilege USING MESSAGE='closed unique conversation population required'; END IF;
 source_refs:=array_append(source_refs,(ref->>'source_id')::uuid);
 SELECT * INTO STRICT receipt FROM oracle2.hosting_employee_conversation_receipt_v1(a.workspace_id,(ref->>'source_id')::uuid,a.principal_id,a.runtime_hash,a.registry_hash);
 IF (receipt.revision,receipt.original_hash,receipt.reading_hash,receipt.parser_id) IS DISTINCT FROM
 ((ref->>'revision')::integer,ref->>'original_sha256',ref->>'reading_sha256',ref->>'parser_id') THEN RAISE insufficient_privilege USING MESSAGE='actual qualified conversation population differs'; END IF;
 readings:=readings||jsonb_build_array(jsonb_build_object('ref',ref,'reading',receipt.original_reading,'display_revision','r'||receipt.revision::text,'aliases','[]'::jsonb));
 until:=least(until,receipt.valid_until,oracle2._replacement_scope(a.workspace_id,a.enduser_principal_id,'source-read:'||(ref->>'source_id')));
 END LOOP;
 IF until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='conversation worker original horizon elapsed'; END IF;
 result:=jsonb_build_object('schema_version',1,'admission_id',a.admission_id,'worker_principal_id',a.principal_id,'workspace_id',a.workspace_id,
 'thread_id',a.thread_id,'thread_revision',a.thread_revision,'employee_event_id',a.employee_event_id,'enduser_principal_id',a.enduser_principal_id,
 'runtime_hash',a.runtime_hash,'registry_hash',a.registry_hash,'config_sha256',a.config_sha256,'dispatch_id',a.dispatch_id,'model_id',a.model_id,
 'qualified_population',a.qualified_population,'qualified_population_sha256',a.qualified_population_sha256,'qualified_readings',readings,
 'original_horizon',a.original_horizon,'valid_until',until,'checked_at',clock_timestamp(),'snapshot',oracle2._conversation_result_v1(t));
 RETURN result;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='actual conversation worker input unavailable';
END $fn$;
REVOKE ALL ON FUNCTION oracle2.conversation_model_input_v1(uuid) FROM PUBLIC,oracle2_source_reader,oracle2_replacement_requester,
 oracle2_candidate_compiler,oracle2_gateway_metadata,oracle2_documentary_executor;
GRANT EXECUTE ON FUNCTION oracle2.conversation_model_input_v1(uuid) TO oracle2_source_reader;

-- Native byte program identity, own actual original phase only. This labels no
-- semantic/model independence or business authority.
CREATE FUNCTION oracle2.original_native_program_identity_v1(wanted_population uuid)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $fn$
DECLARE snapshot jsonb;after_snapshot jsonb;model text;actual_purpose text;n integer;until timestamptz;
BEGIN
 snapshot:=oracle2.original_population_current_v1(wanted_population);
 SELECT count(*),min(model_id),min(purpose),min(expires_at) INTO n,model,actual_purpose,until
 FROM oracle2.hosting_original_population_admissions_v1 WHERE role_name=SESSION_USER AND population_id=wanted_population
 AND principal_id=(snapshot->>'actual_principal_id')::uuid AND runtime_hash=snapshot->'population'->>'runtime_hash'
 AND source_registry_hash=snapshot->'population'->>'source_registry_hash' AND expires_at>clock_timestamp();
 IF n<>1 OR model IS NULL OR actual_purpose NOT IN ('source-original-reading','source-original-review')
 OR model NOT LIKE (CASE WHEN actual_purpose='source-original-reading' THEN 'oracle/native-utf8-reader-v1:%' ELSE 'oracle/native-utf8-reviewer-v1:%' END) THEN
 RAISE insufficient_privilege USING MESSAGE='actual own native byte program identity unavailable'; END IF;
 after_snapshot:=oracle2.original_population_current_v1(wanted_population);
 IF (snapshot->>'actual_principal_id',snapshot->>'session_role',snapshot->'population') IS DISTINCT FROM
 (after_snapshot->>'actual_principal_id',after_snapshot->>'session_role',after_snapshot->'population') THEN
 RAISE insufficient_privilege USING MESSAGE='native byte program population changed'; END IF;
 until:=least(until,(snapshot->>'valid_until')::timestamptz,(after_snapshot->>'valid_until')::timestamptz);
 IF until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='native byte program horizon elapsed'; END IF;
 RETURN jsonb_build_object('schema_version',1,'purpose',actual_purpose,'principal_id',snapshot->>'actual_principal_id',
 'session_role',snapshot->>'session_role','population_id',wanted_population,'model_id',model,'valid_until',until,'checked_at',clock_timestamp());
END $fn$;
REVOKE ALL ON FUNCTION oracle2.original_native_program_identity_v1(uuid) FROM PUBLIC,oracle2_source_original_reader,oracle2_source_original_reviewer,
 oracle2_replacement_requester,oracle2_source_reader,oracle2_candidate_compiler,oracle2_gateway_metadata,oracle2_documentary_executor;
GRANT EXECUTE ON FUNCTION oracle2.original_native_program_identity_v1(uuid) TO oracle2_source_original_reader,oracle2_source_original_reviewer;
