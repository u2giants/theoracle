-- R3.5 — Seed the canonical entity registry.
--
-- Per docs/oracle/07-knowledge-segmentation.md "Layer 3" + the new
-- licensor-vs-vendor and operating-vendor-subtype rules from the recent
-- doc additions.
--
-- This seed is idempotent (ON CONFLICT DO NOTHING on the (entity_type,
-- canonical_value) unique index). Adding aliases or domain_hints to an
-- existing entity is intentionally NOT done here — it would clobber admin
-- edits. Admin UI / R10.5 is responsible for editing those.

BEGIN;

-- ────────────────────────────────────────────────────────────────────────
-- Customers — retailers explicitly named in the master spec Part 1.1.
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('customer', 'Burlington',   'Burlington',   '["Burlington Coat Factory","BCF"]'::jsonb,  '["customer_ops","logistics_shipping"]'::jsonb),
  ('customer', 'TJX',          'TJX',          '["TJ Maxx","TJ Max","Marshalls","HomeGoods","Homesense"]'::jsonb, '["customer_ops","logistics_shipping"]'::jsonb),
  ('customer', 'Ross',         'Ross',         '["Ross Stores","Ross Dress for Less"]'::jsonb, '["customer_ops","logistics_shipping"]'::jsonb),
  ('customer', 'Hobby Lobby',  'Hobby Lobby',  '[]'::jsonb, '["customer_ops","logistics_shipping"]'::jsonb),
  ('customer', 'Walmart',      'Walmart',      '["Wal-Mart","WMT"]'::jsonb, '["customer_ops","logistics_shipping"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- Licensors — entertainment/IP rights holders. FIRST-CLASS type distinct
-- from vendor. These are POP Creations' core licensors.
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('licensor', 'Disney',        'Disney',         '["Walt Disney","The Walt Disney Company","DLG","WDC"]'::jsonb, '["licensing_approvals","creative_design","product_development"]'::jsonb),
  ('licensor', 'Marvel',        'Marvel',         '["Marvel Entertainment","Marvel Studios"]'::jsonb, '["licensing_approvals","creative_design","product_development"]'::jsonb),
  ('licensor', 'Star Wars',     'Star Wars',      '["Lucasfilm","Star Wars / Lucasfilm"]'::jsonb, '["licensing_approvals","creative_design","product_development"]'::jsonb),
  ('licensor', 'NBCUniversal',  'NBCUniversal',   '["NBCU","NBC Universal","Universal Studios"]'::jsonb, '["licensing_approvals","creative_design","product_development"]'::jsonb),
  ('licensor', 'Warner Bros',   'Warner Bros.',   '["WB","Warner Brothers","WBD","Warner Bros. Discovery"]'::jsonb, '["licensing_approvals","creative_design","product_development"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- Systems — internal and external software systems referenced operationally.
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('system', 'Coldlion',       'Coldlion (ERP)',   '["the ERP","ERP","Coldlion ERP","CL"]'::jsonb, '["it_systems","production_lifecycle","product_development"]'::jsonb),
  ('system', 'ResourceSpace',  'ResourceSpace',    '["RS","Resource Space"]'::jsonb, '["creative_design","licensing_approvals","it_systems"]'::jsonb),
  ('system', 'Supabase',       'Supabase',         '["Supa","supabase.io"]'::jsonb, '["it_systems"]'::jsonb),
  ('system', 'Photoshop',      'Adobe Photoshop',  '["PSD","PS","Adobe PS"]'::jsonb, '["creative_design","design_file_operations"]'::jsonb),
  ('system', 'Illustrator',    'Adobe Illustrator','["AI","Ai","Adobe AI"]'::jsonb, '["creative_design","design_file_operations"]'::jsonb),
  ('system', 'InDesign',       'Adobe InDesign',   '["INDD","IDML","Adobe ID"]'::jsonb, '["creative_design","design_file_operations"]'::jsonb),
  ('system', 'Excel',          'Microsoft Excel',  '["XLS","XLSX","spreadsheet"]'::jsonb, '["finance_pricing","it_systems"]'::jsonb),
  ('system', 'Google Drive',   'Google Drive',     '["GDrive","drive"]'::jsonb, '["it_systems","design_file_operations"]'::jsonb),
  ('system', 'SharePoint',     'Microsoft SharePoint','["Sharepoint","SP","Microsoft Sharepoint"]'::jsonb, '["it_systems","design_file_operations"]'::jsonb),
  ('system', 'WhatsApp',       'WhatsApp',         '[]'::jsonb, '["it_systems","supply_chain"]'::jsonb),
  ('system', 'WeChat',         'WeChat',           '[]'::jsonb, '["it_systems","supply_chain"]'::jsonb),
  ('system', 'Email',          'Email',            '[]'::jsonb, '["it_systems"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- Departments — used by the people_org domain and by retrieval scoping.
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('department', 'Design',     'Design',     '["Creative","Creative Design"]'::jsonb, '["creative_design","product_development"]'::jsonb),
  ('department', 'Licensing',  'Licensing',  '[]'::jsonb, '["licensing_approvals"]'::jsonb),
  ('department', 'Production', 'Production', '["Ops","Production/Ops"]'::jsonb, '["production_lifecycle","supply_chain"]'::jsonb),
  ('department', 'Sourcing',   'Sourcing',   '[]'::jsonb, '["supply_chain"]'::jsonb),
  ('department', 'Logistics',  'Logistics',  '["Shipping"]'::jsonb, '["logistics_shipping"]'::jsonb),
  ('department', 'Sales',      'Sales',      '[]'::jsonb, '["customer_ops","finance_pricing"]'::jsonb),
  ('department', 'Finance',    'Finance',    '["Accounting"]'::jsonb, '["finance_pricing"]'::jsonb),
  ('department', 'Admin',      'Admin',      '["Administration"]'::jsonb, '["it_systems"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- Geographies — origin/team countries explicitly named in the master spec.
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('geography', 'United States','United States', '["US","USA","U.S."]'::jsonb, '["customer_ops","logistics_shipping","finance_pricing"]'::jsonb),
  ('geography', 'China',        'China',         '["PRC","Mainland China"]'::jsonb, '["supply_chain","production_lifecycle","import_compliance"]'::jsonb),
  ('geography', 'Brazil',       'Brazil',        '[]'::jsonb, '["creative_design","supply_chain"]'::jsonb),
  ('geography', 'Colombia',     'Colombia',      '[]'::jsonb, '["creative_design","supply_chain","licensing_approvals"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- Process stages — production lifecycle.
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('process_stage', 'concept',        'Concept',         '[]'::jsonb, '["product_development","creative_design"]'::jsonb),
  ('process_stage', 'design',         'Design',          '[]'::jsonb, '["creative_design","product_development"]'::jsonb),
  ('process_stage', 'licensor_approval','Licensor Approval','[]'::jsonb, '["licensing_approvals"]'::jsonb),
  ('process_stage', 'customer_approval','Customer Approval','[]'::jsonb, '["customer_ops"]'::jsonb),
  ('process_stage', 'costing',        'Costing',         '[]'::jsonb, '["finance_pricing"]'::jsonb),
  ('process_stage', 'sourcing',       'Sourcing',        '[]'::jsonb, '["supply_chain"]'::jsonb),
  ('process_stage', 'sample',         'Sample',          '["sample request","sample review"]'::jsonb, '["product_development","supply_chain","production_lifecycle"]'::jsonb),
  ('process_stage', 'pre_production', 'Pre-production',  '["pre-production","pp"]'::jsonb, '["production_lifecycle","supply_chain"]'::jsonb),
  ('process_stage', 'production',     'Production',      '[]'::jsonb, '["production_lifecycle","supply_chain"]'::jsonb),
  ('process_stage', 'qc',             'Quality Control', '["quality control"]'::jsonb, '["production_lifecycle"]'::jsonb),
  ('process_stage', 'pack',           'Packing',         '["packaging"]'::jsonb, '["production_lifecycle","logistics_shipping"]'::jsonb),
  ('process_stage', 'ship',           'Shipping',        '["shipment"]'::jsonb, '["logistics_shipping"]'::jsonb),
  ('process_stage', 'ra',             'Returns/RA',      '["return authorization"]'::jsonb, '["customer_ops","logistics_shipping"]'::jsonb),
  ('process_stage', 'post_sale',      'Post-sale',       '["post sale"]'::jsonb, '["customer_ops"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

-- ────────────────────────────────────────────────────────────────────────
-- Document classes — used by retrieval-plan exclusions.
-- ────────────────────────────────────────────────────────────────────────
INSERT INTO entities (entity_type, canonical_value, display_label, aliases, domain_hints) VALUES
  ('document_class', 'routing_guide',  'Routing Guide',    '[]'::jsonb, '["customer_ops"]'::jsonb),
  ('document_class', 'contract',       'Contract',         '[]'::jsonb, '["licensing_approvals","finance_pricing"]'::jsonb),
  ('document_class', 'sample_spec',    'Sample Spec',      '["tech pack"]'::jsonb, '["product_development","creative_design"]'::jsonb),
  ('document_class', 'email_thread',   'Email Thread',     '[]'::jsonb, '[]'::jsonb),
  ('document_class', 'screenshot',     'Screenshot',       '[]'::jsonb, '["it_systems"]'::jsonb),
  ('document_class', 'vendor_manual',  'Vendor Manual',    '[]'::jsonb, '["vendor_management","supply_chain"]'::jsonb),
  ('document_class', 'internal_sop',   'Internal SOP',     '["SOP"]'::jsonb, '[]'::jsonb),
  ('document_class', 'voice_memo',     'Voice Memo',       '[]'::jsonb, '[]'::jsonb),
  ('document_class', 'freight_invoice','Freight Invoice',  '[]'::jsonb, '["logistics_shipping","finance_pricing"]'::jsonb),
  ('document_class', 'customer_routing_guide','Customer Routing Guide','[]'::jsonb, '["customer_ops","logistics_shipping"]'::jsonb)
ON CONFLICT (entity_type, canonical_value) DO NOTHING;

COMMIT;
