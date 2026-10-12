-- NEW dedicated Oracle application ledger only. Never shared POP/legacy production.
-- Deployment owner separately issues a LOGIN role with membership in this
-- NOLOGIN metadata group. Gateway gets no blob, original or provider credential.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='oracle2_gateway_metadata') THEN
  CREATE ROLE oracle2_gateway_metadata NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
 END IF;
END $$;
-- Fail closed if an earlier issuer assigned elevated role privileges.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='oracle2_gateway_metadata'
  AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolcanlogin OR rolbypassrls))
  OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='oracle2_gateway_metadata')) THEN
  RAISE EXCEPTION 'gateway metadata group has unsafe privileges or memberships';
 END IF;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA oracle2 FROM oracle2_gateway_metadata;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA oracle2 FROM oracle2_gateway_metadata;
REVOKE ALL ON SCHEMA oracle2 FROM oracle2_gateway_metadata;
GRANT USAGE ON SCHEMA oracle2 TO oracle2_gateway_metadata;
GRANT SELECT(run_id,workspace_id,actor_id,release_id,release_hash,status,expires_at)
 ON oracle2.operating_view_runs TO oracle2_gateway_metadata;
GRANT SELECT(run_id,workspace_id,actor_id,operation,release_id,release_hash,status,expires_at)
 ON oracle2.operating_action_runs TO oracle2_gateway_metadata;
GRANT SELECT(workspace_id,release_id,generation,watermark)
 ON oracle2.operating_release_selectors TO oracle2_gateway_metadata;
-- Release payload is typed locator/hash/permission metadata, never originals.
GRANT SELECT(workspace_id,release_id,content_hash,payload)
 ON oracle2.operating_release_manifests TO oracle2_gateway_metadata;
GRANT SELECT(workspace_id,artifact_id,version,state,content_hash,permission_digest,source_digest)
 ON oracle2.artifact_manifests TO oracle2_gateway_metadata;
GRANT SELECT(workspace_id,artifact_id,version,upstream_kind,upstream_id,upstream_revision)
 ON oracle2.artifact_dependencies TO oracle2_gateway_metadata;
GRANT SELECT(workspace_id,artifact_id,version) ON oracle2.artifact_invalidations TO oracle2_gateway_metadata;
GRANT SELECT(workspace_id,sequence) ON oracle2.operating_model_change_log TO oracle2_gateway_metadata;
GRANT SELECT(appointment_id,workspace_id,actor_id,scope,parent_id,expires_at,revoked_at)
 ON oracle2.appointments TO oracle2_gateway_metadata;
GRANT SELECT(source_id,workspace_id,revision,status) ON oracle2.sources TO oracle2_gateway_metadata;
GRANT SELECT(source_id,workspace_id,status) ON oracle2.drafts TO oracle2_gateway_metadata;
GRANT SELECT(workspace_id,source_id,revision,original_hash,reading_hash,parser_id)
 ON oracle2.operating_model_source_receipts TO oracle2_gateway_metadata;

-- Bounded projection avoids granting payload/notes/result to gateway.
-- Owned by ledger installer, not the gateway LOGIN role. Fixed qualified names
-- and search_path prevent attacker-controlled function/table substitution.
CREATE OR REPLACE FUNCTION oracle2.gateway_action_metadata(workspace uuid, run uuid)
 RETURNS TABLE(actor_id uuid,release_id uuid,release_hash text,status text,operation text,requested_scope text)
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT a.actor_id,a.release_id,a.release_hash,a.status,a.operation,a.payload->>'scope'
 FROM oracle2.operating_action_runs a
 WHERE a.workspace_id=workspace AND a.run_id=run AND a.operation='finding_review'
  AND a.expires_at>now() AND a.status='pending'
  AND jsonb_typeof(a.payload->'scope')='string'
  AND length(a.payload->>'scope') BETWEEN 1 AND 512
$$;
REVOKE ALL ON FUNCTION oracle2.gateway_action_metadata(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.gateway_action_metadata(uuid,uuid) TO oracle2_gateway_metadata;
