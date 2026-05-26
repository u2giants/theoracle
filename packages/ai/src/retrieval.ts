// Retrieval helpers for the live chat route.
//
// Spec 9.1 constraint: every chat turn fetches only
//   * recent N messages from the channel
//   * the current employee's profile
//   * top K open gaps relevant to this employee / department
//   * top K semantically relevant approved claims (hybrid pgvector + tsvector RRF)
//
// Do NOT load full brain sections — Phase 6 will pull section excerpts only when
// the search_company_knowledge tool fires.
//
// P1 #3 — Hybrid RRF retrieval:
//   searchWithRetrievalPlan() replaces searchApprovedClaims() in production paths.
//   It runs:
//     1. Metadata pre-filter (claim_top_domains, claim_entities, claim_metadata)
//        driven by the RetrievalPlan — prevents vendor_manual from surfacing in
//        system questions, prevents vendor from polluting licensor-approval results.
//     2. Parallel pgvector cosine ranking + tsvector rank.
//     3. Reciprocal Rank Fusion (RRF, k=60) to combine both signals.
//   searchApprovedClaims() is retained as a thin wrapper for backward compat.

import { and, desc, eq, inArray, or, sql } from 'drizzle-orm';
import {
  brainSections,
  brainSectionVersions,
  channelParticipants,
  claimDomains,
  claims,
  employees,
  gaps,
  messages,
  type Employee,
  type Gap,
} from '@oracle/db/schema';
import type { OracleDb } from '@oracle/db/client';
import type { KnowledgeDomain } from '@oracle/shared';
import { EMBEDDING_DIM } from '@oracle/shared';
import { embedText } from './embeddings';
import { type RetrievalPlan } from './retrieval-plan';

// Use the full-schema-aware DB type so callers passing in the result of
// getDirectDb() / getPooledDb() type-check without casts. The retrieval helpers
// don't actually need the schema at the type level — they hand-write SQL via
// the bare drizzle-orm builders — but accepting a wider type kept the Vercel
// production build failing on a generic mismatch.
type Db = OracleDb;

export const DEFAULT_RECENT_MESSAGES = 30;
export const DEFAULT_GAPS_LIMIT = 5;
export const DEFAULT_CLAIMS_LIMIT = 5;

export type RecentMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: Date;
  authorName: string | null;
};

export type RelevantClaim = {
  id: string;
  summary: string;
  claimType: string;
  impactScore: number;
  confidenceScore: number;
  distance: number;
};

/** Recent messages in a channel, chronological. */
export async function getRecentMessages(
  db: Db,
  channelId: string,
  limit = DEFAULT_RECENT_MESSAGES,
): Promise<RecentMessage[]> {
  const rows = await db
    .select({
      id: messages.id,
      role: messages.role,
      content: messages.content,
      createdAt: messages.createdAt,
      authorName: employees.name,
    })
    .from(messages)
    .leftJoin(employees, eq(messages.employeeId, employees.id))
    .where(eq(messages.channelId, channelId))
    .orderBy(desc(messages.createdAt))
    .limit(limit);
  return rows.reverse();
}

/** Open gaps relevant to this employee, in priority order. */
export async function getRelevantOpenGaps(
  db: Db,
  employee: Employee,
  limit = DEFAULT_GAPS_LIMIT,
): Promise<Gap[]> {
  const rows = await db
    .select()
    .from(gaps)
    .where(
      and(
        inArray(gaps.status, ['open', 'queued', 'asked']),
        or(
          eq(gaps.targetEmployeeId, employee.id),
          eq(gaps.targetDepartment, employee.department),
        ),
      ),
    )
    .orderBy(
      sql`CASE ${gaps.priority}
            WHEN 'urgent' THEN 0
            WHEN 'high'   THEN 1
            WHEN 'medium' THEN 2
            ELSE 3 END`,
      desc(gaps.createdAt),
    )
    .limit(limit);
  return rows;
}

/**
 * @deprecated Use searchWithRetrievalPlan() instead.
 *
 * Raw pgvector cosine-distance search with optional legacy domain filter.
 * Does not enforce the RetrievalPlan metadata pre-filter contract, does not
 * log fallback scope, and does not apply entity-type or document-class
 * exclusions. Retained for backward-compat only — do not add new call sites.
 *
 * Semantically relevant approved claims via pgvector cosine distance.
 * Optionally filter by domain (joined through claim_domains).
 *
 * If embeddings are stubbed (zero vector), the cosine distance is
 * meaningless — we fall back to ordering by impact_score desc so we
 * still surface SOMETHING useful.
 */
export async function searchApprovedClaims(
  db: Db,
  query: string,
  options: { limit?: number; domains?: KnowledgeDomain[] } = {},
): Promise<RelevantClaim[]> {
  const limit = options.limit ?? DEFAULT_CLAIMS_LIMIT;
  const { vector, fallback } = await embedText(query);

  if (fallback) {
    // No real embeddings — return top approved claims by impact score.
    const baseSelect = db
      .select({
        id: claims.id,
        summary: claims.summary,
        claimType: claims.claimType,
        impactScore: claims.impactScore,
        confidenceScore: claims.confidenceScore,
        distance: sql<number>`0`.as('distance'),
      })
      .from(claims);

    if (options.domains && options.domains.length > 0) {
      return await baseSelect
        .innerJoin(claimDomains, eq(claimDomains.claimId, claims.id))
        .where(
          and(
            eq(claims.status, 'approved'),
            inArray(claimDomains.domain, options.domains),
          ),
        )
        .orderBy(desc(claims.impactScore))
        .limit(limit);
    }

    return await baseSelect
      .where(eq(claims.status, 'approved'))
      .orderBy(desc(claims.impactScore))
      .limit(limit);
  }

  // Real embedding — pgvector cosine.
  const vec = `[${vector.join(',')}]`;
  const rows = await db.execute<{
    id: string;
    summary: string;
    claim_type: string;
    impact_score: number;
    confidence_score: number;
    distance: number;
  }>(
    options.domains && options.domains.length > 0
      ? sql`
        SELECT DISTINCT c.id, c.summary, c.claim_type, c.impact_score, c.confidence_score,
               (c.embedding <=> ${vec}::vector(${EMBEDDING_DIM})) AS distance
        FROM claims c
        INNER JOIN claim_domains cd ON cd.claim_id = c.id
        WHERE c.status = 'approved'
          AND c.embedding IS NOT NULL
          AND cd.domain = ANY(${options.domains}::knowledge_domain[])
        ORDER BY distance ASC
        LIMIT ${limit};
      `
      : sql`
        SELECT c.id, c.summary, c.claim_type, c.impact_score, c.confidence_score,
               (c.embedding <=> ${vec}::vector(${EMBEDDING_DIM})) AS distance
        FROM claims c
        WHERE c.status = 'approved' AND c.embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT ${limit};
      `,
  );

  return rows.map((r) => ({
    id: r.id,
    summary: r.summary,
    claimType: r.claim_type,
    impactScore: r.impact_score,
    confidenceScore: r.confidence_score,
    distance: r.distance,
  }));
}

// ---------------------------------------------------------------------------
// Hybrid RRF retrieval — P1 #3
// ---------------------------------------------------------------------------

/**
 * Hybrid pgvector + tsvector retrieval with Reciprocal Rank Fusion (RRF).
 *
 * Implements the full RetrievalPlan spec from docs/oracle/07-knowledge-segmentation.md.
 * Filters the candidate set by top-level domain, entity type exclusions,
 * document class exclusions, and time validity BEFORE vector search.
 *
 * When no real embeddings are available (OPENAI_API_KEY not set), falls back
 * to pure tsvector ranking + metadata filter so retrieval still works in dev.
 *
 * @example
 * const plan = buildRetrievalPlanFromQuery("When does artwork go to China?");
 * const results = await searchWithRetrievalPlan(db, plan);
 */
export async function searchWithRetrievalPlan(
  db: Db,
  plan: RetrievalPlan,
): Promise<RelevantClaim[]> {
  // Enforcement: every global-fallback plan emits a structured warning so
  // operators can audit oracle_context_packs.selected_domains and improve
  // the DOMAIN_KEYWORDS heuristics in retrieval-plan.ts.
  if (plan.searchScope === 'global_fallback') {
    console.warn('[oracle:retrieval] global_fallback — searching entire claim corpus', {
      query: plan.vectorQuery.slice(0, 120),
      hint: 'Add matching keywords to DOMAIN_KEYWORDS in packages/ai/src/retrieval-plan.ts',
      impact: 'vendor_manual / licensor noise may contaminate results',
    });
  }

  const limit = plan.topK;
  const { vector, fallback } = await embedText(plan.vectorQuery);

  if (fallback) {
    return _searchFallbackTsvector(db, plan, limit);
  }

  const vec = `[${vector.join(',')}]`;
  const textQuery = plan.vectorQuery;

  // Optional domain filter — joined against claim_top_domains.
  const topDomainFilter =
    plan.topDomainHints.length > 0
      ? sql`AND ctd.top_domain_id = ANY(${plan.topDomainHints}::text[])`
      : sql``;

  // Optional document-class exclusion — joined against claim_metadata.
  const docClassFilter =
    plan.excludedDocumentClasses && plan.excludedDocumentClasses.length > 0
      ? sql`AND (cm.document_class IS NULL OR NOT (cm.document_class = ANY(${plan.excludedDocumentClasses}::text[])))`
      : sql``;

  // Optional time filter — only claims still in effect.
  const timeFilter =
    plan.timeFilter === 'current'
      ? sql`AND (cm.id IS NULL OR cm.effective_until IS NULL)`
      : plan.timeFilter && plan.timeFilter.startsWith('since:')
      ? (() => {
          const since = plan.timeFilter.slice(6); // 'YYYY-MM-DD'
          return sql`AND (cm.effective_from IS NULL OR cm.effective_from >= ${since}::timestamptz)`;
        })()
      : sql``;

  // Optional excluded-entity-type subquery filter.
  const excludedEntityTypeFilter =
    plan.excludedEntityTypes && plan.excludedEntityTypes.length > 0
      ? sql`AND NOT EXISTS (
          SELECT 1 FROM claim_entities _ce
          JOIN entities _e ON _e.id = _ce.entity_id
          WHERE _ce.claim_id = c.id
            AND _e.entity_type = ANY(${plan.excludedEntityTypes}::text[])
        )`
      : sql``;

  // Optional required-entity subquery filter.
  const requiredEntityFilter =
    plan.requiredEntities.length > 0
      ? sql`AND EXISTS (
          SELECT 1 FROM claim_entities _ce2
          JOIN entities _e2 ON _e2.id = _ce2.entity_id
          WHERE _ce2.claim_id = c.id
            AND _e2.canonical_value = ANY(${plan.requiredEntities.map((e) => e.canonicalValue)}::text[])
        )`
      : sql``;

  const rows = await db.execute<{
    id: string;
    summary: string;
    claim_type: string;
    impact_score: number;
    confidence_score: number;
    distance: number;
    rrf_score: number;
  }>(sql`
    WITH
    pre_filtered AS (
      SELECT DISTINCT
        c.id, c.summary, c.claim_type, c.impact_score, c.confidence_score, c.embedding
      FROM claims c
      LEFT JOIN claim_top_domains ctd ON ctd.claim_id = c.id
      LEFT JOIN claim_metadata    cm  ON cm.claim_id  = c.id
      WHERE c.status = 'approved'
        AND c.embedding IS NOT NULL
        ${topDomainFilter}
        ${docClassFilter}
        ${timeFilter}
        ${excludedEntityTypeFilter}
        ${requiredEntityFilter}
    ),
    vec_ranked AS (
      SELECT
        id, summary, claim_type, impact_score, confidence_score,
        (embedding <=> ${vec}::vector(${EMBEDDING_DIM})) AS vec_dist,
        ROW_NUMBER() OVER (
          ORDER BY embedding <=> ${vec}::vector(${EMBEDDING_DIM})
        ) AS vrank
      FROM pre_filtered
    ),
    txt_scored AS (
      SELECT
        id,
        ts_rank(
          to_tsvector('english', summary),
          plainto_tsquery('english', ${textQuery})
        ) AS ts_score
      FROM pre_filtered
      WHERE to_tsvector('english', summary) @@ plainto_tsquery('english', ${textQuery})
    ),
    txt_ranked AS (
      SELECT id, ROW_NUMBER() OVER (ORDER BY ts_score DESC) AS trank
      FROM txt_scored
    ),
    rrf AS (
      SELECT
        vr.id, vr.summary, vr.claim_type, vr.impact_score, vr.confidence_score,
        vr.vec_dist,
        1.0 / (60.0 + vr.vrank::float) +
        COALESCE(1.0 / (60.0 + tr.trank::float), 0.0) AS rrf_score
      FROM vec_ranked vr
      LEFT JOIN txt_ranked tr ON tr.id = vr.id
    )
    SELECT id, summary, claim_type, impact_score, confidence_score,
           vec_dist AS distance, rrf_score
    FROM rrf
    ORDER BY rrf_score DESC
    LIMIT ${limit}
  `);

  return rows.map((r) => ({
    id: r.id,
    summary: r.summary,
    claimType: r.claim_type,
    impactScore: r.impact_score,
    confidenceScore: r.confidence_score,
    distance: r.distance,
  }));
}

/**
 * Tsvector-only fallback used when OPENAI_API_KEY is absent (dev mode).
 * Applies the same metadata pre-filters from the plan.
 */
async function _searchFallbackTsvector(
  db: Db,
  plan: RetrievalPlan,
  limit: number,
): Promise<RelevantClaim[]> {
  if (plan.searchScope === 'global_fallback') {
    console.warn('[oracle:retrieval] global_fallback (tsvector path) — searching entire claim corpus', {
      query: plan.vectorQuery.slice(0, 120),
      hint: 'Add matching keywords to DOMAIN_KEYWORDS in packages/ai/src/retrieval-plan.ts',
    });
  }

  // Build domain WHERE fragment for the Drizzle ORM query path.
  // We need a small SQL helper for the optional joins here too.
  const textQuery = plan.vectorQuery;

  const topDomainFilter =
    plan.topDomainHints.length > 0
      ? sql`AND ctd.top_domain_id = ANY(${plan.topDomainHints}::text[])`
      : sql``;

  const docClassFilter =
    plan.excludedDocumentClasses && plan.excludedDocumentClasses.length > 0
      ? sql`AND (cm.document_class IS NULL OR NOT (cm.document_class = ANY(${plan.excludedDocumentClasses}::text[])))`
      : sql``;

  const timeFilter =
    plan.timeFilter === 'current'
      ? sql`AND (cm.id IS NULL OR cm.effective_until IS NULL)`
      : sql``;

  const rows = await db.execute<{
    id: string;
    summary: string;
    claim_type: string;
    impact_score: number;
    confidence_score: number;
    ts_score: number;
  }>(sql`
    SELECT DISTINCT
      c.id, c.summary, c.claim_type, c.impact_score, c.confidence_score,
      ts_rank(
        to_tsvector('english', c.summary),
        plainto_tsquery('english', ${textQuery})
      ) AS ts_score
    FROM claims c
    LEFT JOIN claim_top_domains ctd ON ctd.claim_id = c.id
    LEFT JOIN claim_metadata    cm  ON cm.claim_id  = c.id
    WHERE c.status = 'approved'
      ${topDomainFilter}
      ${docClassFilter}
      ${timeFilter}
    ORDER BY ts_score DESC, c.impact_score DESC
    LIMIT ${limit}
  `);

  return rows.map((r) => ({
    id: r.id,
    summary: r.summary,
    claimType: r.claim_type,
    impactScore: r.impact_score,
    confidenceScore: r.confidence_score,
    distance: 1 - r.ts_score, // approximate: lower ts_score → higher distance
  }));
}

/** Fetch the current Markdown for a small set of brain sections. */
export async function getBrainSectionSnippets(
  db: Db,
  sectionIds: string[],
): Promise<Array<{ sectionId: string; title: string; markdown: string }>> {
  if (sectionIds.length === 0) return [];
  const rows = await db
    .select({
      sectionId: brainSections.id,
      title: brainSections.title,
      markdown: brainSectionVersions.markdown,
    })
    .from(brainSections)
    .leftJoin(
      brainSectionVersions,
      eq(brainSectionVersions.id, brainSections.currentVersionId),
    )
    .where(inArray(brainSections.id, sectionIds));
  return rows.map((r) => ({
    sectionId: r.sectionId,
    title: r.title,
    markdown: r.markdown ?? '',
  }));
}

/** Channel-aware gap fetch — used by the check_open_gaps tool. */
export async function getOpenGapsForChannel(
  db: Db,
  channelId: string,
  limit = DEFAULT_GAPS_LIMIT,
): Promise<Gap[]> {
  // Channel members → their departments.
  const members = await db
    .select({
      employeeId: channelParticipants.employeeId,
      department: employees.department,
    })
    .from(channelParticipants)
    .innerJoin(employees, eq(employees.id, channelParticipants.employeeId))
    .where(eq(channelParticipants.channelId, channelId));

  if (members.length === 0) return [];

  const employeeIds = members.map((m) => m.employeeId);
  const departments = Array.from(new Set(members.map((m) => m.department)));

  return db
    .select()
    .from(gaps)
    .where(
      and(
        inArray(gaps.status, ['open', 'queued', 'asked']),
        or(
          inArray(gaps.targetEmployeeId, employeeIds),
          inArray(gaps.targetDepartment, departments),
        ),
      ),
    )
    .orderBy(
      sql`CASE ${gaps.priority}
            WHEN 'urgent' THEN 0
            WHEN 'high'   THEN 1
            WHEN 'medium' THEN 2
            ELSE 3 END`,
      desc(gaps.createdAt),
    )
    .limit(limit);
}
