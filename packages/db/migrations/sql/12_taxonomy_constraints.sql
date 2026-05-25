-- R3.5 taxonomy CHECK constraints.
--
-- Drizzle generates table DDL only — value whitelists live here. These guard
-- every taxonomy table at the DB level so background workers, admin SQL, and
-- any future non-TypeScript integration get the same invariants.
--
-- Idempotent: every constraint uses DROP CONSTRAINT IF EXISTS first.

-- ---------------------------------------------------------------------------
-- knowledge_sub_topics — review_status whitelist
-- ---------------------------------------------------------------------------

ALTER TABLE knowledge_sub_topics
  DROP CONSTRAINT IF EXISTS knowledge_sub_topics_review_status_check;
ALTER TABLE knowledge_sub_topics
  ADD CONSTRAINT knowledge_sub_topics_review_status_check
  CHECK (review_status IN ('proposed','approved','merged','split','retired'));

ALTER TABLE knowledge_sub_topics
  DROP CONSTRAINT IF EXISTS knowledge_sub_topics_member_count_check;
ALTER TABLE knowledge_sub_topics
  ADD CONSTRAINT knowledge_sub_topics_member_count_check
  CHECK (member_count >= 0);

-- ---------------------------------------------------------------------------
-- *_top_domains assignment_reason whitelist + confidence range
-- ---------------------------------------------------------------------------

-- claims  (model produced it via extraction, or admin / reclassification / backfill set it)
ALTER TABLE claim_top_domains
  DROP CONSTRAINT IF EXISTS claim_top_domains_assignment_reason_check;
ALTER TABLE claim_top_domains
  ADD CONSTRAINT claim_top_domains_assignment_reason_check
  CHECK (assignment_reason IN ('extraction','ingestion','reclassification','manual','backfill'));

ALTER TABLE claim_top_domains
  DROP CONSTRAINT IF EXISTS claim_top_domains_confidence_range_check;
ALTER TABLE claim_top_domains
  ADD CONSTRAINT claim_top_domains_confidence_range_check
  CHECK (assignment_confidence IS NULL OR (assignment_confidence >= 0 AND assignment_confidence <= 1));

-- documents (ingestion / reclassification / manual)
ALTER TABLE document_top_domains
  DROP CONSTRAINT IF EXISTS document_top_domains_assignment_reason_check;
ALTER TABLE document_top_domains
  ADD CONSTRAINT document_top_domains_assignment_reason_check
  CHECK (assignment_reason IN ('ingestion','reclassification','manual'));

ALTER TABLE document_top_domains
  DROP CONSTRAINT IF EXISTS document_top_domains_confidence_range_check;
ALTER TABLE document_top_domains
  ADD CONSTRAINT document_top_domains_confidence_range_check
  CHECK (assignment_confidence IS NULL OR (assignment_confidence >= 0 AND assignment_confidence <= 1));

-- document chunks
ALTER TABLE document_chunk_top_domains
  DROP CONSTRAINT IF EXISTS document_chunk_top_domains_assignment_reason_check;
ALTER TABLE document_chunk_top_domains
  ADD CONSTRAINT document_chunk_top_domains_assignment_reason_check
  CHECK (assignment_reason IN ('ingestion','reclassification','manual'));

ALTER TABLE document_chunk_top_domains
  DROP CONSTRAINT IF EXISTS document_chunk_top_domains_confidence_range_check;
ALTER TABLE document_chunk_top_domains
  ADD CONSTRAINT document_chunk_top_domains_confidence_range_check
  CHECK (assignment_confidence IS NULL OR (assignment_confidence >= 0 AND assignment_confidence <= 1));

-- messages (extraction / reclassification / manual)
ALTER TABLE message_top_domains
  DROP CONSTRAINT IF EXISTS message_top_domains_assignment_reason_check;
ALTER TABLE message_top_domains
  ADD CONSTRAINT message_top_domains_assignment_reason_check
  CHECK (assignment_reason IN ('extraction','reclassification','manual'));

ALTER TABLE message_top_domains
  DROP CONSTRAINT IF EXISTS message_top_domains_confidence_range_check;
ALTER TABLE message_top_domains
  ADD CONSTRAINT message_top_domains_confidence_range_check
  CHECK (assignment_confidence IS NULL OR (assignment_confidence >= 0 AND assignment_confidence <= 1));

-- claim_sub_topics
ALTER TABLE claim_sub_topics
  DROP CONSTRAINT IF EXISTS claim_sub_topics_assignment_reason_check;
ALTER TABLE claim_sub_topics
  ADD CONSTRAINT claim_sub_topics_assignment_reason_check
  CHECK (assignment_reason IN ('extraction','reclassification','manual'));

ALTER TABLE claim_sub_topics
  DROP CONSTRAINT IF EXISTS claim_sub_topics_confidence_range_check;
ALTER TABLE claim_sub_topics
  ADD CONSTRAINT claim_sub_topics_confidence_range_check
  CHECK (assignment_confidence IS NULL OR (assignment_confidence >= 0 AND assignment_confidence <= 1));

-- ---------------------------------------------------------------------------
-- entities.entity_type whitelist
--   licensor is a first-class type distinct from vendor. The operating-vendor
--   subtypes are also enumerated so the constraint catches anyone trying to
--   create a generic 'vendor' row when a more specific type fits.
-- ---------------------------------------------------------------------------

ALTER TABLE entities
  DROP CONSTRAINT IF EXISTS entities_entity_type_check;
ALTER TABLE entities
  ADD CONSTRAINT entities_entity_type_check
  CHECK (entity_type IN (
    'system','customer','licensor',
    'factory','freight_provider','testing_lab','packaging_supplier','service_provider',
    'vendor',
    'person','sku_or_product_line','process_stage','department','geography','document_class'
  ));

-- ---------------------------------------------------------------------------
-- taxonomy_proposals — proposal_type + status whitelists
-- ---------------------------------------------------------------------------

ALTER TABLE taxonomy_proposals
  DROP CONSTRAINT IF EXISTS taxonomy_proposals_proposal_type_check;
ALTER TABLE taxonomy_proposals
  ADD CONSTRAINT taxonomy_proposals_proposal_type_check
  CHECK (proposal_type IN (
    'create_top_domain','merge_top_domains','split_top_domain',
    'create_sub_topic','merge_sub_topics','split_sub_topic',
    'reassign_claims','retire_sub_topic'
  ));

ALTER TABLE taxonomy_proposals
  DROP CONSTRAINT IF EXISTS taxonomy_proposals_status_check;
ALTER TABLE taxonomy_proposals
  ADD CONSTRAINT taxonomy_proposals_status_check
  CHECK (status IN ('pending','approved','rejected'));

-- An approved or rejected proposal must record who reviewed it and when.
ALTER TABLE taxonomy_proposals
  DROP CONSTRAINT IF EXISTS taxonomy_proposals_reviewed_consistency_check;
ALTER TABLE taxonomy_proposals
  ADD CONSTRAINT taxonomy_proposals_reviewed_consistency_check
  CHECK (
    (status = 'pending' AND reviewed_at IS NULL AND reviewed_by_employee_id IS NULL)
    OR (status <> 'pending' AND reviewed_at IS NOT NULL AND reviewed_by_employee_id IS NOT NULL)
  );

-- ---------------------------------------------------------------------------
-- entity_proposals — source type + status whitelists
-- ---------------------------------------------------------------------------

ALTER TABLE entity_proposals
  DROP CONSTRAINT IF EXISTS entity_proposals_observed_in_source_type_check;
ALTER TABLE entity_proposals
  ADD CONSTRAINT entity_proposals_observed_in_source_type_check
  CHECK (observed_in_source_type IN ('claim_candidate','document_chunk','message'));

ALTER TABLE entity_proposals
  DROP CONSTRAINT IF EXISTS entity_proposals_status_check;
ALTER TABLE entity_proposals
  ADD CONSTRAINT entity_proposals_status_check
  CHECK (status IN ('pending','approved','rejected','merged_into_existing'));

-- The proposed entity_type must be in the same whitelist as entities.entity_type
-- so a future approval can land directly.
ALTER TABLE entity_proposals
  DROP CONSTRAINT IF EXISTS entity_proposals_entity_type_check;
ALTER TABLE entity_proposals
  ADD CONSTRAINT entity_proposals_entity_type_check
  CHECK (proposed_entity_type IN (
    'system','customer','licensor',
    'factory','freight_provider','testing_lab','packaging_supplier','service_provider',
    'vendor',
    'person','sku_or_product_line','process_stage','department','geography','document_class'
  ));

-- merged_into_existing implies a non-null merge target.
ALTER TABLE entity_proposals
  DROP CONSTRAINT IF EXISTS entity_proposals_merge_consistency_check;
ALTER TABLE entity_proposals
  ADD CONSTRAINT entity_proposals_merge_consistency_check
  CHECK (
    (status <> 'merged_into_existing' AND merged_into_entity_id IS NULL)
    OR (status = 'merged_into_existing' AND merged_into_entity_id IS NOT NULL)
  );
