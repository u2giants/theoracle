-- Historical reader metadata is evidence; only CURRENT own reviewer authority
-- permits this bounded read. No reader admission is renewed and no grant issued.
CREATE OR REPLACE FUNCTION oracle2.original_review_reading_input_v1(wanted_reading_commit_hash text)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $body$
DECLARE reading oracle2.original_phase_response_commits%ROWTYPE;identity jsonb;snapshot jsonb;after_snapshot jsonb;
 reviewer_model text;count_admissions integer;deadline timestamptz;ref jsonb;pid uuid;
BEGIN
 IF wanted_reading_commit_hash IS NULL OR wanted_reading_commit_hash !~ '^[0-9a-f]{64}$' THEN
  RAISE invalid_parameter_value USING MESSAGE='exact retained reader commitment required';
 END IF;
 SELECT * INTO reading FROM oracle2.original_phase_response_commits
  WHERE commit_sha256=wanted_reading_commit_hash AND purpose='source-original-reading';
 IF reading.commit_sha256 IS NULL THEN
  RAISE insufficient_privilege USING MESSAGE='retained original reading unavailable';
 END IF;
 -- The caller selects no population. Its own actual source admission must be
 -- unambiguous, and the retained current access functions prove all group/TLS/
 -- source membership/runtime/rooted-rights and complete population controls.
 SELECT count(*),(array_agg(a.population_id))[1] INTO count_admissions,pid
 FROM oracle2.hosting_original_source_admissions a
 JOIN oracle2.hosting_original_population_admissions_v1 p
  ON p.role_name=a.role_name AND p.population_id=a.population_id
 WHERE a.role_name=SESSION_USER AND a.workspace_id=reading.workspace_id
  AND a.source_id=reading.source_id AND a.revision=reading.revision
  AND a.purpose='source-original-review' AND p.purpose='source-original-review'
  AND a.expires_at>clock_timestamp() AND p.expires_at>clock_timestamp();
 IF count_admissions<>1 OR pid IS NULL THEN
  RAISE insufficient_privilege USING MESSAGE='unique actual current reviewer admission required';
 END IF;
 identity:=oracle2._original_revision_access(reading.source_id,reading.revision,'oracle2_source_original_reviewer');
 snapshot:=oracle2.original_population_current_v1(pid);
 SELECT count(*),min(model_id) INTO count_admissions,reviewer_model
 FROM oracle2.hosting_original_population_admissions_v1
 WHERE role_name=SESSION_USER AND population_id=pid AND purpose='source-original-review'
  AND runtime_hash=identity->>'runtime_hash' AND expires_at>clock_timestamp();
 IF count_admissions<>1 OR reviewer_model IS NULL OR length(reviewer_model) NOT BETWEEN 1 AND 255
 OR (identity->>'population_id')::uuid IS DISTINCT FROM pid
 OR (identity->>'principal_id')::uuid IS DISTINCT FROM (snapshot->>'actual_principal_id')::uuid
 OR snapshot->>'session_role' IS DISTINCT FROM SESSION_USER::text
 OR reading.principal_id=(identity->>'principal_id')::uuid OR reading.session_role=SESSION_USER
 OR reading.model_id IS NULL OR reading.model_id=reviewer_model THEN
  RAISE insufficient_privilege USING MESSAGE='independent current reviewer model and identity required';
 END IF;
 IF reading.canonical_body IS NULL OR octet_length(reading.canonical_body) NOT BETWEEN 1 AND 65536
 OR encode(sha256(reading.canonical_body),'hex') IS DISTINCT FROM reading.commit_sha256
 OR convert_to(oracle2._replacement_metadata_json(reading.body),'UTF8') IS DISTINCT FROM reading.canonical_body
 OR convert_from(reading.canonical_body,'UTF8')::jsonb IS DISTINCT FROM reading.body
 OR reading.model_identity_sha256 IS DISTINCT FROM oracle2._original_model_identity_v1(
  reading.model_id,reading.purpose,reading.session_role,reading.runtime_hash,reading.population_id,reading.commit_sha256)
 OR reading.body->>'population_id' IS DISTINCT FROM reading.population_id::text
 OR reading.body->>'operation_registry_hash' IS DISTINCT FROM reading.operation_registry_hash
 OR reading.body->>'transport' IS DISTINCT FROM reading.transport
 OR reading.body->>'purpose' IS DISTINCT FROM 'observed-authorized-original-reading-response-v1' THEN
  RAISE insufficient_privilege USING MESSAGE='actual sealed canonical historical reader metadata required';
 END IF;
 SELECT x INTO ref FROM jsonb_array_elements(snapshot->'population'->'raw_refs') x
 WHERE x->>'source_id'=reading.source_id::text AND (x->>'revision')::integer=reading.revision;
 IF ref IS NULL OR reading.body->'raw_ref' IS DISTINCT FROM ref
 OR reading.original_sha256 IS DISTINCT FROM ref->>'original_sha256'
 OR reading.original_root_hash IS DISTINCT FROM snapshot->'population'->>'original_root_hash'
 OR reading.body->>'original_root_hash' IS DISTINCT FROM reading.original_root_hash
 OR reading.allocation_hash IS DISTINCT FROM snapshot->>'original_allocation_hash'
 OR reading.body->>'allocation_hash' IS DISTINCT FROM reading.allocation_hash
 OR reading.body->>'population_hash' IS DISTINCT FROM snapshot->'population'->>'population_digest'
 OR reading.body->>'source_registry_hash' IS DISTINCT FROM snapshot->'population'->>'source_registry_hash'
 OR reading.source_registry_hash IS DISTINCT FROM snapshot->'population'->>'source_registry_hash'
 OR NOT isfinite(reading.original_horizon) OR reading.original_horizon IS DISTINCT FROM (snapshot->>'original_horizon')::timestamptz
 OR (reading.body->>'original_horizon')::timestamptz IS DISTINCT FROM reading.original_horizon
 OR reading.original_horizon<=clock_timestamp()
 OR ((reading.body->>'reading_body_hash') ~ '^[0-9a-f]{64}$') IS DISTINCT FROM TRUE
 OR ((reading.body->>'reading_sha256') ~ '^[0-9a-f]{64}$') IS DISTINCT FROM TRUE
 OR ((reading.body->>'view_manifest_hash') ~ '^[0-9a-f]{64}$') IS DISTINCT FROM TRUE
 OR ((reading.body->>'locator_map_hash') ~ '^[0-9a-f]{64}$') IS DISTINCT FROM TRUE THEN
  RAISE insufficient_privilege USING MESSAGE='same complete current original and retained reader metadata required';
 END IF;
 -- Never consult or borrow the completed reader's current admission/expiry.
 identity:=oracle2._original_revision_access(reading.source_id,reading.revision,'oracle2_source_original_reviewer');
 after_snapshot:=oracle2.original_population_current_v1(pid);
 IF (snapshot-'checked_at'-'valid_until') IS DISTINCT FROM (after_snapshot-'checked_at'-'valid_until')
 OR (identity->>'principal_id')::uuid IS DISTINCT FROM (after_snapshot->>'actual_principal_id')::uuid
 OR (identity->>'population_id')::uuid IS DISTINCT FROM pid THEN
  RAISE insufficient_privilege USING MESSAGE='current reviewer changed during historical read';
 END IF;
 deadline:=least((identity->>'valid_until')::timestamptz,(after_snapshot->>'valid_until')::timestamptz,reading.original_horizon);
 IF deadline<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='current reviewer read expired'; END IF;
 RETURN jsonb_build_object('schema_version',1,'purpose','original-review-reading-input-v1',
  'reading_commit_sha256',reading.commit_sha256,'reading_commit_canonical_utf8_hex',encode(reading.canonical_body,'hex'),
  'reader_principal_id',reading.principal_id,'reader_session_role',reading.session_role,'reader_model_id',reading.model_id,
  'reader_runtime_hash',reading.runtime_hash,'reader_population_id',reading.population_id,
  'reader_operation_registry_hash',reading.operation_registry_hash,'reader_model_identity_sha256',reading.model_identity_sha256,
  'reviewer_snapshot',after_snapshot,'checked_at',clock_timestamp(),'valid_until',deadline);
END $body$;
REVOKE ALL ON FUNCTION oracle2.original_review_reading_input_v1(text) FROM PUBLIC,
 oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor,oracle2_gateway_metadata,
 oracle2_source_original_reader,oracle2_source_original_reviewer,oracle2_source_original_viewer,oracle2_replacement_requester;
GRANT EXECUTE ON FUNCTION oracle2.original_review_reading_input_v1(text) TO oracle2_source_original_reviewer;
