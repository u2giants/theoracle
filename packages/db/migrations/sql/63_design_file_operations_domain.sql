-- R3.5 follow-up — split designer file-management knowledge out of
-- Creative/Product/IT workflow domains.
--
-- This file is idempotent. Existing bootstrap rows are updated only while
-- their descriptions still match the original seed text, so later admin edits
-- are not clobbered on every migrate run.

BEGIN;

INSERT INTO knowledge_top_domains (
  id, name, description,
  belongs_here, does_not_belong_here, common_entity_hints,
  default_excluded_document_classes, neighboring_domain_ids,
  display_order, is_active
) VALUES (
  'design_file_operations', 'Design File Operations',
  'Technical file-management practices for designers: naming, saving, slimming, linking, packaging, server storage, versioning, archive, and handoff file hygiene.',
  '["Designer file naming conventions","Invalid characters for server-safe filenames","How to keep Photoshop and Illustrator files from becoming bloated","Where design source/final/export files belong on the server","Linked versus embedded asset rules","Packaging artwork files for handoff","Versioning and archive cleanup for creative files"]'::jsonb,
  '["Product approval status","Design review workflow","Customer revision history","Production-stage movement","Art direction for a new SKU","Licensor approval decisions"]'::jsonb,
  '[{"entityType":"department","canonicalValue":"Design"},{"entityType":"system","canonicalValue":"Photoshop"},{"entityType":"system","canonicalValue":"Illustrator"},{"entityType":"system","canonicalValue":"ResourceSpace"},{"entityType":"system","canonicalValue":"SharePoint"}]'::jsonb,
  '["vendor_manual","freight_invoice","customer_routing_guide"]'::jsonb,
  '["creative_design","it_systems","product_development","production_lifecycle"]'::jsonb,
  45, true
)
ON CONFLICT (id) DO NOTHING;

UPDATE knowledge_top_domains
SET
  does_not_belong_here = '["Factory shipping","Customer-facing pricing","Final retailer routing","Creative file naming rules","Server folder cleanup for design files"]'::jsonb,
  neighboring_domain_ids = '["creative_design","design_file_operations","licensing_approvals","supply_chain","production_lifecycle"]'::jsonb
WHERE id = 'product_development'
  AND description = 'SKU/product-line development, concept-to-spec workflow, tech-pack handoff, sample concept gating.';

UPDATE knowledge_top_domains
SET
  description = 'Product design, art direction, sample creation, visual direction, and creative-to-technical handoff.',
  belongs_here = '["Design intent for new SKU","Color/material call-outs","Style direction for licensors","New art concept direction","Visual treatment for a product line"]'::jsonb,
  does_not_belong_here = '["Factory production scheduling","Freight booking","Customer chargebacks","File naming conventions","How to reduce Photoshop file size","Server folder organization"]'::jsonb,
  neighboring_domain_ids = '["product_development","design_file_operations","licensing_approvals","production_lifecycle"]'::jsonb
WHERE id = 'creative_design'
  AND description = 'Product design, art direction, sample creation, creative-to-technical handoff, artwork file management.';

UPDATE knowledge_top_domains
SET
  description = 'ERP (Coldlion), ResourceSpace, internal tooling, integrations, automation, permissions, accounts, and system administration.',
  belongs_here = '["Coldlion image upload step","ResourceSpace sync rules","Excel template conventions","ERP field semantics","Internal script outputs","SharePoint permission troubleshooting"]'::jsonb,
  does_not_belong_here = '["Vendor capacity","Licensor approval rounds","Customer compliance docs","Design file naming conventions","How to package Illustrator files for handoff"]'::jsonb,
  neighboring_domain_ids = '["design_file_operations","creative_design","product_development","production_lifecycle"]'::jsonb
WHERE id = 'it_systems'
  AND description = 'ERP (Coldlion), ResourceSpace, internal tooling, integrations, automation, image upload workflows.';

INSERT INTO claim_top_domains (
  claim_id, top_domain_id, assignment_reason, assignment_confidence
)
SELECT cd.claim_id, 'design_file_operations', 'backfill', 0.95
FROM claim_domains cd
WHERE cd.domain::text = 'artwork_files'
  AND EXISTS (
    SELECT 1 FROM knowledge_top_domains
    WHERE id = 'design_file_operations'
      AND is_active = true
  )
ON CONFLICT (claim_id, top_domain_id) DO NOTHING;

INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('system', 'SharePoint', 'Microsoft SharePoint', '["Sharepoint","SP","Microsoft Sharepoint"]'::jsonb, '["it_systems","design_file_operations"]'::jsonb),
  ('system', 'InDesign', 'Adobe InDesign', '["INDD","IDML","Adobe ID"]'::jsonb, '["creative_design","design_file_operations"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

UPDATE entities
SET domain_hints = (
  SELECT jsonb_agg(DISTINCT value)
  FROM jsonb_array_elements_text(COALESCE(entities.domain_hints, '[]'::jsonb) || '["design_file_operations"]'::jsonb) AS t(value)
)
WHERE entity_type = 'system'
  AND canonical_value IN ('Photoshop', 'Illustrator', 'Google Drive');

DELETE FROM claim_top_domains ctd
WHERE ctd.top_domain_id = 'creative_design'
  AND ctd.assignment_reason = 'backfill'
  AND EXISTS (
    SELECT 1
    FROM claim_domains cd
    WHERE cd.claim_id = ctd.claim_id
      AND cd.domain::text = 'artwork_files'
  )
  AND NOT EXISTS (
    SELECT 1
    FROM claim_domains cd
    WHERE cd.claim_id = ctd.claim_id
      AND cd.domain::text = 'design'
  );

COMMIT;
