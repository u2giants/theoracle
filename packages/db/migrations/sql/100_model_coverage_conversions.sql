-- GAP-11: audited, admin-only conversion of administrative model coverage findings.
ALTER TABLE gaps ADD COLUMN IF NOT EXISTS source_context jsonb;

CREATE TABLE IF NOT EXISTS model_coverage_conversions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_gap_id uuid NOT NULL REFERENCES gaps(id) ON DELETE RESTRICT,
  question_to_ask text NOT NULL,
  conversion_reason text NOT NULL,
  target_employee_ids jsonb NOT NULL,
  source_snapshot jsonb NOT NULL,
  status varchar(30) NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'sent', 'cancelled')),
  created_gap_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by_employee_id uuid NOT NULL REFERENCES employees(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS model_coverage_conversions_status_created_idx
  ON model_coverage_conversions(status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS model_coverage_conversions_active_source_gap_unique
  ON model_coverage_conversions(source_gap_id)
  WHERE status IN ('draft', 'sent');

CREATE TABLE IF NOT EXISTS model_coverage_conversion_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversion_id uuid NOT NULL REFERENCES model_coverage_conversions(id) ON DELETE RESTRICT,
  source_gap_id uuid NOT NULL REFERENCES gaps(id) ON DELETE RESTRICT,
  action varchar(30) NOT NULL CHECK (action IN ('draft_created', 'sent', 'cancelled')),
  acted_by_employee_id uuid NOT NULL REFERENCES employees(id),
  source_snapshot jsonb NOT NULL,
  after_state jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS model_coverage_conversion_events_conversion_created_idx
  ON model_coverage_conversion_events(conversion_id, created_at);

CREATE OR REPLACE FUNCTION prevent_model_coverage_conversion_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'model_coverage_conversion_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS model_coverage_conversion_events_append_only
  ON model_coverage_conversion_events;
CREATE TRIGGER model_coverage_conversion_events_append_only
  BEFORE UPDATE OR DELETE ON model_coverage_conversion_events
  FOR EACH ROW EXECUTE FUNCTION prevent_model_coverage_conversion_event_mutation();

ALTER TABLE model_coverage_conversions ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_coverage_conversion_events ENABLE ROW LEVEL SECURITY;

COMMENT ON COLUMN gaps.source_context IS
  'Server-authored stable provenance for administrative findings. Never rendered to employee consumers.';
COMMENT ON TABLE model_coverage_conversions IS
  'Admin-reviewed drafts that turn one model_coverage finding into employee-facing gaps.';
COMMENT ON TABLE model_coverage_conversion_events IS
  'Append-only audit of draft, send, and cancellation decisions for GAP-11.';
