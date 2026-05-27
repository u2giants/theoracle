-- 56_employees_departments_array.sql
-- Data migration: copy existing employees.department (varchar) into the new
-- employees.departments (text[]) column added in Drizzle migration 0006.
-- Safe to re-run: only updates rows where departments is still empty.

UPDATE employees
SET departments = ARRAY[department]
WHERE department IS NOT NULL
  AND department <> ''
  AND (departments IS NULL OR departments = '{}');
