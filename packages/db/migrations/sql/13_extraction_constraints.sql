-- R4 extraction-staging CHECK constraints.
--
-- Drizzle generates table DDL only — value whitelists and source-type/
-- pointer consistency rules live here. These guard the staging tables at
-- the DB level so background workers, admin SQL, and any future
-- non-TypeScript integration get the same invariants.
--
-- Idempotent: every constraint uses DROP CONSTRAINT IF EXISTS first.

-- ---------------------------------------------------------------------------
-- extraction_batches — status + type whitelists; counters non-negative
-- ---------------------------------------------------------------------------

ALTER TABLE extraction_batches
  DROP CONSTRAINT IF EXISTS extraction_batches_batch_type_check;
ALTER TABLE extraction_batches
  ADD CONSTRAINT extraction_batches_batch_type_check
  CHECK (batch_type IN (
    'message_segment',
    'document_chunk',
    'document_page',
    'document_lens_group',
    'transcript_segment'
  ));

ALTER TABLE extraction_batches
  DROP CONSTRAINT IF EXISTS extraction_batches_status_check;
ALTER TABLE extraction_batches
  ADD CONSTRAINT extraction_batches_status_check
  CHECK (status IN (
    'pending_model','model_complete','validation_complete',
    'promoted','complete','failed','skipped','failed_validation_loop'
  ));

ALTER TABLE extraction_batches
  DROP CONSTRAINT IF EXISTS extraction_batches_attempt_count_check;
ALTER TABLE extraction_batches
  ADD CONSTRAINT extraction_batches_attempt_count_check
  CHECK (validation_attempt_count >= 0);

ALTER TABLE extraction_batches
  DROP CONSTRAINT IF EXISTS extraction_batches_failure_count_check;
ALTER TABLE extraction_batches
  ADD CONSTRAINT extraction_batches_failure_count_check
  CHECK (consecutive_quote_failure_count >= 0);

-- ---------------------------------------------------------------------------
-- extraction_candidates — status whitelist + stance whitelist
-- ---------------------------------------------------------------------------

ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_status_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_status_check
  CHECK (status IN (
    'pending_validation','validation_failed','failed_validation_loop',
    'validated','duplicate','promoted',
    'rejected','rejected_sensitive','quarantined_sensitive'
  ));

ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_stance_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_stance_check
  CHECK (
    stance IS NULL
    OR stance IN ('stated','confirmed','challenged','refined','exception_introduced','ambiguity_revealed')
  );

-- A promoted candidate must record promotedToClaimId + promotedAt.
ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_promoted_consistency_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_promoted_consistency_check
  CHECK (
    (status <> 'promoted' AND promoted_at IS NULL AND promoted_to_claim_id IS NULL)
    OR (status = 'promoted' AND promoted_at IS NOT NULL AND promoted_to_claim_id IS NOT NULL)
  );

-- A duplicate candidate must point at either an earlier candidate or a claim.
ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_duplicate_consistency_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_duplicate_consistency_check
  CHECK (
    status <> 'duplicate'
    OR duplicate_of_candidate_id IS NOT NULL
    OR duplicate_of_claim_id IS NOT NULL
  );

-- A sensitive candidate (rejected_sensitive / quarantined_sensitive) must
-- have at least one sensitivity flag set.
ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_sensitive_consistency_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_sensitive_consistency_check
  CHECK (
    status NOT IN ('rejected_sensitive','quarantined_sensitive')
    OR contains_sensitive_personal_data = TRUE
    OR contains_sensitive_hr_data = TRUE
    OR is_personal_conflict = TRUE
  );

ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_impact_range_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_impact_range_check
  CHECK (impact_score >= 0 AND impact_score <= 10);

ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_confidence_range_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_confidence_range_check
  CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 10));

-- A candidate cannot be its own duplicate.
ALTER TABLE extraction_candidates
  DROP CONSTRAINT IF EXISTS extraction_candidates_no_self_duplicate_check;
ALTER TABLE extraction_candidates
  ADD CONSTRAINT extraction_candidates_no_self_duplicate_check
  CHECK (duplicate_of_candidate_id IS NULL OR duplicate_of_candidate_id <> id);

-- ---------------------------------------------------------------------------
-- extraction_candidate_evidence — source-type/pointer consistency + status
--
-- Mirrors the claim_evidence_source_check rule from spec 6.8: each
-- source_type requires its matching FK column to be non-null.
-- ---------------------------------------------------------------------------

ALTER TABLE extraction_candidate_evidence
  DROP CONSTRAINT IF EXISTS extraction_candidate_evidence_source_check;
ALTER TABLE extraction_candidate_evidence
  ADD CONSTRAINT extraction_candidate_evidence_source_check
  CHECK (
    (source_type = 'message'         AND source_message_id IS NOT NULL)
    OR (source_type = 'document_chunk' AND source_document_chunk_id IS NOT NULL)
    OR (source_type = 'external_system' AND source_external_record_id IS NOT NULL)
    OR (source_type = 'manual_admin'  AND created_by_employee_id IS NOT NULL)
  );

ALTER TABLE extraction_candidate_evidence
  DROP CONSTRAINT IF EXISTS extraction_candidate_evidence_validation_status_check;
ALTER TABLE extraction_candidate_evidence
  ADD CONSTRAINT extraction_candidate_evidence_validation_status_check
  CHECK (validation_status IN (
    'pending','exact_match','normalized_match','failed','ambiguous','failed_validation_loop'
  ));

-- If validation passed (exact_match / normalized_match), the validated fields
-- must be populated. Forces validators to record what they actually matched.
ALTER TABLE extraction_candidate_evidence
  DROP CONSTRAINT IF EXISTS extraction_candidate_evidence_validated_fields_check;
ALTER TABLE extraction_candidate_evidence
  ADD CONSTRAINT extraction_candidate_evidence_validated_fields_check
  CHECK (
    validation_status NOT IN ('exact_match','normalized_match')
    OR (
      validated_exact_quote IS NOT NULL
      AND validated_char_start IS NOT NULL
      AND validated_char_end IS NOT NULL
      AND validated_at IS NOT NULL
    )
  );

-- Validated offsets must be non-negative and ordered.
ALTER TABLE extraction_candidate_evidence
  DROP CONSTRAINT IF EXISTS extraction_candidate_evidence_offset_order_check;
ALTER TABLE extraction_candidate_evidence
  ADD CONSTRAINT extraction_candidate_evidence_offset_order_check
  CHECK (
    (validated_char_start IS NULL OR validated_char_start >= 0)
    AND (validated_char_end IS NULL OR validated_char_end >= 0)
    AND (
      validated_char_start IS NULL
      OR validated_char_end IS NULL
      OR validated_char_end >= validated_char_start
    )
  );

-- ---------------------------------------------------------------------------
-- extraction_validation_results — check_name + status whitelists
-- ---------------------------------------------------------------------------

ALTER TABLE extraction_validation_results
  DROP CONSTRAINT IF EXISTS extraction_validation_results_check_name_check;
ALTER TABLE extraction_validation_results
  ADD CONSTRAINT extraction_validation_results_check_name_check
  CHECK (check_name IN (
    'source_exists','quote_exact_match','quote_offsets_match','source_type_valid',
    'not_duplicate','domain_valid','score_range_valid','sensitivity_gate',
    'promotion_transaction','duplicate_promotion_lock','validation_loop_circuit_breaker'
  ));

ALTER TABLE extraction_validation_results
  DROP CONSTRAINT IF EXISTS extraction_validation_results_status_check;
ALTER TABLE extraction_validation_results
  ADD CONSTRAINT extraction_validation_results_status_check
  CHECK (status IN ('pass','fail','warning','skipped','circuit_breaker'));

-- A validation result must reference either a candidate or an evidence row
-- (or both). A row that pins nothing is meaningless for audit.
ALTER TABLE extraction_validation_results
  DROP CONSTRAINT IF EXISTS extraction_validation_results_target_present_check;
ALTER TABLE extraction_validation_results
  ADD CONSTRAINT extraction_validation_results_target_present_check
  CHECK (candidate_id IS NOT NULL OR candidate_evidence_id IS NOT NULL);
