CREATE ROLE oracle2_extract LOGIN PASSWORD 'oracle2_local_extract_only';
CREATE ROLE oracle2_project LOGIN PASSWORD 'oracle2_local_project_only';
CREATE ROLE oracle2_checkpoint LOGIN PASSWORD 'oracle2_local_checkpoint_only';
-- Pilot web path: read appointments + write pilot journey rows (not admin).
CREATE ROLE oracle2_pilot_web LOGIN PASSWORD 'oracle2_local_pilot_web_only';
