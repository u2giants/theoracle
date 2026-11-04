-- Department and job title the Teams bot asks each employee for (owner
-- direction 2026-11-03). Idempotent.
ALTER TABLE cmap.employee_flags ADD COLUMN IF NOT EXISTS department text;
ALTER TABLE cmap.employee_flags ADD COLUMN IF NOT EXISTS job_title text;
ALTER TABLE cmap.employee_flags ADD COLUMN IF NOT EXISTS profile_answer text;
ALTER TABLE cmap.employee_flags ADD COLUMN IF NOT EXISTS profile_asked_at timestamptz;
ALTER TABLE cmap.employee_flags ADD COLUMN IF NOT EXISTS profile_updated_at timestamptz;
