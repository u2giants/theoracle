-- Repair plan C1: the curated business-function vocabulary. One row per
-- business function; the owner renames, merges, adds and retires on
-- /map/functions. C2's assignment tables (source_function / chunk_function /
-- entity_function) and eval_question.function will point at this vocabulary —
-- one graph, function is an attribute, never a separate database.
--
-- The seed inserts only rows whose key is missing (ON CONFLICT DO NOTHING) so
-- owner edits survive re-migration; migrate runs at every service start-up and
-- must never clobber them.
--
-- Seed evidence (clustered Department entities and department_hint values;
-- no employee names):
--   * mention names in cmap_s8_base — docs/verification/company-map/bake-off/
--     2026-11-04-stage-2-alias-pairs.json and
--     2026-11-04-stage-5-resolve-larger-sample.json
--     (Sales/Sales Team, Licensing Team/Licensed Team/license team/licensing,
--      Creative/creative team/Creative direction/creative directors,
--      Design/design team, Technical Design/technical team/tech team/Technical,
--      Production Team/production, Sourcing/sourcing,
--      China team/Sales China team, POP Creations/POP, New York office)
--   * fixture Department entities (T/test_project.py: Sample Room, Licensing;
--     zh fixtures and docs/verification/chinese/live-proof.md: 采购部)
--   * department_hint values (folder import "Licensing", interview profile
--     "Sales, account manager")
--   * oracle_master_spec.md §1.1–1.2 department labels (Design, Licensing,
--     Production / Logistics, Sales, Sourcing, Logistics, China).
-- Functions with no Department evidence yet (Compliance & Testing,
-- Finance & Accounting, IT & Systems, HR & Administration) seed with empty
-- aliases; the owner fills them on the page.

CREATE TABLE IF NOT EXISTS cmap.function (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key text NOT NULL UNIQUE,             -- stable slug; assignments reference this vocabulary
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  aliases text[] NOT NULL DEFAULT '{}', -- matched Department names / hints from the evidence
  parent_id uuid REFERENCES cmap.function(id) ON DELETE SET NULL,
  sort int NOT NULL DEFAULT 0,
  active boolean NOT NULL DEFAULT true
);

INSERT INTO cmap.function (key, name, description, aliases, sort) VALUES
  (
    'sales-customer-accounts',
    'Sales & Customer Accounts',
    'Selling to retail accounts and owning the customer relationship: buyer conversations, orders and account follow-up.',
    ARRAY['Sales', 'Sales Team', 'sales']::text[],
    10
  ),
  (
    'licensing',
    'Licensing',
    'Licensor submissions, approvals and sign-off: the licensing team''s path from concept package to licensor decision.',
    ARRAY['Licensing Team', 'Licensed Team', 'Licensed team', 'license team', 'licensing team', 'licensing']::text[],
    20
  ),
  (
    'product-design-development',
    'Product Design & Development',
    'Concept and product development: creative concept art, technical design and specifications, and design rework.',
    ARRAY['Creative', 'creative', 'creative team', 'Creative direction', 'creative directors', 'Design', 'design team', 'Technical Design', 'Technical', 'technical', 'technical team', 'tech team']::text[],
    30
  ),
  (
    'sourcing-vendor-management',
    'Sourcing & Vendor Management',
    'Vendor and factory sourcing: purchasing, vendor relationships and quote/cost work with suppliers.',
    ARRAY['Sourcing', 'sourcing', '采购部']::text[],
    40
  ),
  (
    'sampling',
    'Sampling',
    'Physical samples: sample room requests, sample reviews and sample sign-off before production.',
    ARRAY['Sample Room']::text[],
    50
  ),
  (
    'production-quality',
    'Production & Quality',
    'Production and quality: factory production runs, production follow-up and quality checks.',
    ARRAY['Production', 'Production Team', 'production', 'production team']::text[],
    60
  ),
  (
    'logistics-shipping',
    'Logistics & Shipping',
    'Logistics and shipping: booking, shipment follow-up, routing and delivery to customers.',
    ARRAY['Logistics']::text[],
    70
  ),
  (
    'compliance-testing',
    'Compliance & Testing',
    'Compliance and testing: product testing, certifications and regulatory requirements.',
    ARRAY[]::text[],
    80
  ),
  (
    'finance-accounting',
    'Finance & Accounting',
    'Finance and accounting: payments, costing, receivables and the money side of orders.',
    ARRAY[]::text[],
    90
  ),
  (
    'it-systems',
    'IT & Systems',
    'IT and systems: Coldlion ERP and the other tools the company runs on, and their limitations.',
    ARRAY[]::text[],
    100
  ),
  (
    'hr-administration',
    'HR & Administration',
    'HR and administration: people, office administration and internal company paperwork.',
    ARRAY[]::text[],
    110
  ),
  (
    'china-office-operations',
    'China Office Operations',
    'China office operations: the China team''s work across sourcing, production follow-up and samples.',
    ARRAY['China team', 'China Team', 'Sales China team']::text[],
    120
  ),
  (
    'executive-company-wide',
    'Executive/Company-wide',
    'Executive and company-wide: ownership-level decisions and rules that span every function.',
    ARRAY['POP Creations', 'POP', 'New York', 'New York office']::text[],
    130
  )
ON CONFLICT (key) DO NOTHING;
