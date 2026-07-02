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
//   searchWithRetrievalPlan() is the ONE endorsed claim-retrieval path. It runs:
//     1. Metadata pre-filter (claim_top_domains, claim_entities, claim_metadata)
//        driven by the RetrievalPlan — prevents vendor_manual from surfacing in
//        system questions, prevents vendor from polluting licensor-approval results.
//     2. Parallel pgvector cosine ranking + tsvector rank.
//     3. Reciprocal Rank Fusion (RRF, k=60) to combine both signals.
//   The fallback tsvector path (_searchFallbackTsvector) MUST stay behaviorally
//   identical for filtering — both paths build their WHERE clauses from the
//   shared buildPlanMetadataFilters() helper precisely so they cannot drift.

import { and, desc, eq, inArray, or, sql } from 'drizzle-orm';
import {
  brainSections,
  brainSectionVersions,
  channelParticipants,
  claims,
  employees,
  gaps,
  messages,
  type Employee,
  type Gap,
} from '@oracle/db/schema';
import type { OracleDb } from '@oracle/db/client';
import { EMBEDDING_DIM, DEFAULT_LOCALE, type SupportedLocale } from '@oracle/shared';
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

/**
 * Build the shared metadata WHERE fragments used by both the hybrid and
 * tsvector-fallback retrieval paths. Both paths use `c` as the claims alias,
 * `ctd` as the claim_top_domains join alias, and `cm` as the claim_metadata
 * join alias. Keep those alias names stable in the consuming queries.
 *
 * Important: requiredEntities matches on both (entity_type, canonical_value)
 * — matching canonical_value alone lets a name registered under a different
 * type incorrectly match.
 */
function buildPlanMetadataFilters(plan: RetrievalPlan, locale: SupportedLocale) {
  // Bilingual claim layer (china_imp.md). These three fragments localize the
  // claim text/keyword-search to the reader's language and MUST be interpolated
  // into BOTH the hybrid and fallback query bodies — the parity guard
  // (verify:retrieval-filter-parity) enforces that every key returned here
  // appears in both paths, so they cannot silently drift:
  //   * translationJoin   — LEFT JOIN the reader's translation row (≤1 per claim)
  //   * localizedSummary  — COALESCE(ct.summary, c.summary): translated text, else canonical
  //   * ftsConfig         — tsvector regconfig: 'simple' for zh-CN (Postgres can't
  //                         tokenize spaceless Chinese), 'english' otherwise.
  // The localized EMBEDDING (COALESCE(ct.embedding, c.embedding)) is hybrid-only
  // — the fallback path has no embedding concept — so it is applied inline in the
  // hybrid query rather than returned here (like the dept-bonus CTE).
  const translationJoin = sql`LEFT JOIN claim_translations ct ON ct.claim_id = c.id AND ct.lang = ${locale}`;
  const localizedSummary = sql`COALESCE(ct.summary, c.summary)`;
  // regconfig is derived from a coerced locale (never user input), injected as
  // raw SQL because a tsvector config cannot be a bind parameter.
  const ftsConfig = sql.raw(locale === 'zh-CN' ? `'simple'` : `'english'`);

  // NOTE: list filters are bound as ONE JSON-string parameter and unpacked in
  // SQL via jsonb_array_elements_text / jsonb_to_recordset. Two driver pitfalls
  // make the obvious forms break at runtime (2026-06-10 incident):
  //   * a bare JS array in a drizzle sql template expands to a placeholder
  //     list `($1, $2)`, so `ANY((...)::text[])` is invalid SQL;
  //   * binding the array as a single param (sql.param) relies on postgres-js
  //     array serialization, which mis-serializes for unknown-typed params.
  // A plain string param + jsonb unpacking is unambiguous on every driver.
  const topDomainFilter =
    plan.topDomainHints.length > 0
      ? sql`AND ctd.top_domain_id IN (SELECT jsonb_array_elements_text(${JSON.stringify(plan.topDomainHints)}::jsonb))`
      : sql``;

  // Exclude claims that carry ANY excluded top-domain. claim_top_domains is
  // multi-valued, so a direct predicate on the LEFT-JOINed ctd row would let
  // a claim survive through a different, non-excluded domain row. NOT EXISTS
  // against the full set is the only correct form. Composes with
  // topDomainFilter: a claim must (match a hint, if hints given) AND (carry no
  // excluded domain).
  const excludedTopDomainFilter =
    plan.excludedTopDomains && plan.excludedTopDomains.length > 0
      ? sql`AND NOT EXISTS (
          SELECT 1 FROM claim_top_domains _xtd
          WHERE _xtd.claim_id = c.id
            AND _xtd.top_domain_id IN (SELECT jsonb_array_elements_text(${JSON.stringify(plan.excludedTopDomains)}::jsonb))
        )`
      : sql``;

  const docClassFilter =
    plan.excludedDocumentClasses && plan.excludedDocumentClasses.length > 0
      ? sql`AND (cm.document_class IS NULL OR cm.document_class NOT IN (SELECT jsonb_array_elements_text(${JSON.stringify(plan.excludedDocumentClasses)}::jsonb)))`
      : sql``;

  const timeFilter =
    plan.timeFilter === 'current'
      ? // claim_metadata's PK is claim_id (1:1 with claims) — there is no id column.
        sql`AND (cm.claim_id IS NULL OR cm.effective_until IS NULL)`
      : plan.timeFilter && plan.timeFilter.startsWith('since:')
        ? (() => {
            const since = plan.timeFilter.slice(6); // 'YYYY-MM-DD'
            return sql`AND (cm.effective_from IS NULL OR cm.effective_from >= ${since}::timestamptz)`;
          })()
        : sql``;

  // Narrowing filter (not a ranking hint): keep only claims whose
  // claim_metadata.process_stage is one of the requested stages. claim_metadata
  // is 1:1 with claims, so this predicates directly on the LEFT-JOINed cm row.
  // A claim with no metadata row (cm.process_stage IS NULL) does not satisfy a
  // specific-stage requirement and is correctly dropped — `NULL = ANY(...)`
  // evaluates to NULL, which is not TRUE.
  const processStageFilter =
    plan.processStageHints && plan.processStageHints.length > 0
      ? sql`AND cm.process_stage IN (SELECT jsonb_array_elements_text(${JSON.stringify(plan.processStageHints)}::jsonb))`
      : sql``;

  const excludedEntityTypeFilter =
    plan.excludedEntityTypes && plan.excludedEntityTypes.length > 0
      ? sql`AND NOT EXISTS (
          SELECT 1 FROM claim_entities _ce
          JOIN entities _e ON _e.id = _ce.entity_id
          WHERE _ce.claim_id = c.id
            AND _e.entity_type IN (SELECT jsonb_array_elements_text(${JSON.stringify(plan.excludedEntityTypes)}::jsonb))
        )`
      : sql``;

  // Tuple match on (entity_type, canonical_value) so a canonical_value
  // registered under a different entity_type cannot incidentally match.
  // jsonb_to_recordset turns the bound JSON pairs into a derived table.
  const requiredEntityFilter =
    plan.requiredEntities.length > 0
      ? sql`AND EXISTS (
          SELECT 1
          FROM claim_entities _ce2
          JOIN entities _e2 ON _e2.id = _ce2.entity_id
          JOIN jsonb_to_recordset(${JSON.stringify(
            plan.requiredEntities.map((e) => ({ t: e.entityType, v: e.canonicalValue })),
          )}::jsonb) AS _req(t text, v text)
            ON _e2.entity_type = _req.t
           AND _e2.canonical_value = _req.v
          WHERE _ce2.claim_id = c.id
        )`
      : sql``;

  return {
    topDomainFilter,
    excludedTopDomainFilter,
    docClassFilter,
    timeFilter,
    processStageFilter,
    excludedEntityTypeFilter,
    requiredEntityFilter,
    translationJoin,
    localizedSummary,
    ftsConfig,
  };
}

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
  claimKind: string | null;
  claimKindReviewStatus: string | null;
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
  const depts = employee.departments.length > 0
    ? employee.departments
    : employee.department ? [employee.department] : [];

  const rows = await db
    .select()
    .from(gaps)
    .where(
      and(
        inArray(gaps.status, ['open', 'queued', 'asked']),
        or(
          eq(gaps.targetEmployeeId, employee.id),
          depts.length > 0
            ? inArray(gaps.targetDepartment, depts)
            : undefined,
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
  locale: SupportedLocale = DEFAULT_LOCALE,
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
  const { vector, fallback } = plan.precomputedVector
    ? { vector: plan.precomputedVector, fallback: false }
    : await embedText(plan.vectorQuery);

  if (fallback) {
    return _searchFallbackTsvector(db, plan, limit, locale);
  }

  const vec = `[${vector.join(',')}]`;
  const textQuery = plan.vectorQuery;

  const {
    topDomainFilter,
    excludedTopDomainFilter,
    docClassFilter,
    timeFilter,
    processStageFilter,
    excludedEntityTypeFilter,
    requiredEntityFilter,
    translationJoin,
    localizedSummary,
    ftsConfig,
  } = buildPlanMetadataFilters(plan, locale);

  // Small department-match bonus — joins claim_metadata on department to give
  // a soft nudge to claims tagged with the requesting employee's department(s).
  // Value (0.002) is intentionally small: roughly equivalent to ~15-rank RRF
  // lift at mid-list, so it nudges without overriding semantic relevance.
  const deptHints = plan.departmentHints ?? [];
  const deptBonusCte =
    deptHints.length > 0
      ? sql`
    dept_bonus AS (
      SELECT DISTINCT cm_d.claim_id
      FROM claim_metadata cm_d
      WHERE cm_d.department IN (SELECT jsonb_array_elements_text(${JSON.stringify(deptHints)}::jsonb))
    ),`
      : sql``;
  const deptBonusTerm =
    deptHints.length > 0
      ? sql`+ CASE WHEN db.claim_id IS NOT NULL THEN 0.002 ELSE 0.0 END`
      : sql``;
  const deptBonusJoin =
    deptHints.length > 0
      ? sql`LEFT JOIN dept_bonus db ON db.claim_id = vr.id`
      : sql``;

  const rows = await db.execute<{
    id: string;
    summary: string;
    claim_type: string;
    claim_kind: string | null;
    claim_kind_review_status: string | null;
    impact_score: number;
    confidence_score: number;
    distance: number;
    rrf_score: number;
  }>(sql`
    WITH
    pre_filtered AS (
      -- Bilingual: render summary/embedding in the reader's locale, falling
      -- back to the canonical claim when no translation row exists.
      SELECT DISTINCT
        c.id, ${localizedSummary} AS summary, c.claim_type, c.claim_kind, c.claim_kind_review_status,
        c.impact_score, c.confidence_score,
        COALESCE(ct.embedding, c.embedding) AS embedding
      FROM claims c
      ${translationJoin}
      LEFT JOIN claim_top_domains ctd ON ctd.claim_id = c.id
      LEFT JOIN claim_metadata    cm  ON cm.claim_id  = c.id
      WHERE c.status = 'approved'
        AND COALESCE(ct.embedding, c.embedding) IS NOT NULL
        ${topDomainFilter}
        ${excludedTopDomainFilter}
        ${docClassFilter}
        ${timeFilter}
        ${processStageFilter}
        ${excludedEntityTypeFilter}
        ${requiredEntityFilter}
    ),
    vec_ranked AS (
      -- EMBEDDING_DIM is inlined via sql.raw: a type modifier like vector(N)
      -- cannot be a bind parameter, and the constant is project-owned (1536).
      SELECT
        id, summary, claim_type, claim_kind, claim_kind_review_status, impact_score, confidence_score,
        (embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))})) AS vec_dist,
        ROW_NUMBER() OVER (
          ORDER BY embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))})
        ) AS vrank
      FROM pre_filtered
    ),
    txt_scored AS (
      SELECT
        id,
        ts_rank(
          to_tsvector(${ftsConfig}, summary),
          plainto_tsquery(${ftsConfig}, ${textQuery})
        ) AS ts_score
      FROM pre_filtered
      WHERE to_tsvector(${ftsConfig}, summary) @@ plainto_tsquery(${ftsConfig}, ${textQuery})
    ),
    txt_ranked AS (
      SELECT id, ROW_NUMBER() OVER (ORDER BY ts_score DESC) AS trank
      FROM txt_scored
    ),
    ${deptBonusCte}
    rrf AS (
      SELECT
        vr.id, vr.summary, vr.claim_type, vr.claim_kind, vr.claim_kind_review_status, vr.impact_score, vr.confidence_score,
        vr.vec_dist,
        1.0 / (60.0 + vr.vrank::float) +
        COALESCE(1.0 / (60.0 + tr.trank::float), 0.0)
        ${deptBonusTerm} AS rrf_score
      FROM vec_ranked vr
      LEFT JOIN txt_ranked tr ON tr.id = vr.id
      ${deptBonusJoin}
    )
    SELECT id, summary, claim_type, claim_kind, claim_kind_review_status, impact_score, confidence_score,
           vec_dist AS distance, rrf_score
    FROM rrf
    ORDER BY rrf_score DESC
    LIMIT ${limit}
  `);

  return rows.map((r) => ({
    id: r.id,
    summary: r.summary,
    claimType: r.claim_type,
    claimKind: r.claim_kind,
    claimKindReviewStatus: r.claim_kind_review_status,
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
  locale: SupportedLocale = DEFAULT_LOCALE,
): Promise<RelevantClaim[]> {
  if (plan.searchScope === 'global_fallback') {
    console.warn('[oracle:retrieval] global_fallback (tsvector path) — searching entire claim corpus', {
      query: plan.vectorQuery.slice(0, 120),
      hint: 'Add matching keywords to DOMAIN_KEYWORDS in packages/ai/src/retrieval-plan.ts',
    });
  }

  const textQuery = plan.vectorQuery;

  // Shared filter helper — keeps fallback behaviorally identical to the main
  // hybrid path for every narrowing field (top-domain hint + exclusion,
  // doc-class, time, process-stage, entity-type exclusion, required-entity),
  // so the dev fallback isn't silently weaker. Any filter added here MUST be
  // consumed in the WHERE clause below too — the parity smoke test
  // (verify:retrieval-filter-parity) fails if a key is destructured but unused.
  const {
    topDomainFilter,
    excludedTopDomainFilter,
    docClassFilter,
    timeFilter,
    processStageFilter,
    excludedEntityTypeFilter,
    requiredEntityFilter,
    translationJoin,
    localizedSummary,
    ftsConfig,
  } = buildPlanMetadataFilters(plan, locale);

  const rows = await db.execute<{
    id: string;
    summary: string;
    claim_type: string;
    claim_kind: string | null;
    claim_kind_review_status: string | null;
    impact_score: number;
    confidence_score: number;
    ts_score: number;
  }>(sql`
    SELECT DISTINCT
      c.id, ${localizedSummary} AS summary, c.claim_type, c.claim_kind, c.claim_kind_review_status,
      c.impact_score, c.confidence_score,
      ts_rank(
        to_tsvector(${ftsConfig}, ${localizedSummary}),
        plainto_tsquery(${ftsConfig}, ${textQuery})
      ) AS ts_score
    FROM claims c
    ${translationJoin}
    LEFT JOIN claim_top_domains ctd ON ctd.claim_id = c.id
    LEFT JOIN claim_metadata    cm  ON cm.claim_id  = c.id
    WHERE c.status = 'approved'
      ${topDomainFilter}
      ${excludedTopDomainFilter}
      ${docClassFilter}
      ${timeFilter}
      ${processStageFilter}
      ${excludedEntityTypeFilter}
      ${requiredEntityFilter}
    ORDER BY ts_score DESC, c.impact_score DESC
    LIMIT ${limit}
  `);

  return rows.map((r) => ({
    id: r.id,
    summary: r.summary,
    claimType: r.claim_type,
    claimKind: r.claim_kind,
    claimKindReviewStatus: r.claim_kind_review_status,
    impactScore: r.impact_score,
    confidenceScore: r.confidence_score,
    // `distance` is PATH-DEPENDENT and must NOT be cross-thresholded against
    // the hybrid path: there it is cosine vec_dist, here it is an approximate
    // 1 - ts_score (clamped to >= 0, since ts_rank can exceed 1 and would
    // otherwise yield a negative distance). Lower ts_score → higher distance.
    distance: Math.max(0, 1 - r.ts_score),
  }));
}

/** Fetch the current Markdown for a small set of brain sections. */
export async function getBrainSectionSnippets(
  db: Db,
  sectionIds: string[],
): Promise<Array<{ sectionId: string; title: string; markdown: string }>> {
  if (sectionIds.length === 0) return [];
  // Brain synthesis is English-only (china_imp.md decision), so no per-locale
  // rendering here — return the canonical markdown.
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
      departments: employees.departments,
    })
    .from(channelParticipants)
    .innerJoin(employees, eq(employees.id, channelParticipants.employeeId))
    .where(eq(channelParticipants.channelId, channelId));

  if (members.length === 0) return [];

  const employeeIds = members.map((m) => m.employeeId);
  // Flatten all departments from all channel members (both old and new fields).
  const departments = Array.from(new Set(
    members.flatMap((m) =>
      m.departments.length > 0
        ? m.departments
        : m.department ? [m.department] : [],
    ),
  ));

  return db
    .select()
    .from(gaps)
    .where(
      and(
        inArray(gaps.status, ['open', 'queued', 'asked']),
        or(
          inArray(gaps.targetEmployeeId, employeeIds),
          departments.length > 0
            ? inArray(gaps.targetDepartment, departments)
            : undefined,
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
