import { and, eq, inArray, sql } from 'drizzle-orm';
import {
  claims,
  macroRelationshipClaims,
  macroRelationships,
  type OracleDb,
} from '@oracle/db';

export type ApprovedMacroRelationship = {
  id: string;
  relationshipType: string;
  summary: string;
  impactScore: number;
  confidenceScore: number;
  supportClaims: Array<{
    id: string;
    summary: string;
    claimType: string;
    claimKind: string | null;
    supportRole: string;
  }>;
};

export async function getApprovedMacroRelationships(args: {
  db: OracleDb;
  domainIds?: string[];
  claimIds?: string[];
  limit?: number;
}): Promise<ApprovedMacroRelationship[]> {
  const limit = args.limit ?? 25;
  const domainFilter =
    args.domainIds && args.domainIds.length > 0
      ? sql`AND EXISTS (
          SELECT 1
          FROM macro_relationship_claims mrc_domain
          JOIN claim_top_domains ctd ON ctd.claim_id = mrc_domain.claim_id
          WHERE mrc_domain.macro_relationship_id = mr.id
            AND ctd.top_domain_id IN (
              SELECT jsonb_array_elements_text(${JSON.stringify(args.domainIds)}::jsonb)
            )
        )`
      : sql``;
  const claimFilter =
    args.claimIds && args.claimIds.length > 0
      ? sql`AND EXISTS (
          SELECT 1
          FROM macro_relationship_claims mrc_filter
          WHERE mrc_filter.macro_relationship_id = mr.id
            AND mrc_filter.claim_id IN (
              SELECT x.value::uuid
              FROM jsonb_array_elements_text(${JSON.stringify(args.claimIds)}::jsonb) AS x(value)
            )
        )`
      : sql``;

  const rows = await args.db.execute(sql`
    SELECT
      mr.id,
      mr.relationship_type,
      mr.summary,
      mr.impact_score,
      mr.confidence_score
    FROM macro_relationships mr
    WHERE mr.status = 'approved'
      ${domainFilter}
      ${claimFilter}
      AND NOT EXISTS (
        SELECT 1
        FROM macro_relationship_claims mrc
        JOIN claims c ON c.id = mrc.claim_id
        WHERE mrc.macro_relationship_id = mr.id
          AND c.status <> 'approved'
      )
    ORDER BY mr.impact_score DESC, mr.confidence_score DESC, mr.created_at DESC
    LIMIT ${limit}
  `);

  const relationshipRows = [...rows] as Array<{
    id: string;
    relationship_type: string;
    summary: string;
    impact_score: number;
    confidence_score: number;
  }>;
  if (relationshipRows.length === 0) return [];

  const supportRows = await args.db
    .select({
      relationshipId: macroRelationshipClaims.macroRelationshipId,
      supportRole: macroRelationshipClaims.supportRole,
      claimId: claims.id,
      summary: claims.summary,
      claimType: claims.claimType,
      claimKind: claims.claimKind,
    })
    .from(macroRelationshipClaims)
    .innerJoin(claims, eq(claims.id, macroRelationshipClaims.claimId))
    .where(
      and(
        inArray(
          macroRelationshipClaims.macroRelationshipId,
          relationshipRows.map((row) => row.id),
        ),
        eq(claims.status, 'approved'),
      ),
    );

  const supportByRelationship = new Map<string, ApprovedMacroRelationship['supportClaims']>();
  for (const row of supportRows) {
    const list = supportByRelationship.get(row.relationshipId) ?? [];
    list.push({
      id: row.claimId,
      summary: row.summary,
      claimType: row.claimType,
      claimKind: row.claimKind,
      supportRole: row.supportRole,
    });
    supportByRelationship.set(row.relationshipId, list);
  }

  return relationshipRows.map((row) => ({
    id: row.id,
    relationshipType: row.relationship_type,
    summary: row.summary,
    impactScore: row.impact_score,
    confidenceScore: row.confidence_score,
    supportClaims: supportByRelationship.get(row.id) ?? [],
  }));
}

export async function markMacroRelationshipsStaleForClaim(args: {
  db: OracleDb;
  claimId: string;
  reason?: string;
}): Promise<number> {
  const before = await args.db
    .select({ id: macroRelationships.id, status: macroRelationships.status })
    .from(macroRelationships)
    .innerJoin(
      macroRelationshipClaims,
      eq(macroRelationshipClaims.macroRelationshipId, macroRelationships.id),
    )
    .where(
      and(
        eq(macroRelationshipClaims.claimId, args.claimId),
        eq(macroRelationships.status, 'approved'),
      ),
    );
  if (before.length === 0) return 0;

  await args.db
    .update(macroRelationships)
    .set({
      status: 'stale_support',
      stalenessReason: args.reason ?? 'support claim left approved status',
      staleSince: new Date(),
      updatedAt: new Date(),
    })
    .where(inArray(macroRelationships.id, before.map((row) => row.id)));

  return before.length;
}

export async function sweepStaleMacroRelationships(db: OracleDb): Promise<number> {
  const rows = await db.execute(sql`
    SELECT DISTINCT mr.id
    FROM macro_relationships mr
    JOIN macro_relationship_claims mrc ON mrc.macro_relationship_id = mr.id
    JOIN claims c ON c.id = mrc.claim_id
    WHERE mr.status = 'approved'
      AND c.status <> 'approved'
  `);
  const staleIds = ([...rows] as Array<{ id: string }>).map((row) => row.id);
  if (staleIds.length === 0) return 0;
  await db
    .update(macroRelationships)
    .set({
      status: 'stale_support',
      stalenessReason: 'support claim left approved status',
      staleSince: new Date(),
      updatedAt: new Date(),
    })
    .where(inArray(macroRelationships.id, staleIds));
  return staleIds.length;
}

export async function requeueMacroRelationshipsReadyForReview(args: {
  db: OracleDb;
  claimId: string;
}): Promise<number> {
  const rows = await args.db.execute(sql`
    SELECT DISTINCT mr.id
    FROM macro_relationships mr
    JOIN macro_relationship_claims mrc_seed ON mrc_seed.macro_relationship_id = mr.id
    WHERE mr.status IN ('blocked_pending_support', 'needs_review')
      AND mrc_seed.claim_id = ${args.claimId}::uuid
      AND NOT EXISTS (
        SELECT 1
        FROM macro_relationship_claims mrc
        JOIN claims c ON c.id = mrc.claim_id
        WHERE mrc.macro_relationship_id = mr.id
          AND c.status <> 'approved'
      )
  `);
  const ids = ([...rows] as Array<{ id: string }>).map((row) => row.id);
  if (ids.length === 0) return 0;
  await args.db
    .update(macroRelationships)
    .set({
      status: 'pending_review',
      stalenessReason: null,
      staleSince: null,
      updatedAt: new Date(),
    })
    .where(inArray(macroRelationships.id, ids));
  return ids.length;
}
