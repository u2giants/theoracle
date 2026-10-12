-- Additive dedicated Oracle ledger. No shared-database objects or legacy erasure.
CREATE TABLE IF NOT EXISTS oracle2.artifact_manifests (
 workspace_id uuid NOT NULL, artifact_id uuid NOT NULL, version integer NOT NULL CHECK(version>0),
 kind text NOT NULL, input_digest text NOT NULL, source_digest text NOT NULL,
 permission_digest text NOT NULL, compiler_digest text NOT NULL, dependency_digest text NOT NULL,
 content_hash text NOT NULL CHECK(content_hash ~ '^[0-9a-f]{64}$'), private_object_key text NOT NULL,
 state text NOT NULL CHECK(state IN ('ready','failed')), manifest jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,artifact_id,version));
CREATE TABLE IF NOT EXISTS oracle2.artifact_dependencies (
 workspace_id uuid NOT NULL, artifact_id uuid NOT NULL, version integer NOT NULL,
 upstream_kind text NOT NULL, upstream_id text NOT NULL, upstream_revision text NOT NULL,
 PRIMARY KEY(workspace_id,artifact_id,version,upstream_kind,upstream_id,upstream_revision),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests);
CREATE INDEX IF NOT EXISTS artifact_upstream ON oracle2.artifact_dependencies(workspace_id,upstream_kind,upstream_id);
CREATE TABLE IF NOT EXISTS oracle2.artifact_invalidations (
 workspace_id uuid NOT NULL, artifact_id uuid NOT NULL, version integer NOT NULL,
 reason text NOT NULL, event_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,artifact_id,version,event_id),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests);
CREATE TABLE IF NOT EXISTS oracle2.finding_events (
 workspace_id uuid NOT NULL, finding_id text NOT NULL, event_id uuid NOT NULL,
 actor_id uuid NOT NULL, scope text NOT NULL, action text NOT NULL,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,event_id));
CREATE TABLE IF NOT EXISTS oracle2.operational_imports (
 workspace_id uuid NOT NULL, import_id uuid NOT NULL, revision integer NOT NULL CHECK(revision>0),
 mapping_hash text NOT NULL, window_hash text NOT NULL, quality jsonb NOT NULL,
 accepted_count bigint NOT NULL CHECK(accepted_count>=0), quarantined_count bigint NOT NULL CHECK(quarantined_count>=0),
 content_hash text NOT NULL, artifact_id uuid NOT NULL, PRIMARY KEY(workspace_id,import_id,revision));
CREATE TABLE IF NOT EXISTS oracle2.operating_model_source_receipts (
 workspace_id uuid NOT NULL, source_id uuid NOT NULL, revision integer NOT NULL CHECK(revision>0),
 original_hash text NOT NULL, reading_hash text NOT NULL, parser_id text NOT NULL,
 receipt jsonb NOT NULL, PRIMARY KEY(workspace_id,source_id,revision));
CREATE TABLE IF NOT EXISTS oracle2.document_observations (
 workspace_id uuid NOT NULL, observation_id text NOT NULL, source_id uuid NOT NULL,
 source_revision integer NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(workspace_id,observation_id),
 FOREIGN KEY(workspace_id,source_id,source_revision) REFERENCES oracle2.operating_model_source_receipts(workspace_id,source_id,revision));
CREATE TABLE IF NOT EXISTS oracle2.assembly_revisions (
 workspace_id uuid NOT NULL, assembly_id uuid NOT NULL, revision integer NOT NULL CHECK(revision>0),
 artifact_id uuid NOT NULL, payload jsonb NOT NULL, PRIMARY KEY(workspace_id,assembly_id,revision));
CREATE OR REPLACE FUNCTION oracle2.deny_operating_model_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'operating model history is append-only'; END $$;
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['artifact_manifests','artifact_dependencies','artifact_invalidations','finding_events','operational_imports','operating_model_source_receipts','document_observations','assembly_revisions'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='immutable_'||name AND tgrelid=('oracle2.'||name)::regclass) THEN
   EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()', 'immutable_'||name,name);
  END IF;
 END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA oracle2 FROM PUBLIC;
-- Conservative prepaid reservation; immutable holds avoid freeing budget after failures.
CREATE TABLE IF NOT EXISTS oracle2.operating_dispatch_reservations (
 reservation_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, artifact_id uuid NOT NULL,
 batch_id uuid NOT NULL, purpose text NOT NULL, attempt integer NOT NULL CHECK(attempt IN (1,2)),
 reserved_usd numeric(12,6) NOT NULL CHECK(reserved_usd>0 AND reserved_usd<=1),
 pricing_hash text NOT NULL, reserved_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,artifact_id,purpose,attempt));
CREATE TABLE IF NOT EXISTS oracle2.operating_dispatch_receipts (
 reservation_id uuid PRIMARY KEY REFERENCES oracle2.operating_dispatch_reservations,
 actual_usd numeric(12,6) NOT NULL CHECK(actual_usd>=0), status text NOT NULL CHECK(status IN ('completed','failed','overrun')),
 response_hash text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS oracle2.operating_dispatch_diagnoses (
 reservation_id uuid PRIMARY KEY REFERENCES oracle2.operating_dispatch_receipts,
 diagnosed_by uuid NOT NULL, failure_kind text NOT NULL CHECK(failure_kind IN ('invalid_output','truncated_output','transport_failure','quota_exhausted')),
 correction_hash text NOT NULL CHECK(correction_hash ~ '^[0-9a-f]{64}$'),
 diagnosis_hash text NOT NULL CHECK(diagnosis_hash ~ '^[0-9a-f]{64}$'), created_at timestamptz NOT NULL DEFAULT now());
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['operating_dispatch_reservations','operating_dispatch_receipts','operating_dispatch_diagnoses'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='immutable_'||name AND tgrelid=('oracle2.'||name)::regclass) THEN
 EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()', 'immutable_'||name,name);
 END IF; END LOOP; END $$;
REVOKE ALL ON oracle2.operating_dispatch_reservations,oracle2.operating_dispatch_receipts,oracle2.operating_dispatch_diagnoses FROM PUBLIC;
-- Fence the serving selector, never source ingestion. Existing writes remain enabled.
CREATE TABLE IF NOT EXISTS oracle2.operating_model_change_log (
 sequence bigserial PRIMARY KEY, workspace_id uuid NOT NULL, object_kind text NOT NULL,
 object_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS operating_change_workspace ON oracle2.operating_model_change_log(workspace_id,sequence);
CREATE OR REPLACE FUNCTION oracle2.record_operating_model_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE data jsonb; BEGIN
 data=CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
 INSERT INTO oracle2.operating_model_change_log(workspace_id,object_kind,object_id)
 VALUES((data->>'workspace_id')::uuid,TG_TABLE_NAME,COALESCE(data->>'source_id',data->>'appointment_id'));
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['sources','source_blocks','drafts','appointments'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='operating_change_'||name AND tgrelid=('oracle2.'||name)::regclass) THEN
 EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.record_operating_model_change()', 'operating_change_'||name,name);
 END IF; END LOOP; END $$;
CREATE TABLE IF NOT EXISTS oracle2.operating_release_manifests (
 workspace_id uuid NOT NULL, release_id uuid NOT NULL, content_hash text NOT NULL,
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,release_id));
CREATE TABLE IF NOT EXISTS oracle2.operating_release_selectors (
 workspace_id uuid PRIMARY KEY, release_id uuid NOT NULL, generation integer NOT NULL CHECK(generation>0),
 watermark bigint NOT NULL CHECK(watermark>=0),
 FOREIGN KEY(workspace_id,release_id) REFERENCES oracle2.operating_release_manifests);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='immutable_operating_releases' AND tgrelid='oracle2.operating_release_manifests'::regclass) THEN
 CREATE TRIGGER immutable_operating_releases BEFORE UPDATE OR DELETE ON oracle2.operating_release_manifests FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
 END IF;
END $$;
REVOKE ALL ON oracle2.operating_model_change_log,oracle2.operating_release_manifests,oracle2.operating_release_selectors FROM PUBLIC;
CREATE OR REPLACE FUNCTION oracle2.guard_operating_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF current_user='oracle2_extract' THEN
  IF NEW.payload->>'namespace' IS DISTINCT FROM 'oracle_operating_model_v1' OR NOT EXISTS(
    SELECT 1 FROM oracle2.artifact_manifests m WHERE m.workspace_id=NEW.workspace_id
      AND m.artifact_id=NEW.assertion_id AND m.version=NEW.revision AND m.state='ready'
      AND m.manifest=NEW.payload->'manifest') THEN
   RAISE EXCEPTION 'extractor may enqueue only its immutable reported artifact manifest';
  END IF;
 END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='operating_outbox_guard' AND tgrelid='oracle2.outbox'::regclass) THEN
 CREATE TRIGGER operating_outbox_guard BEFORE INSERT ON oracle2.outbox FOR EACH ROW EXECUTE FUNCTION oracle2.guard_operating_outbox();
 END IF;
END $$;
-- Opaque, actor-owned view jobs. No text is placed in Trigger task payloads.
CREATE TABLE IF NOT EXISTS oracle2.operating_view_runs (
 run_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, actor_id uuid NOT NULL,
 query_plan jsonb NOT NULL, release_id uuid NOT NULL, release_hash text NOT NULL,
 status text NOT NULL CHECK(status IN ('pending','completed','error')),
 pack jsonb, source_refs jsonb NOT NULL, error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL DEFAULT now()+interval '5 minutes');
REVOKE ALL ON oracle2.operating_view_runs FROM PUBLIC;

-- Recompute requests preserve denial until a newly authorized artifact is sealed.
CREATE TABLE IF NOT EXISTS oracle2.operating_recompute_requests (
 request_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, artifact_id uuid NOT NULL, version integer NOT NULL,
 event_id uuid NOT NULL, reason text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,artifact_id,version,event_id),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests);
CREATE TABLE IF NOT EXISTS oracle2.operating_recompute_events (
 request_id uuid NOT NULL REFERENCES oracle2.operating_recompute_requests, event_id uuid PRIMARY KEY,
 state text NOT NULL CHECK(state IN ('blocked','rebuilt')), payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS oracle2.operating_source_stewards (
 event_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, source_id uuid NOT NULL,
 steward_id uuid NOT NULL, appointed_by uuid NOT NULL, scope text NOT NULL,
 source_revision integer NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['operating_recompute_requests','operating_recompute_events','operating_source_stewards'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='immutable_'||name AND tgrelid=('oracle2.'||name)::regclass) THEN
 EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON oracle2.%I FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation()', 'immutable_'||name,name);
 END IF; END LOOP; END $$;
REVOKE ALL ON oracle2.operating_recompute_requests,oracle2.operating_recompute_events,oracle2.operating_source_stewards FROM PUBLIC;

CREATE TABLE IF NOT EXISTS oracle2.operating_projection_receipts (
 event_id uuid PRIMARY KEY REFERENCES oracle2.outbox,workspace_id uuid NOT NULL,artifact_id uuid NOT NULL,
 version integer NOT NULL,payload jsonb NOT NULL,signature text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(workspace_id,artifact_id,version) REFERENCES oracle2.artifact_manifests);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='immutable_operating_projection_receipts' AND tgrelid='oracle2.operating_projection_receipts'::regclass) THEN
 CREATE TRIGGER immutable_operating_projection_receipts BEFORE UPDATE OR DELETE ON oracle2.operating_projection_receipts FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_model_mutation();
 END IF;
END $$;
CREATE OR REPLACE FUNCTION oracle2.deny_operating_outbox_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.payload->>'namespace'='oracle_operating_model_v1' OR NEW.payload->>'namespace'='oracle_operating_model_v1' THEN
  IF (OLD.event_id,OLD.workspace_id,OLD.assertion_id,OLD.revision,OLD.operation,OLD.payload) IS DISTINCT FROM
     (NEW.event_id,NEW.workspace_id,NEW.assertion_id,NEW.revision,NEW.operation,NEW.payload) THEN
   RAISE EXCEPTION 'operating artifact outbox identity is immutable';
  END IF;
 END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='operating_outbox_identity' AND tgrelid='oracle2.outbox'::regclass) THEN
 CREATE TRIGGER operating_outbox_identity BEFORE UPDATE ON oracle2.outbox FOR EACH ROW EXECUTE FUNCTION oracle2.deny_operating_outbox_rewrite();
 END IF;
END $$;
REVOKE ALL ON oracle2.operating_projection_receipts FROM PUBLIC;
