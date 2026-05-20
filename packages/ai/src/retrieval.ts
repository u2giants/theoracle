// Retrieval helpers for the live chat route.
//
// Spec 9.1 constraint: every chat turn fetches only
//   * recent N messages from the channel
//   * the current employee's profile
//   * top K open gaps relevant to this employee / department
//   * top K semantically relevant approved claims (cosine via pgvector)
//
// Do NOT load full brain sections — Phase 6 will pull section excerpts only when
// the search_company_knowledge tool fires.

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
