-- Dedicated Oracle operational participation. No provider/meeting activation,
-- appointment issuer, accepted truth, supplier dedup or visible-message proof.
DO $owner$ DECLARE o oid;p record; BEGIN
 SELECT nspowner INTO o FROM pg_namespace WHERE nspname='oracle2';
 SELECT proowner,prosecdef,proconfig,proacl INTO p FROM pg_proc
 WHERE oid=to_regprocedure('oracle2._meeting_capture_current_v1(uuid,text,timestamp with time zone)');
 IF o IS DISTINCT FROM (SELECT oid FROM pg_roles WHERE rolname=CURRENT_USER)
 OR p.proowner IS DISTINCT FROM o OR p.prosecdef IS DISTINCT FROM true
 OR p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, oracle2']::text[]
 OR EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',o))) WHERE grantee<>o AND privilege_type='EXECUTE') THEN
  RAISE EXCEPTION 'reviewed private current capture owner required';
 END IF;
END $owner$;
CREATE TABLE oracle2.meeting_participation_admissions_v1 (
 admission_id uuid PRIMARY KEY,admission_sha256 text NOT NULL CHECK(admission_sha256~'^[a-f0-9]{64}$'),
 workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,principal_id uuid NOT NULL,role_name name NOT NULL,
 kind text NOT NULL CHECK(kind IN('host','sender','observer')),
 leaf_appointment_id uuid NOT NULL REFERENCES oracle2.appointments(appointment_id),
 capture_admission_id uuid NOT NULL,capture_admission_sha256 text NOT NULL CHECK(capture_admission_sha256~'^[a-f0-9]{64}$'),
 provider text NOT NULL CHECK(provider='recall'),platform text NOT NULL CHECK(platform='microsoft_teams'),
 provider_account text NOT NULL CHECK(length(btrim(provider_account)) BETWEEN 1 AND 256),
 tenant_id text NOT NULL CHECK(length(btrim(tenant_id)) BETWEEN 1 AND 256),
 provider_meeting_id text NOT NULL CHECK(length(btrim(provider_meeting_id)) BETWEEN 1 AND 2048),bot_id uuid NOT NULL,
 runtime_hash text NOT NULL CHECK(runtime_hash~'^[a-f0-9]{64}$'),registry_hash text NOT NULL CHECK(registry_hash~'^[a-f0-9]{64}$'),
 observation_owner_sha256 text NOT NULL CHECK(observation_owner_sha256~'^[a-f0-9]{64}$'),
 composer_sha256 text NOT NULL CHECK(composer_sha256~'^[a-f0-9]{64}$'),
 actions text[] NOT NULL CHECK(cardinality(actions) BETWEEN 1 AND 5),
 issuer_actor uuid NOT NULL,reviewer_actor uuid NOT NULL CHECK(issuer_actor<>reviewer_actor),
 valid_from timestamptz NOT NULL,expires_at timestamptz NOT NULL,original_horizon timestamptz NOT NULL,
 CHECK(principal_id<>issuer_actor AND principal_id<>reviewer_actor),
 CHECK(isfinite(valid_from) AND isfinite(expires_at) AND isfinite(original_horizon) AND valid_from<expires_at AND expires_at<=original_horizon),
 CHECK((kind='host' AND actions<@ARRAY['enable','disable','status']) OR
       (kind='sender' AND actions<@ARRAY['prepare','claim','receipt','status']) OR
       (kind='observer' AND actions<@ARRAY['observe','status'])));
CREATE TABLE oracle2.meeting_participation_revocations_v1 (
 revocation_id uuid PRIMARY KEY,admission_id uuid NOT NULL REFERENCES oracle2.meeting_participation_admissions_v1(admission_id),
 revoked_at timestamptz NOT NULL CHECK(isfinite(revoked_at)),reason_sha256 text NOT NULL CHECK(reason_sha256~'^[a-f0-9]{64}$'));
CREATE TABLE oracle2.meeting_participation_heads_v1 (
 workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,version integer NOT NULL DEFAULT 0 CHECK(version BETWEEN 0 AND 16384),
 generation integer NOT NULL DEFAULT 0 CHECK(generation>=0),enabled boolean NOT NULL DEFAULT false,proactive_enabled boolean NOT NULL DEFAULT false,
 cooldown_seconds integer NOT NULL DEFAULT 120 CHECK(cooldown_seconds BETWEEN 120 AND 86400),
 max_proactive integer NOT NULL DEFAULT 3 CHECK(max_proactive BETWEEN 0 AND 3),
 proactive_count integer NOT NULL DEFAULT 0 CHECK(proactive_count BETWEEN 0 AND 3),last_proactive_at timestamptz,
 last_event_id uuid,active_intent_id uuid,PRIMARY KEY(workspace_id,meeting_id));
CREATE TABLE oracle2.meeting_participation_observations_v1 (
 observation_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_participation_admissions_v1(admission_id),actor_id uuid NOT NULL,
 payload jsonb NOT NULL,payload_sha256 text NOT NULL CHECK(payload_sha256~'^[a-f0-9]{64}$'),
 observed_at timestamptz NOT NULL,valid_until timestamptz NOT NULL,
 CHECK(isfinite(observed_at) AND isfinite(valid_until) AND observed_at<valid_until AND valid_until<=observed_at+interval '30 seconds'));
CREATE TABLE oracle2.meeting_participation_events_v1 (
 event_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,version integer NOT NULL CHECK(version>0),
 generation integer NOT NULL,admission_id uuid NOT NULL REFERENCES oracle2.meeting_participation_admissions_v1(admission_id),actor_id uuid NOT NULL,
 action text NOT NULL,payload jsonb NOT NULL,payload_sha256 text NOT NULL CHECK(payload_sha256~'^[a-f0-9]{64}$'),
 operation_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,meeting_id,version),UNIQUE(workspace_id,meeting_id,operation_id));
CREATE TABLE oracle2.meeting_participation_intents_v1 (
 intent_id uuid PRIMARY KEY,workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,generation integer NOT NULL,
 sender_admission_id uuid NOT NULL REFERENCES oracle2.meeting_participation_admissions_v1(admission_id),actor_id uuid NOT NULL,
 turn_event_id uuid NOT NULL,raw_sha256 text NOT NULL CHECK(raw_sha256~'^[a-f0-9]{64}$'),turn_frame jsonb NOT NULL,capture_event_id uuid NOT NULL,
 capture_sha256 text NOT NULL CHECK(capture_sha256~'^[a-f0-9]{64}$'),capture_revision integer NOT NULL CHECK(capture_revision>0),
 body text NOT NULL CHECK(char_length(body) BETWEEN 1 AND 4096 AND length(btrim(body))>0),body_sha256 text NOT NULL CHECK(body_sha256~'^[a-f0-9]{64}$'),
 proactive boolean NOT NULL,evidence_scope text NOT NULL CHECK(evidence_scope='meeting_only'),
 observation_id uuid NOT NULL REFERENCES oracle2.meeting_participation_observations_v1(observation_id),
 request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 -- A host toggle is never a resend key, including after UNKNOWN.
 UNIQUE(workspace_id,meeting_id,turn_event_id));
CREATE TABLE oracle2.meeting_participation_delivery_heads_v1 (
 intent_id uuid PRIMARY KEY REFERENCES oracle2.meeting_participation_intents_v1(intent_id),revision integer NOT NULL DEFAULT 0,
 state text NOT NULL CHECK(state IN('intent','inflight','provider-response-observed','UNKNOWN','suppressed')),
 claim_event_id uuid,claim_operation_id uuid,claim_deadline timestamptz,last_event_id uuid,
 CHECK((state='intent' AND claim_event_id IS NULL) OR state<>'intent'));
CREATE TABLE oracle2.meeting_participation_delivery_events_v1 (
 event_id uuid PRIMARY KEY,intent_id uuid NOT NULL REFERENCES oracle2.meeting_participation_intents_v1(intent_id),revision integer NOT NULL CHECK(revision>0),
 admission_id uuid NOT NULL REFERENCES oracle2.meeting_participation_admissions_v1(admission_id),actor_id uuid NOT NULL,
 action text NOT NULL CHECK(action IN('claim','provider-response-observed','UNKNOWN','suppressed')),
 operation_id uuid NOT NULL,payload jsonb NOT NULL,payload_sha256 text NOT NULL CHECK(payload_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(intent_id,revision),UNIQUE(intent_id,operation_id));
DO $private$ DECLARE n text; BEGIN
 FOREACH n IN ARRAY ARRAY['meeting_participation_admissions_v1','meeting_participation_revocations_v1','meeting_participation_observations_v1','meeting_participation_events_v1','meeting_participation_intents_v1','meeting_participation_delivery_events_v1'] LOOP
  EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()','immutable_'||n,n);
 END LOOP;
 FOREACH n IN ARRAY ARRAY['meeting_participation_admissions_v1','meeting_participation_revocations_v1','meeting_participation_heads_v1','meeting_participation_observations_v1','meeting_participation_events_v1','meeting_participation_intents_v1','meeting_participation_delivery_heads_v1','meeting_participation_delivery_events_v1'] LOOP
  EXECUTE format('ALTER TABLE oracle2.%I ENABLE ROW LEVEL SECURITY',n);
  EXECUTE format('REVOKE ALL ON oracle2.%I FROM PUBLIC,oracle2_replacement_requester',n);
 END LOOP;
END $private$;

CREATE FUNCTION oracle2._meeting_participation_lineage_v1(m oracle2.meeting_participation_admissions_v1)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE p oracle2.appointments%ROWTYPE;seen uuid[]:='{}';until timestamptz:=m.expires_at;
BEGIN
 SELECT * INTO p FROM oracle2.appointments WHERE appointment_id=m.leaf_appointment_id FOR SHARE;
 IF p.appointment_id IS NULL OR p.workspace_id<>m.workspace_id OR p.actor_id<>m.principal_id OR p.scope<>'meeting-participation-'||m.kind THEN
  RAISE insufficient_privilege USING MESSAGE='exact participation leaf denied';END IF;
 LOOP
  IF p.appointment_id=ANY(seen) OR cardinality(seen)>=16 OR p.workspace_id<>m.workspace_id OR p.revoked_at IS NOT NULL
  OR (p.expires_at IS NOT NULL AND(NOT isfinite(p.expires_at) OR p.expires_at<=clock_timestamp())) THEN
   RAISE insufficient_privilege USING MESSAGE='current participation root denied';END IF;
  seen:=array_append(seen,p.appointment_id);until:=least(until,coalesce(p.expires_at,until));
  IF p.parent_id IS NULL THEN
   IF p.scope<>'root' OR until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='participation root denied';END IF;
   RETURN until;
  END IF;
  SELECT parent.* INTO p FROM oracle2.appointments parent WHERE parent.appointment_id=p.parent_id
   AND parent.actor_id=p.granted_by AND parent.scope IN('meeting-participation-'||m.kind,'root') FOR SHARE;
  IF p.appointment_id IS NULL THEN RAISE insufficient_privilege USING MESSAGE='participation root broken';END IF;
 END LOOP;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_lineage_v1(oracle2.meeting_participation_admissions_v1) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_participation_peer_current_v1(m oracle2.meeting_participation_admissions_v1,wanted_kind text)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE until timestamptz;root_until timestamptz;
BEGIN
 IF wanted_kind NOT IN('host','observer') OR wanted_kind IS NULL OR m.kind IS DISTINCT FROM wanted_kind THEN
  RAISE insufficient_privilege USING MESSAGE='closed installed participation peer required';END IF;
 PERFORM 1 FROM oracle2.meeting_participation_admissions_v1 WHERE admission_id=m.admission_id AND admission_sha256=m.admission_sha256 FOR SHARE;
 IF NOT FOUND THEN RAISE insufficient_privilege USING MESSAGE='actual immutable peer admission required';END IF;
 SELECT least(a.expires_at,r.expires_at,m.expires_at,m.original_horizon) INTO until
 FROM oracle2.hosting_request_principal_admissions a JOIN oracle2.hosting_role_runtime_admissions r USING(role_name)
 WHERE a.role_name=m.role_name AND a.principal_id=m.principal_id AND a.workspace_id=m.workspace_id
 AND a.runtime_hash=m.runtime_hash AND a.registry_hash=m.registry_hash
 AND r.runtime_hash=a.runtime_hash AND r.registry_hash=a.registry_hash
 AND isfinite(a.expires_at) AND isfinite(r.expires_at) FOR SHARE OF a,r;
 IF until IS NULL OR until<=clock_timestamp() OR m.valid_from>clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.meeting_participation_revocations_v1 WHERE admission_id=m.admission_id)
 OR NOT EXISTS(SELECT 1 FROM pg_roles login JOIN pg_roles g ON g.rolname='oracle2_replacement_requester'
  WHERE login.rolname=m.role_name AND login.rolcanlogin AND NOT(login.rolsuper OR login.rolcreatedb OR login.rolcreaterole OR login.rolreplication OR login.rolbypassrls)
  AND pg_has_role(login.oid,g.oid,'MEMBER') AND NOT EXISTS(SELECT 1 FROM pg_roles x WHERE x.oid NOT IN(login.oid,g.oid)
   AND(pg_has_role(login.oid,x.oid,'MEMBER') OR pg_has_role(login.oid,x.oid,'SET') OR pg_has_role(login.oid,x.oid,'USAGE')))) THEN
  RAISE insufficient_privilege USING MESSAGE='current exact installed participation peer denied';END IF;
 root_until:=oracle2._meeting_participation_lineage_v1(m);
 RETURN least(until,root_until);
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_peer_current_v1(oracle2.meeting_participation_admissions_v1,text) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_participation_host_v1(m oracle2.meeting_participation_admissions_v1,wanted_generation integer,deadline timestamptz)
 RETURNS timestamptz LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE authority oracle2.meeting_participation_admissions_v1%ROWTYPE;event oracle2.meeting_participation_events_v1%ROWTYPE;
BEGIN
 SELECT * INTO event FROM oracle2.meeting_participation_events_v1 e
 WHERE e.workspace_id=m.workspace_id AND e.meeting_id=m.meeting_id AND e.generation=wanted_generation AND e.action='enable';
 SELECT * INTO authority FROM oracle2.meeting_participation_admissions_v1 WHERE admission_id=event.admission_id FOR SHARE;
 IF event.event_id IS NULL OR event.actor_id IS DISTINCT FROM authority.principal_id
 OR authority.workspace_id IS DISTINCT FROM m.workspace_id OR authority.meeting_id IS DISTINCT FROM m.meeting_id
 OR authority.provider IS DISTINCT FROM m.provider OR authority.platform IS DISTINCT FROM m.platform
 OR authority.provider_account IS DISTINCT FROM m.provider_account OR authority.tenant_id IS DISTINCT FROM m.tenant_id
 OR authority.provider_meeting_id IS DISTINCT FROM m.provider_meeting_id OR authority.bot_id IS DISTINCT FROM m.bot_id THEN
  RAISE insufficient_privilege USING MESSAGE='actual current enabling host denied';END IF;
 RETURN least(deadline,m.expires_at,oracle2._meeting_participation_peer_current_v1(authority,'host'));
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_host_v1(oracle2.meeting_participation_admissions_v1,integer,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_participation_admission_v1(selected uuid,seal text,act text,deadline timestamptz)
 RETURNS oracle2.meeting_participation_admissions_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE a oracle2.hosting_request_principal_admissions%ROWTYPE;m oracle2.meeting_participation_admissions_v1%ROWTYPE;
BEGIN
 a:=oracle2._replacement_request_context();
 SELECT * INTO m FROM oracle2.meeting_participation_admissions_v1 WHERE admission_id=selected FOR SHARE;
 IF m.admission_id IS NULL OR m.admission_sha256 IS DISTINCT FROM seal OR m.workspace_id<>a.workspace_id OR m.principal_id<>a.principal_id
 OR m.role_name<>SESSION_USER OR m.runtime_hash<>a.runtime_hash OR m.registry_hash<>a.registry_hash OR NOT(act=ANY(m.actions))
 OR deadline IS NULL OR act IS NULL OR NOT isfinite(deadline) OR deadline<=clock_timestamp() OR deadline>clock_timestamp()+interval '30 seconds'
 OR m.valid_from>clock_timestamp() OR m.expires_at<=clock_timestamp() OR m.original_horizon<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.meeting_participation_revocations_v1 WHERE admission_id=selected) THEN
  RAISE insufficient_privilege USING MESSAGE='current participation admission denied';END IF;
 m.expires_at:=least(a.expires_at,m.expires_at,m.original_horizon,deadline);
 m.expires_at:=oracle2._meeting_participation_lineage_v1(m);RETURN m;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_admission_v1(uuid,text,text,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_participation_capture_v1(m oracle2.meeting_participation_admissions_v1,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE c jsonb;
BEGIN
 c:=oracle2._meeting_capture_current_v1(m.capture_admission_id,m.capture_admission_sha256,deadline);
 IF c->>'workspace_id' IS DISTINCT FROM m.workspace_id::text OR c->>'meeting_id' IS DISTINCT FROM m.meeting_id::text
 OR c->>'provider' IS DISTINCT FROM m.provider OR c->>'provider_account' IS DISTINCT FROM m.provider_account
 OR c->>'tenant_id' IS DISTINCT FROM m.tenant_id OR c->>'provider_meeting_id' IS DISTINCT FROM m.provider_meeting_id
 OR c->>'bot_id' IS DISTINCT FROM m.bot_id::text THEN RAISE insufficient_privilege USING MESSAGE='exact current capture differs';END IF;
 RETURN c;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_capture_v1(oracle2.meeting_participation_admissions_v1,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_participation_observation_v1(m oracle2.meeting_participation_admissions_v1,wanted uuid,c jsonb,deadline timestamptz)
 RETURNS oracle2.meeting_participation_observations_v1 LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE o oracle2.meeting_participation_observations_v1%ROWTYPE;authority oracle2.meeting_participation_admissions_v1%ROWTYPE;until timestamptz;observer_until timestamptz;
BEGIN
 SELECT * INTO o FROM oracle2.meeting_participation_observations_v1 WHERE observation_id=wanted FOR SHARE;
 SELECT * INTO authority FROM oracle2.meeting_participation_admissions_v1 WHERE admission_id=o.admission_id FOR SHARE;
 observer_until:=oracle2._meeting_participation_peer_current_v1(authority,'observer');
 PERFORM 1 FROM oracle2.meeting_participation_audience_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 IF o.observation_id IS NULL OR o.workspace_id<>m.workspace_id OR o.meeting_id<>m.meeting_id OR authority.kind<>'observer'
 OR authority.provider_account<>m.provider_account OR authority.tenant_id<>m.tenant_id OR authority.provider_meeting_id<>m.provider_meeting_id
 OR authority.bot_id<>m.bot_id OR authority.observation_owner_sha256<>m.observation_owner_sha256
 OR observer_until IS NULL OR observer_until<=clock_timestamp()
 OR NOT EXISTS(SELECT 1 FROM oracle2.meeting_participation_audience_heads_v1 h WHERE h.workspace_id=m.workspace_id AND h.meeting_id=m.meeting_id AND h.observation_id=wanted)
 OR authority.valid_from>clock_timestamp() OR authority.expires_at<=clock_timestamp() OR authority.original_horizon<=clock_timestamp()
 OR EXISTS(SELECT 1 FROM oracle2.meeting_participation_revocations_v1 WHERE admission_id=authority.admission_id)
 OR o.observed_at>clock_timestamp() OR o.valid_until<=clock_timestamp()
 OR o.payload->>'capture_event_id' IS DISTINCT FROM c->>'capture_event_id' OR o.payload->>'capture_sha256' IS DISTINCT FROM c->>'capture_event_sha256'
 OR o.payload->>'capture_revision' IS DISTINCT FROM c->>'capture_revision' OR o.payload->>'platform' IS DISTINCT FROM 'microsoft_teams'
 OR o.payload->'channel_meeting' IS DISTINCT FROM 'false'::jsonb OR o.payload->'chat_available' IS DISTINCT FROM 'true'::jsonb THEN
  RAISE insufficient_privilege USING MESSAGE='current independently appointed Teams capability denied';END IF;
 -- Current observer exact rooted path is rechecked; a stored fact is not a lease.
 until:=oracle2._meeting_participation_lineage_v1(authority);
 o.valid_until:=least(o.valid_until,until,observer_until,authority.original_horizon,deadline,(c->>'valid_until')::timestamptz,m.expires_at);
 IF o.valid_until<=clock_timestamp() THEN RAISE insufficient_privilege USING MESSAGE='current audience observation expired';END IF;
 RETURN o;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_observation_v1(oracle2.meeting_participation_admissions_v1,uuid,jsonb,timestamptz) FROM PUBLIC,oracle2_replacement_requester;
CREATE TABLE oracle2.meeting_participation_audience_heads_v1 (
 workspace_id uuid NOT NULL,meeting_id uuid NOT NULL,revision integer NOT NULL CHECK(revision>0),
 observation_id uuid NOT NULL REFERENCES oracle2.meeting_participation_observations_v1(observation_id),PRIMARY KEY(workspace_id,meeting_id));
ALTER TABLE oracle2.meeting_participation_audience_heads_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON oracle2.meeting_participation_audience_heads_v1 FROM PUBLIC,oracle2_replacement_requester;
CREATE FUNCTION oracle2._meeting_participation_revoke_lock_v1() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,oracle2 AS $f$
BEGIN
 PERFORM 1 FROM oracle2.meeting_participation_admissions_v1 WHERE admission_id=NEW.admission_id FOR UPDATE;
 RETURN NEW;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_revoke_lock_v1() FROM PUBLIC;
CREATE TRIGGER participation_revocation_serial BEFORE INSERT ON oracle2.meeting_participation_revocations_v1 FOR EACH ROW EXECUTE FUNCTION oracle2._meeting_participation_revoke_lock_v1();

CREATE FUNCTION oracle2.meeting_participation_observe_audience_v1(selected uuid,seal text,expected_revision integer,observation uuid,body jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_participation_admissions_v1%ROWTYPE;c jsonb;old oracle2.meeting_participation_observations_v1%ROWTYPE;
 head oracle2.meeting_participation_audience_heads_v1%ROWTYPE;hash text;at timestamptz;until timestamptz;entry jsonb;ids text[]:='{}';required text[];
BEGIN
 m:=oracle2._meeting_participation_admission_v1(selected,seal,'observe',deadline);
 IF m.kind<>'observer' THEN RAISE insufficient_privilege USING MESSAGE='independently appointed observation owner required';END IF;
 required:=ARRAY['observation_owner_sha256','provider_observation_sha256','capture_event_id','capture_sha256','capture_revision','platform','channel_meeting','chat_available','audience_complete','participants','observed_at','valid_until'];
 IF observation IS NULL OR expected_revision IS NULL OR expected_revision<0 OR jsonb_typeof(body) IS DISTINCT FROM 'object'
 OR NOT(body ?& required) OR body-required<>'{}'::jsonb OR octet_length(body::text)>262144
 OR body->>'observation_owner_sha256' IS DISTINCT FROM m.observation_owner_sha256
 OR jsonb_typeof(body->'provider_observation_sha256') IS DISTINCT FROM 'string' OR body->>'provider_observation_sha256'!~'^[a-f0-9]{64}$'
 OR jsonb_typeof(body->'capture_event_id') IS DISTINCT FROM 'string' OR body->>'capture_event_id'!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
 OR jsonb_typeof(body->'capture_sha256') IS DISTINCT FROM 'string' OR body->>'capture_sha256'!~'^[a-f0-9]{64}$'
 OR jsonb_typeof(body->'capture_revision') IS DISTINCT FROM 'number' OR body->>'capture_revision'!~'^[1-9][0-9]{0,8}$'
 OR body->>'platform' NOT IN('microsoft_teams','unknown') OR jsonb_typeof(body->'platform') IS DISTINCT FROM 'string'
 OR jsonb_typeof(body->'channel_meeting') NOT IN('boolean','null') OR jsonb_typeof(body->'chat_available') NOT IN('boolean','null')
 OR jsonb_typeof(body->'audience_complete') IS DISTINCT FROM 'boolean' OR jsonb_typeof(body->'participants') IS DISTINCT FROM 'array'
 OR jsonb_array_length(body->'participants')>1000
 OR jsonb_typeof(body->'observed_at') IS DISTINCT FROM 'string' OR jsonb_typeof(body->'valid_until') IS DISTINCT FROM 'string' THEN
  RAISE EXCEPTION 'closed current provider observation required';END IF;
 FOR entry IN SELECT value FROM jsonb_array_elements(body->'participants') LOOP
  IF jsonb_typeof(entry) IS DISTINCT FROM 'object' OR NOT(entry ?& ARRAY['provider_participant_id','actor_id'])
  OR entry-ARRAY['provider_participant_id','actor_id']<>'{}'::jsonb OR jsonb_typeof(entry->'provider_participant_id') IS DISTINCT FROM 'string'
  OR length(btrim(entry->>'provider_participant_id')) NOT BETWEEN 1 AND 256 OR entry->>'provider_participant_id'<>btrim(entry->>'provider_participant_id')
  OR entry->>'provider_participant_id'~'[[:cntrl:]]' OR entry->>'provider_participant_id'=ANY(ids)
  OR jsonb_typeof(entry->'actor_id') NOT IN('string','null')
  OR (jsonb_typeof(entry->'actor_id')='string' AND entry->>'actor_id'!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$') THEN
   RAISE EXCEPTION 'attributed canonical audience required';END IF;
  ids:=array_append(ids,entry->>'provider_participant_id');
 END LOOP;
 IF ids IS DISTINCT FROM ARRAY(SELECT unnest(ids) ORDER BY 1) OR (body->'audience_complete'='true'::jsonb AND cardinality(ids)=0) THEN
  RAISE EXCEPTION 'closed ordered audience required';END IF;
 at:=(body->>'observed_at')::timestamptz;until:=(body->>'valid_until')::timestamptz;
 IF NOT isfinite(at) OR NOT isfinite(until) OR at>clock_timestamp() OR until<=clock_timestamp() OR until>at+interval '30 seconds'
 OR until>m.expires_at THEN RAISE insufficient_privilege USING MESSAGE='finite observation window denied';END IF;
 c:=oracle2._meeting_participation_capture_v1(m,deadline);
 IF body->>'capture_event_id' IS DISTINCT FROM c->>'capture_event_id' OR body->>'capture_sha256' IS DISTINCT FROM c->>'capture_event_sha256'
 OR body->>'capture_revision' IS DISTINCT FROM c->>'capture_revision' OR until>(c->>'valid_until')::timestamptz THEN
  RAISE insufficient_privilege USING MESSAGE='exact current capture observation differs';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-participation:'||m.workspace_id::text||':'||m.meeting_id::text));
 hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(body),'UTF8')),'hex');
 SELECT * INTO old FROM oracle2.meeting_participation_observations_v1 WHERE observation_id=observation;
 IF old.observation_id IS NOT NULL THEN
  IF old.admission_id<>selected OR old.actor_id<>m.principal_id OR old.payload_sha256<>hash THEN RAISE EXCEPTION 'observation collision';END IF;
  RETURN jsonb_build_object('observation_id',observation,'created',false,'valid_until',least(until,m.expires_at),'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),least(until,m.expires_at)));
 END IF;
 SELECT * INTO head FROM oracle2.meeting_participation_audience_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 IF coalesce(head.revision,0)<>expected_revision OR expected_revision>=16384 THEN RAISE EXCEPTION 'current audience revision conflict';END IF;
 INSERT INTO oracle2.meeting_participation_observations_v1 VALUES(observation,m.workspace_id,m.meeting_id,selected,m.principal_id,body,hash,at,until);
 INSERT INTO oracle2.meeting_participation_audience_heads_v1 VALUES(m.workspace_id,m.meeting_id,expected_revision+1,observation)
 ON CONFLICT(workspace_id,meeting_id) DO UPDATE SET revision=EXCLUDED.revision,observation_id=EXCLUDED.observation_id;
 RETURN jsonb_build_object('observation_id',observation,'created',true,'valid_until',until,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),until));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_participation_observe_audience_v1(uuid,text,integer,uuid,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_participation_observe_audience_v1(uuid,text,integer,uuid,jsonb,timestamptz) TO oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_participation_control_v1(selected uuid,seal text,expected_head integer,operation uuid,act text,body jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_participation_admissions_v1%ROWTYPE;h oracle2.meeting_participation_heads_v1%ROWTYPE;
 old oracle2.meeting_participation_events_v1%ROWTYPE;c jsonb;o oracle2.meeting_participation_observations_v1%ROWTYPE;hash text;event uuid;
BEGIN
 m:=oracle2._meeting_participation_admission_v1(selected,seal,act,deadline);
 IF m.kind<>'host' OR act NOT IN('enable','disable') OR operation IS NULL OR expected_head IS NULL OR expected_head<0
 OR jsonb_typeof(body) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'closed actual host action required';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-participation:'||m.workspace_id::text||':'||m.meeting_id::text));
 IF act='enable' THEN
  IF NOT(body ?& ARRAY['proactive_enabled','cooldown_seconds','max_proactive','observation_id'])
  OR body-ARRAY['proactive_enabled','cooldown_seconds','max_proactive','observation_id']<>'{}'::jsonb
  OR jsonb_typeof(body->'proactive_enabled') IS DISTINCT FROM 'boolean'
  OR jsonb_typeof(body->'cooldown_seconds') IS DISTINCT FROM 'number' OR body->>'cooldown_seconds'!~'^[1-9][0-9]{0,4}$'
  OR (body->>'cooldown_seconds')::integer NOT BETWEEN 120 AND 86400
  OR jsonb_typeof(body->'max_proactive') IS DISTINCT FROM 'number' OR body->>'max_proactive'!~'^[0-3]$'
  OR jsonb_typeof(body->'observation_id') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'bounded explicit host settings required';END IF;
  c:=oracle2._meeting_participation_capture_v1(m,deadline);
  o:=oracle2._meeting_participation_observation_v1(m,(body->>'observation_id')::uuid,c,deadline);
  m.expires_at:=least(m.expires_at,o.valid_until);
 ELSIF body<>'{}'::jsonb THEN RAISE EXCEPTION 'disable accepts no selectors';END IF;
 hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('action',act,'body',body)),'UTF8')),'hex');
 SELECT * INTO old FROM oracle2.meeting_participation_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND operation_id=operation;
 IF old.event_id IS NOT NULL THEN
  IF old.admission_id<>selected OR old.actor_id<>m.principal_id OR old.action<>act OR old.payload_sha256<>hash THEN RAISE EXCEPTION 'participation operation collision';END IF;
  RETURN jsonb_build_object('event_id',old.event_id,'created',false,'meeting_id',m.meeting_id,'valid_until',m.expires_at,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
 END IF;
 INSERT INTO oracle2.meeting_participation_heads_v1(workspace_id,meeting_id) VALUES(m.workspace_id,m.meeting_id) ON CONFLICT DO NOTHING;
 SELECT * INTO h FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 IF h.version<>expected_head OR h.version>=16384 THEN RAISE EXCEPTION 'participation head conflict';END IF;
 event:=gen_random_uuid();
 INSERT INTO oracle2.meeting_participation_events_v1 VALUES(event,m.workspace_id,m.meeting_id,h.version+1,h.generation+1,selected,m.principal_id,act,body,hash,operation,clock_timestamp());
 UPDATE oracle2.meeting_participation_heads_v1 SET version=h.version+1,generation=h.generation+1,enabled=(act='enable'),
 proactive_enabled=CASE WHEN act='enable' THEN (body->>'proactive_enabled')::boolean ELSE false END,
 cooldown_seconds=CASE WHEN act='enable' THEN (body->>'cooldown_seconds')::integer ELSE h.cooldown_seconds END,
 max_proactive=CASE WHEN act='enable' THEN (body->>'max_proactive')::integer ELSE h.max_proactive END,last_event_id=event
 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id;
 -- Off changes participation only; it never edits capture or claims remote stop.
 RETURN jsonb_build_object('event_id',event,'created',true,'meeting_id',m.meeting_id,'valid_until',m.expires_at,'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_participation_control_v1(uuid,text,integer,uuid,text,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_participation_control_v1(uuid,text,integer,uuid,text,jsonb,timestamptz) TO oracle2_replacement_requester;
CREATE FUNCTION oracle2._meeting_participation_current_v1(m oracle2.meeting_participation_admissions_v1,wanted uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE i oracle2.meeting_participation_intents_v1%ROWTYPE;h oracle2.meeting_participation_heads_v1%ROWTYPE;
 c jsonb;t jsonb;o oracle2.meeting_participation_observations_v1%ROWTYPE;host_until timestamptz;
BEGIN
 SELECT * INTO i FROM oracle2.meeting_participation_intents_v1 WHERE intent_id=wanted FOR SHARE;
 SELECT * INTO h FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 IF i.intent_id IS NULL OR i.workspace_id<>m.workspace_id OR i.meeting_id<>m.meeting_id OR i.sender_admission_id<>m.admission_id
 OR i.actor_id<>m.principal_id OR h.meeting_id IS NULL OR NOT h.enabled OR h.generation<>i.generation THEN
  RAISE insufficient_privilege USING MESSAGE='current enabled exact participation intent denied';END IF;
 host_until:=oracle2._meeting_participation_host_v1(m,h.generation,deadline);
 c:=oracle2._meeting_participation_capture_v1(m,deadline);
 IF c->>'capture_event_id' IS DISTINCT FROM i.capture_event_id::text OR c->>'capture_event_sha256' IS DISTINCT FROM i.capture_sha256
 OR c->>'capture_revision' IS DISTINCT FROM i.capture_revision::text THEN
  RAISE insufficient_privilege USING MESSAGE='current capture turn changed';END IF;
 o:=oracle2._meeting_participation_observation_v1(m,i.observation_id,c,deadline);
 t:=oracle2._meeting_participation_turn_v1(m,i.turn_event_id,i.turn_frame,deadline);
 RETURN jsonb_build_object('generation',h.generation,'head_revision',h.version,'valid_until',least(m.expires_at,host_until,o.valid_until,(t->>'valid_until')::timestamptz),
  'capture',c,'observation_id',o.observation_id,'audience_sha256',o.payload_sha256);
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_current_v1(oracle2.meeting_participation_admissions_v1,uuid,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2._meeting_participation_prepare_binding_v1(m oracle2.meeting_participation_admissions_v1,h oracle2.meeting_participation_heads_v1,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE c jsonb;t jsonb;prior oracle2.meeting_participation_intents_v1%ROWTYPE;
 o oracle2.meeting_participation_observations_v1%ROWTYPE;audience uuid;until timestamptz;
BEGIN
 IF m.kind<>'sender' OR NOT('prepare'=ANY(m.actions)) OR h.workspace_id IS DISTINCT FROM m.workspace_id
 OR h.meeting_id IS DISTINCT FROM m.meeting_id OR NOT h.enabled OR h.version>=16384 THEN
  RAISE insufficient_privilege USING MESSAGE='current independently installed composer denied';END IF;
 until:=oracle2._meeting_participation_host_v1(m,h.generation,deadline);
 c:=oracle2._meeting_participation_capture_v1(m,deadline);
 SELECT observation_id INTO audience FROM oracle2.meeting_participation_audience_heads_v1
 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 o:=oracle2._meeting_participation_observation_v1(m,audience,c,deadline);
 -- SAME S07 current epoch/event/actor metadata owner before any private bytes.
 t:=oracle2.meeting_capture_current_turn_v1(m.capture_admission_id,m.capture_admission_sha256,(c->>'capture_event_id')::uuid,deadline);
 SELECT * INTO prior FROM oracle2.meeting_participation_intents_v1 WHERE workspace_id=m.workspace_id
 AND meeting_id=m.meeting_id AND turn_event_id=(c->>'capture_event_id')::uuid FOR SHARE;
 IF prior.intent_id IS NOT NULL AND(prior.sender_admission_id<>m.admission_id OR prior.actor_id<>m.principal_id) THEN
  RAISE insufficient_privilege USING MESSAGE='old turn receipt cannot borrow another appointment';END IF;
 RETURN jsonb_build_object('capture_event_id',c->'capture_event_id','head_revision',h.version,'generation',h.generation,
  'existing_intent_id',prior.intent_id,'valid_until',least(until,m.expires_at,o.valid_until,(t->>'valid_until')::timestamptz));
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_prepare_binding_v1(oracle2.meeting_participation_admissions_v1,oracle2.meeting_participation_heads_v1,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_participation_claim_v1(selected uuid,seal text,wanted uuid,expected_revision integer,operation uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_participation_admissions_v1%ROWTYPE;i oracle2.meeting_participation_intents_v1%ROWTYPE;
 d oracle2.meeting_participation_delivery_heads_v1%ROWTYPE;h oracle2.meeting_participation_heads_v1%ROWTYPE;
 current jsonb;event uuid;payload jsonb;hash text;until timestamptz;
BEGIN
 m:=oracle2._meeting_participation_admission_v1(selected,seal,'claim',deadline);
 IF m.kind<>'sender' OR wanted IS NULL OR operation IS NULL OR expected_revision IS NULL OR expected_revision<0 THEN
  RAISE EXCEPTION 'closed exact sender claim required';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-participation:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO i FROM oracle2.meeting_participation_intents_v1 WHERE intent_id=wanted FOR SHARE;
 IF i.intent_id IS NULL OR i.workspace_id<>m.workspace_id OR i.meeting_id<>m.meeting_id OR i.sender_admission_id<>selected OR i.actor_id<>m.principal_id THEN
  RAISE insufficient_privilege USING MESSAGE='own exact participation intent required';END IF;
 SELECT * INTO d FROM oracle2.meeting_participation_delivery_heads_v1 WHERE intent_id=wanted FOR UPDATE;
 IF d.intent_id IS NULL THEN RAISE EXCEPTION 'durable intent missing';END IF;
 IF d.state<>'intent' THEN
  -- A replay NEVER returns provider bytes, even if the original claim ACK was lost.
  RETURN jsonb_build_object('intent_id',wanted,'state',d.state,
   'outcome',CASE WHEN d.state='inflight' THEN 'UNKNOWN' ELSE d.state END,'created',false,'executable',false,'claim_event_id',d.claim_event_id,'revision',d.revision,'valid_until',m.expires_at,
   'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
 END IF;
 IF d.revision<>expected_revision THEN RAISE EXCEPTION 'delivery revision conflict';END IF;
 SELECT * INTO h FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 current:=oracle2._meeting_participation_current_v1(m,wanted,deadline);until:=(current->>'valid_until')::timestamptz;
 IF h.active_intent_id IS NOT NULL OR (i.proactive AND(NOT h.proactive_enabled OR h.proactive_count>=h.max_proactive
  OR(h.last_proactive_at IS NOT NULL AND clock_timestamp()<h.last_proactive_at+make_interval(secs=>h.cooldown_seconds)))) THEN
  RAISE insufficient_privilege USING MESSAGE='bounded participation attempt denied';END IF;
 event:=gen_random_uuid();payload:=jsonb_build_object('intent_id',wanted,'request_sha256',i.request_sha256,'generation',i.generation);
 hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(payload),'UTF8')),'hex');
 INSERT INTO oracle2.meeting_participation_delivery_events_v1 VALUES(event,wanted,d.revision+1,selected,m.principal_id,'claim',operation,payload,hash,clock_timestamp());
 UPDATE oracle2.meeting_participation_delivery_heads_v1 SET revision=d.revision+1,state='inflight',claim_event_id=event,claim_operation_id=operation,claim_deadline=until,last_event_id=event WHERE intent_id=wanted;
 UPDATE oracle2.meeting_participation_heads_v1 SET active_intent_id=wanted,
 proactive_count=h.proactive_count+CASE WHEN i.proactive THEN 1 ELSE 0 END,
 last_proactive_at=CASE WHEN i.proactive THEN clock_timestamp() ELSE h.last_proactive_at END
 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id;
 RETURN jsonb_build_object('intent_id',wanted,'state','inflight','created',true,'executable',true,'claim_event_id',event,'revision',d.revision+1,
  'body',oracle2._replacement_metadata_json(jsonb_build_object('to','everyone','message',i.body)),
  'request_sha256',i.request_sha256,'bot_id',m.bot_id,'valid_until',until,
  'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),until));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_participation_claim_v1(uuid,text,uuid,integer,uuid,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_participation_claim_v1(uuid,text,uuid,integer,uuid,timestamptz) TO oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_participation_observe_v1(selected uuid,seal text,wanted uuid,claim uuid,operation uuid,body jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_participation_admissions_v1%ROWTYPE;i oracle2.meeting_participation_intents_v1%ROWTYPE;
 d oracle2.meeting_participation_delivery_heads_v1%ROWTYPE;old oracle2.meeting_participation_delivery_events_v1%ROWTYPE;
 hash text;target text;event uuid;still_current boolean:=false;required text[];
BEGIN
 -- Forensic completion can record one already-inflight own attempt after host
 -- disable. It grants no body/claim/send and still requires its OWN current root.
 m:=oracle2._meeting_participation_admission_v1(selected,seal,'receipt',deadline);
 required:=ARRAY['request_sha256','complete','http_status','response_sha256','response_byte_count','response_object_key','error'];
 IF m.kind<>'sender' OR wanted IS NULL OR claim IS NULL OR operation IS NULL OR jsonb_typeof(body) IS DISTINCT FROM 'object'
 OR NOT(body ?& required) OR body-required<>'{}'::jsonb OR octet_length(body::text)>2048
 OR jsonb_typeof(body->'request_sha256') IS DISTINCT FROM 'string' OR body->>'request_sha256'!~'^[a-f0-9]{64}$'
 OR jsonb_typeof(body->'complete') IS DISTINCT FROM 'boolean'
 OR jsonb_typeof(body->'http_status') NOT IN('number','null')
 OR(jsonb_typeof(body->'http_status')='number' AND body->>'http_status'!~'^[1-5][0-9]{2}$')
 OR jsonb_typeof(body->'response_sha256') IS DISTINCT FROM 'string'
 OR body->>'response_sha256'!~'^[a-f0-9]{64}$'
 OR jsonb_typeof(body->'response_byte_count') IS DISTINCT FROM 'number' OR body->>'response_byte_count'!~'^(0|[1-9][0-9]{0,6})$'
 OR(body->>'response_byte_count')::integer>1064960
 OR body->>'response_object_key' IS DISTINCT FROM 'meeting-participation/'||m.workspace_id::text||'/'||m.meeting_id::text||'/'||wanted::text||'/'||claim::text||'/provider-response.wire'
 OR jsonb_typeof(body->'error') NOT IN('string','null')
 OR(jsonb_typeof(body->'error')='string' AND body->>'error' NOT IN('network','timeout','framing','expired','unknown'))
 OR(body->'complete'='true'::jsonb AND(body->'http_status'='null'::jsonb OR body->'response_sha256'='null'::jsonb OR body->'error'<>'null'::jsonb)) THEN
  RAISE EXCEPTION 'exact bounded observed wire outcome required';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-participation:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO i FROM oracle2.meeting_participation_intents_v1 WHERE intent_id=wanted FOR SHARE;
 IF i.intent_id IS NULL OR i.workspace_id<>m.workspace_id OR i.meeting_id<>m.meeting_id OR i.sender_admission_id<>selected
 OR i.actor_id<>m.principal_id OR body->>'request_sha256'<>i.request_sha256 THEN
  RAISE insufficient_privilege USING MESSAGE='exact own inflight receipt denied';END IF;
 SELECT * INTO d FROM oracle2.meeting_participation_delivery_heads_v1 WHERE intent_id=wanted FOR UPDATE;
 IF d.intent_id IS NULL OR d.claim_event_id IS DISTINCT FROM claim THEN RAISE EXCEPTION 'actual own claim required';END IF;
 hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(body),'UTF8')),'hex');
 SELECT * INTO old FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=wanted AND operation_id=operation;
 IF old.event_id IS NOT NULL THEN
  IF old.admission_id<>selected OR old.actor_id<>m.principal_id OR old.payload_sha256<>hash OR old.action='claim' THEN RAISE EXCEPTION 'receipt operation collision';END IF;
  RETURN jsonb_build_object('intent_id',wanted,'event_id',old.event_id,'state',d.state,'revision',d.revision,'created',false,'executable',false,
   'visible_message_proven',false,'remote_stop_proven',false,'current',false,'valid_until',m.expires_at,
   'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
 END IF;
 IF d.state<>'inflight' THEN RAISE EXCEPTION 'terminal receipt cannot be replaced';END IF;
 target:=CASE WHEN body->'complete'='true'::jsonb AND body->'http_status'='200'::jsonb AND body->'error'='null'::jsonb THEN 'provider-response-observed' ELSE 'UNKNOWN' END;
 event:=gen_random_uuid();
 INSERT INTO oracle2.meeting_participation_delivery_events_v1 VALUES(event,wanted,d.revision+1,selected,m.principal_id,target,operation,body,hash,clock_timestamp());
 UPDATE oracle2.meeting_participation_delivery_heads_v1 SET revision=d.revision+1,state=target,last_event_id=event WHERE intent_id=wanted;
 UPDATE oracle2.meeting_participation_heads_v1 SET active_intent_id=NULL WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND active_intent_id=wanted;
 BEGIN
  PERFORM oracle2._meeting_participation_current_v1(m,wanted,deadline);still_current:=true;
 EXCEPTION WHEN insufficient_privilege THEN still_current:=false;
 END;
 RETURN jsonb_build_object('intent_id',wanted,'event_id',event,'state',target,'revision',d.revision+1,'created',true,'executable',false,
  'visible_message_proven',false,'remote_stop_proven',false,'current',still_current,'valid_until',m.expires_at,
  'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),m.expires_at));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_participation_observe_v1(uuid,text,uuid,uuid,uuid,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_participation_observe_v1(uuid,text,uuid,uuid,uuid,jsonb,timestamptz) TO oracle2_replacement_requester;
CREATE FUNCTION oracle2.meeting_participation_status_v1(selected uuid,seal text,wanted uuid,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_participation_admissions_v1%ROWTYPE;h oracle2.meeting_participation_heads_v1%ROWTYPE;
 i oracle2.meeting_participation_intents_v1%ROWTYPE;d oracle2.meeting_participation_delivery_heads_v1%ROWTYPE;current jsonb;live boolean:=false;
 audience oracle2.meeting_participation_audience_heads_v1%ROWTYPE;observation oracle2.meeting_participation_observations_v1%ROWTYPE;prepare_binding jsonb;reconcile_intent uuid;
BEGIN
 m:=oracle2._meeting_participation_admission_v1(selected,seal,'status',deadline);
 -- Same lock order as writes: admission, meeting, then mutable heads/receipt.
 -- This cannot claim or mutate a body; it prevents status/claim row inversion.
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-participation:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO audience FROM oracle2.meeting_participation_audience_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 SELECT * INTO observation FROM oracle2.meeting_participation_observations_v1 WHERE observation_id=audience.observation_id FOR SHARE;
 SELECT * INTO h FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR SHARE;
 IF m.kind='sender' THEN
  SELECT selected_intent.intent_id INTO reconcile_intent
  FROM oracle2.meeting_participation_intents_v1 selected_intent JOIN oracle2.meeting_participation_events_v1 prepared
   ON prepared.workspace_id=selected_intent.workspace_id AND prepared.meeting_id=selected_intent.meeting_id
   AND prepared.action='prepare' AND prepared.payload->'answer'->>'intent_id'=selected_intent.intent_id::text
  WHERE selected_intent.workspace_id=m.workspace_id AND selected_intent.meeting_id=m.meeting_id
   AND selected_intent.sender_admission_id=m.admission_id AND selected_intent.actor_id=m.principal_id
  ORDER BY (selected_intent.intent_id=h.active_intent_id) DESC NULLS LAST,prepared.version DESC LIMIT 1;
 END IF;
 IF wanted IS NULL AND m.kind='sender' AND 'prepare'=ANY(m.actions) THEN
  BEGIN
   prepare_binding:=oracle2._meeting_participation_prepare_binding_v1(m,h,deadline);
  EXCEPTION WHEN insufficient_privilege THEN prepare_binding:=NULL;
  END;
 END IF;
 IF wanted IS NOT NULL THEN
  SELECT * INTO i FROM oracle2.meeting_participation_intents_v1 WHERE intent_id=wanted FOR SHARE;
  IF m.kind<>'sender' OR i.intent_id IS NULL OR i.workspace_id<>m.workspace_id OR i.meeting_id<>m.meeting_id OR i.sender_admission_id<>selected OR i.actor_id<>m.principal_id THEN
   RAISE insufficient_privilege USING MESSAGE='own receipt metadata denied';END IF;
  SELECT * INTO d FROM oracle2.meeting_participation_delivery_heads_v1 WHERE intent_id=wanted FOR SHARE;
  BEGIN
   current:=oracle2._meeting_participation_current_v1(m,wanted,deadline);live:=true;
  EXCEPTION WHEN insufficient_privilege THEN live:=false;
  END;
  -- A later readonly call cannot renew the original once-claim send window.
  -- Forensic receipts remain possible under their own finite current scope.
  IF d.state='inflight' AND(d.claim_deadline IS NULL OR d.claim_deadline<=clock_timestamp()) THEN live:=false;END IF;
 END IF;
 RETURN jsonb_build_object('meeting_id',m.meeting_id,'head_revision',coalesce(h.version,0),'generation',coalesce(h.generation,0),
  'host_enabled',coalesce(h.enabled,false),'proactive_enabled',coalesce(h.proactive_enabled,false),'proactive_count',coalesce(h.proactive_count,0),
  'intent_id',wanted,'state',d.state,'outcome',CASE WHEN d.state='inflight' THEN 'UNKNOWN' WHEN d.state='intent' THEN 'not-dispatched' ELSE d.state END,'delivery_revision',d.revision,
  'claim_event_id',d.claim_event_id,'claim_current',live AND d.state='inflight','request_sha256',i.request_sha256,
  'intent_current',live,
  -- Private same-role reconciliation only. Hosting reopens these SAME bytes
  -- through S07; public/browser metadata strips this frame, never body replay.
  'turn_binding',CASE WHEN wanted IS NULL THEN NULL ELSE i.turn_frame END,
  'intent_proactive',i.proactive,
  'receipt_permitted',m.kind='sender' AND 'receipt'=ANY(m.actions),
  -- Private immutable same-admission forensic identity, never a send grant.
  'receipt_bot_id',CASE WHEN wanted IS NOT NULL AND d.claim_event_id IS NOT NULL AND m.kind='sender' AND 'receipt'=ANY(m.actions) THEN m.bot_id ELSE NULL END,
  'prepare_binding',prepare_binding,
  'reconcile_intent_id',reconcile_intent,
  'visible_message_proven',false,'remote_stop_proven',false,'executable',false,
  'observation_id',audience.observation_id,'observation_revision',coalesce(audience.revision,0),'observation_sha256',observation.payload_sha256,'observation_valid_until',observation.valid_until,
  'valid_until',CASE WHEN live AND d.state='inflight' THEN least(m.expires_at,d.claim_deadline,(current->>'valid_until')::timestamptz) ELSE m.expires_at END,
  'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),
   CASE WHEN live AND d.state='inflight' THEN least(m.expires_at,d.claim_deadline,(current->>'valid_until')::timestamptz) ELSE m.expires_at END));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_participation_status_v1(uuid,text,uuid,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_participation_status_v1(uuid,text,uuid,timestamptz) TO oracle2_replacement_requester;
CREATE FUNCTION oracle2._meeting_participation_turn_v1(m oracle2.meeting_participation_admissions_v1,wanted uuid,frame jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE t jsonb;c jsonb;e jsonb;link jsonb;keys text[];name text;
BEGIN
 keys:=ARRAY['capture_event_id','capture_event_sha256','capture_revision','raw_sha256','normalized_sha256','participant_epoch_id','participant_epoch_revision','participant_epoch_sha256','participant_set_sha256','provider_speaker_id','actor_id'];
 IF wanted IS NULL OR jsonb_typeof(frame) IS DISTINCT FROM 'object' OR NOT(frame ?& keys) OR frame-keys<>'{}'::jsonb THEN
  RAISE EXCEPTION 'closed current turn provenance required';END IF;
 FOREACH name IN ARRAY ARRAY['capture_event_id','participant_epoch_id','actor_id'] LOOP
  IF jsonb_typeof(frame->name) IS DISTINCT FROM 'string' OR frame->>name!~'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' THEN RAISE EXCEPTION 'canonical current turn identity required';END IF;
 END LOOP;
 FOREACH name IN ARRAY ARRAY['capture_event_sha256','raw_sha256','normalized_sha256','participant_epoch_sha256','participant_set_sha256'] LOOP
  IF jsonb_typeof(frame->name) IS DISTINCT FROM 'string' OR frame->>name!~'^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'separate exact turn hashes required';END IF;
 END LOOP;
 FOREACH name IN ARRAY ARRAY['capture_revision','participant_epoch_revision'] LOOP
  IF jsonb_typeof(frame->name) IS DISTINCT FROM 'number' OR frame->>name!~'^[1-9][0-9]{0,8}$' THEN RAISE EXCEPTION 'strict turn revision required';END IF;
 END LOOP;
 IF jsonb_typeof(frame->'provider_speaker_id') IS DISTINCT FROM 'string' OR length(btrim(frame->>'provider_speaker_id')) NOT BETWEEN 1 AND 256
 OR frame->>'provider_speaker_id'<>btrim(frame->>'provider_speaker_id') OR frame->>'provider_speaker_id'~'[[:cntrl:]]' THEN RAISE EXCEPTION 'stable attributed speaker required';END IF;
 -- SAME canonical S07 owner: no direct raw-table/file access or role borrowing.
 t:=oracle2.meeting_capture_current_turn_v1(m.capture_admission_id,m.capture_admission_sha256,wanted,deadline);
 c:=t->'capture';e:=t->'epoch';
 IF c->>'workspace_id' IS DISTINCT FROM m.workspace_id::text OR c->>'meeting_id' IS DISTINCT FROM m.meeting_id::text
 OR c->>'provider' IS DISTINCT FROM m.provider OR c->>'provider_account' IS DISTINCT FROM m.provider_account
 OR c->>'tenant_id' IS DISTINCT FROM m.tenant_id OR c->>'provider_meeting_id' IS DISTINCT FROM m.provider_meeting_id
 OR c->>'bot_id' IS DISTINCT FROM m.bot_id::text OR c->>'capture_event_id' IS DISTINCT FROM wanted::text
 OR frame->>'capture_event_id' IS DISTINCT FROM wanted::text OR frame->>'capture_event_sha256' IS DISTINCT FROM c->>'capture_event_sha256'
 OR frame->>'capture_revision' IS DISTINCT FROM c->>'capture_revision'
 OR frame->>'raw_sha256' IS DISTINCT FROM t->'receipt'->'payload'->>'raw_sha256'
 OR frame->>'participant_epoch_id' IS DISTINCT FROM e->>'epoch_id' OR frame->>'participant_epoch_revision' IS DISTINCT FROM e->>'epoch_revision'
 OR frame->>'participant_epoch_sha256' IS DISTINCT FROM t->>'epoch_sha256' OR frame->>'participant_set_sha256' IS DISTINCT FROM e->>'participant_set_sha256' THEN
  RAISE insufficient_privilege USING MESSAGE='actual current turn event epoch or raw provenance differs';END IF;
 SELECT value INTO link FROM jsonb_array_elements(e->'links') WHERE value->>'provider_participant_id'=frame->>'provider_speaker_id';
 IF link IS NULL OR link->>'attribution' IS DISTINCT FROM 'workspace_actor' OR link->>'actor_id' IS DISTINCT FROM frame->>'actor_id' THEN
  RAISE insufficient_privilege USING MESSAGE='current mapped workspace participant required';END IF;
 -- normalized_sha256 is verified by the actual protected S07 normalizer and
 -- installed deterministic composer. SQL binds it immutably; it does NOT
 -- independently parse private raw bytes or fabricate qualification/employee ID.
 RETURN t;
END $f$;
REVOKE ALL ON FUNCTION oracle2._meeting_participation_turn_v1(oracle2.meeting_participation_admissions_v1,uuid,jsonb,timestamptz) FROM PUBLIC,oracle2_replacement_requester;

CREATE FUNCTION oracle2.meeting_participation_prepare_v1(selected uuid,seal text,expected_head integer,operation uuid,turn jsonb,answer jsonb,deadline timestamptz)
 RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,oracle2 AS $f$
DECLARE m oracle2.meeting_participation_admissions_v1%ROWTYPE;h oracle2.meeting_participation_heads_v1%ROWTYPE;
 old oracle2.meeting_participation_events_v1%ROWTYPE;o oracle2.meeting_participation_observations_v1%ROWTYPE;
 t jsonb;c jsonb;payload jsonb;hash text;event uuid;wanted uuid;message text;proactive boolean;until timestamptz;entry jsonb;host_until timestamptz;
BEGIN
 m:=oracle2._meeting_participation_admission_v1(selected,seal,'prepare',deadline);
 IF m.kind<>'sender' OR operation IS NULL OR expected_head IS NULL OR expected_head<0
 OR jsonb_typeof(answer) IS DISTINCT FROM 'object' OR NOT(answer ?& ARRAY['intent_id','proactive','observation_id','composer_sha256','turn_text'])
 OR answer-ARRAY['intent_id','proactive','observation_id','composer_sha256','turn_text']<>'{}'::jsonb
 OR jsonb_typeof(answer->'intent_id') IS DISTINCT FROM 'string' OR jsonb_typeof(answer->'observation_id') IS DISTINCT FROM 'string'
 OR jsonb_typeof(answer->'proactive') IS DISTINCT FROM 'boolean' OR jsonb_typeof(answer->'turn_text') IS DISTINCT FROM 'string'
 OR answer->>'composer_sha256' IS DISTINCT FROM m.composer_sha256
 OR char_length(answer->>'turn_text') NOT BETWEEN 1 AND 4096 OR length(btrim(answer->>'turn_text'))=0
 OR encode(sha256(convert_to(answer->>'turn_text','UTF8')),'hex') IS DISTINCT FROM turn->>'normalized_sha256' THEN
  RAISE EXCEPTION 'exact installed deterministic current-turn composer required';END IF;
 wanted:=(answer->>'intent_id')::uuid;proactive:=(answer->>'proactive')::boolean;
 IF NOT proactive AND (lower(answer->>'turn_text') COLLATE "C")!~'^@?oracle([[:space:][:punct:]]|$)' THEN
  RAISE insufficient_privilege USING MESSAGE='explicit leading Oracle address required';END IF;
 -- Exact fixed composer's presentation fence, not another raw normalizer:
 -- authenticated original text/hash stays separate from HTML-escaped body.
 message:=CASE WHEN proactive THEN 'Could you clarify: ' ELSE 'You asked: ' END||replace(replace(replace(answer->>'turn_text','&','&amp;'),'<','&lt;'),'>','&gt;');
 IF char_length(message)>4096 THEN RAISE EXCEPTION 'complete reply exceeds provider bound; no truncation';END IF;
 PERFORM pg_advisory_xact_lock(hashtext('oracle2-participation:'||m.workspace_id::text||':'||m.meeting_id::text));
 SELECT * INTO h FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id FOR UPDATE;
 IF h.meeting_id IS NULL OR NOT h.enabled OR h.version<>expected_head OR h.version>=16384
 OR(proactive AND(NOT h.proactive_enabled OR h.proactive_count>=h.max_proactive)) THEN
  RAISE insufficient_privilege USING MESSAGE='current exact enabled host generation denied';END IF;
 host_until:=oracle2._meeting_participation_host_v1(m,h.generation,deadline);
 t:=oracle2._meeting_participation_turn_v1(m,(turn->>'capture_event_id')::uuid,turn,deadline);c:=t->'capture';
 o:=oracle2._meeting_participation_observation_v1(m,(answer->>'observation_id')::uuid,c,deadline);
 IF o.payload->'audience_complete'='true'::jsonb THEN
  IF (SELECT coalesce(jsonb_agg(value->'provider_participant_id' ORDER BY value->>'provider_participant_id'),'[]'::jsonb) FROM jsonb_array_elements(o.payload->'participants')) IS DISTINCT FROM t->'epoch'->'provider_participant_ids' THEN
   RAISE insufficient_privilege USING MESSAGE='current complete recipient population differs';END IF;
  FOR entry IN SELECT value FROM jsonb_array_elements(o.payload->'participants') LOOP
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(t->'epoch'->'links') link WHERE link->>'provider_participant_id'=entry->>'provider_participant_id'
    AND link->'actor_id'=entry->'actor_id') THEN RAISE insufficient_privilege USING MESSAGE='independent current audience attribution differs';END IF;
  END LOOP;
 END IF;
 -- Unknown audience is restricted to this exact SAME-current-turn reply only.
 -- No SourceRef/shared-access/policy facts are accepted by this capability.
 until:=least(m.expires_at,host_until,o.valid_until,(t->>'valid_until')::timestamptz);
 payload:=jsonb_build_object('turn',turn,'answer',answer);hash:=encode(sha256(convert_to(oracle2._replacement_metadata_json(payload),'UTF8')),'hex');
 SELECT * INTO old FROM oracle2.meeting_participation_events_v1 WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id AND operation_id=operation;
 IF old.event_id IS NOT NULL THEN
  IF old.admission_id<>selected OR old.actor_id<>m.principal_id OR old.action<>'prepare' OR old.payload_sha256<>hash THEN RAISE EXCEPTION 'immutable reply operation collision';END IF;
  RETURN jsonb_build_object('intent_id',wanted,'created',false,'executable',false,'valid_until',until,
   'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),until));
 END IF;
 event:=gen_random_uuid();
 INSERT INTO oracle2.meeting_participation_intents_v1(intent_id,workspace_id,meeting_id,generation,sender_admission_id,actor_id,turn_event_id,raw_sha256,turn_frame,capture_event_id,capture_sha256,capture_revision,body,body_sha256,proactive,evidence_scope,observation_id,request_sha256)
 VALUES(wanted,m.workspace_id,m.meeting_id,h.generation,selected,m.principal_id,(turn->>'capture_event_id')::uuid,turn->>'raw_sha256',turn,(c->>'capture_event_id')::uuid,
 c->>'capture_event_sha256',(c->>'capture_revision')::integer,message,encode(sha256(convert_to(message,'UTF8')),'hex'),proactive,'meeting_only',o.observation_id,
 encode(sha256(convert_to(oracle2._replacement_metadata_json(jsonb_build_object('to','everyone','message',message)),'UTF8')),'hex'));
 INSERT INTO oracle2.meeting_participation_delivery_heads_v1(intent_id,state) VALUES(wanted,'intent');
 INSERT INTO oracle2.meeting_participation_events_v1 VALUES(event,m.workspace_id,m.meeting_id,h.version+1,h.generation,selected,m.principal_id,'prepare',payload,hash,operation,clock_timestamp());
 UPDATE oracle2.meeting_participation_heads_v1 SET version=h.version+1,last_event_id=event WHERE workspace_id=m.workspace_id AND meeting_id=m.meeting_id;
 RETURN jsonb_build_object('intent_id',wanted,'created',true,'executable',false,'valid_until',until,
  'context',oracle2._replacement_private_context(oracle2._replacement_request_context(),until));
END $f$;
REVOKE ALL ON FUNCTION oracle2.meeting_participation_prepare_v1(uuid,text,integer,uuid,jsonb,jsonb,timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION oracle2.meeting_participation_prepare_v1(uuid,text,integer,uuid,jsonb,jsonb,timestamptz) TO oracle2_replacement_requester;

-- Installation/catalog invariant, not a new runtime issuer. Unexpected default
-- grants or foreign owners fail migration; never silently borrow their rights.
DO $catalog$
DECLARE owner_id oid;item record;allowed oid[];
BEGIN
 SELECT nspowner INTO owner_id FROM pg_namespace WHERE nspname='oracle2';
 FOR item IN SELECT c.oid,c.relowner,c.relacl,c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='oracle2' AND c.relname=ANY(ARRAY[
   'meeting_participation_admissions_v1','meeting_participation_revocations_v1','meeting_participation_heads_v1',
   'meeting_participation_observations_v1','meeting_participation_events_v1','meeting_participation_intents_v1',
   'meeting_participation_delivery_heads_v1','meeting_participation_delivery_events_v1','meeting_participation_audience_heads_v1']) LOOP
  IF item.relowner<>owner_id OR NOT item.relrowsecurity OR EXISTS(
   SELECT 1 FROM aclexplode(coalesce(item.relacl,acldefault('r',item.relowner))) a WHERE a.grantee<>owner_id) THEN
   RAISE EXCEPTION 'participation private table catalog denied';END IF;
 END LOOP;
 FOR item IN SELECT p.*,n.nspname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='oracle2' AND(p.proname LIKE 'meeting_participation_%' OR p.proname LIKE '\_meeting_participation\_%' ESCAPE '\') LOOP
  allowed:=ARRAY[owner_id];
  IF left(item.proname,1)<>'_' THEN
   allowed:=array_append(allowed,(SELECT oid FROM pg_roles WHERE rolname='oracle2_replacement_requester'));
  END IF;
  IF item.proowner<>owner_id OR item.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, oracle2']::text[]
  OR item.prosecdef IS DISTINCT FROM (item.proname<>'_meeting_participation_revoke_lock_v1')
  OR EXISTS(SELECT 1 FROM aclexplode(coalesce(item.proacl,acldefault('f',item.proowner))) a
    WHERE NOT(a.grantee=ANY(allowed)) OR a.privilege_type<>'EXECUTE' OR a.is_grantable)
  OR EXISTS(SELECT 1 FROM unnest(allowed) expected WHERE NOT EXISTS(
    SELECT 1 FROM aclexplode(coalesce(item.proacl,acldefault('f',item.proowner))) a WHERE a.grantee=expected AND a.privilege_type='EXECUTE')) THEN
   RAISE EXCEPTION 'fixed participation function owner ACL denied';END IF;
 END LOOP;
END $catalog$;
