// Write-time fuzzy-dedup for entity_proposals.
//
// Uses pg_trgm similarity (threshold 0.85) to detect near-duplicate proposals
// for the same (entity_type, canonical_value) surface before inserting.
//
// If a sufficiently similar pending/approved proposal exists:
//   → increment proposal_count and append the new rawString to raw_strings_observed.
// If not:
//   → insert a fresh row.
//
// This keeps the admin queue clean as the same unknown entity (e.g. "Disney",
// "Walt Disney", "Disney approvals") gets extracted repeatedly before review.

import { sql } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';

export interface StageEntityProposalArgs {
  proposedEntityType: string;
  proposedCanonicalValue: string;
  rawString: string;
  observedInSourceType: 'claim_candidate' | 'document_chunk';
  observedInSourceId: string;
  proposedByModelRunId: string | null;
}

export async function stageEntityProposal(
  db: OracleDb,
  args: StageEntityProposalArgs,
): Promise<{ action: 'inserted' | 'merged'; proposalId: string }> {
  // Similarity threshold: 0.85 — catches obvious surface-form variants while
  // avoiding false positives between genuinely different entities.
  const SIMILARITY_THRESHOLD = 0.85;

  type ExistingRow = { id: string };

  const existing = await db.execute(sql`
    SELECT id FROM entity_proposals
    WHERE proposed_entity_type = ${args.proposedEntityType}
      AND status IN ('pending', 'approved')
      AND similarity(proposed_canonical_value, ${args.proposedCanonicalValue}) >= ${SIMILARITY_THRESHOLD}
    ORDER BY similarity(proposed_canonical_value, ${args.proposedCanonicalValue}) DESC
    LIMIT 1
  `);

  const existingRow = ([...existing][0] ?? null) as ExistingRow | null;

  if (existingRow) {
    // Merge: increment count, append the new raw string if not already present.
    await db.execute(sql`
      UPDATE entity_proposals
      SET
        proposal_count        = proposal_count + 1,
        raw_strings_observed  = (
          CASE
            WHEN ${args.rawString} IN (SELECT jsonb_array_elements_text(raw_strings_observed))
            THEN raw_strings_observed
            ELSE raw_strings_observed || to_jsonb(${args.rawString}::text)
          END
        )
      WHERE id = ${existingRow.id}
    `);
    return { action: 'merged', proposalId: existingRow.id };
  }

  // Insert fresh proposal.
  type InsertedRow = { id: string };
  const inserted = await db.execute(sql`
    INSERT INTO entity_proposals (
      proposed_entity_type,
      proposed_canonical_value,
      raw_strings_observed,
      observed_in_source_type,
      observed_in_source_id,
      status,
      proposed_by_model_run_id,
      proposal_count
    ) VALUES (
      ${args.proposedEntityType},
      ${args.proposedCanonicalValue},
      ${JSON.stringify([args.rawString])}::jsonb,
      ${args.observedInSourceType},
      ${args.observedInSourceId}::uuid,
      'pending',
      ${args.proposedByModelRunId ? sql`${args.proposedByModelRunId}::uuid` : sql`NULL`},
      1
    )
    RETURNING id
  `);

  const insertedRow = ([...inserted][0] ?? null) as InsertedRow | null;
  if (!insertedRow) throw new Error('[stageEntityProposal] INSERT returned no row');

  return { action: 'inserted', proposalId: insertedRow.id };
}
