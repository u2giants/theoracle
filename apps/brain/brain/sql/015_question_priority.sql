-- Owner 2026-11-10: every stored question is vetted first. Idempotent.
-- priority: 3-5, how much the answer matters (NULL = never vetted, never sent
--   unless an admin routed it by hand).
-- suggested_person / department: who the vetting picked to ask. An empty
--   department ('') means "vetted, nobody suitable" (stays for manual routing).
ALTER TABLE cmap.open_question ADD COLUMN IF NOT EXISTS priority smallint;
ALTER TABLE cmap.open_question ADD COLUMN IF NOT EXISTS suggested_person text;
ALTER TABLE cmap.open_question ADD COLUMN IF NOT EXISTS department text;
