/**
 * R6 — Legacy → top-level-domain mapping.
 *
 * The existing claim-extraction prompt still asks the model for
 * `KNOWLEDGE_DOMAINS` values (the pre-retrofit enum: design, licensing,
 * production, sourcing, etc.). The new candidate-before-claim pipeline
 * expects `TOP_LEVEL_DOMAINS` ids (customer_ops, licensing_approvals,
 * product_development, etc.).
 *
 * Until R5.5's extraction-prompt rewrite lands (a separate prompt-engineering
 * pass with its own evals), the R6 worker uses this deterministic mapping
 * to translate the model output into top-domain IDs that satisfy the
 * taxonomy validator.
 *
 * This started as the same mapping as
 * `migrations/sql/42_claim_top_domains_backfill.sql`. Later domain splits
 * are applied through follow-up SQL migrations (for example, `63_...`) and
 * reflected here for future extraction output.
 */

import type { KnowledgeDomain, TopLevelDomainId } from '@oracle/shared';

const LEGACY_TO_TOP_DOMAIN: Record<KnowledgeDomain, TopLevelDomainId> = {
  // Direct fits.
  licensing: 'licensing_approvals',
  approvals: 'licensing_approvals',
  sourcing: 'supply_chain',
  factory_communication: 'supply_chain',
  logistics: 'logistics_shipping',
  shipping_documents: 'logistics_shipping',
  coldlion: 'it_systems',
  design: 'creative_design',
  artwork_files: 'design_file_operations',
  sampling: 'product_development',
  production: 'production_lifecycle',
  quality_control: 'production_lifecycle',
  customers: 'customer_ops',
  sales: 'customer_ops',
  retail_compliance: 'customer_ops',
  costing: 'finance_pricing',
  // 'general' has no clean target — drop to customer_ops as the best-effort
  // residual; admin can reclassify via R10.5 admin UI.
  general: 'customer_ops',
};

/**
 * Map a legacy knowledge-domain value to a top-level-domain ID.
 * Returns the residual `customer_ops` if the input is unrecognized — that
 * matches the backfill SQL's behavior.
 */
export function mapLegacyDomainToTopDomain(domain: KnowledgeDomain): TopLevelDomainId {
  return LEGACY_TO_TOP_DOMAIN[domain] ?? 'customer_ops';
}

/**
 * Map a set of legacy knowledge-domain values to a unique set of top-level-
 * domain IDs (preserves declaration order; deduplicates collisions).
 */
export function mapLegacyDomainsToTopDomains(domains: KnowledgeDomain[]): TopLevelDomainId[] {
  const seen = new Set<TopLevelDomainId>();
  const out: TopLevelDomainId[] = [];
  for (const d of domains) {
    const top = mapLegacyDomainToTopDomain(d);
    if (!seen.has(top)) {
      seen.add(top);
      out.push(top);
    }
  }
  return out;
}
