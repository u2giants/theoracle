-- 61_departments.sql
-- Org-unit departments.
--
-- Scope: this file is the SOLE creator of the `department` Postgres enum,
-- the `departments` metadata table, and the `employee_departments` join
-- table. Drizzle generated migrations are NOT used for these because the
-- repo's drizzle migration journal is out of sync with prod (see
-- docs/deployment.md "Known drift 2026-05-28"). The Drizzle schema in
-- packages/db/src/schema.ts declares these for typing only; the actual
-- DDL lives here.
--
-- Idempotency: this file runs on every `pnpm db:migrate`. Every statement
-- below is wrapped in IF NOT EXISTS, ON CONFLICT DO NOTHING, or a DO block
-- that swallows duplicate_object errors.

-- ---------------------------------------------------------------------------
-- 1. Enum type
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  CREATE TYPE department AS ENUM (
    'sales',
    'design',
    'licensing',
    'production',
    'logistics',
    'operations',
    'administrative',
    'management',
    'sourcing'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Adding a new enum value later: ALTER TYPE department ADD VALUE IF NOT EXISTS
-- 'new_value';  -- must run outside a transaction (Postgres limitation), so
-- put it in its own file, e.g. 62_departments_add_X.sql.

-- ---------------------------------------------------------------------------
-- 2. Tables
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS departments (
  id              department PRIMARY KEY,
  display_label   varchar(120) NOT NULL,
  description     text,
  head_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
  created_at      timestamp NOT NULL DEFAULT now(),
  updated_at      timestamp NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_departments (
  employee_id     uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  department_id   department NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
  added_at        timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (employee_id, department_id)
);

CREATE INDEX IF NOT EXISTS idx_employee_departments_department
  ON employee_departments (department_id);

-- ---------------------------------------------------------------------------
-- 3. Seed one departments row per enum value
-- ---------------------------------------------------------------------------
INSERT INTO departments (id, display_label) VALUES
  ('sales',          'Sales'),
  ('design',         'Design'),
  ('licensing',      'Licensing'),
  ('production',     'Production'),
  ('logistics',      'Logistics'),
  ('operations',     'Operations'),
  ('administrative', 'Administrative'),
  ('management',     'Management'),
  ('sourcing',       'Sourcing')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. Best-effort backfill from the legacy employees.departments text[] column.
--
-- Pre-existing rows carry free-text department names like 'Sales' or
-- 'sales' or 'Sales & Marketing'. Map case-insensitively against our enum
-- values; anything that doesn't match is left in the legacy text[] column
-- untouched and surfaces in the admin UI as "unmapped" for manual fixup.
--
-- This runs every boot but is idempotent (PRIMARY KEY blocks duplicates).
-- ---------------------------------------------------------------------------
INSERT INTO employee_departments (employee_id, department_id)
SELECT
  e.id,
  lower(dep)::department
FROM employees e
CROSS JOIN LATERAL unnest(e.departments) AS dep
WHERE lower(dep) IN (
  'sales','design','licensing','production','logistics',
  'operations','administrative','management','sourcing'
)
ON CONFLICT (employee_id, department_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. updated_at trigger so admin edits bump the timestamp.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION departments_touch_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_departments_touch_updated_at ON departments;
CREATE TRIGGER trg_departments_touch_updated_at
  BEFORE UPDATE ON departments
  FOR EACH ROW EXECUTE FUNCTION departments_touch_updated_at();
