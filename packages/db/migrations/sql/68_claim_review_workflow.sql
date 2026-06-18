-- Claim review workflow: revisions + domain-scoped reviewer permissions.
--
-- A revised claim is not an in-place mutation. The app creates a replacement
-- claim, marks the original as superseded, and writes a claim_review_events
-- row preserving the before/after state and reviewer note.
--
-- Domain review permissions are department-based: membership in a department
-- listed for one of a claim's top domains can review that claim without full
-- admin rights.

BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_domain_review_departments (
  top_domain_id varchar(100) NOT NULL REFERENCES knowledge_top_domains(id) ON DELETE CASCADE,
  department_id department NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
  can_review_claims boolean NOT NULL DEFAULT true,
  created_at timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (top_domain_id, department_id)
);

CREATE INDEX IF NOT EXISTS knowledge_domain_review_departments_department_idx
  ON knowledge_domain_review_departments (department_id);

CREATE TABLE IF NOT EXISTS claim_review_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  replacement_claim_id uuid REFERENCES claims(id) ON DELETE SET NULL,
  action varchar(50) NOT NULL,
  reviewed_by_employee_id uuid NOT NULL REFERENCES employees(id),
  reviewer_note text,
  before_state jsonb NOT NULL,
  after_state jsonb,
  ai_comparison_json jsonb,
  created_at timestamp NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS claim_review_events_claim_idx
  ON claim_review_events (claim_id, created_at DESC);

CREATE INDEX IF NOT EXISTS claim_review_events_replacement_claim_idx
  ON claim_review_events (replacement_claim_id);

DO $$
BEGIN
  ALTER TABLE claim_review_events
    ADD CONSTRAINT claim_review_events_action_check
    CHECK (action IN ('approve', 'reject', 'revise'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Seed a conservative starting map from domains to the departments most likely
-- to have enough subject-matter context to review claims. Admins can edit this
-- table later without granting global admin access.
INSERT INTO knowledge_domain_review_departments (top_domain_id, department_id) VALUES
  ('customer_ops', 'sales'),
  ('licensing_approvals', 'licensing'),
  ('product_development', 'design'),
  ('product_development', 'production'),
  ('creative_design', 'design'),
  ('design_file_operations', 'design'),
  ('supply_chain', 'sourcing'),
  ('supply_chain', 'production'),
  ('it_systems', 'operations'),
  ('operations_systems', 'operations'),
  ('operations_systems', 'production'),
  ('training_enablement', 'management'),
  ('training_enablement', 'operations'),
  ('production_lifecycle', 'production'),
  ('finance_pricing', 'sales'),
  ('finance_pricing', 'administrative'),
  ('people_org', 'management'),
  ('vendor_management', 'sourcing'),
  ('logistics_shipping', 'logistics'),
  ('import_compliance', 'logistics')
ON CONFLICT (top_domain_id, department_id) DO NOTHING;

COMMIT;
