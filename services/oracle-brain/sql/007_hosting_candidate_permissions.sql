-- NEW dedicated Oracle native ledger ONLY. Issuance/catalog seeding is separate.
CREATE TABLE IF NOT EXISTS oracle2.hosting_role_source_admissions (
 role_name name NOT NULL, workspace_id uuid NOT NULL, source_id uuid NOT NULL,
 revision integer NOT NULL CHECK(revision>0), principal_id uuid NOT NULL,
 original_hash text NOT NULL CHECK(original_hash ~ '^[0-9a-f]{64}$'),
 reading_hash text NOT NULL CHECK(reading_hash ~ '^[0-9a-f]{64}$'), parser_id text NOT NULL,
 runtime_hash text NOT NULL CHECK(runtime_hash ~ '^[0-9a-f]{64}$'),
 registry_hash text NOT NULL CHECK(registry_hash ~ '^[0-9a-f]{64}$'), expires_at timestamptz NOT NULL,
 PRIMARY KEY(role_name,workspace_id,source_id,revision));
REVOKE ALL ON oracle2.hosting_role_source_admissions FROM PUBLIC;
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT',r);
  END IF;
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls OR rolcanlogin))
   OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=r)) THEN
   RAISE EXCEPTION 'unsafe hosting scoped group';
  END IF;
  EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA oracle2 FROM %I',r);
  EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA oracle2 FROM %I',r);
  EXECUTE format('GRANT USAGE ON SCHEMA oracle2 TO %I',r);
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION oracle2.hosting_source_visible(workspace uuid, source uuid)
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT EXISTS(
 SELECT 1 FROM oracle2.hosting_role_source_admissions a
 JOIN oracle2.sources s ON s.workspace_id=a.workspace_id AND s.source_id=a.source_id AND s.revision=a.revision
 JOIN oracle2.operating_model_source_receipts r ON r.workspace_id=a.workspace_id AND r.source_id=a.source_id AND r.revision=a.revision
 WHERE a.role_name=SESSION_USER AND a.workspace_id=workspace AND a.source_id=source AND a.expires_at>now()
 AND s.status IN ('draft','confirmed') AND r.original_hash=a.original_hash AND r.reading_hash=a.reading_hash AND r.parser_id=a.parser_id
 AND EXISTS(SELECT 1 FROM oracle2.drafts d WHERE d.workspace_id=workspace AND d.source_id=source AND d.status='confirmed')
 AND EXISTS(WITH RECURSIVE lineage AS (
 SELECT p.appointment_id start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,1 depth
 FROM oracle2.appointments p WHERE p.workspace_id=workspace AND p.actor_id=a.principal_id AND p.scope IN ('source-read:'||source::text,'root')
 UNION ALL SELECT l.start_id,p.appointment_id,p.parent_id,p.revoked_at,p.expires_at,p.scope,p.workspace_id,l.depth+1
 FROM oracle2.appointments p JOIN lineage l ON l.parent_id=p.appointment_id WHERE l.depth<16 AND p.workspace_id=l.workspace_id)
 SELECT 1 FROM lineage GROUP BY start_id HAVING bool_and(revoked_at IS NULL AND (expires_at IS NULL OR expires_at>now())) AND bool_or(scope='root' AND parent_id IS NULL)));
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_source_visible(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_source_visible(uuid,uuid) TO oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor;
ALTER TABLE oracle2.source_blocks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hosting_source_read ON oracle2.source_blocks;
CREATE POLICY hosting_source_read ON oracle2.source_blocks FOR SELECT TO oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor
 USING(kind IN ('original','original-metadata') AND oracle2.hosting_source_visible(workspace_id,source_id));
GRANT SELECT(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) ON oracle2.source_blocks
 TO oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor;
CREATE OR REPLACE FUNCTION oracle2.hosting_candidate_outbox_visible(workspace uuid, assertion uuid, version integer, operation text, payload jsonb)
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT operation='project' AND jsonb_typeof(payload)='object'
 AND payload ?& ARRAY['namespace','manifest'] AND (payload - ARRAY['namespace','manifest'])='{}'::jsonb
 AND payload->>'namespace'='oracle_operating_model_v1'
 AND EXISTS(SELECT 1 FROM oracle2.artifact_manifests m WHERE m.workspace_id=workspace AND m.artifact_id=assertion AND m.version=version
 AND m.state IN ('ready','failed') AND m.manifest=payload->'manifest')
 AND EXISTS(SELECT 1 FROM oracle2.hosting_role_source_admissions a WHERE a.role_name=SESSION_USER AND a.workspace_id=workspace
 AND oracle2.hosting_source_visible(a.workspace_id,a.source_id));
$$;
REVOKE ALL ON FUNCTION oracle2.hosting_candidate_outbox_visible(uuid,uuid,integer,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.hosting_candidate_outbox_visible(uuid,uuid,integer,text,jsonb) TO oracle2_candidate_compiler;
ALTER TABLE oracle2.outbox ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS hosting_candidate_outbox_insert ON oracle2.outbox;
CREATE POLICY hosting_candidate_outbox_insert ON oracle2.outbox FOR INSERT TO oracle2_candidate_compiler
 WITH CHECK(oracle2.hosting_candidate_outbox_visible(workspace_id,assertion_id,revision,operation,payload)
 AND attempts=0 AND lease_until IS NULL AND delivered_at IS NULL);
GRANT INSERT(event_id,workspace_id,assertion_id,revision,operation,payload) ON oracle2.outbox TO oracle2_candidate_compiler;
-- Candidate/job write grants intentionally absent until each native table's
-- current workspace/run authority policy has its own reviewed contract.
-- No source/appointment/confirmed policy writes. Billing/gateway unchanged.
-- Exact columns retained PostgresSources/current authority needs; no receipts,
-- notes, draft connections or filenames granted.
GRANT SELECT(source_id,workspace_id,revision,status) ON oracle2.sources TO oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor;
GRANT SELECT(source_id,workspace_id,status) ON oracle2.drafts TO oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor;
GRANT SELECT(appointment_id,workspace_id,actor_id,scope,parent_id,expires_at,revoked_at) ON oracle2.appointments TO oracle2_source_reader,oracle2_candidate_compiler,oracle2_documentary_executor;
