-- Dedicated synthetic ledger only; no grants to private source/receipt tables.
-- The gateway holds the transaction through its bounded five-second socket write.
CREATE OR REPLACE FUNCTION oracle2.gateway_view_result(run uuid, runtime text, admission text)
 RETURNS TABLE(result_status text,canonical_pack bytea)
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE j oracle2.operating_view_runs%ROWTYPE; m jsonb; seal text; selected bigint; current_watermark bigint;
 ref jsonb; metadata jsonb; reading text; n bigint; budget integer; r oracle2.operating_view_pack_receipts%ROWTYPE;
BEGIN
 IF NOT pg_has_role(SESSION_USER,'oracle2_gateway_metadata','member') OR runtime !~ '^[0-9a-f]{64}$' OR admission !~ '^[0-9a-f]{64}$' THEN
 RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO j FROM oracle2.operating_view_runs WHERE run_id=run;
 IF NOT FOUND THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||j.workspace_id::text));
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-selector:'||j.workspace_id::text,0));
 -- SHARE prevents insertion phantoms/new source population, withdrawal, receipt,
 -- selector or watermark mutations until the bounded transaction is released.
 LOCK TABLE oracle2.sources,oracle2.source_blocks,oracle2.drafts,oracle2.appointments,
 oracle2.operating_model_source_receipts,oracle2.artifact_manifests,oracle2.artifact_dependencies,
 oracle2.artifact_invalidations,oracle2.operating_release_selectors,oracle2.operating_release_manifests,
 oracle2.operating_model_change_log IN SHARE MODE;
 SELECT * INTO j FROM oracle2.operating_view_runs WHERE run_id=run FOR SHARE;
 IF j.status NOT IN ('pending','completed') OR j.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 SELECT x.payload,x.content_hash,s.watermark INTO m,seal,selected FROM oracle2.operating_release_selectors s
 JOIN oracle2.operating_release_manifests x ON x.workspace_id=s.workspace_id AND x.release_id=s.release_id
 WHERE s.workspace_id=j.workspace_id AND s.release_id=j.release_id;
 SELECT COALESCE(max(sequence),0) INTO current_watermark FROM oracle2.operating_model_change_log WHERE workspace_id=j.workspace_id;
 IF m IS NULL OR m->>'acceptance_state' IS DISTINCT FROM 'synthetic' OR m->>'runtime_digest' IS DISTINCT FROM runtime
 OR m->>'documentary_gate_hash' IS DISTINCT FROM admission OR seal IS DISTINCT FROM j.release_hash
 OR (m->>'workspace_id') IS DISTINCT FROM j.workspace_id::text OR (m->>'release_id') IS DISTINCT FROM j.release_id::text
 OR jsonb_typeof(m->'ledger_watermark') IS DISTINCT FROM 'number' OR (m->>'ledger_watermark')::bigint IS DISTINCT FROM current_watermark
 OR selected IS DISTINCT FROM current_watermark OR jsonb_typeof(j.source_refs) IS DISTINCT FROM 'array'
 OR j.source_refs IS DISTINCT FROM m->'source_refs' OR jsonb_array_length(j.source_refs)=0
 THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM oracle2.artifact_manifests a WHERE a.workspace_id=j.workspace_id
 AND a.artifact_id=(m->>'artifact_id')::uuid AND a.version=(m->>'artifact_version')::integer
 AND a.state='ready' AND a.content_hash=m->>'artifact_content_hash' AND a.permission_digest=m->>'permission_digest')
 OR EXISTS(SELECT 1 FROM oracle2.artifact_invalidations a WHERE a.workspace_id=j.workspace_id
 AND a.artifact_id=(m->>'artifact_id')::uuid AND a.version=(m->>'artifact_version')::integer)
 OR (SELECT count(*) FROM oracle2.artifact_dependencies a WHERE a.workspace_id=j.workspace_id
 AND a.artifact_id=(m->>'artifact_id')::uuid AND a.version=(m->>'artifact_version')::integer AND a.upstream_kind='source')<>jsonb_array_length(j.source_refs)
 OR (SELECT count(DISTINCT value->>'source_id') FROM jsonb_array_elements(j.source_refs))<>jsonb_array_length(j.source_refs)
 THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 FOR ref IN SELECT value FROM jsonb_array_elements(j.source_refs) LOOP
 IF NOT EXISTS(SELECT 1 FROM oracle2.artifact_dependencies a WHERE a.workspace_id=j.workspace_id
 AND a.artifact_id=(m->>'artifact_id')::uuid AND a.version=(m->>'artifact_version')::integer AND a.upstream_kind='source'
 AND a.upstream_id=ref->>'source_id' AND a.upstream_revision=ref->>'revision')
 OR (ref->>'workspace_id') IS DISTINCT FROM j.workspace_id::text
 OR NOT EXISTS(SELECT 1 FROM oracle2.sources s WHERE s.workspace_id=j.workspace_id AND s.source_id=(ref->>'source_id')::uuid
 AND s.revision=(ref->>'revision')::integer AND s.status IN ('draft','confirmed'))
 OR (SELECT count(*) FROM oracle2.drafts d WHERE d.workspace_id=j.workspace_id AND d.source_id=(ref->>'source_id')::uuid)<>1
 OR NOT EXISTS(SELECT 1 FROM oracle2.drafts d WHERE d.workspace_id=j.workspace_id AND d.source_id=(ref->>'source_id')::uuid AND d.status='confirmed')
 OR NOT EXISTS(SELECT 1 FROM oracle2.operating_model_source_receipts x WHERE x.workspace_id=j.workspace_id AND x.source_id=(ref->>'source_id')::uuid
 AND x.revision=(ref->>'revision')::integer AND x.original_hash=ref->>'original_sha256' AND x.reading_hash=ref->>'reading_sha256' AND x.parser_id=ref->>'parser_id')
 THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 SELECT count(*),min(b.text) INTO n,reading FROM oracle2.source_blocks b WHERE b.workspace_id=j.workspace_id AND b.source_id=(ref->>'source_id')::uuid AND b.kind='original';
 IF n<>1 OR encode(sha256(convert_to(reading,'UTF8')),'hex') IS DISTINCT FROM ref->>'reading_sha256' THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 SELECT count(*),min(b.text)::jsonb INTO n,metadata FROM oracle2.source_blocks b WHERE b.workspace_id=j.workspace_id AND b.source_id=(ref->>'source_id')::uuid AND b.kind='original-metadata';
 IF n<>1 OR jsonb_typeof(metadata) IS DISTINCT FROM 'object'
 OR NOT metadata ?& ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt']
 OR (metadata-ARRAY['original_hash','content_hash','parser_identity','content_type','evidence_kind','page_count','review_receipt'])<>'{}'::jsonb
 OR jsonb_typeof(metadata->'content_type') IS DISTINCT FROM 'string'
 OR metadata->>'evidence_kind' NOT IN ('native_text','visual_transcription')
 OR metadata->>'parser_identity' !~ '^[0-9a-f]{64}$' OR metadata->>'review_receipt' !~ '^[0-9a-f]{64}$'
 OR jsonb_typeof(metadata->'page_count') IS DISTINCT FROM 'number' OR (metadata->>'page_count')::numeric NOT BETWEEN 1 AND 40
 OR (metadata->>'page_count')::numeric<>trunc((metadata->>'page_count')::numeric)
 OR metadata->>'original_hash' IS DISTINCT FROM ref->>'original_sha256'
 OR metadata->>'content_hash' IS DISTINCT FROM ref->>'reading_sha256' OR metadata->>'parser_identity' IS DISTINCT FROM ref->>'parser_id'
 THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(WITH RECURSIVE lineage AS (
 SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,1 depth
 FROM oracle2.appointments p WHERE p.workspace_id=j.workspace_id AND p.actor_id=j.actor_id AND p.scope IN ('source-read:'||(ref->>'source_id'),'root')
 UNION ALL SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,l.depth+1
 FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id WHERE l.depth<16 AND p.workspace_id=l.workspace_id)
 SELECT 1 FROM lineage GROUP BY start_id HAVING bool_and(revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp())) AND bool_or(scope='root' AND parent_id IS NULL))
 THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 END LOOP;
 IF jsonb_typeof(j.query_plan->'max_bytes') IS DISTINCT FROM 'number' OR j.query_plan->>'max_bytes' !~ '^[0-9]+$' THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 budget=(j.query_plan->>'max_bytes')::integer;
 IF budget NOT BETWEEN 1024 AND 131072 THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 IF j.status='pending' THEN
 IF EXISTS(SELECT 1 FROM oracle2.operating_view_pack_receipts WHERE run_id=run) THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT 'pending'::text,NULL::bytea;RETURN;
 END IF;
 SELECT * INTO r FROM oracle2.operating_view_pack_receipts WHERE run_id=run FOR SHARE;
 IF NOT FOUND OR (r.workspace_id,r.actor_id,r.release_id,r.release_hash,r.runtime_hash) IS DISTINCT FROM (j.workspace_id,j.actor_id,j.release_id,j.release_hash,runtime)
 OR octet_length(r.canonical_pack)>budget+131072 OR encode(sha256(r.canonical_pack),'hex') IS DISTINCT FROM r.pack_hash
 OR convert_from(r.canonical_pack,'UTF8')::jsonb IS DISTINCT FROM j.pack
 OR j.pack->>'artifact_hash' IS DISTINCT FROM m->>'artifact_content_hash' OR j.expires_at<=clock_timestamp()
 THEN RAISE EXCEPTION 'result denied' USING ERRCODE='42501'; END IF;
 RETURN QUERY SELECT 'completed'::text,r.canonical_pack;
END $$;
REVOKE ALL ON FUNCTION oracle2.gateway_view_result(uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.gateway_view_result(uuid,text,text) TO oracle2_gateway_metadata;
