-- Idempotent local roles for the isolated oracle2 store (not production).
DO $$ BEGIN
  CREATE ROLE oracle2_extract LOGIN PASSWORD 'oracle2_local_extract_only';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE oracle2_project LOGIN PASSWORD 'oracle2_local_project_only';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE oracle2_checkpoint LOGIN PASSWORD 'oracle2_local_checkpoint_only';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE ROLE oracle2_pilot_web LOGIN PASSWORD 'oracle2_local_pilot_web_only';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
