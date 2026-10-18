-- NEW empty oracle_native_proof_v2 ledger only; never the retained pilot DB.
-- One separately authorized invented run. Old jobs/roots are not admitted.
DO $$ BEGIN
 IF current_database()<>'oracle_native_proof_v2' THEN RAISE EXCEPTION 'new native proof database required'; END IF;
 IF EXISTS(SELECT 1 FROM oracle2.operating_view_runs WHERE run_id<>'6714d4ed-51df-4c38-9155-c456edf7b727') THEN
 RAISE EXCEPTION 'foreign native job population'; END IF;
END $$;
CREATE TABLE oracle2.native_trigger_projections(
 run_id uuid PRIMARY KEY CHECK(run_id='6714d4ed-51df-4c38-9155-c456edf7b727'),
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),completed_at timestamptz
);
REVOKE ALL ON oracle2.native_trigger_projections FROM PUBLIC,oracle_native_v2_gateway_metadata,oracle_native_v2_documentary_executor;
CREATE FUNCTION oracle2.native_trigger_projection(run uuid,finish boolean)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE j oracle2.operating_view_runs%ROWTYPE;
BEGIN
 IF SESSION_USER<>'oracle_native_v2_projector' OR run<>'6714d4ed-51df-4c38-9155-c456edf7b727' OR finish IS NULL OR NOT oracle2.hosting_runtime_registered() THEN
 RAISE EXCEPTION 'new native projector denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO j FROM oracle2.operating_view_runs WHERE run_id=run FOR UPDATE;
 IF NOT FOUND OR j.status<>'pending' OR j.expires_at<=clock_timestamp() OR NOT oracle2.hosting_view_authorized(j.workspace_id,j.actor_id,j.release_id,j.release_hash,j.source_refs) THEN
 RAISE EXCEPTION 'current new native projector permission required' USING ERRCODE='42501'; END IF;
 IF finish THEN
 UPDATE oracle2.native_trigger_projections SET completed_at=clock_timestamp() WHERE run_id=run AND completed_at IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'native projection attempt absent or completed' USING ERRCODE='42501'; END IF;
 ELSE
 INSERT INTO oracle2.native_trigger_projections(run_id) VALUES(run);
 END IF;
END $$;
REVOKE ALL ON FUNCTION oracle2.native_trigger_projection(uuid,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.native_trigger_projection(uuid,boolean) TO oracle_native_v2_documentary_executor;
CREATE TABLE oracle2.native_trigger_attempts(
 run_id uuid PRIMARY KEY REFERENCES oracle2.operating_view_runs(run_id)
 CHECK(run_id='6714d4ed-51df-4c38-9155-c456edf7b727'),
 requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 trigger_run text CHECK(trigger_run ~ '^run_[A-Za-z0-9]{8,100}$'),
 worker_claimed_at timestamptz
);
REVOKE ALL ON oracle2.native_trigger_attempts FROM PUBLIC,oracle_native_v2_gateway_metadata,oracle_native_v2_documentary_executor;
CREATE FUNCTION oracle2.native_trigger_dispatch(run uuid,runtime text,admission text)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
BEGIN
 IF run<>'6714d4ed-51df-4c38-9155-c456edf7b727' OR (SESSION_USER<>'oracle_native_v2_gateway' OR NOT pg_has_role(SESSION_USER,'oracle_native_v2_gateway_metadata','MEMBER')) THEN
 RAISE EXCEPTION 'new native dispatch denied' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM oracle2.native_trigger_projections WHERE run_id=run AND completed_at IS NOT NULL) THEN RAISE EXCEPTION 'native projection not proved' USING ERRCODE='42501'; END IF;
 IF (SELECT result_status FROM oracle2.gateway_view_result(run,runtime,admission)) IS DISTINCT FROM 'pending' THEN
 RAISE EXCEPTION 'new pending native dispatch required' USING ERRCODE='42501'; END IF;
 -- Primary-key conflict is a spent/uncertain dispatch; never retry it.
 INSERT INTO oracle2.native_trigger_attempts(run_id) VALUES(run);
END $$;
CREATE FUNCTION oracle2.native_trigger_bind(run uuid,trigger_id text)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
BEGIN
 IF run<>'6714d4ed-51df-4c38-9155-c456edf7b727' OR trigger_id IS NULL OR trigger_id !~ '^run_[A-Za-z0-9]{8,100}$'
 OR (SESSION_USER<>'oracle_native_v2_gateway' OR NOT pg_has_role(SESSION_USER,'oracle_native_v2_gateway_metadata','MEMBER')) THEN
 RAISE EXCEPTION 'new native dispatch binding denied' USING ERRCODE='42501'; END IF;
 UPDATE oracle2.native_trigger_attempts SET trigger_run=trigger_id WHERE run_id=run AND (trigger_run IS NULL OR trigger_run=trigger_id);
 IF NOT FOUND THEN RAISE EXCEPTION 'native dispatch binding changed' USING ERRCODE='42501'; END IF;
END $$;
CREATE FUNCTION oracle2.native_trigger_claim(run uuid,trigger_id text)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE j oracle2.operating_view_runs%ROWTYPE;
BEGIN
 IF run<>'6714d4ed-51df-4c38-9155-c456edf7b727' OR trigger_id IS NULL OR trigger_id !~ '^run_[A-Za-z0-9]{8,100}$'
 OR SESSION_USER<>'oracle_native_v2_executor' OR NOT pg_has_role(SESSION_USER,'oracle_native_v2_documentary_executor','MEMBER') OR NOT oracle2.hosting_runtime_registered() THEN
 RAISE EXCEPTION 'new native executor denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO j FROM oracle2.operating_view_runs WHERE run_id=run FOR UPDATE;
 IF NOT FOUND OR j.status<>'pending' OR j.workspace_id<>'cc904285-f213-4a57-9cdb-06f8c278d3ec'
 OR j.actor_id<>'a29fad82-de03-43c7-8ab2-885e94d8e8dc' OR j.expires_at<=clock_timestamp()
 OR NOT oracle2.hosting_view_authorized(j.workspace_id,j.actor_id,j.release_id,j.release_hash,j.source_refs) THEN
 RAISE EXCEPTION 'current new native job required' USING ERRCODE='42501'; END IF;
 UPDATE oracle2.native_trigger_attempts SET trigger_run=trigger_id,worker_claimed_at=clock_timestamp()
 WHERE run_id=run AND worker_claimed_at IS NULL AND (trigger_run IS NULL OR trigger_run=trigger_id);
 IF NOT FOUND THEN RAISE EXCEPTION 'native attempt absent or already spent' USING ERRCODE='42501'; END IF;
END $$;
CREATE FUNCTION oracle2.native_trigger_run(run uuid)
 RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT a.trigger_run FROM oracle2.native_trigger_attempts a WHERE a.run_id=run
 AND run='6714d4ed-51df-4c38-9155-c456edf7b727' AND SESSION_USER='oracle_native_v2_gateway' AND pg_has_role(SESSION_USER,'oracle_native_v2_gateway_metadata','MEMBER')
$$;
REVOKE ALL ON FUNCTION oracle2.native_trigger_dispatch(uuid,text,text),oracle2.native_trigger_bind(uuid,text),oracle2.native_trigger_claim(uuid,text),oracle2.native_trigger_run(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.native_trigger_dispatch(uuid,text,text),oracle2.native_trigger_bind(uuid,text),oracle2.native_trigger_run(uuid) TO oracle_native_v2_gateway_metadata;
GRANT EXECUTE ON FUNCTION oracle2.native_trigger_claim(uuid,text) TO oracle_native_v2_documentary_executor;
CREATE TABLE oracle2.native_trigger_sessions(
 session_hash text PRIMARY KEY CHECK(session_hash ~ '^[a-f0-9]{64}$'),
 settings_hash text NOT NULL CHECK(settings_hash ~ '^[a-f0-9]{64}$'),
 token_hash text NOT NULL CHECK(token_hash ~ '^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,revoked_at timestamptz
);
REVOKE ALL ON oracle2.native_trigger_sessions FROM PUBLIC,oracle_native_v2_gateway_metadata,oracle_native_v2_documentary_executor;
CREATE FUNCTION oracle2.native_trigger_session_create(session_hash text,settings_hash text,token_hash text)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
DECLARE expiry timestamptz;
BEGIN
 IF (SESSION_USER<>'oracle_native_v2_gateway' OR NOT pg_has_role(SESSION_USER,'oracle_native_v2_gateway_metadata','MEMBER')) OR session_hash IS NULL OR settings_hash IS NULL OR token_hash IS NULL
 OR session_hash !~ '^[a-f0-9]{64}$' OR settings_hash !~ '^[a-f0-9]{64}$' OR token_hash !~ '^[a-f0-9]{64}$' THEN
 RAISE EXCEPTION 'native session denied' USING ERRCODE='42501'; END IF;
 SELECT expires_at INTO expiry FROM oracle2.operating_view_runs WHERE run_id='6714d4ed-51df-4c38-9155-c456edf7b727' AND expires_at>clock_timestamp();
 IF NOT FOUND OR (SELECT count(*) FROM oracle2.native_trigger_sessions WHERE expires_at>clock_timestamp() AND revoked_at IS NULL)>=32 THEN
 RAISE EXCEPTION 'native session unavailable' USING ERRCODE='42501'; END IF;
 INSERT INTO oracle2.native_trigger_sessions VALUES(session_hash,settings_hash,token_hash,least(expiry,clock_timestamp()+interval '300 seconds'),NULL);
END $$;
CREATE FUNCTION oracle2.native_trigger_session_live(s text,settings text,token text)
 RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 SELECT SESSION_USER='oracle_native_v2_gateway' AND pg_has_role(SESSION_USER,'oracle_native_v2_gateway_metadata','MEMBER') AND EXISTS(
 SELECT 1 FROM oracle2.native_trigger_sessions WHERE session_hash=s AND settings_hash=settings AND token_hash=token AND expires_at>clock_timestamp() AND revoked_at IS NULL)
$$;
CREATE FUNCTION oracle2.native_trigger_session_revoke(s text)
 RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $$
 UPDATE oracle2.native_trigger_sessions SET revoked_at=clock_timestamp() WHERE session_hash=s AND SESSION_USER='oracle_native_v2_gateway' AND pg_has_role(SESSION_USER,'oracle_native_v2_gateway_metadata','MEMBER')
$$;
REVOKE ALL ON FUNCTION oracle2.native_trigger_session_create(text,text,text),oracle2.native_trigger_session_live(text,text,text),oracle2.native_trigger_session_revoke(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.native_trigger_session_create(text,text,text),oracle2.native_trigger_session_live(text,text,text),oracle2.native_trigger_session_revoke(text) TO oracle_native_v2_gateway_metadata;
