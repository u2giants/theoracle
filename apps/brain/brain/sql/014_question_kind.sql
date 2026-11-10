-- Step 2.3: interview questions share the translation sidecar. Idempotent.
-- kind='question' rows cache the zh-CN translation of an open question
-- (write-once per question, plan step 2.3).
ALTER TABLE cmap.translation DROP CONSTRAINT IF EXISTS translation_kind_check;
ALTER TABLE cmap.translation ADD CONSTRAINT translation_kind_check
  CHECK (kind IN ('entity', 'community', 'edge', 'question'));
