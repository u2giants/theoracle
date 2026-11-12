-- B2 (repair plan §9 Phase B): eval questions can be marked "do not know"
-- questions that must be answered with a decline, and eval runs keep the
-- legacy formula's mean next to the new composite one for three runs of
-- continuity. B1's SQL 019 adds the same abstention column; IF NOT EXISTS
-- keeps both landing orders safe.
ALTER TABLE cmap.eval_question
  ADD COLUMN IF NOT EXISTS abstention boolean NOT NULL DEFAULT false;
ALTER TABLE cmap.eval_run
  ADD COLUMN IF NOT EXISTS mean_score_legacy real;
