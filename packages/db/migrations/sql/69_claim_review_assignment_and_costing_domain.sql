-- Claim-review follow-ups:
-- 1. Allow review events to record that a reviewer assigned a follow-up
--    question to another employee.
-- 2. Rename/rebound finance_pricing so it means product costing/pricing, not
--    company finance/accounting.

BEGIN;

ALTER TABLE claim_review_events
  DROP CONSTRAINT IF EXISTS claim_review_events_action_check;

ALTER TABLE claim_review_events
  ADD CONSTRAINT claim_review_events_action_check
  CHECK (action IN ('approve', 'reject', 'revise', 'assign_question'));

UPDATE knowledge_top_domains
SET
  name = 'Product Costing & Pricing',
  description = 'Product costing sheets, SKU cost build-up, customer product pricing, margin assumptions, factory quote inputs, and costing handoffs. Company finance/accounting is out of scope.',
  belongs_here = '["Costing sheet fields for a SKU","Factory quote inputs used in product costing","Margin assumptions for customer product pricing","Design-to-factory costing handoff","Pre-season product pricing reviews"]'::jsonb,
  does_not_belong_here = '["Company P&L","Payroll","Accounts payable","Accounts receivable aging","Corporate budgeting","Licensor brand rules","Factory production scheduling"]'::jsonb,
  common_entity_hints = '[{"entityType":"system","canonicalValue":"Excel"},{"entityType":"department","canonicalValue":"Design"},{"entityType":"department","canonicalValue":"Production"},{"entityType":"factory","canonicalValue":"China Factory A"}]'::jsonb,
  neighboring_domain_ids = '["product_development","creative_design","supply_chain","production_lifecycle","vendor_management","customer_ops"]'::jsonb,
  updated_at = now()
WHERE id = 'finance_pricing';

COMMIT;
