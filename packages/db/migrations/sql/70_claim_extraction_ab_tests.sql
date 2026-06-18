CREATE TABLE IF NOT EXISTS claim_extraction_ab_tests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_review_event_id uuid NOT NULL REFERENCES claim_review_events(id) ON DELETE CASCADE,
  source_claim_id uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  revised_claim_id uuid NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  source_type varchar(50) NOT NULL,
  source_id uuid,
  source_excerpt text NOT NULL,
  gemini_3_1_output_json jsonb,
  qwen_3_7_output_json jsonb,
  gemini_3_1_error text,
  qwen_3_7_error text,
  best_variant varchar(50),
  reviewer_note text,
  reviewed_by_employee_id uuid REFERENCES employees(id),
  reviewed_at timestamp,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now(),
  CONSTRAINT claim_extraction_ab_tests_event_unique UNIQUE (claim_review_event_id),
  CONSTRAINT claim_extraction_ab_tests_best_variant_check
    CHECK (
      best_variant IS NULL
      OR best_variant IN ('existing_gemini_2_5', 'gemini_3_1_flash_lite', 'qwen_3_7_max', 'human_revision')
    )
);

CREATE INDEX IF NOT EXISTS claim_extraction_ab_tests_reviewed_idx
  ON claim_extraction_ab_tests (reviewed_at, created_at);
