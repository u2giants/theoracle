-- Dedicated Oracle ledger only: real NOINHERIT executor, never gateway membership.
-- Global UUID ambiguity is checked before scoped rows, including foreign workspaces.
CREATE OR REPLACE FUNCTION oracle2.hosting_review_authorized(run uuid)
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT EXISTS(SELECT 1 FROM oracle2.operating_action_runs a
 JOIN oracle2.operating_release_manifests m ON m.workspace_id=a.workspace_id AND m.release_id=a.release_id
 WHERE a.run_id=run AND a.operation='finding_review' AND a.status IN ('pending','completed')
 AND a.expires_at>clock_timestamp() AND oracle2.hosting_runtime_registered()
 AND m.payload->>'acceptance_state'='synthetic'
 AND jsonb_typeof(a.payload)='object'
 AND a.payload ?& ARRAY['finding_id','scope','action','note']
 AND (a.payload-ARRAY['finding_id','scope','action','note'])='{}'::jsonb
 AND jsonb_typeof(a.payload->'finding_id')='string' AND length(a.payload->>'finding_id') BETWEEN 1 AND 512
 AND jsonb_typeof(a.payload->'scope')='string' AND length(a.payload->>'scope') BETWEEN 1 AND 512
 AND jsonb_typeof(a.payload->'note')='string' AND length(a.payload->>'note') BETWEEN 1 AND 4000
 AND a.payload->>'action' IN ('annotate','resolve','supersede','withdraw')
 AND oracle2.hosting_view_authorized(a.workspace_id,a.actor_id,a.release_id,a.release_hash,m.payload->'source_refs')
 AND EXISTS(WITH RECURSIVE lineage AS (
 SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,1 depth
 FROM oracle2.appointments p WHERE p.workspace_id=a.workspace_id AND p.actor_id=a.actor_id
 AND p.scope IN ('finding-review:'||(a.payload->>'scope'),'root')
 UNION ALL SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,l.depth+1
 FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id WHERE l.depth<16 AND p.workspace_id=l.workspace_id)
 SELECT 1 FROM lineage GROUP BY start_id HAVING bool_and(revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp()))
 AND bool_or(scope='root' AND parent_id IS NULL)));
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_review_authorized(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_review_authorized(uuid) TO oracle2_documentary_executor;
ALTER TABLE oracle2.operating_action_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hosting_gateway_action_read ON oracle2.operating_action_runs;
CREATE POLICY hosting_gateway_action_read ON oracle2.operating_action_runs FOR SELECT TO oracle2_gateway_metadata USING(true);
DROP POLICY IF EXISTS hosting_documentary_action_read ON oracle2.operating_action_runs;
CREATE POLICY hosting_documentary_action_read ON oracle2.operating_action_runs FOR SELECT TO oracle2_documentary_executor
 USING(oracle2.hosting_review_authorized(run_id));
GRANT SELECT ON oracle2.operating_action_runs TO oracle2_documentary_executor;
-- No UPDATE, INSERT, DELETE or event_import access is conferred.
CREATE OR REPLACE FUNCTION oracle2.hosting_job_metadata(run uuid)
 RETURNS TABLE(workspace_id uuid,run_id uuid,scope text,expires_at timestamptz)
 LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE n bigint; gateway boolean; documentary boolean;
BEGIN
 gateway := pg_has_role(SESSION_USER,'oracle2_gateway_metadata','member');
 documentary := pg_has_role(SESSION_USER,'oracle2_documentary_executor','member') AND oracle2.hosting_runtime_registered();
 IF NOT gateway AND NOT documentary THEN RETURN; END IF;
 SELECT count(*) INTO n FROM (
 SELECT v.run_id FROM oracle2.operating_view_runs v WHERE v.run_id=run AND v.status='pending' AND v.expires_at>clock_timestamp()
 UNION ALL SELECT a.run_id FROM oracle2.operating_action_runs a WHERE a.run_id=run AND a.status='pending' AND a.expires_at>clock_timestamp()) jobs;
 IF n<>1 THEN RETURN; END IF;
 RETURN QUERY SELECT v.workspace_id,v.run_id,'documentary-view'::text,v.expires_at
 FROM oracle2.operating_view_runs v WHERE v.run_id=run AND v.status='pending' AND v.expires_at>clock_timestamp()
 AND (gateway OR (documentary AND oracle2.hosting_view_authorized(v.workspace_id,v.actor_id,v.release_id,v.release_hash,v.source_refs)))
 UNION ALL SELECT a.workspace_id,a.run_id,'finding-review'::text,a.expires_at
 FROM oracle2.operating_action_runs a WHERE a.run_id=run AND a.status='pending' AND a.expires_at>clock_timestamp()
 AND a.operation='finding_review' AND (gateway OR (documentary AND oracle2.hosting_review_authorized(a.run_id)));
END $$;
REVOKE ALL ON FUNCTION oracle2.hosting_job_metadata(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_job_metadata(uuid) TO oracle2_gateway_metadata,oracle2_documentary_executor;
CREATE OR REPLACE FUNCTION oracle2.gateway_action_metadata(workspace uuid, run uuid)
 RETURNS TABLE(actor_id uuid,release_id uuid,release_hash text,status text,operation text,requested_scope text)
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT a.actor_id,a.release_id,a.release_hash,a.status,a.operation,a.payload->>'scope'
 FROM oracle2.operating_action_runs a WHERE a.workspace_id=workspace AND a.run_id=run
 AND a.operation='finding_review' AND a.expires_at>clock_timestamp() AND a.status='pending'
 AND jsonb_typeof(a.payload->'scope')='string' AND length(a.payload->>'scope') BETWEEN 1 AND 512
 AND (pg_has_role(SESSION_USER,'oracle2_gateway_metadata','member') OR
 (pg_has_role(SESSION_USER,'oracle2_documentary_executor','member') AND oracle2.hosting_review_authorized(run)));
$$;
REVOKE ALL ON FUNCTION oracle2.gateway_action_metadata(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.gateway_action_metadata(uuid,uuid) TO oracle2_gateway_metadata,oracle2_documentary_executor;
-- Bounded append binds the existing immutable action; arbitrary event insertion
-- and policy promotion remain unavailable. The worker validates the sealed finding.
CREATE OR REPLACE FUNCTION oracle2.append_hosted_finding_review(run uuid,event_payload jsonb)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE job oracle2.operating_action_runs%ROWTYPE; manifest jsonb; prior oracle2.finding_events%ROWTYPE;
BEGIN
 SELECT * INTO job FROM oracle2.operating_action_runs WHERE run_id=run FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'review unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||job.workspace_id::text));
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-selector:'||job.workspace_id::text,0));
 PERFORM 1 FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 PERFORM 1 FROM oracle2.hosting_role_source_admissions WHERE role_name=SESSION_USER AND workspace_id=job.workspace_id FOR SHARE;
 IF NOT pg_has_role(SESSION_USER,'oracle2_documentary_executor','member') OR job.status<>'pending'
 OR NOT oracle2.hosting_review_authorized(run) THEN RAISE EXCEPTION 'current scoped review required' USING ERRCODE='42501'; END IF;
 SELECT m.payload INTO manifest FROM oracle2.operating_release_manifests m WHERE m.workspace_id=job.workspace_id AND m.release_id=job.release_id;
 IF jsonb_typeof(event_payload) IS DISTINCT FROM 'object'
 OR NOT event_payload ?& ARRAY['artifact_id','version','finding_hash','note']
 OR (event_payload-ARRAY['artifact_id','version','finding_hash','note'])<>'{}'::jsonb
 OR event_payload->'artifact_id' IS DISTINCT FROM manifest->'artifact_id'
 OR event_payload->'version' IS DISTINCT FROM manifest->'artifact_version'
 OR event_payload->'note' IS DISTINCT FROM job.payload->'note'
 OR jsonb_typeof(event_payload->'finding_hash') IS DISTINCT FROM 'string'
 OR event_payload->>'finding_hash' !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'exact review binding required' USING ERRCODE='42501'; END IF;
 SELECT * INTO prior FROM oracle2.finding_events e WHERE e.workspace_id=job.workspace_id AND e.event_id=run;
 IF FOUND AND (prior.finding_id,prior.actor_id,prior.scope,prior.action,prior.payload)
 IS DISTINCT FROM (job.payload->>'finding_id',job.actor_id,job.payload->>'scope',job.payload->>'action',event_payload)
 THEN RAISE EXCEPTION 'review identity changed' USING ERRCODE='42501'; END IF;
 INSERT INTO oracle2.finding_events(workspace_id,finding_id,event_id,actor_id,scope,action,payload)
 VALUES(job.workspace_id,job.payload->>'finding_id',run,job.actor_id,job.payload->>'scope',job.payload->>'action',event_payload) ON CONFLICT DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION oracle2.append_hosted_finding_review(uuid,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.append_hosted_finding_review(uuid,jsonb) TO oracle2_documentary_executor;
CREATE OR REPLACE FUNCTION oracle2.complete_hosted_finding_review(run uuid)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE job oracle2.operating_action_runs%ROWTYPE; outcome jsonb;
BEGIN
 SELECT * INTO job FROM oracle2.operating_action_runs WHERE run_id=run FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'review unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-authz:'||job.workspace_id::text));
 PERFORM pg_advisory_xact_lock(hashtextextended('operating-selector:'||job.workspace_id::text,0));
 PERFORM 1 FROM oracle2.hosting_role_runtime_admissions WHERE role_name=SESSION_USER FOR SHARE;
 PERFORM 1 FROM oracle2.hosting_role_source_admissions WHERE role_name=SESSION_USER AND workspace_id=job.workspace_id FOR SHARE;
 IF NOT pg_has_role(SESSION_USER,'oracle2_documentary_executor','member') OR NOT oracle2.hosting_review_authorized(run)
 OR NOT EXISTS(SELECT 1 FROM oracle2.finding_events e WHERE e.workspace_id=job.workspace_id AND e.event_id=run
 AND e.actor_id=job.actor_id AND e.finding_id=job.payload->>'finding_id' AND e.scope=job.payload->>'scope'
 AND e.action=job.payload->>'action' AND e.payload->'note'=job.payload->'note')
 THEN RAISE EXCEPTION 'current recorded review required' USING ERRCODE='42501'; END IF;
 outcome := jsonb_build_object('state','completed','run_id',run::text,'review_recorded',true,'policy_promoted',false);
 IF job.status='completed' THEN
 IF job.result IS DISTINCT FROM outcome THEN RAISE EXCEPTION 'review result changed' USING ERRCODE='42501'; END IF;
 ELSE UPDATE oracle2.operating_action_runs SET status='completed',result=outcome WHERE run_id=run AND status='pending'; END IF;
 RETURN outcome;
END $$;
REVOKE ALL ON FUNCTION oracle2.complete_hosted_finding_review(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.complete_hosted_finding_review(uuid) TO oracle2_documentary_executor;
