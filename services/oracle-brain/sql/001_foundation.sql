-- Isolated Oracle 2 schema. Applied to the local test database only in S02.
CREATE SCHEMA IF NOT EXISTS oracle2;
CREATE TABLE IF NOT EXISTS oracle2.candidates (
  workspace_id uuid NOT NULL,
  assertion_id uuid NOT NULL,
  source_id uuid NOT NULL,
  source_revision integer NOT NULL CHECK (source_revision > 0),
  bundle jsonb NOT NULL,
  PRIMARY KEY (workspace_id, assertion_id)
);
CREATE TABLE IF NOT EXISTS oracle2.appointments (
  appointment_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  scope text NOT NULL,
  granted_by uuid NOT NULL,
  parent_id uuid REFERENCES oracle2.appointments(appointment_id),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (actor_id <> granted_by)
);
CREATE INDEX IF NOT EXISTS appointments_actor_scope ON oracle2.appointments(workspace_id,actor_id,scope);
CREATE TABLE IF NOT EXISTS oracle2.accepted (
  workspace_id uuid NOT NULL,
  assertion_id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  status text NOT NULL CHECK (status IN ('active','withdrawn')),
  payload jsonb NOT NULL,
  PRIMARY KEY (workspace_id, assertion_id)
);
CREATE TABLE IF NOT EXISTS oracle2.outbox (
  event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  assertion_id uuid NOT NULL,
  revision integer NOT NULL CHECK (revision > 0),
  operation text NOT NULL CHECK (operation IN ('project','withdraw')),
  payload jsonb NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  lease_until timestamptz,
  delivered_at timestamptz,
  UNIQUE (workspace_id, assertion_id, revision)
);
-- Pending-work index for lease_next; delivered rows drop out of it.
CREATE INDEX IF NOT EXISTS outbox_pending ON oracle2.outbox (revision, event_id)
  WHERE delivered_at IS NULL;
CREATE TABLE IF NOT EXISTS oracle2.projection_receipts (
  event_id uuid PRIMARY KEY REFERENCES oracle2.outbox(event_id),
  workspace_id uuid NOT NULL,
  assertion_id uuid NOT NULL,
  revision integer NOT NULL,
  operation text NOT NULL,
  projector_id text NOT NULL,
  signature text NOT NULL,
  applied_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS oracle2.checkpoint_owners (
  thread_id text PRIMARY KEY,
  workspace_id uuid NOT NULL,
  user_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Separate database roles protect the durable authority ledger even if a
-- candidate worker is compromised. Runtime roles are provisioned by compose.
REVOKE ALL ON SCHEMA oracle2 FROM PUBLIC;
