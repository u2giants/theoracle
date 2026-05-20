-- Spec Part 8 — Admin views.
-- Per spec 7.3 these are accessed only through privileged server routes
-- (service role), so we leave them as plain views.

-- ---------------------------------------------------------------------------
-- 1. claims_with_primary_evidence (critical view, spec Part 8 verbatim)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS claims_with_primary_evidence;
CREATE VIEW claims_with_primary_evidence AS
SELECT
  c.id,
  c.summary,
  c.claim_type,
  c.status,
  c.impact_score,
  c.confidence_score,
  ce.exact_quote,
  ce.asserted_by_employee_id,
  ce.source_message_id,
  ce.source_document_chunk_id
FROM claims c
LEFT JOIN LATERAL (
  SELECT *
  FROM claim_evidence ce
  WHERE ce.claim_id = c.id
  ORDER BY ce.confidence DESC NULLS LAST, ce.created_at ASC
  LIMIT 1
) ce ON true;

-- ---------------------------------------------------------------------------
-- 2. employee_claims — claims an employee asserted via any evidence row
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS employee_claims;
CREATE VIEW employee_claims AS
SELECT DISTINCT
  ce.asserted_by_employee_id AS employee_id,
  c.id                       AS claim_id,
  c.summary,
  c.claim_type,
  c.status,
  c.impact_score,
  c.confidence_score,
  c.created_at
FROM claim_evidence ce
JOIN claims c ON c.id = ce.claim_id
WHERE ce.asserted_by_employee_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. section_claims_with_evidence — for the brain section detail page
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS section_claims_with_evidence;
CREATE VIEW section_claims_with_evidence AS
SELECT
  sc.section_id,
  c.id              AS claim_id,
  c.summary,
  c.claim_type,
  c.status,
  c.impact_score,
  c.confidence_score,
  ce.id             AS evidence_id,
  ce.source_type,
  ce.source_message_id,
  ce.source_document_chunk_id,
  ce.asserted_by_employee_id,
  ce.exact_quote,
  ce.confidence    AS evidence_confidence
FROM section_claims sc
JOIN claims c        ON c.id = sc.claim_id
LEFT JOIN claim_evidence ce ON ce.claim_id = c.id;

-- ---------------------------------------------------------------------------
-- 4. open_gaps_by_employee
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS open_gaps_by_employee;
CREATE VIEW open_gaps_by_employee AS
SELECT
  g.target_employee_id     AS employee_id,
  g.id                     AS gap_id,
  g.question_to_ask,
  g.why_it_matters,
  g.priority,
  g.status,
  g.section_id,
  g.target_department,
  g.created_at
FROM gaps g
WHERE g.status IN ('open', 'queued', 'asked');

-- ---------------------------------------------------------------------------
-- 5. claims_pending_review_with_evidence
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS claims_pending_review_with_evidence;
CREATE VIEW claims_pending_review_with_evidence AS
SELECT
  c.id,
  c.summary,
  c.claim_type,
  c.status,
  c.impact_score,
  c.confidence_score,
  c.created_at,
  ce.id   AS evidence_id,
  ce.source_type,
  ce.source_message_id,
  ce.source_document_chunk_id,
  ce.asserted_by_employee_id,
  ce.exact_quote,
  ce.confidence AS evidence_confidence
FROM claims c
LEFT JOIN claim_evidence ce ON ce.claim_id = c.id
WHERE c.status = 'pending_review';

-- ---------------------------------------------------------------------------
-- 6. latest_brain_sections
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS latest_brain_sections;
CREATE VIEW latest_brain_sections AS
SELECT
  bs.id           AS section_id,
  bs.knowledge_domain,
  bs.related_domains,
  bs.title,
  bs.category,
  bsv.id              AS version_id,
  bsv.version_number,
  bsv.markdown,
  bsv.structured_content,
  bsv.change_summary,
  bsv.review_status,
  bsv.reviewed_by_employee_id,
  bsv.reviewed_at,
  bsv.created_at       AS version_created_at,
  bs.updated_at        AS section_updated_at
FROM brain_sections bs
LEFT JOIN brain_section_versions bsv
  ON bsv.id = bs.current_version_id;

-- ---------------------------------------------------------------------------
-- 7. contradictions_with_claim_summaries
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS contradictions_with_claim_summaries;
CREATE VIEW contradictions_with_claim_summaries AS
SELECT
  ctr.id,
  ctr.status,
  ctr.severity,
  ctr.description,
  ctr.detection_confidence,
  ctr.created_at,
  ctr.resolved_at,
  ctr.claim_a_id,
  ca.summary AS claim_a_summary,
  ca.status  AS claim_a_status,
  ctr.claim_b_id,
  cb.summary AS claim_b_summary,
  cb.status  AS claim_b_status,
  ctr.suggested_question,
  ctr.assigned_gap_id,
  ctr.resolved_by_claim_id
FROM contradictions ctr
JOIN claims ca ON ca.id = ctr.claim_a_id
JOIN claims cb ON cb.id = ctr.claim_b_id;
