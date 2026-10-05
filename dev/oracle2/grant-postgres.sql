GRANT USAGE ON SCHEMA oracle2 TO oracle2_extract, oracle2_project, oracle2_checkpoint, oracle2_pilot_web;
GRANT SELECT, INSERT, UPDATE ON oracle2.candidates TO oracle2_extract;
GRANT SELECT, INSERT ON oracle2.checkpoint_owners TO oracle2_checkpoint;
GRANT SELECT ON oracle2.accepted TO oracle2_project;
GRANT SELECT, UPDATE ON oracle2.outbox TO oracle2_project;
GRANT SELECT, INSERT ON oracle2.projection_receipts TO oracle2_project;
-- Pilot web: read appointments (FOR UPDATE row locks need SELECT); journey
-- writes are insert-only except draft state. Source blocks, reviews, and runs
-- are append-only evidence. Bootstrap of appointments requires admin.
GRANT SELECT ON oracle2.appointments TO oracle2_pilot_web;
GRANT INSERT ON oracle2.sources, oracle2.source_blocks, oracle2.reviews, oracle2.runs TO oracle2_pilot_web;
GRANT SELECT ON oracle2.sources, oracle2.source_blocks, oracle2.drafts, oracle2.reviews, oracle2.runs TO oracle2_pilot_web;
GRANT INSERT, UPDATE ON oracle2.drafts TO oracle2_pilot_web;
