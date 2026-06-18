-- Claim review groups:
-- Admin-managed recipient lists for sending a claim-review follow-up question
-- to multiple employees at once. Assignments still materialize as one `gaps`
-- row per employee so the existing /claims "Assigned to me" queue works.

BEGIN;

CREATE TABLE IF NOT EXISTS claim_review_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name varchar(120) NOT NULL,
  description text,
  created_by_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  archived_at timestamp,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS claim_review_groups_active_name_unique
  ON claim_review_groups (name)
  WHERE archived_at IS NULL;

CREATE INDEX IF NOT EXISTS claim_review_groups_archived_idx
  ON claim_review_groups (archived_at);

CREATE TABLE IF NOT EXISTS claim_review_group_members (
  group_id uuid NOT NULL REFERENCES claim_review_groups(id) ON DELETE CASCADE,
  employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  added_by_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  added_at timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (group_id, employee_id)
);

CREATE INDEX IF NOT EXISTS claim_review_group_members_employee_idx
  ON claim_review_group_members (employee_id);

ALTER TABLE claim_review_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_review_group_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS claim_review_groups_admin_all ON claim_review_groups;
DROP POLICY IF EXISTS claim_review_group_members_admin_all ON claim_review_group_members;

CREATE POLICY claim_review_groups_admin_all ON claim_review_groups
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

CREATE POLICY claim_review_group_members_admin_all ON claim_review_group_members
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

COMMIT;
