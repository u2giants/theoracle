-- R3.5 — Backfill claim_top_domains from the legacy claim_domains table.
--
-- Maps the old `knowledge_domain` enum values (design, licensing, production,
-- etc.) onto the new `knowledge_top_domains.id` text rows seeded by
-- 16_knowledge_top_domains_seed.sql.
--
-- The legacy claim_domains table is intentionally preserved (per R3.5
-- acceptance gate) so the existing chat/admin code keeps working until R6+
-- migrates it. Drop only after the worker retrofit (a future cleanup migration).
--
-- Idempotent: ON CONFLICT DO NOTHING on the composite PK.

BEGIN;

INSERT INTO claim_top_domains (claim_id, top_domain_id, assignment_reason, assignment_confidence)
SELECT
  cd.claim_id,
  CASE cd.domain::text
    -- Direct fits.
    WHEN 'licensing'             THEN 'licensing_approvals'
    WHEN 'approvals'             THEN 'licensing_approvals'
    WHEN 'sourcing'              THEN 'supply_chain'
    WHEN 'factory_communication' THEN 'supply_chain'
    WHEN 'logistics'             THEN 'logistics_shipping'
    WHEN 'shipping_documents'    THEN 'logistics_shipping'
    WHEN 'coldlion'              THEN 'it_systems'
    WHEN 'design'                THEN 'creative_design'
    WHEN 'artwork_files'         THEN 'creative_design'
    WHEN 'sampling'              THEN 'product_development'
    WHEN 'production'            THEN 'production_lifecycle'
    WHEN 'quality_control'       THEN 'production_lifecycle'
    WHEN 'customers'             THEN 'customer_ops'
    WHEN 'sales'                 THEN 'customer_ops'
    WHEN 'retail_compliance'     THEN 'customer_ops'
    WHEN 'costing'               THEN 'finance_pricing'
    -- 'general' has no clean target. Drop to customer_ops as the
    -- best-effort residual; admin can reclassify via R10.5 admin UI.
    WHEN 'general'               THEN 'customer_ops'
    -- Defensive: should not be reachable because the enum is closed.
    ELSE 'customer_ops'
  END AS top_domain_id,
  'backfill'::varchar(50) AS assignment_reason,
  0.500::numeric(4,3) AS assignment_confidence  -- backfill is mechanical, not model-derived
FROM claim_domains cd
WHERE EXISTS (SELECT 1 FROM knowledge_top_domains)  -- only run after the seed has landed
ON CONFLICT (claim_id, top_domain_id) DO NOTHING;

COMMIT;
