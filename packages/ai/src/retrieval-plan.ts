// RetrievalPlan — spec docs/oracle/07-knowledge-segmentation.md §"What this does to retrieval code".
//
// Every query to the Oracle knowledge graph MUST go through a RetrievalPlan.
// Global vector search without metadata pre-filtering is forbidden (spec rule from
// 00-buildout-index.md "Retrieval rule" and 07-knowledge-segmentation.md).
//
// Enforcement mechanism: the `searchScope` field on every RetrievalPlan records
// HOW the scope was determined.  searchWithRetrievalPlan() emits a structured
// console.warn for every 'global_fallback' plan so operators can audit
//   SELECT ... WHERE selected_domains @> ARRAY['_global_fallback']
// in the oracle_context_packs table and improve heuristics accordingly.
//
// This module provides:
//   - RetrievalPlanSearchScope — 'domain_filtered' | 'global_fallback' | 'global_explicit'
//   - RetrievalPlan type (matches the spec shape exactly + searchScope).
//   - buildRetrievalPlanFromQuery() — lightweight synchronous heuristic builder.
//   - buildDomainScopedPlan()       — explicit domain list, no heuristic exclusions.
//   - buildGlobalRetrievalPlan()    — intentional all-corpus search.
//
// A model-backed variant (buildRetrievalPlanWithModel) can be added later when
// per-query latency budgets allow an extra cheap structured-output call.

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * How the retrieval scope was determined.
 *
 *   domain_filtered  — ≥1 domain matched from keyword heuristics or explicit
 *                      caller input. Search is scoped; vendor-manual noise is
 *                      suppressed from unrelated results.
 *   global_fallback  — 0 domains matched. Falling back to full-corpus search.
 *                      searchWithRetrievalPlan() logs a structured warning so
 *                      the gap can be closed by adding keywords to DOMAIN_KEYWORDS.
 *   global_explicit  — Caller intentionally requested all domains (e.g. the
 *                      contradiction-watcher checking a claim with no taxonomy
 *                      tags yet, or a broad synthesis sweep).
 */
export type RetrievalPlanSearchScope =
  | 'domain_filtered'
  | 'global_fallback'
  | 'global_explicit';

export type RetrievalPlan = {
  /** Top-level domain IDs from knowledge_top_domains. Empty = search all. */
  topDomainHints: string[];
  /** Entity references the query is about; matched against canonical entity registry. */
  requiredEntities: { entityType: string; canonicalValue: string }[];
  /** Document classes to exclude from the candidate set (e.g. vendor_manual for system questions). */
  excludedDocumentClasses?: string[];
  /** Entity types whose presence in a claim should exclude it. */
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
  /**
   * How the retrieval scope was determined.
   * Used for observability — searchWithRetrievalPlan() warns on global_fallback.
   * Chat route stores this in oracle_context_packs.selected_domains as
   * '_global_fallback' so operators can query the fallback rate.
   */
  searchScope: RetrievalPlanSearchScope;
  /**
   * Optional pre-computed embedding for `vectorQuery`.
   * When present, searchWithRetrievalPlan() skips the embedText() call and uses
   * this vector directly, saving one OpenAI API round-trip.
   *
   * Must be exactly EMBEDDING_DIM (1536) floats.  The canonical use-case is
   * contradiction-watcher: it already computes/stores the claim embedding once
   * to persist it in `claims.embedding`, then threads the same vector here so
   * the subsequent ANN search doesn't embed the same summary a second time.
   */
  precomputedVector?: number[];
  /**
   * Department(s) of the employee making the request.
   * Used by searchWithRetrievalPlan() to apply a small RRF score bonus to
   * claims whose claim_metadata.department matches one of these values.
   * This is a soft signal — it nudges ranking but never filters results.
   * Sourced from employees.departments (the full array) at query time.
   */
  departmentHints?: string[];
};

export const DEFAULT_TOP_K = 8;

// ---------------------------------------------------------------------------
// Domain-hint heuristics.
// Keyword groups that map query text to top-level domain IDs.
// These domain IDs MUST match the `id` column in knowledge_top_domains
// (seeded in packages/db/migrations/sql/16_knowledge_top_domains_seed.sql).
//
// When a user query produces topDomainHints: [] (no keywords matched), the
// plan's searchScope is set to 'global_fallback' and a warning is logged.
// Add keywords here to reduce the fallback rate.
// ---------------------------------------------------------------------------

const DOMAIN_KEYWORDS: Array<{ domainId: string; keywords: string[] }> = [
  {
    domainId: 'business_process',
    keywords: [
      // Broad company workflow / operating model questions
      'business process', 'business processes', 'company process', 'company processes',
      'company workflow', 'company workflows', 'overall process', 'overall workflow',
      'end to end', 'end-to-end', 'how things work', 'how the company works',
      'how does the company work', 'how does the business work', 'how our business works',
      'operating model', 'process flow', 'process flows', 'workflow overview',
      'company overview', 'business overview', 'cross-functional', 'cross functional',
      'handoff between departments', 'handoffs between departments',
      'department handoff', 'department handoffs',
      // Common broad process arcs
      'order to ship', 'order-to-ship', 'quote to cash', 'quote-to-cash',
      'concept to production', 'concept-to-production', 'request to delivery',
      'customer request through shipping',
    ],
  },
  {
    domainId: 'it_systems',
    keywords: [
      // Systems and tools
      'erp', 'coldlion', 'resourcespace', 'system', 'software', 'tool',
      'platform', 'portal', 'dashboard',
      // Collaboration tools
      'slack', 'teams', 'microsoft teams', 'sharepoint', 'onedrive', 'google drive',
      'dropbox', 'box ', 'notion', 'airtable', 'monday', 'asana', 'trello',
      // File / data operations
      'upload', 'sync', 'database', 'export', 'import', 'integration',
      'api', 'automat', 'process automation',
      // Asset types
      'image', 'photo', 'template', 'barcode', 'label', 'report',
      'document', 'spreadsheet',
      // Access / credentials
      'password', 'login', 'log in', 'sign in', 'account', 'credentials',
      'two-factor', '2fa', 'sso', 'access to', 'permission', 'user account',
      'drive',
      // Common IT question patterns
      'how does the system', 'how does it work', 'where do i',
    ],
  },
  {
    domainId: 'operations_systems',
    keywords: [
      // Business systems and system families
      'operations system', 'operations systems', 'operational system',
      'business system', 'business systems', 'erp', 'crm', 'plm',
      'designflow', 'design flow', 'designflow plm',
      'coldlion',
      // Google Sheets sources that feed Designflow/PLM workflows
      'google sheets', 'google sheet', 'sheets',
      'orderlist', 'order list',
      'masterdata', 'master data',
      'tasklist', 'task list',
      // Data movement and integration language
      'data migration', 'migrate data', 'move data', 'data flow',
      'field mapping', 'map fields', 'field semantics', 'source of truth',
      'data validation', 'data cleanup', 'data clean up',
      'import into designflow', 'import to designflow',
      'load into designflow', 'sync to designflow',
      'spreadsheet to plm', 'sheets to plm', 'erp integration',
      'crm integration', 'plm integration',
    ],
  },
  {
    domainId: 'licensing_approvals',
    keywords: [
      // Licensors by name
      'disney', 'marvel', 'star wars', 'lucasfilm', 'warner bros', 'nbcuniversal',
      'nickelodeon', 'hasbro', 'mattel', 'sega', 'nintendo', 'universal',
      'dreamworks', 'sony pictures', 'paramount', 'nfl', 'nba', 'mlb', 'nhl',
      // License terms
      'licensor', 'license', 'licens', 'licensee', 'ip right',
      'trademark', 'copyright', 'brand', 'intellectual property',
      // Approval process
      'approval', 'approve', 'approved', 'submit', 'submission', 'resubmit',
      'round', 'revision', 'notes', 'art notes', 'feedback',
      'approval form', 'approval timeline', 'approval process', 'approval deadline',
      'digital sample', 'physical sample approval', 'pre-production approval',
      // Collateral
      'style guide', 'artwork approval', 'licensed', 'brand approval',
      'art approval', 'character art', 'licensed art', 'art submission',
      'print approval', 'color approval', 'color standard',
    ],
  },
  {
    domainId: 'customer_ops',
    keywords: [
      // Retailers by name
      'burlington', 'tjx', 'tj maxx', 'ross', 'hobby lobby', 'walmart',
      'target', 'amazon', 'five below', 'dollar tree', 'big lots',
      'marshalls', 'homegoods', 'tuesday morning', 'bealls', 'ollie',
      // Customer ops terms
      'customer', 'retailer', 'buyer', 'account', 'vendor portal',
      'retail compliance', 'compliance portal',
      // Compliance and logistics
      'routing guide', 'chargeback', 'chargeback dispute', 'edi', 'compliance',
      'dc ', 'distribution center', 'store', 'floor-ready', 'floor ready',
      // Item setup and UPC
      'upc', 'item setup', 'item number', 'sku setup', 'new item',
      'gtin', 'barcode setup', 'product setup',
      // Order management
      'purchase order', 'po ', 'order', 'replenishment', 'assortment',
      'planogram', 'retail price', 'sell-through', 'floor display',
    ],
  },
  {
    domainId: 'supply_chain',
    keywords: [
      // Geography / partners
      'factory', 'china', 'manufacturing', 'overseas', 'brazil', 'colombia',
      'vendor', 'supplier', 'vietnam', 'bangladesh', 'india', 'cambodia',
      // Procurement
      'procurement', 'purchase', 'rfq', 'request for quote', 'quotation',
      'vendor evaluation', 'supplier evaluation', 'vendor selection',
      // Production terms
      'lead time', 'capacity', 'sourcing', 'production order', 'production run',
      'mold', 'tooling', 'raw material', 'component', 'bom', 'bill of material',
      'bill of materials',
      // Quantities
      'quantity', 'moq', 'minimum order', 'lot size', 'order quantity',
      // Vendor management
      'vendor management', 'vendor audit', 'factory audit', 'coc',
      'factory performance', 'vendor performance', 'scorecard',
    ],
  },
  {
    domainId: 'creative_design',
    keywords: [
      // Art and design concept work — distinct from product_development's
      // physical-product framing and design_file_operations' file hygiene.
      // Matching is substring-based (`query.includes`), so broad single tokens
      // ('art', 'comp', 'illustrator', 'color') are intentionally avoided: they
      // bleed into design_file_operations (e.g. "Illustrator files") and match
      // unrelated words ("company", "part"). Keep keywords distinctive.
      'art direction', 'design concept', 'creative concept',
      'illustration', 'graphic design', 'visual design',
      'mockup', 'moodboard', 'mood board',
      // Visual / print / packaging design
      'color palette', 'palette', 'typography', 'logo design',
      'print design', 'packaging art', 'packaging design', 'label design',
      'pattern design', 'character design', 'key art', 'hero image',
      // Creative process
      'creative brief', 'design brief', 'render concept', 'rendering',
    ],
  },
  {
    domainId: 'vendor_management',
    keywords: [
      // Disambiguated from supply_chain (sourcing/procurement/production).
      // These terms are about managing the vendor relationship itself.
      'vendor management', 'vendor onboarding', 'onboard vendor', 'vendor setup',
      'vendor scorecard', 'vendor scorecards', 'vendor audit', 'vendor audits',
      'vendor compliance', 'vendor approval', 'approved vendor list',
      'vendor evaluation', 'supplier evaluation', 'supplier onboarding',
      'supplier scorecard', 'supplier audit', 'supplier management',
      'vendor performance review', 'vendor rating', 'vendor qualification',
      'supplier qualification', 'vendor agreement', 'vendor contract',
      'vendor offboarding', 'preferred vendor', 'vendor relationship',
    ],
  },
  {
    domainId: 'logistics_shipping',
    keywords: [
      // General shipping
      'freight', 'ship', 'shipping', 'delivery', 'transit',
      // Routing and distribution
      'routing', 'warehouse', 'distribution', '3pl', 'container',
      'booking', 'forwarder', 'last mile', 'trucking', 'drayage',
      // Trade terms
      'fob', 'cif', 'incoterm', 'port', 'ocean', 'air freight',
      'customs', 'customs clearance', 'entry',
      // Documents
      'bill of lading', 'bol', 'commercial invoice', 'packing list',
      'telex release', 'sea waybill', 'arrival notice', 'delivery order',
      // Container types
      'fcl', 'lcl', 'full container', 'less than container',
      // Charges
      'demurrage', 'detention', 'storage fee', 'surcharge', 'fuel surcharge',
      // Tracking
      'tracking', 'eta', 'in transit', 'on the water', 'vessel',
      'departed', 'arrived', 'cleared customs',
    ],
  },
  {
    domainId: 'product_development',
    keywords: [
      // Design / creative
      'design', 'artwork', 'creative', 'concept', 'sketch', 'render',
      'mockup', 'dieline', 'graphic', 'illustration',
      // Materials and decoration
      'material', 'fabric', 'color', 'colour', 'pantone', 'decoration',
      'print', 'embroidery', 'embossing', 'debossing', 'foil', 'screen print',
      'pattern', 'finish', 'texture', 'coating',
      // Product structure
      'sku', 'product line', 'collection', 'story', 'theme', 'seasonal',
      'assortment', 'roadmap', 'catalog',
      // Sampling
      'sample', 'proto', 'prototype', 'pre-production sample', 'salesman sample',
      'spec sheet', 'product spec', 'tech pack',
      // Line review
      'line review', 'presentation', 'show', 'showroom',
    ],
  },
  {
    domainId: 'design_file_operations',
    keywords: [
      // File hygiene and storage
      'file naming', 'filename', 'file name', 'name files', 'naming convention',
      'invalid character', 'invalid characters', 'special character',
      'slash', 'backslash', 'colon', 'asterisk', 'question mark',
      'save files', 'saving files', 'save as', 'working file', 'source file',
      'final file', 'native file', 'packaged file', 'archive file',
      'organize files', 'folder structure', 'folder naming', 'shared folder',
      'server folder', 'file server', 'design server', 'nas', 'network drive', 'sharepoint folder',
      // Design-app file size and linking practices
      'bloated', 'file size', 'large file', 'huge file', 'compress',
      'flatten', 'linked asset', 'linked assets', 'embedded asset',
      'embedded assets', 'missing link', 'missing links', 'package links',
      'collect for output', 'placed image', 'high res', 'resolution',
      // Creative file formats and handoff artifacts
      'psd', 'ai file', 'illustrator file', 'photoshop file',
      'indesign file', 'idml', 'pdf export', 'export settings',
      'artwork file', 'art files', 'design files', 'designer file', 'designer files',
      'creative files', 'proof file', 'print file', 'production art file',
      // Versioning and cleanup
      'version file', 'file version', 'v1', 'v2', 'revision file',
      'duplicate file', 'old files', 'cleanup files', 'clean up files',
      'archive folder', 'archive files',
    ],
  },
  {
    domainId: 'production_lifecycle',
    keywords: [
      // Stages
      'pre-production', 'pre production', 'preproduction', 'production stage',
      'before production', 'production workflow', 'bulk', 'mass production', 'post-sale',
      // Sample stages
      'top sample', 'top of production', 'bulk sample', 'production sample',
      'final sample', 'counter sample',
      // QC
      'qc', 'quality', 'inspection', 'testing', 'third-party audit',
      'qc report', 'qc failure', 'qc pass', 'qc hold', 'rework',
      'defect rate', 'rejection rate',
      // Packaging
      'pack', 'packing', 'packaging', 'case pack', 'inner pack', 'display',
      'polybag', 'header card', 'hang tag', 'sticker', 'insert',
      // Scheduling
      'stage', 'lifecycle', 'schedule', 'commit date', 'ship date',
      'deadline', 'milestone', 'timeline', 'top ', 'ex-factory', 'ex factory',
      'in-dc date', 'in dc', 'cancel date', 'cancel by',
      // Returns
      'ra ', 'returns', 'rma', 'defect', 'recall', 'shortage', 'overage',
    ],
  },
  {
    domainId: 'import_compliance',
    keywords: [
      // Tariffs and duties
      'import', 'tariff', 'duty', 'hts', 'section 301', 'tariff exclusion',
      'country of origin', 'coo',
      // Customs agencies
      'cbp', 'ftz', 'customs clearance', 'regulatory',
      // Documentation
      'isf', 'bond', 'classification', 'harmonized code', 'hs code',
      'certificate of origin', 'form a', 'coo certificate',
      // Testing and safety
      'cpsc', 'astm', 'en71', 'safety test', 'product safety',
      'test report', 'test lab', 'testing lab', 'third party test',
      'lead test', 'flammability', 'prop 65', 'reach', 'rohs',
      'compliance document', 'age grading', 'choking hazard',
      'california prop', 'phthalate',
    ],
  },
  {
    domainId: 'finance_pricing',
    keywords: [
      // Product costing and customer product pricing. Company finance/accounting
      // is intentionally out of scope for this domain.
      'costing sheet', 'sku costing', 'product costing', 'cost sheet',
      'fob cost', 'landed cost', 'unit cost', 'duty cost', 'freight cost',
      'all-in cost', 'factory quote', 'factory quotation', 'quote sheet',
      'price list', 'price sheet',
      'customer pricing', 'product pricing', 'wholesale price', 'retail price',
      'msrp', 'markup', 'margin', 'gross margin', 'contribution margin',
      // IP fees
      'royalty', 'royalties', 'licensing fee', 'advance', 'guarantee',
      'minimum guarantee', 'mg ',
    ],
  },
  {
    domainId: 'training_enablement',
    keywords: [
      // Learning how to perform a job or workflow, distinct from people_org's
      // ownership/escalation map and from sensitive HR performance records.
      'training', 'train people', 'train employees', 'trained on',
      'how to train', 'training plan', 'training guide', 'training material',
      'training materials', 'training checklist', 'training video',
      'onboarding checklist', 'new hire training', 'new employee training',
      'job training', 'role training', 'sop training', 'standard operating procedure',
      'work instruction', 'work instructions', 'shadowing', 'job shadow',
      'cross train', 'cross-training', 'cross training', 'refresher training',
      'certification', 'skill check', 'skills check', 'competency',
      'learn to do', 'learn how to', 'teach someone', 'teach the team',
      'how do i learn', 'how should i learn',
    ],
  },
  {
    domainId: 'people_org',
    keywords: [
      // Org
      'employee', 'team', 'department', 'division', 'report to', 'org chart',
      'responsibility matrix', 'raci',
      // Questions about ownership
      'who handles', 'who is responsible', 'who owns', 'who should',
      'who manages', 'who do i contact', 'contact',
      // Handoffs and coverage
      'hand off', 'handoff', 'handover', 'hand over', 'assign', 'assigned to',
      'coverage', 'backup', 'vacation coverage', 'out of office', 'ooo',
      'covering for', 'delegate',
      // HR terms
      'escalat', 'manager', 'ownership', 'role', 'email',
      'point of contact', 'poc', 'new hire', 'onboard', 'onboarding',
    ],
  },
];

// Entity type exclusion hints — inferred from query content.
const ENTITY_EXCLUSION_HINTS: Array<{ keywords: string[]; excludeEntityTypes: string[] }> = [
  {
    // Licensor questions → exclude generic vendors and factories from results.
    keywords: [
      'disney', 'marvel', 'star wars', 'lucasfilm', 'warner bros', 'nbcuniversal',
      'licensor', 'licens',
    ],
    excludeEntityTypes: ['vendor', 'factory', 'freight_provider'],
  },
  {
    // IT system questions → exclude licensor + vendor from results.
    keywords: [
      'erp', 'coldlion', 'system', 'software', 'tool', 'platform', 'portal',
      'plm', 'designflow', 'google sheets', 'orderlist', 'masterdata', 'tasklist',
    ],
    excludeEntityTypes: ['licensor', 'vendor'],
  },
];

// Document class exclusion hints — inferred from query content.
const DOCUMENT_CLASS_EXCLUSIONS: Array<{ keywords: string[]; excludeClasses: string[] }> = [
  {
    // IT system questions should not pull vendor manuals.
    keywords: [
      'erp', 'coldlion', 'system', 'software', 'tool', 'upload', 'sync', 'platform',
      'plm', 'designflow', 'google sheets', 'orderlist', 'masterdata', 'tasklist',
      'field mapping', 'data migration',
    ],
    excludeClasses: ['vendor_manual'],
  },
  {
    // Licensing questions should not pull vendor manuals or generic routing guides.
    keywords: ['disney', 'marvel', 'licens', 'approval', 'style guide', 'art approval'],
    excludeClasses: ['vendor_manual', 'routing_guide'],
  },
];

// ---------------------------------------------------------------------------
// Public builders
// ---------------------------------------------------------------------------

/**
 * Build a RetrievalPlan from a natural-language query using lightweight
 * keyword heuristics. No model call — synchronous.
 *
 * Callers may pass explicit overrides (e.g. the Oracle tool caller already
 * knows the domains from context); those take priority over heuristic inference.
 *
 * Sets searchScope:
 *   'domain_filtered' — ≥1 domain matched.
 *   'global_fallback' — 0 domains matched; searchWithRetrievalPlan() will warn.
 *
 * @example
 * const plan = buildRetrievalPlanFromQuery(
 *   "When does an image get uploaded to the ERP system?",
 *   { topK: 10 }
 * );
 * // → topDomainHints: ['it_systems', 'production_lifecycle']
 * //   excludedDocumentClasses: ['vendor_manual']
 * //   excludedEntityTypes: ['licensor', 'vendor']
 * //   searchScope: 'domain_filtered'
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
      | 'precomputedVector'
      | 'departmentHints'
      | 'excludedTopDomains'
    >
  >,
): RetrievalPlan {
  const q = query.toLowerCase();

  const inferredTopDomainHints: string[] =
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

  const excludedTopDomains: string[] =
    opts?.excludedTopDomains && opts.excludedTopDomains.length > 0
      ? opts.excludedTopDomains
      : inferTopDomainExclusions(q, inferredTopDomainHints);

  const topDomainHints =
    excludedTopDomains.length > 0
      ? inferredTopDomainHints.filter((d) => !excludedTopDomains.includes(d)).slice(0, 3)
      : inferredTopDomainHints;

  const searchScope: RetrievalPlanSearchScope =
    topDomainHints.length > 0 ? 'domain_filtered' : 'global_fallback';

  return {
    topDomainHints,
    requiredEntities: opts?.requiredEntities ?? [],
    excludedDocumentClasses: excludedDocumentClasses.length > 0 ? excludedDocumentClasses : undefined,
    excludedEntityTypes: excludedEntityTypes.length > 0 ? excludedEntityTypes : undefined,
    excludedTopDomains: excludedTopDomains.length > 0 ? excludedTopDomains : undefined,
    processStageHints: opts?.processStageHints,
    timeFilter: opts?.timeFilter ?? 'current',
    vectorQuery: query,
    topK: opts?.topK ?? DEFAULT_TOP_K,
    searchScope,
    precomputedVector: opts?.precomputedVector,
    departmentHints: opts?.departmentHints,
  };
}

/**
 * Build a RetrievalPlan with explicitly-provided domain hints and NO heuristic
 * entity/document-class exclusion inference.
 *
 * Use this when the caller already knows the exact domains (e.g. contradiction-
 * watcher passing the target claim's claim_top_domains). Avoids accidental
 * exclusions when the intent is to search broadly within known domains.
 *
 * Sets searchScope: 'domain_filtered' if domainHints is non-empty,
 *                   'global_fallback' if empty (caller should use buildGlobalRetrievalPlan instead).
 */
export function buildDomainScopedPlan(
  query: string,
  topDomainHints: string[],
  opts?: Partial<
    Pick<
      RetrievalPlan,
      | 'topK'
      | 'timeFilter'
      | 'requiredEntities'
      | 'excludedDocumentClasses'
      | 'excludedEntityTypes'
      | 'precomputedVector'
    >
  >,
): RetrievalPlan {
  return {
    topDomainHints: topDomainHints.slice(0, 3),
    requiredEntities: opts?.requiredEntities ?? [],
    excludedDocumentClasses: opts?.excludedDocumentClasses,
    excludedEntityTypes: opts?.excludedEntityTypes,
    excludedTopDomains: undefined,
    processStageHints: undefined,
    timeFilter: opts?.timeFilter ?? 'current',
    vectorQuery: query,
    topK: opts?.topK ?? DEFAULT_TOP_K,
    searchScope: topDomainHints.length > 0 ? 'domain_filtered' : 'global_fallback',
    precomputedVector: opts?.precomputedVector,
  };
}

/**
 * Build a RetrievalPlan that intentionally searches the full claim corpus.
 *
 * Use when the caller explicitly wants all domains — e.g. a broad synthesis
 * sweep, a re-indexing job, or a diagnostic search. Marks searchScope as
 * 'global_explicit' so monitoring can distinguish intentional global searches
 * from heuristic failures (global_fallback).
 *
 * Do NOT use this for ordinary chat-route retrieval. Use buildRetrievalPlanFromQuery
 * so the query goes through domain inference and gets a domain_filtered scope.
 */
export function buildGlobalRetrievalPlan(
  query: string,
  opts?: Partial<
    Pick<
      RetrievalPlan,
      | 'topK'
      | 'timeFilter'
      | 'excludedDocumentClasses'
      | 'requiredEntities'
      | 'precomputedVector'
    >
  >,
): RetrievalPlan {
  return {
    topDomainHints: [],
    requiredEntities: opts?.requiredEntities ?? [],
    excludedDocumentClasses: opts?.excludedDocumentClasses,
    excludedEntityTypes: undefined,
    excludedTopDomains: undefined,
    processStageHints: undefined,
    timeFilter: opts?.timeFilter ?? 'current',
    vectorQuery: query,
    topK: opts?.topK ?? DEFAULT_TOP_K,
    searchScope: 'global_explicit',
    precomputedVector: opts?.precomputedVector,
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
  if (scores.has('business_process')) {
    return expandBusinessProcessDomains(scores);
  }
  return Array.from(scores.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([id]) => id);
}

function expandBusinessProcessDomains(scores: Map<string, number>): string[] {
  const broadProcessDomains = [
    'business_process',
    'licensing_approvals',
    'product_development',
    'production_lifecycle',
    'supply_chain',
    'customer_ops',
    'logistics_shipping',
    'operations_systems',
    'finance_pricing',
    'people_org',
  ];
  const specificMatches = Array.from(scores.entries())
    .filter(([id]) => id !== 'business_process')
    .sort((a, b) => b[1] - a[1])
    .map(([id]) => id);
  return Array.from(new Set(['business_process', ...specificMatches, ...broadProcessDomains]));
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

function inferTopDomainExclusions(query: string, topDomainHints: string[]): string[] {
  if (topDomainHints.includes('operations_systems')) {
    const looksLikeOperationsSystems =
      [
        'designflow', 'design flow', 'plm', 'google sheets', 'google sheet',
        'orderlist', 'order list', 'masterdata', 'master data', 'tasklist',
        'task list', 'field mapping', 'map fields', 'data migration',
        'spreadsheet to plm', 'sheets to plm', 'source of truth',
      ].some((k) => query.includes(k));

    if (looksLikeOperationsSystems) {
      // Data-flow questions about business systems should not be pulled into
      // generic customer orders, licensor approvals, or design-art workflow
      // just because the source sheet or PLM name contains overlapping words.
      // NOTE: creative_design is now an inferable domain (it has its own
      // DOMAIN_KEYWORDS group). This exclusion is intentional — when the query
      // is clearly a Designflow/PLM data-flow question, art-concept claims are
      // off-topic noise and must be suppressed even though the domain matched.
      return ['customer_ops', 'licensing_approvals', 'creative_design'];
    }
  }

  if (topDomainHints.includes('training_enablement')) {
    const looksLikeTraining =
      [
        'training', 'trained on', 'training plan', 'training guide',
        'training material', 'training materials', 'training checklist',
        'onboarding checklist', 'new hire training', 'job training',
        'role training', 'sop training', 'work instruction', 'shadowing',
        'cross train', 'cross-training', 'cross training', 'refresher training',
        'certification', 'skill check', 'skills check', 'competency',
        'learn to do', 'learn how to', 'teach someone', 'teach the team',
      ].some((k) => query.includes(k));

    if (looksLikeTraining) {
      // Training questions need procedural learning material. They should not
      // drift into org ownership or sensitive HR/performance context unless the
      // user explicitly asks who owns the training or about personnel records.
      return ['people_org'];
    }
  }

  if (!topDomainHints.includes('design_file_operations')) return [];

  const looksLikeFileOps =
    [
      'file naming', 'filename', 'file name', 'invalid character', 'save files',
      'saving files', 'bloated', 'file size', 'folder structure', 'shared folder',
      'server folder', 'design server', 'linked asset', 'embedded asset',
      'missing link', 'package links', 'artwork file', 'design files',
      'designer files', 'creative files',
    ].some((k) => query.includes(k));

  if (!looksLikeFileOps) return [];

  // File-operations questions are about keeping creative files usable, small,
  // compatible, and findable. They should not silently drift into product
  // approval/status workflow unless the user asks that workflow question.
  return ['product_development', 'production_lifecycle', 'it_systems'];
}
