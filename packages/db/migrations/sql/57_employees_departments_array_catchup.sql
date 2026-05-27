-- 57_employees_departments_array_catchup.sql
--
-- Production was deploying code that referenced employees.departments
-- (a text[] column added by Drizzle migration 0006) without the matching
-- ALTER ever being applied to the DB. Every employee query (including
-- the OAuth callback) failed with "Failed query: select..." and returned
-- a 500.
--
-- This migration is what 0006 *should* have applied for the employees
-- table. The model_capabilities table and typing_indicators / entity_proposals
-- changes from 0006 had already been applied via earlier hand-written SQL,
-- so we only restore the employees part here.

ALTER TABLE employees ALTER COLUMN department DROP NOT NULL;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS departments text[] DEFAULT '{}' NOT NULL;

-- Backfill: copy existing scalar department into the new array column.
-- Safe to re-run.
UPDATE employees
SET departments = ARRAY[department]
WHERE department IS NOT NULL
  AND department <> ''
  AND (departments IS NULL OR departments = '{}');
