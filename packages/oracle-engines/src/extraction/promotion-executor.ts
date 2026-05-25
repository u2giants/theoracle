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

import { eq, sql } from 'drizzle-orm';
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
import type { PromotionDecision } from './promote-candidate';

export class AdvisoryLockBusyError extends Error {
  constructor(public readonly candidateHash: string) {
    super(
      `Could not acquire advisory lock for candidate hash ${candidateHash.slice(0, 12)}…. Another worker is promoting this candidate; back off and retry.`,
    );
    this.name = 'AdvisoryLockBusyError';
  }
}

export interface ExecutePromotionInput {
  db: OracleDb;
  candidateId: string;
  candidateHash: string;
  decision: PromotionDecision;
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
}

/**
 * Execute a promotion decision against the live DB.
 *
 * Caller MUST run `decidePromotion(...)` first; this function does not
 * re-decide. If the candidate's state changed between the decision and
 * execution (e.g. another worker raced), the executor will see the
 * existing claim row inside the transaction and the caller's decision
 * may be stale — that's why production code re-reads the candidate and
 * re-decides INSIDE the lock. R6's worker follows that pattern.
 */
export async function executePromotion(input: ExecutePromotionInput): Promise<ExecutePromotionResult> {
  const { db, candidateId, candidateHash, decision, modelRunId } = input;

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

    // 2. Stage any entity_proposals first — they're useful to admin
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
        };
      }
    }
  });
}
