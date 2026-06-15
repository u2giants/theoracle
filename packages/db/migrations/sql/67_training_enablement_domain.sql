-- R3.5 follow-up — add job-training and enablement knowledge.
--
-- This keeps "how people learn to do the work" distinct from people/org
-- ownership, escalation paths, and sensitive HR performance records.
--
-- Idempotent: inserts use ON CONFLICT DO NOTHING and updates merge the
-- new domain hint into existing entities / neighboring domain lists.

BEGIN;

INSERT INTO knowledge_top_domains (
  id, name, description,
  belongs_here, does_not_belong_here, common_entity_hints,
  default_excluded_document_classes, neighboring_domain_ids,
  display_order, is_active
) VALUES (
  'training_enablement', 'Training & Enablement',
  'Role-based training, onboarding, SOP learning paths, shadowing, cross-training, skill checks, and refresher guidance for employees learning how to do their jobs.',
  '["New-hire training checklist for order entry","Role-based onboarding plan for a design coordinator","How to shadow an experienced production coordinator","SOP training for submitting licensor approvals","Cross-training plan for backup coverage","Skill check before an employee handles customer routing guides","Refresher training after a workflow changes"]'::jsonb,
  '["Org chart ownership and reporting lines","Compensation or performance evaluations","Disciplinary HR records","Personal conflicts between employees","Generic password reset instructions","Customer routing-guide rules themselves","Product approval status"]'::jsonb,
  '[{"entityType":"department","canonicalValue":"Design"},{"entityType":"department","canonicalValue":"Production"},{"entityType":"department","canonicalValue":"Sales"},{"entityType":"department","canonicalValue":"Sourcing"},{"entityType":"department","canonicalValue":"Licensing"},{"entityType":"department","canonicalValue":"Admin"},{"entityType":"process_stage","canonicalValue":"concept"},{"entityType":"process_stage","canonicalValue":"production"},{"entityType":"system","canonicalValue":"Coldlion"},{"entityType":"system","canonicalValue":"Designflow PLM"}]'::jsonb,
  '["freight_invoice","customer_routing_guide","vendor_manual"]'::jsonb,
  '["people_org","it_systems","operations_systems","product_development","production_lifecycle","customer_ops"]'::jsonb,
  95, true
)
ON CONFLICT (id) DO NOTHING;

UPDATE knowledge_top_domains
SET neighboring_domain_ids = (
  SELECT jsonb_agg(DISTINCT value ORDER BY value)
  FROM jsonb_array_elements_text(
    COALESCE(knowledge_top_domains.neighboring_domain_ids, '[]'::jsonb)
    || '["training_enablement"]'::jsonb
  ) AS t(value)
)
WHERE id IN (
  'people_org', 'it_systems', 'operations_systems',
  'product_development', 'production_lifecycle', 'customer_ops'
);

UPDATE entities
SET domain_hints = (
  SELECT jsonb_agg(DISTINCT value ORDER BY value)
  FROM jsonb_array_elements_text(
    COALESCE(entities.domain_hints, '[]'::jsonb)
    || '["training_enablement"]'::jsonb
  ) AS t(value)
)
WHERE entity_type = 'department'
  AND canonical_value IN (
    'Design', 'Licensing', 'Production', 'Sourcing',
    'Logistics', 'Sales', 'Finance', 'Admin'
  );

UPDATE entities
SET domain_hints = (
  SELECT jsonb_agg(DISTINCT value ORDER BY value)
  FROM jsonb_array_elements_text(
    COALESCE(entities.domain_hints, '[]'::jsonb)
    || '["training_enablement"]'::jsonb
  ) AS t(value)
)
WHERE entity_type = 'system'
  AND canonical_value IN ('Coldlion', 'Designflow PLM', 'Google Sheets', 'ResourceSpace');

COMMIT;
