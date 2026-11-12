-- Repair plan B1: owner-approved eval questions. Only rows with approved_at
-- count toward the eval bar (the eval runner filters on it); retired_at marks
-- the owner's retire action; abstention marks the "the documents do not say"
-- questions whose correct answer is an admission of ignorance (B2 scores
-- against this column name); recommendation is the admin's note shown on the
-- eval page. function (multi-valued: a question may span several functions)
-- is filled later by step C1. Idempotent.
ALTER TABLE cmap.eval_question ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE cmap.eval_question ADD COLUMN IF NOT EXISTS function text[];
ALTER TABLE cmap.eval_question ADD COLUMN IF NOT EXISTS abstention boolean NOT NULL DEFAULT false;
ALTER TABLE cmap.eval_question ADD COLUMN IF NOT EXISTS retired_at timestamptz;
ALTER TABLE cmap.eval_question ADD COLUMN IF NOT EXISTS recommendation text;
