-- R3.5 — Seed the 12 top-level knowledge domains with boundary rules.
--
-- Per docs/oracle/07-knowledge-segmentation.md "Layer 1: Top-level domains".
--
-- This is the bootstrap proposal set — it represents an admin-approved
-- starting vocabulary, NOT auto-activation. The seed is idempotent (ON
-- CONFLICT DO NOTHING) so re-running migrate doesn't overwrite domain rows
-- the admin may have customized.
--
-- Boundary rules are required (R3.5 task 1) so the LLM has a stable contract
-- against which to classify claims:
--   belongs_here                   — example claims/docs/chunks that route here
--   does_not_belong_here           — neighboring-domain examples that should NOT route here
--   common_entity_hints            — typical customers, licensors, systems, etc.
--   default_excluded_document_classes — document classes to exclude from retrieval unless asked
--   neighboring_domain_ids         — domains that often overlap

BEGIN;

INSERT INTO knowledge_top_domains (
  id, name, description,
  belongs_here, does_not_belong_here, common_entity_hints,
  default_excluded_document_classes, neighboring_domain_ids,
  display_order, is_active
) VALUES
-- ────────────────────────────────────────────────────────────────────
('customer_ops', 'Customer Operations',
 'Retailer compliance, routing guides, customer-specific rules and chargeback patterns.',
 '["Burlington seasonal routing rules","TJX ticket placement requirements","Hobby Lobby chargeback patterns","Walmart EDI exception handling","Ross seasonal shipment windows"]'::jsonb,
 '["Licensor approval gates","Factory capacity planning","Internal design handoff"]'::jsonb,
 '[{"entityType":"customer","canonicalValue":"Burlington"},{"entityType":"customer","canonicalValue":"TJX"},{"entityType":"customer","canonicalValue":"Ross"},{"entityType":"customer","canonicalValue":"Hobby Lobby"},{"entityType":"customer","canonicalValue":"Walmart"}]'::jsonb,
 '["vendor_manual"]'::jsonb,
 '["logistics_shipping","import_compliance","production_lifecycle"]'::jsonb,
 10, true),

('licensing_approvals', 'Licensing & Approvals',
 'Licensor workflows, approval gates, asset usage rules, style-guide constraints, entertainment-brand requirements.',
 '["Disney style guide review steps","Marvel approval gating before tooling","Warner Bros legal sign-off windows","NBCUniversal asset usage limits","Star Wars approval document checklists"]'::jsonb,
 '["Factory capacity","Freight bookings","Generic customer routing guides","Vendor payment terms"]'::jsonb,
 '[{"entityType":"licensor","canonicalValue":"Disney"},{"entityType":"licensor","canonicalValue":"Marvel"},{"entityType":"licensor","canonicalValue":"Star Wars"},{"entityType":"licensor","canonicalValue":"NBCUniversal"},{"entityType":"licensor","canonicalValue":"Warner Bros"}]'::jsonb,
 '["vendor_manual","freight_invoice"]'::jsonb,
 '["creative_design","product_development","production_lifecycle","customer_ops"]'::jsonb,
 20, true),

('product_development', 'Product Development',
 'SKU/product-line development, concept-to-spec workflow, tech-pack handoff, sample concept gating.',
 '["Tech pack handoff requirements","SKU creation in Coldlion","Sample concept approval","Product-line briefs","Pre-production spec sign-off"]'::jsonb,
 '["Factory shipping","Customer-facing pricing","Final retailer routing"]'::jsonb,
 '[{"entityType":"system","canonicalValue":"Coldlion"},{"entityType":"system","canonicalValue":"ResourceSpace"}]'::jsonb,
 '["vendor_manual"]'::jsonb,
 '["creative_design","licensing_approvals","supply_chain","production_lifecycle"]'::jsonb,
 30, true),

('creative_design', 'Creative & Design',
 'Product design, art direction, sample creation, creative-to-technical handoff, artwork file management.',
 '["Design intent for new SKU","Artwork file delivery to tech","Color/material call-outs","Style direction for licensors","Photoshop/Illustrator file conventions"]'::jsonb,
 '["Factory production scheduling","Freight booking","Customer chargebacks"]'::jsonb,
 '[{"entityType":"system","canonicalValue":"Photoshop"},{"entityType":"system","canonicalValue":"Illustrator"},{"entityType":"system","canonicalValue":"ResourceSpace"}]'::jsonb,
 '["vendor_manual","freight_invoice"]'::jsonb,
 '["product_development","licensing_approvals","production_lifecycle"]'::jsonb,
 40, true),

('supply_chain', 'Supply Chain',
 'Overseas production, sourcing, factory relationships, China/Brazil/Colombia team coordination, capacity, lead times.',
 '["Factory capacity planning","Lead time negotiations","Tooling cost discussions","Sample production scheduling","Sourcing for new materials"]'::jsonb,
 '["Licensor brand approvals","Customer routing guides","Internal HR"]'::jsonb,
 '[{"entityType":"factory","canonicalValue":"China Factory A"},{"entityType":"geography","canonicalValue":"China"},{"entityType":"geography","canonicalValue":"Brazil"},{"entityType":"geography","canonicalValue":"Colombia"}]'::jsonb,
 '["customer_routing_guide"]'::jsonb,
 '["production_lifecycle","logistics_shipping","vendor_management","import_compliance"]'::jsonb,
 50, true),

('it_systems', 'IT & Systems',
 'ERP (Coldlion), ResourceSpace, internal tooling, integrations, automation, image upload workflows.',
 '["Coldlion image upload step","ResourceSpace sync rules","Excel template conventions","ERP field semantics","Internal script outputs"]'::jsonb,
 '["Vendor capacity","Licensor approval rounds","Customer compliance docs"]'::jsonb,
 '[{"entityType":"system","canonicalValue":"Coldlion"},{"entityType":"system","canonicalValue":"ResourceSpace"},{"entityType":"system","canonicalValue":"Supabase"}]'::jsonb,
 '["vendor_manual"]'::jsonb,
 '["creative_design","product_development","production_lifecycle"]'::jsonb,
 60, true),

('production_lifecycle', 'Production Lifecycle',
 'Sample → pre-production → production → QC → ship → RA stages, including handoff rules between them.',
 '["Sample-to-production handoff","Pre-production go/no-go","Production QC fail patterns","RA process for defective shipments","Packing-out instructions"]'::jsonb,
 '["Customer chargeback policies","Licensor style-guide updates","Vendor payment terms"]'::jsonb,
 '[{"entityType":"system","canonicalValue":"Coldlion"},{"entityType":"process_stage","canonicalValue":"sample"},{"entityType":"process_stage","canonicalValue":"production"},{"entityType":"process_stage","canonicalValue":"qc"}]'::jsonb,
 '["customer_routing_guide"]'::jsonb,
 '["supply_chain","creative_design","logistics_shipping"]'::jsonb,
 70, true),

('finance_pricing', 'Finance & Pricing',
 'Costing, margin rules, customer pricing, vendor terms, freight cost allocation.',
 '["SKU costing model","Margin floor by retailer","Vendor payment terms","Freight cost allocation rules","Pre-season pricing reviews"]'::jsonb,
 '["Licensor brand rules","Factory production scheduling","Internal HR"]'::jsonb,
 '[{"entityType":"system","canonicalValue":"QuickBooks"},{"entityType":"system","canonicalValue":"Excel"}]'::jsonb,
 '["vendor_manual"]'::jsonb,
 '["vendor_management","customer_ops","supply_chain"]'::jsonb,
 80, true),

('people_org', 'People & Org',
 'Employees, departments, roles, internal escalation paths, ownership of specific systems and workflows.',
 '["Who owns Coldlion","Who approves licensor sign-offs","Escalation when production stalls","Department roles for retailer comms","Cross-team ownership of an SKU"]'::jsonb,
 '["HR performance evaluation","Compensation","Disciplinary actions","Personal conflicts"]'::jsonb,
 '[{"entityType":"department","canonicalValue":"Design"},{"entityType":"department","canonicalValue":"Production"},{"entityType":"department","canonicalValue":"Sales"},{"entityType":"department","canonicalValue":"Sourcing"},{"entityType":"department","canonicalValue":"Licensing"}]'::jsonb,
 '[]'::jsonb,
 '["product_development","supply_chain","customer_ops"]'::jsonb,
 90, true),

('vendor_management', 'Vendor Management',
 'Non-customer vendor relationships, vendor manuals, vendor SLAs, vendor onboarding.',
 '["Vendor onboarding checklist","Vendor SLA terms","Vendor manual versions","Vendor performance reviews","Vendor escalation contacts"]'::jsonb,
 '["Licensor approvals","Customer routing guides","Internal design handoff"]'::jsonb,
 '[]'::jsonb,
 '[]'::jsonb,
 '["supply_chain","finance_pricing","logistics_shipping"]'::jsonb,
 100, true),

('logistics_shipping', 'Logistics & Shipping',
 'Freight, routing, customs paperwork, delivery to retailer DCs, EDI shipments.',
 '["Freight forwarder routing","Customer DC delivery windows","Customs paperwork prep","EDI shipment confirmations","Container booking timelines"]'::jsonb,
 '["Licensor approvals","Factory tooling","Sample QC"]'::jsonb,
 '[{"entityType":"freight_provider","canonicalValue":"Generic Freight Provider"}]'::jsonb,
 '["vendor_manual"]'::jsonb,
 '["customer_ops","import_compliance","supply_chain"]'::jsonb,
 110, true),

('import_compliance', 'Import Compliance',
 'Import paperwork, customs, tariffs, country-of-origin, regulatory constraints.',
 '["Country-of-origin labeling","Tariff classification","Customs broker workflows","CPSIA / child safety paperwork","Section 301 tariff impact"]'::jsonb,
 '["Internal design handoff","Licensor style guide","HR"]'::jsonb,
 '[{"entityType":"geography","canonicalValue":"China"},{"entityType":"service_provider","canonicalValue":"Customs Broker"}]'::jsonb,
 '["vendor_manual"]'::jsonb,
 '["logistics_shipping","supply_chain","customer_ops","finance_pricing"]'::jsonb,
 120, true)

ON CONFLICT (id) DO NOTHING;

COMMIT;
