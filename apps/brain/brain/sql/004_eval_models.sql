-- Eval runs record the model configuration that produced them so bake-off
-- runs can be compared honestly (Albert's direction 2026-10-30: eval runs
-- must record their models). Pre-provenance rows keep NULL.
ALTER TABLE cmap.eval_run ADD COLUMN IF NOT EXISTS models jsonb;
