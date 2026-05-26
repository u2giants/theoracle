// RetrievalPlan — spec docs/oracle/07-knowledge-segmentation.md §"What this does to retrieval code".
//
// Every query to the Oracle knowledge graph MUST go through a RetrievalPlan.
// Global vector search without metadata pre-filtering is forbidden (spec rule from
// 00-buildout-index.md "Retrieval rule" and 07-knowledge-segmentation.md).
//
// This module provides:
//   - The RetrievalPlan type (matches the spec shape exactly).
//   - buildRetrievalPlanFromQuery() — a lightweight synchronous heuristic builder
//     that maps a natural-language query to topDomainHints, exclusion rules, and
//     timeFilter WITHOUT a model call. Callers may pass explicit overrides.
//
// A model-backed variant (buildRetrievalPlanWithModel) can be added later when
// per-query latency budgets allow an extra cheap structured-output call.
// For now the heuristics are good enough for the production retrieval gate.

export type RetrievalPlan = {
  /** Up to 3 top-level domain IDs from knowledge_top_domains. Empty = search all. */
  topDomainHints: string[];
  /** Entity references the query is about; matched against canonical entity registry. */
  requiredEntities: { entityType: string; canonicalValue: string }[];
  /** Document classes to exclude from the candidate set (e.g. vendor_manual for system questions). */
  excludedDocumentClasses?: string[];
  /** Entity types whose presence in a claim should down-rank or exclude it. */
  excludedEntityTypes?: string[];
  /** Top-level domain IDs to exclude from the search. */
  excludedTopDomains?: string[];
  /** Process stage hints for narrowing retrieval to a specific lifecycle stage. */
  processStageHints?: string[];
  /**
   * Time validity filter.
   *   'current' — only claims whose effective_until IS NULL (still in force).
   *   'all'     — no time filter.
   *   'since:YYYY-MM-DD' — claims effective after a given date.
   */
  timeFilter?: 'current' | 'all' | `since:${string}`;
  /** The actual semantic query string sent to the embedding + tsvector search. */
  vectorQuery: string;
  /** Maximum number of results to return. */
  topK: number;
};

export const DEFAULT_TOP_K = 8;

// ---------------------------------------------------------------------------
// Domain-hint heuristics.
// Keyword groups that map query text to top-level domain IDs.
// These domain IDs MUST match the `id` column in knowledge_top_domains
// (seeded in packages/db/migrations/sql/16_knowledge_top_domains_seed.sql).
// ---------------------------------------------------------------------------

const DOMAIN_KEYWORDS: Array<{ domainId: string; keywords: string[] }> = [
  {
    domainId: 'it_systems',
    keywords: [
      'erp', 'coldlion', 'resourcespace', 'system', 'software', 'tool',
      'upload', 'sync', 'database', 'export', 'import', 'integration',
      'api', 'automat',
    ],
  },
  {
    domainId: 'licensing_approvals',
    keywords: [
      'disney', 'marvel', 'star wars', 'lucasfilm', 'warner bros', 'nbcuniversal',
      'licensor', 'license', 'licens', 'approval', 'approve', 'style guide',
      'artwork approval', 'licensed', 'ip right', 'brand approval',
    ],
  },
  {
    domainId: 'customer_ops',
    keywords: [
      'burlington', 'tjx', 'ross', 'hobby lobby', 'walmart', 'customer',
      'retailer', 'routing guide', 'chargeback', 'edi', 'compliance',
      'buyer', 'dc ', 'distribution center',
    ],
  },
  {
    domainId: 'supply_chain',
    keywords: [
      'factory', 'china', 'manufacturing', 'overseas', 'lead time',
      'capacity', 'sourcing', 'vendor', 'supplier', 'production order',
      'brazil', 'colombia',
    ],
  },
  {
    domainId: 'logistics_shipping',
    keywords: [
      'freight', 'ship', 'shipping', 'customs', 'delivery', 'routing',
      'transit', 'warehouse', 'distribution', '3pl', 'container',
      'booking', 'forwarder',
    ],
  },
  {
    domainId: 'product_development',
    keywords: [
      'design', 'sku', 'sample', 'artwork', 'creative', 'product line',
      'concept', 'proto', 'prototype', 'spec sheet', 'product spec',
    ],
  },
  {
    domainId: 'production_lifecycle',
    keywords: [
      'pre-production', 'pre production', 'preproduction', 'production stage',
      'qc', 'quality', 'pack', 'packing', 'stage', 'lifecycle', 'ra ',
      'returns', 'post-sale',
    ],
  },
  {
    domainId: 'import_compliance',
    keywords: [
      'import', 'tariff', 'duty', 'country of origin', 'hts', 'customs clearance',
      'regulatory', 'cbp', 'dhl', 'ftz',
    ],
  },
  {
    domainId: 'finance_pricing',
    keywords: [
      'cost', 'price', 'margin', 'costing', 'vendor terms', 'finance',
      'payment', 'invoice', 'budget', 'markup',
    ],
  },
  {
    domainId: 'people_org',
    keywords: [
      'employee', 'team', 'department', 'who handles', 'who is responsible',
      'escalat', 'manager', 'ownership', 'role',
    ],
  },
];

// Entity type exclusion hints — inferred from query content.
const ENTITY_EXCLUSION_HINTS: Array<{ keywords: string[]; excludeEntityTypes: string[] }> = [
  {
    // Licensor questions → exclude generic vendors and factories from results.
    keywords: ['disney', 'marvel', 'star wars', 'lucasfilm', 'warner bros', 'nbcuniversal', 'licensor', 'licens'],
    excludeEntityTypes: ['vendor', 'factory', 'freight_provider'],
  },
  {
    // IT system questions → exclude licensor + vendor from results.
    keywords: ['erp', 'coldlion', 'system', 'software', 'tool'],
    excludeEntityTypes: ['licensor', 'vendor'],
  },
];

// Document class exclusion hints — inferred from query content.
const DOCUMENT_CLASS_EXCLUSIONS: Array<{ keywords: string[]; excludeClasses: string[] }> = [
  {
    // IT system questions should not pull vendor manuals.
    keywords: ['erp', 'coldlion', 'system', 'software', 'tool', 'upload', 'sync'],
    excludeClasses: ['vendor_manual'],
  },
  {
    // Licensing questions should not pull vendor manuals or generic routing guides.
    keywords: ['disney', 'marvel', 'licens', 'approval', 'style guide'],
    excludeClasses: ['vendor_manual', 'routing_guide'],
  },
];

// ---------------------------------------------------------------------------
// Public builder
// ---------------------------------------------------------------------------

/**
 * Build a RetrievalPlan from a natural-language query using lightweight
 * keyword heuristics. No model call — synchronous.
 *
 * Callers may pass explicit overrides (e.g. the Oracle tool caller already
 * knows the domains from context); those take priority over heuristic inference.
 *
 * @example
 * const plan = buildRetrievalPlanFromQuery(
 *   "When does an image get uploaded to the ERP system?",
 *   { topK: 10 }
 * );
 * // → topDomainHints: ['it_systems', 'production_lifecycle']
 * //   excludedDocumentClasses: ['vendor_manual']
 * //   excludedEntityTypes: ['licensor', 'vendor']
 */
export function buildRetrievalPlanFromQuery(
  query: string,
  opts?: Partial<
    Pick<
      RetrievalPlan,
      | 'topDomainHints'
      | 'requiredEntities'
      | 'excludedDocumentClasses'
      | 'excludedEntityTypes'
      | 'topK'
      | 'timeFilter'
      | 'processStageHints'
    >
  >,
): RetrievalPlan {
  const q = query.toLowerCase();

  const topDomainHints: string[] =
    opts?.topDomainHints && opts.topDomainHints.length > 0
      ? opts.topDomainHints.slice(0, 3)
      : inferTopDomains(q);

  const excludedEntityTypes: string[] =
    opts?.excludedEntityTypes && opts.excludedEntityTypes.length > 0
      ? opts.excludedEntityTypes
      : inferEntityExclusions(q);

  const excludedDocumentClasses: string[] =
    opts?.excludedDocumentClasses && opts.excludedDocumentClasses.length > 0
      ? opts.excludedDocumentClasses
      : inferDocumentClassExclusions(q);

  return {
    topDomainHints,
    requiredEntities: opts?.requiredEntities ?? [],
    excludedDocumentClasses: excludedDocumentClasses.length > 0 ? excludedDocumentClasses : undefined,
    excludedEntityTypes: excludedEntityTypes.length > 0 ? excludedEntityTypes : undefined,
    excludedTopDomains: undefined,
    processStageHints: opts?.processStageHints,
    timeFilter: opts?.timeFilter ?? 'current',
    vectorQuery: query,
    topK: opts?.topK ?? DEFAULT_TOP_K,
  };
}

// ---------------------------------------------------------------------------
// Private heuristic helpers
// ---------------------------------------------------------------------------

function inferTopDomains(query: string): string[] {
  const scores = new Map<string, number>();
  for (const { domainId, keywords } of DOMAIN_KEYWORDS) {
    const score = keywords.filter((k) => query.includes(k)).length;
    if (score > 0) scores.set(domainId, score);
  }
  return Array.from(scores.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([id]) => id);
}

function inferEntityExclusions(query: string): string[] {
  const excluded = new Set<string>();
  for (const { keywords, excludeEntityTypes } of ENTITY_EXCLUSION_HINTS) {
    if (keywords.some((k) => query.includes(k))) {
      for (const t of excludeEntityTypes) excluded.add(t);
    }
  }
  return Array.from(excluded);
}

function inferDocumentClassExclusions(query: string): string[] {
  const excluded = new Set<string>();
  for (const { keywords, excludeClasses } of DOCUMENT_CLASS_EXCLUSIONS) {
    if (keywords.some((k) => query.includes(k))) {
      for (const c of excludeClasses) excluded.add(c);
    }
  }
  return Array.from(excluded);
}
