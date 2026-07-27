-- Translations created before GAP-4 were already live and had no review fields.
-- Preserve that serving behavior during rollout. New worker output always writes
-- a prompt version and explicitly starts at pending_review.
UPDATE claim_translations
SET review_status = 'approved'
WHERE review_status = 'pending_review'
  AND translation_prompt_version IS NULL;
