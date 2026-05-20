-- Spec 6.8 — Claim Evidence source check.
-- A claim_evidence row's source columns must align with its source_type.

ALTER TABLE claim_evidence
  DROP CONSTRAINT IF EXISTS claim_evidence_source_check;

ALTER TABLE claim_evidence
  ADD CONSTRAINT claim_evidence_source_check
  CHECK (
    (source_type = 'message'         AND source_message_id         IS NOT NULL) OR
    (source_type = 'document_chunk'  AND source_document_chunk_id  IS NOT NULL) OR
    (source_type = 'external_system' AND source_external_record_id IS NOT NULL) OR
    (source_type = 'manual_admin'    AND created_by_employee_id    IS NOT NULL)
  );
