-- R3.5 follow-up — add a cross-functional business-process domain.
--
-- This domain is for end-to-end company workflows and "how the business works"
-- explanations that span departments. Department-specific process details still
-- belong in their narrower domains too; this row lets broad process docs and
-- broad user questions retrieve the overview without forcing everything into
-- Customer Operations.

BEGIN;

INSERT INTO knowledge_top_domains (
  id, name, description,
  belongs_here, does_not_belong_here, common_entity_hints,
  default_excluded_document_classes, neighboring_domain_ids,
  display_order, is_active
) VALUES (
  'business_process', 'Business Process',
  'End-to-end company workflows, cross-functional handoffs, operating model overviews, and explanations of how work moves across departments.',
  '["Company-wide business process overview","Order-to-ship workflow across Sales, Licensing, Design, Production, Sourcing, Logistics, and Finance","Cross-functional handoff map between departments","How a product moves from customer request through licensor approval, design, production, and shipping","Overall operating model and process-flow explanation"]'::jsonb,
  '["A single retailer routing-guide rule","A single licensor style-guide constraint","Generic password reset instructions","Adobe file naming conventions","A standalone freight invoice","A single vendor payment term with no workflow context"]'::jsonb,
  '[{"entityType":"department","canonicalValue":"Sales"},{"entityType":"department","canonicalValue":"Licensing"},{"entityType":"department","canonicalValue":"Design"},{"entityType":"department","canonicalValue":"Production"},{"entityType":"department","canonicalValue":"Sourcing"},{"entityType":"department","canonicalValue":"Logistics"},{"entityType":"department","canonicalValue":"Operations"},{"entityType":"department","canonicalValue":"Finance"}]'::jsonb,
  '["vendor_manual","freight_invoice"]'::jsonb,
  '["licensing_approvals","product_development","creative_design","supply_chain","operations_systems","production_lifecycle","customer_ops","logistics_shipping","finance_pricing","people_org"]'::jsonb,
  5, true
)
ON CONFLICT (id) DO NOTHING;

UPDATE knowledge_top_domains
SET neighboring_domain_ids = (
  SELECT jsonb_agg(DISTINCT value ORDER BY value)
  FROM jsonb_array_elements_text(
    COALESCE(knowledge_top_domains.neighboring_domain_ids, '[]'::jsonb)
    || '["business_process"]'::jsonb
  ) AS t(value)
)
WHERE id IN (
  'licensing_approvals',
  'product_development',
  'creative_design',
  'supply_chain',
  'operations_systems',
  'production_lifecycle',
  'customer_ops',
  'logistics_shipping',
  'finance_pricing',
  'people_org'
);

UPDATE entities
SET domain_hints = (
  SELECT jsonb_agg(DISTINCT value ORDER BY value)
  FROM jsonb_array_elements_text(
    COALESCE(entities.domain_hints, '[]'::jsonb)
    || '["business_process"]'::jsonb
  ) AS t(value)
)
WHERE entity_type = 'department'
  AND canonical_value IN (
    'Sales',
    'Licensing',
    'Design',
    'Production',
    'Sourcing',
    'Logistics',
    'Operations',
    'Administrative',
    'Management'
  );

COMMIT;
