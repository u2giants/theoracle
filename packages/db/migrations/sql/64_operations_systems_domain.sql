-- R3.5 follow-up — add operations-system integration knowledge.
--
-- This keeps ERP/CRM/PLM data-flow rules distinct from generic IT support.
-- The motivating workflow is moving operational data from Google Sheets
-- (OrderList, MasterData, TaskList) into Designflow PLM.
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
  'operations_systems', 'Operations Systems',
  'Operational business systems and data flows across ERP, CRM, PLM, spreadsheets, and internal integration workflows.',
  '["Moving OrderList data from Google Sheets into Designflow PLM","Mapping MasterData fields into a PLM item master","TaskList-to-PLM workflow status integration","ERP/CRM/PLM field semantics and ownership","Spreadsheet-to-system migration rules","Data validation before importing operational records into Designflow"]'::jsonb,
  '["Generic password reset or account access troubleshooting","Adobe file naming conventions","Factory capacity planning","Customer routing-guide compliance","Licensor artwork approval decisions","Freight booking status"]'::jsonb,
  '[{"entityType":"system","canonicalValue":"Designflow PLM"},{"entityType":"system","canonicalValue":"Google Sheets"},{"entityType":"system","canonicalValue":"OrderList"},{"entityType":"system","canonicalValue":"MasterData"},{"entityType":"system","canonicalValue":"TaskList"},{"entityType":"system","canonicalValue":"Coldlion"},{"entityType":"department","canonicalValue":"Production"},{"entityType":"department","canonicalValue":"Sales"},{"entityType":"department","canonicalValue":"Admin"}]'::jsonb,
  '["vendor_manual","freight_invoice","customer_routing_guide"]'::jsonb,
  '["it_systems","product_development","production_lifecycle","customer_ops","finance_pricing"]'::jsonb,
  65, true
)
ON CONFLICT (id) DO NOTHING;

UPDATE knowledge_top_domains
SET neighboring_domain_ids = (
  SELECT jsonb_agg(DISTINCT value ORDER BY value)
  FROM jsonb_array_elements_text(
    COALESCE(knowledge_top_domains.neighboring_domain_ids, '[]'::jsonb)
    || '["operations_systems"]'::jsonb
  ) AS t(value)
)
WHERE id IN ('it_systems', 'product_development', 'production_lifecycle', 'customer_ops', 'finance_pricing');

INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('system', 'Designflow PLM', 'Designflow PLM', '["Designflow","Design Flow","PLM","Designflow system"]'::jsonb, '["operations_systems","product_development","production_lifecycle"]'::jsonb),
  ('system', 'Google Sheets', 'Google Sheets', '["Sheets","Google Sheet","spreadsheet","spreadsheets"]'::jsonb, '["operations_systems","it_systems"]'::jsonb),
  ('system', 'OrderList', 'OrderList', '["Order List","order list sheet","OrderList sheet"]'::jsonb, '["operations_systems","customer_ops","production_lifecycle"]'::jsonb),
  ('system', 'MasterData', 'MasterData', '["Master Data","master data sheet","MasterData sheet","item master"]'::jsonb, '["operations_systems","product_development","finance_pricing"]'::jsonb),
  ('system', 'TaskList', 'TaskList', '["Task List","task list sheet","TaskList sheet"]'::jsonb, '["operations_systems","production_lifecycle","people_org"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

UPDATE entities
SET domain_hints = (
  SELECT jsonb_agg(DISTINCT value ORDER BY value)
  FROM jsonb_array_elements_text(
    COALESCE(entities.domain_hints, '[]'::jsonb)
    || '["operations_systems"]'::jsonb
  ) AS t(value)
)
WHERE entity_type = 'system'
  AND canonical_value IN ('Coldlion', 'Excel');

COMMIT;
