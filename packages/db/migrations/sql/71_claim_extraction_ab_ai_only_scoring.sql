ALTER TABLE claim_extraction_ab_tests
DROP CONSTRAINT IF EXISTS claim_extraction_ab_tests_best_variant_check;

UPDATE claim_extraction_ab_tests
SET best_variant = NULL,
    reviewed_by_employee_id = NULL,
    reviewed_at = NULL,
    updated_at = now()
WHERE best_variant = 'human_revision';

ALTER TABLE claim_extraction_ab_tests
ADD CONSTRAINT claim_extraction_ab_tests_best_variant_check
CHECK (
  best_variant IS NULL
  OR best_variant IN ('existing_gemini_2_5', 'gemini_3_1_flash_lite', 'qwen_3_7_max')
);
