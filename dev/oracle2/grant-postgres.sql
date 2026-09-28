GRANT USAGE ON SCHEMA oracle2 TO oracle2_extract, oracle2_project, oracle2_checkpoint;
GRANT SELECT, INSERT, UPDATE ON oracle2.candidates TO oracle2_extract;
GRANT SELECT, INSERT ON oracle2.checkpoint_owners TO oracle2_checkpoint;
GRANT SELECT ON oracle2.accepted TO oracle2_project;
GRANT SELECT, UPDATE ON oracle2.outbox TO oracle2_project;
GRANT SELECT, INSERT ON oracle2.projection_receipts TO oracle2_project;
