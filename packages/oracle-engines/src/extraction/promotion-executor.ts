/**
 * R6 — Promotion executor.
 *
 * Turns a `PromotionDecision` (from R5's `decidePromotion`) into actual
 * Drizzle inserts inside a single transaction. Uses
 * `pg_try_advisory_xact_lock(hashtextextended($1, 0))` to serialize
 * concurrent workers racing for the same candidate hash.
 *
 * Spec: docs/oracle/03-candidate-before-claim-validation.md
 * "Candidate promotion transaction (Concurrency Locked)" — implementation
 * of the PROMOTION_TRANSACTION_RUNBOOK from R5's promote-candidate.ts.
 *
 * Failure semantics:
 *
 *   - If the advisory lock can't be acquired, the executor throws
 *     `AdvisoryLockBusyError`. The worker should catch this and either
 *     retry after backoff or move on to the next candidate.
 *
 *   - If the candidate decision is `reject`, the executor records a
 *     `promotion_transaction` validation result row and updates the
 *     candidate status (without inserting a claim).
 *
 *   - Any DB error during the inserts rolls the whole transaction back.
 *     The advisory lock is automatically released at rollback because it's
 *     an *xact* lock.
 *
 * The executor uses the `db.transaction(...)` callback shape from
 * `drizzle-orm/postgres-js`, so it works with the existing
 * `getDirectDb()` / `getPooledDb()` clients in @oracle/db.
 */

import { and, eq, isNotNull, sql } from 'drizzle-orm';
import {
  claims,
  claimEvidence,
  claimEntities,
  claimMetadata,
  claimTopDomains,
  entityProposals,
  extractionCandidates,
  extractionValidationResults,
  type OracleDb,
} from '@oracle/db';
import { decidePromotion, type CandidateSnapshot, type PromotionDecision } from './promote-candidate';

export class AdvisoryLockBusyError extends Error {
  constructor(public readonly candidateHash: string) {
    super(
      `Could not acquire advisory lock for candidate hash ${candidateHash.slice(0, 12)}…. Another worker is promoting this candidate; back off and retry.`,
    );
    this.name = 'AdvisoryLockBusyError';
  }
}

/**
 * Inputs to executePromotion.
 *
 * R7+ shape: the caller supplies the snapshot *without* `existingClaimWithSameHash`
 * and *without* having called `decidePromotion` yet. The executor:
 *   1. Acquires the advisory lock inside the transaction.
 *   2. Looks up any existing claim with the same `candidate_hash` (the
 *      partial UNIQUE index in 14_claims_candidate_hash_unique.sql means
 *      at most one will be found).
 *   3. Calls `decidePromotion` with the snapshot + existing-claim lookup.
 *   4. Applies the decision.
 *
 * This is the race-safe pattern: the hash lookup and the insert happen
 * inside the same advisory-locked transaction, so two concurrent workers
 * with the same hash can't both succeed at "insert_new_claim". One will
 * win; the other will see the existing claim and append.
 *
 * The legacy R6 pre-built-decision shape is preserved on `decision` for
 * callers that still want to make the decision themselves — but the new
 * snapshot-based path is preferred.
 */
export interface ExecutePromotionInput {
  db: OracleDb;
  candidateId: string;
  candidateHash: string;
  /**
   * Either supply a pre-built `decision` (legacy R6 shape) OR a
   * `snapshotInputs` (R7 shape) that lets the executor look up existing
   * claims by hash inside the transaction and decide race-safely.
   */
  decision?: PromotionDecision;
  snapshotInputs?: Omit<CandidateSnapshot, 'existingClaimWithSameHash'>;
  /** Used to stamp entity_proposals rows with provenance. */
  modelRunId?: string;
}

export interface ExecutePromotionResult {
  /** What the executor actually did. May differ from decision.kind if e.g. an entity_proposals stage was the only outcome. */
  outcome:
    | 'inserted_new_claim'
    | 'appended_to_existing_claim'
    | 'recorded_rejection';
  claimId?: string;
  appendedEvidenceCount?: number;
  stagedEntityProposalIds: string[];
  /** The decision the executor actually applied (after the in-lock re-decide if applicable). */
  appliedDecision: PromotionDecision;
}

/**
 * Execute a promotion against the live DB.
 *
 * R7 pattern (preferred): pass `snapshotInputs`. The executor takes the
 * advisory lock, looks up `claims WHERE candidate_hash = $hash` inside
 * the transaction, and calls `decidePromotion` with the race-safe view.
 *
 * Legacy R6 pattern: pass a pre-built `decision`. The executor still
 * looks up the existing claim and will UPGRADE an `insert_new_claim`
 * decision to `append_to_existing_claim` if a race is detected — but
 * a `reject` or `append_to_existing_claim` decision is honored as-is.
 */
export async function executePromotion(input: ExecutePromotionInput): Promise<ExecutePromotionResult> {
  const { db, candidateId, candidateHash, modelRunId } = input;
  if (!input.decision && !input.snapshotInputs) {
    throw new Error('executePromotion requires either `decision` or `snapshotInputs`.');
  }

  return db.transaction(async (tx) => {
    // 1. Advisory lock. pg_try_advisory_xact_lock returns FALSE if another
    //    transaction holds it. We refuse to block.
    const lockRes = await tx.execute<{ locked: boolean }>(
      sql`SELECT pg_try_advisory_xact_lock(hashtextextended(${candidateHash}, 0)) AS locked`,
    );
    // postgres-js result rows can be in `rows` or be the array itself depending
    // on driver build — handle both shapes.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rows: Array<{ locked: boolean }> = (lockRes as any).rows ?? (lockRes as any);
    const locked = rows[0]?.locked === true;
    if (!locked) throw new AdvisoryLockBusyError(candidateHash);

    // 2. Race-safe hash lookup. Even if the caller pre-built a decision,
    // we double-check inside the lock — another worker may have committed
    // a claim with the same hash between the caller's decide and our
    // execute. The partial UNIQUE on claims.candidate_hash means at most
    // one row matches.
    const existingByHash = await tx
      .select({ id: claims.id })
      .from(claims)
      .where(and(eq(claims.candidateHash, candidateHash), isNotNull(claims.candidateHash)))
      .limit(1);
    const existingClaimWithSameHash =
      existingByHash[0] ? { claimId: existingByHash[0].id } : null;

    // 3. Decide. The R7 path always re-decides inside the lock with the
    // freshly-looked-up existing claim. The legacy R6 path provided a
    // decision; we upgrade insert_new_claim → append_to_existing_claim
    // if a race was detected, but otherwise honor the pre-built decision.
    let decision: PromotionDecision;
    if (input.snapshotInputs) {
      decision = decidePromotion({
        ...input.snapshotInputs,
        existingClaimWithSameHash,
      });
    } else {
      const provided = input.decision!;
      if (
        existingClaimWithSameHash &&
        provided.kind === 'insert_new_claim'
      ) {
        // Race detected — convert to an append.
        decision = {
          kind: 'append_to_existing_claim',
          candidateHash: provided.candidateHash,
          existingClaimId: existingClaimWithSameHash.claimId,
          entityAssignments: provided.entityAssignments,
          entityProposalsToStage: provided.entityProposalsToStage,
          evidenceRows: provided.evidenceRows,
          candidateUpdate: {
            status: 'duplicate',
            setDuplicateOfClaimId: existingClaimWithSameHash.claimId,
          },
        };
      } else {
        decision = provided;
      }
    }

    // 4. Stage any entity_proposals first — they're useful to admin
    //    regardless of which decision branch we take.
    const stagedEntityProposalIds: string[] = [];
    const proposalsToStage =
      decision.kind === 'insert_new_claim' || decision.kind === 'append_to_existing_claim'
        ? decision.entityProposalsToStage
        : (decision.entityProposalsToStage ?? []);

    for (const proposal of proposalsToStage) {
      const inserted = await tx
        .insert(entityProposals)
        .values({
          proposedEntityType: proposal.proposedEntityType,
          proposedCanonicalValue: proposal.proposedCanonicalValue,
          rawStringsObserved: [proposal.rawString],
          observedInSourceType: 'claim_candidate',
          observedInSourceId: candidateId,
          status: 'pending',
          mergedIntoEntityId: proposal.matchedEntityId ?? null,
          proposedByModelRunId: modelRunId ?? null,
        })
        .returning({ id: entityProposals.id });
      const id = inserted[0]?.id;
      if (id) stagedEntityProposalIds.push(id);
    }

    // 3. Branch on the decision.
    switch (decision.kind) {
      case 'insert_new_claim': {
        const [newClaim] = await tx
          .insert(claims)
          .values({
            claimType: decision.claim.claimType,
            summary: decision.claim.summary,
            impactScore: decision.claim.impactScore,
            confidenceScore: decision.claim.confidenceScore ?? 5,
            status: 'pending_review',
            candidateHash, // R7 — enables historical duplicate detection
          })
          .returning({ id: claims.id });
        if (!newClaim) throw new Error('claims insert returned no row');
        const claimId = newClaim.id;

        if (decision.topDomainAssignments.length > 0) {
          await tx
            .insert(claimTopDomains)
            .values(
              decision.topDomainAssignments.map((a) => ({
                claimId,
                topDomainId: a.topDomainId,
                assignmentReason: a.assignmentReason,
              })),
            )
            .onConflictDoNothing();
        }

        if (decision.entityAssignments.length > 0) {
          await tx
            .insert(claimEntities)
            .values(
              decision.entityAssignments.map((e) => ({
                claimId,
                entityId: e.entityId,
              })),
            )
            .onConflictDoNothing();
        }

        if (decision.metadata) {
          await tx.insert(claimMetadata).values({
            claimId,
            processStage: decision.metadata.processStage ?? null,
            department: decision.metadata.department ?? null,
            geography: decision.metadata.geography ?? null,
            documentClass: decision.metadata.documentClass ?? null,
            effectiveFrom: decision.metadata.effectiveFrom ?? null,
            effectiveUntil: decision.metadata.effectiveUntil ?? null,
          });
        }

        if (decision.evidenceRows.length > 0) {
          await tx.insert(claimEvidence).values(
            decision.evidenceRows.map((e) => ({
              claimId,
              sourceType: e.sourceType,
              sourceMessageId: e.sourceMessageId ?? null,
              sourceDocumentChunkId: e.sourceDocumentChunkId ?? null,
              sourceExternalRecordId: e.sourceExternalRecordId ?? null,
              assertedByEmployeeId: e.assertedByEmployeeId ?? null,
              uploadedByEmployeeId: e.uploadedByEmployeeId ?? null,
              createdByEmployeeId: e.createdByEmployeeId ?? null,
              exactQuote: e.validatedExactQuote,
              charStart: e.validatedCharStart,
              charEnd: e.validatedCharEnd,
              pageNumber: e.pageNumber ?? null,
              confidence: e.confidence ?? null,
            })),
          );
        }

        await tx
          .update(extractionCandidates)
          .set({
            status: 'promoted',
            promotedToClaimId: claimId,
            promotedAt: new Date(),
            validatedAt: new Date(),
          })
          .where(eq(extractionCandidates.id, candidateId));

        await tx.insert(extractionValidationResults).values({
          candidateId,
          checkName: 'promotion_transaction',
          status: 'pass',
          detail: `Inserted claim ${claimId}, ${decision.topDomainAssignments.length} top-domain rows, ${decision.entityAssignments.length} entity rows, ${decision.evidenceRows.length} evidence rows.`,
        });

        return {
          outcome: 'inserted_new_claim',
          claimId,
          stagedEntityProposalIds,
          appliedDecision: decision,
        };
      }

      case 'append_to_existing_claim': {
        const claimId = decision.existingClaimId;

        if (decision.entityAssignments.length > 0) {
          await tx
            .insert(claimEntities)
            .values(
              decision.entityAssignments.map((e) => ({
                claimId,
                entityId: e.entityId,
              })),
            )
            .onConflictDoNothing();
        }

        let appendedEvidenceCount = 0;
        if (decision.evidenceRows.length > 0) {
          await tx.insert(claimEvidence).values(
            decision.evidenceRows.map((e) => ({
              claimId,
              sourceType: e.sourceType,
              sourceMessageId: e.sourceMessageId ?? null,
              sourceDocumentChunkId: e.sourceDocumentChunkId ?? null,
              sourceExternalRecordId: e.sourceExternalRecordId ?? null,
              assertedByEmployeeId: e.assertedByEmployeeId ?? null,
              uploadedByEmployeeId: e.uploadedByEmployeeId ?? null,
              createdByEmployeeId: e.createdByEmployeeId ?? null,
              exactQuote: e.validatedExactQuote,
              charStart: e.validatedCharStart,
              charEnd: e.validatedCharEnd,
              pageNumber: e.pageNumber ?? null,
              confidence: e.confidence ?? null,
            })),
          );
          appendedEvidenceCount = decision.evidenceRows.length;
        }

        await tx
          .update(extractionCandidates)
          .set({
            status: 'duplicate',
            duplicateOfClaimId: claimId,
            promotedAt: new Date(),
            validatedAt: new Date(),
          })
          .where(eq(extractionCandidates.id, candidateId));

        await tx.insert(extractionValidationResults).values({
          candidateId,
          checkName: 'duplicate_promotion_lock',
          status: 'pass',
          detail: `Appended ${appendedEvidenceCount} evidence rows + ${decision.entityAssignments.length} entity assignments to existing claim ${claimId}.`,
        });

        return {
          outcome: 'appended_to_existing_claim',
          claimId,
          appendedEvidenceCount,
          stagedEntityProposalIds,
          appliedDecision: decision,
        };
      }

      case 'reject': {
        // Map decision.reason → candidate.status. validated_loop and
        // already_promoted leave candidate.status alone (already terminal).
        let newCandidateStatus: string | undefined;
        switch (decision.reason) {
          case 'taxonomy_invalid':
            newCandidateStatus = 'validation_failed';
            break;
          case 'no_validated_evidence':
          case 'no_domains':
          case 'invalid_state':
            newCandidateStatus = 'validation_failed';
            break;
          case 'not_validated':
          case 'already_promoted':
            newCandidateStatus = undefined;
            break;
        }

        if (newCandidateStatus) {
          await tx
            .update(extractionCandidates)
            .set({
              status: newCandidateStatus,
              validationError: decision.detail,
              validatedAt: new Date(),
            })
            .where(eq(extractionCandidates.id, candidateId));
        }

        await tx.insert(extractionValidationResults).values({
          candidateId,
          checkName: 'promotion_transaction',
          status: 'fail',
          detail: `${decision.reason}: ${decision.detail}`,
          metadataJson: { reason: decision.reason, stagedEntityProposalIds },
        });

        return {
          outcome: 'recorded_rejection',
          stagedEntityProposalIds,
          appliedDecision: decision,
        };
      }
    }
  });
}
