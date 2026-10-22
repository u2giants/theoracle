-- S09: current recipient read lease around exact retained canonical ACK proof.
-- No new ledger, projector/job authority, ACK write/adoption or runtime grant.
-- Preserve the old current helper OID/signature/owner/ACL/search_path/guards.
CREATE FUNCTION oracle2._retained_processing_projection_receipt_v1(
 workspace uuid,artifact uuid,ver integer,manifest jsonb)
 RETURNS TABLE(receipt jsonb,signature text)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE e record;
 keys text[]:=ARRAY['schema_version','event_id','workspace_id','artifact_id','version','content_hash','source_digest','permission_digest','graph_name','record_digest','sdk_version','projector_id','lease_role','lease_token','lease_attempt','lease_until','projection_schema','projection_digest','embedding_protocol','embedding_inventory_hash','embedding_context_hash','embedding_native_receipt_hash','embedding_wire_hash','embedding_commit_hash','embedding_vectors_hash','embedding_coverage_hash'];
 hashes text[]:=ARRAY['record_digest','projection_digest','embedding_inventory_hash','embedding_context_hash','embedding_native_receipt_hash','embedding_wire_hash','embedding_commit_hash','embedding_vectors_hash','embedding_coverage_hash'];
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
  RAISE insufficient_privilege USING MESSAGE='fresh read-committed projection snapshot required';
 END IF;
 IF manifest IS DISTINCT FROM (SELECT a.manifest FROM oracle2.artifact_manifests a
  WHERE a.workspace_id=workspace AND a.artifact_id=artifact AND a.version=ver AND a.state='ready'
   AND a.kind='processing_qualified_model_v1') THEN
  RAISE insufficient_privilege USING MESSAGE='exact current qualified model required';
 END IF;
 SELECT o.event_id,o.delivered_at,o.processing_lease_role,o.processing_lease_token,o.attempts,r.payload AS body,r.signature AS seal INTO STRICT e
 FROM oracle2.outbox o JOIN oracle2.operating_projection_receipts r ON r.event_id=o.event_id
 AND r.workspace_id=o.workspace_id AND r.artifact_id=o.assertion_id AND r.version=o.revision
 WHERE o.workspace_id=workspace AND o.assertion_id=artifact AND o.revision=ver AND o.operation='project'
 AND o.payload=jsonb_build_object('namespace','oracle_processing_v1','manifest',manifest) AND o.delivered_at IS NOT NULL FOR SHARE OF o,r;
 IF jsonb_typeof(e.body) IS DISTINCT FROM 'object' OR NOT e.body ?& keys OR (e.body-keys)<>'{}'::jsonb
 OR e.body->'schema_version' IS DISTINCT FROM '3'::jsonb OR e.body->>'schema_version' IS DISTINCT FROM '3'
 OR EXISTS(SELECT 1 FROM unnest(keys) k WHERE k NOT IN ('schema_version','version','lease_attempt') AND jsonb_typeof(e.body->k) IS DISTINCT FROM 'string')
 OR jsonb_typeof(e.body->'version') IS DISTINCT FROM 'number' OR jsonb_typeof(e.body->'lease_attempt') IS DISTINCT FROM 'number'
 OR e.body->>'event_id' IS DISTINCT FROM e.event_id::text OR e.body->>'workspace_id' IS DISTINCT FROM workspace::text
 OR e.body->>'artifact_id' IS DISTINCT FROM artifact::text OR e.body->>'version' IS DISTINCT FROM ver::text
 OR e.body->>'content_hash' IS DISTINCT FROM manifest->>'content_hash' OR e.body->>'source_digest' IS DISTINCT FROM manifest->>'source_digest'
 OR e.body->>'permission_digest' IS DISTINCT FROM manifest->>'permission_digest'
 OR e.body->>'projection_schema' IS DISTINCT FROM 'qualified-evidence-projection-v1' OR e.body->>'sdk_version' IS DISTINCT FROM '1.4.0'
 OR e.body->>'embedding_protocol' IS DISTINCT FROM 'paid-sdk-embedding-v3'
 OR EXISTS(SELECT 1 FROM unnest(hashes) k WHERE e.body->>k !~ '^[0-9a-f]{64}$')
 OR e.body->>'projector_id'='' OR e.seal IS NULL OR e.seal !~ '^[0-9a-f]{64}$'
 OR e.body->>'lease_role' IS DISTINCT FROM e.processing_lease_role::text
 OR e.body->>'lease_token' IS DISTINCT FROM e.processing_lease_token::text OR e.body->>'lease_attempt' IS DISTINCT FROM e.attempts::text
 OR NOT isfinite((e.body->>'lease_until')::timestamptz) OR e.delivered_at>=(e.body->>'lease_until')::timestamptz
 OR e.body->>'graph_name' !~ ('^oracle_processing_v1_'||replace(workspace::text,'-','')||'_'||replace(artifact::text,'-','')||'_'||ver::text||'_[0-9a-f]{32}$') THEN
 RAISE insufficient_privilege USING MESSAGE='exact delivered paid V3 receipt required'; END IF;
 RETURN QUERY SELECT e.body,e.seal;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='paid projection delivery unavailable';
END $$;

REVOKE ALL ON FUNCTION oracle2._retained_processing_projection_receipt_v1(uuid,uuid,integer,jsonb) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;

CREATE OR REPLACE FUNCTION oracle2._processing_projection_receipt_v3(
 workspace uuid,artifact uuid,ver integer,manifest jsonb)
 RETURNS TABLE(receipt jsonb,signature text)
 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN
  RAISE insufficient_privilege USING MESSAGE='fresh read-committed projection snapshot required';
 END IF;
 IF manifest IS DISTINCT FROM (SELECT a.manifest FROM oracle2.artifact_manifests a
  WHERE a.workspace_id=workspace AND a.artifact_id=artifact AND a.version=ver AND a.state='ready'
   AND a.kind='processing_qualified_model_v1')
 OR ver IS DISTINCT FROM (SELECT max(a.version) FROM oracle2.artifact_manifests a
  WHERE a.workspace_id=workspace AND a.artifact_id=artifact AND a.kind='processing_qualified_model_v1' AND a.state='ready') THEN
  RAISE insufficient_privilege USING MESSAGE='exact current qualified model required';
 END IF;
 RETURN QUERY SELECT r.receipt,r.signature FROM oracle2._retained_processing_projection_receipt_v1(workspace,artifact,ver,manifest) r;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='paid projection delivery unavailable';
END $$;

CREATE FUNCTION oracle2.hosting_consolidated_projection_delivery_v1(
 model uuid,ver integer,valid_at timestamptz,known_at timestamptz,
 appointment uuid,runtime text,registry text,config text,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE a oracle2.processing_model_admissions_v1;before_metadata jsonb;after_metadata jsonb;
 retained record;accepted record;decisions jsonb:='[]'::jsonb;item record;selection jsonb;
 checked timestamptz;until_at timestamptz;result jsonb;body_hash text;idx jsonb;
BEGIN
 PERFORM oracle2._purpose_deadlines_v2();
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 IF model IS DISTINCT FROM a.model_id OR ver IS NULL OR ver<=0
 OR (valid_at IS NULL) IS DISTINCT FROM (known_at IS NULL)
 OR known_at IS NOT NULL AND (NOT isfinite(known_at) OR NOT isfinite(valid_at) OR known_at>clock_timestamp())
 THEN RAISE insufficient_privilege USING MESSAGE='exact bounded current or historical model selector required'; END IF;
 IF known_at IS NULL THEN
  before_metadata:=oracle2.hosting_current_consolidated_model_v1(model,appointment,runtime,registry,config,deadline);
 ELSE
  before_metadata:=oracle2.hosting_historical_consolidated_model_v1(model,valid_at,known_at,appointment,runtime,registry,config,deadline);
 END IF;
 IF (before_metadata->'manifest'->>'version')::integer IS DISTINCT FROM ver THEN
  RAISE serialization_failure USING MESSAGE='selected model revision changed';
 END IF;
 -- The exact same canonical retained validator, never the current-head shortcut.
 SELECT r.receipt,r.signature INTO STRICT retained
 FROM oracle2._retained_processing_projection_receipt_v1(a.workspace_id,model,ver,before_metadata->'manifest') r;
 SELECT e.delivered_at,r.created_at INTO STRICT accepted
 FROM oracle2.outbox e JOIN oracle2.operating_projection_receipts r USING(event_id)
 WHERE e.event_id=(retained.receipt->>'event_id')::uuid AND e.workspace_id=a.workspace_id
 AND e.assertion_id=model AND e.revision=ver AND r.workspace_id=a.workspace_id AND r.artifact_id=model AND r.version=ver
 AND r.payload=retained.receipt AND r.signature=retained.signature AND e.delivered_at IS NOT NULL
 FOR SHARE OF e,r;
 IF NOT isfinite(accepted.delivered_at) OR NOT isfinite(accepted.created_at)
 OR accepted.delivered_at>clock_timestamp() OR accepted.created_at>clock_timestamp()
 THEN RAISE insufficient_privilege USING MESSAGE='actual retained receipt timestamps required'; END IF;
 IF known_at IS NOT NULL THEN
  idx:=before_metadata->'assertionIndex';
  FOR item IN SELECT e.* FROM oracle2.processing_model_events_v1 e
   WHERE e.workspace_id=a.workspace_id AND e.artifact_id=model AND e.version=ver AND e.kind='business-accept'
   AND e.recorded_at<=known_at ORDER BY e.recorded_at,e.event_id LOOP
   IF item.payload->>'model_content_hash' IS DISTINCT FROM before_metadata->'manifest'->>'content_hash'
   OR item.payload->>'decision_kind' IS NULL OR item.payload->>'decision_kind' NOT IN('employee-account','process-policy','company-policy')
   OR item.payload->>'scope_hash' IS NULL OR item.payload->>'scope_hash' !~ '^[0-9a-f]{64}$'
   OR jsonb_typeof(item.payload->'assertions') IS DISTINCT FROM 'array'
   OR jsonb_array_length(item.payload->'assertions') NOT BETWEEN 1 AND 2048
   OR (SELECT count(DISTINCT value) FROM jsonb_array_elements(item.payload->'assertions'))<>jsonb_array_length(item.payload->'assertions')
   THEN RAISE insufficient_privilege USING MESSAGE='exact retained decision observation required'; END IF;
   FOR selection IN SELECT value FROM jsonb_array_elements(item.payload->'assertions') LOOP
    IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(idx) x
     WHERE jsonb_build_object('assertion_id',x->'assertion_id','revision',x->'revision')=selection
     AND encode(sha256(convert_to(oracle2._processing_canonical_jsonb_v1(x->'scope'),'UTF8')),'hex')=item.payload->>'scope_hash'
     AND CASE item.payload->>'decision_kind' WHEN 'employee-account' THEN x->>'provenance'='employee_account'
      WHEN 'process-policy' THEN x->>'provenance'='documented_process'
      WHEN 'company-policy' THEN x->>'provenance'='reported_policy' ELSE false END)
    THEN RAISE insufficient_privilege USING MESSAGE='retained decision scope or assertion differs'; END IF;
   END LOOP;
   IF EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 change
    WHERE change.workspace_id=a.workspace_id AND change.artifact_id=model
    AND change.kind IN('business-challenge','business-withdraw') AND change.recorded_at<=known_at
    AND change.payload->>'target_event_id'=item.event_id::text
    AND (change.version IS DISTINCT FROM ver
     OR change.payload->'scope_hash' IS DISTINCT FROM item.payload->'scope_hash'
     OR change.payload->'decision_kind' IS DISTINCT FROM item.payload->'decision_kind'
     OR change.payload->'model_content_hash' IS DISTINCT FROM item.payload->'model_content_hash'))
   THEN RAISE insufficient_privilege USING MESSAGE='retained decision change target/scope/model differs'; END IF;
   decisions:=decisions||jsonb_build_array(jsonb_build_object('event_id',item.event_id,'recorded_at',item.recorded_at,
    'decision_kind',item.payload->'decision_kind','scope_sha256',item.payload->'scope_hash','assertions',item.payload->'assertions',
    'challenged_as_of',EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 change
     WHERE change.workspace_id=a.workspace_id AND change.artifact_id=model AND change.version=ver
     AND change.kind='business-challenge' AND change.recorded_at<=known_at AND change.payload->>'target_event_id'=item.event_id::text
     AND change.payload->'scope_hash'=item.payload->'scope_hash' AND change.payload->'decision_kind'=item.payload->'decision_kind'
     AND change.payload->'model_content_hash'=item.payload->'model_content_hash'),
    'withdrawn_as_of',EXISTS(SELECT 1 FROM oracle2.processing_model_events_v1 change
     WHERE change.workspace_id=a.workspace_id AND change.artifact_id=model AND change.version=ver
     AND change.kind='business-withdraw' AND change.recorded_at<=known_at AND change.payload->>'target_event_id'=item.event_id::text
     AND change.payload->'scope_hash'=item.payload->'scope_hash' AND change.payload->'decision_kind'=item.payload->'decision_kind'
     AND change.payload->'model_content_hash'=item.payload->'model_content_hash')));
   IF jsonb_array_length(decisions)>128 THEN RAISE insufficient_privilege USING MESSAGE='complete retained decision observations exceed bounded read'; END IF;
  END LOOP;
 END IF;
 -- SAME actual own authority and exact selected version after receipt packing.
 a:=oracle2._processing_model_admission_v1(appointment,'history-read',runtime,registry,config,deadline);
 IF known_at IS NULL THEN
  after_metadata:=oracle2.hosting_current_consolidated_model_v1(model,appointment,runtime,registry,config,deadline);
 ELSE
  after_metadata:=oracle2.hosting_historical_consolidated_model_v1(model,valid_at,known_at,appointment,runtime,registry,config,deadline);
 END IF;
 IF after_metadata IS DISTINCT FROM before_metadata THEN RAISE insufficient_privilege USING MESSAGE='current recipient model scope changed during retained receipt read'; END IF;
 SELECT encode(sha256(convert_to('{'||string_agg(to_jsonb(key)::text||':'||value::text,',' ORDER BY key COLLATE "C")||'}','UTF8')),'hex') INTO body_hash FROM jsonb_each(retained.receipt);
 until_at:=least(a.expires_at,(after_metadata->>'validUntil')::timestamptz,deadline);
 checked:=clock_timestamp();
 IF checked>=until_at THEN RAISE insufficient_privilege; END IF;
 result:=jsonb_build_object('schema_version',1,'protocol','consolidated-readonly-delivery-v1',
  'workspace_id',a.workspace_id,'model_id',model,'version',ver,'model_content_hash',after_metadata->'manifest'->'content_hash',
  'source_refs',after_metadata->'sourceRefs','mode',after_metadata->'mode','valid_at',valid_at,'known_at',known_at,
  'retained_receipt',retained.receipt,'retained_signature',retained.signature,'retained_receipt_body_sha256',body_hash,
  'retained_delivered_at',accepted.delivered_at,'retained_receipt_recorded_at',accepted.created_at,
  'business_decisions_as_of',decisions,'checked_at',checked,'valid_until',until_at);
 IF octet_length(result::text)>2*1024*1024 THEN RAISE insufficient_privilege USING MESSAGE='bounded complete retained delivery envelope required'; END IF;
 RETURN result;
EXCEPTION WHEN no_data_found OR too_many_rows OR invalid_text_representation OR numeric_value_out_of_range THEN
 RAISE insufficient_privilege USING MESSAGE='retained consolidated delivery unavailable';
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_consolidated_projection_delivery_v1(uuid,integer,timestamptz,timestamptz,uuid,text,text,text,timestamptz)
 FROM PUBLIC,oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;
-- No source-authored runtime EXECUTE grants. Exact external installation is required.
