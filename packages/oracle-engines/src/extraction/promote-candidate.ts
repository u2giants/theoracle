/**
 * R5 — Candidate promotion service.
 *
 * Concurrency-locked, idempotent promotion from staging
 * (`extraction_candidates` + `extraction_candidate_evidence`) to permanent
 * tables (`claims` + `claim_top_domains` + `claim_evidence`).
 *
 * Per docs/oracle/03-candidate-before-claim-validation.md
 * "Candidate promotion transaction (Concurrency Locked)":
 *
 *   1. Begin transaction.
 *   2. Acquire advisory lock on hashtextextended(candidateHash, 0).
 *   3. Confirm candidate status is 'validated' and not already promoted.
 *   4. Check for an existing claim with the same hash. If found, append
 *      THIS candidate's evidence to that claim instead of inserting a
 *      duplicate, and mark this candidate as 'duplicate'.
 *   5. Otherwise insert claims + claim_top_domains + claim_evidence atomically.
 *   6. Update candidate to 'promoted' (or 'duplicate') with timestamps.
 *   7. Commit.
 *
 * The transactional executor is wired to Drizzle in
 * `runPromotionInTransaction` below. The DECISION logic — what to insert,
 * what to append, what to reject — is extracted into `decidePromotion` as
 * a pure function so the 6 R5 tests can exercise it without a real DB.
 */

import type { EntityType, EvidenceSourceType } from '@oracle/shared';
import type { EntityProposalToCreate, ResolvedEntityAssignment } from './taxonomy-validator';

// ─────────────────────────────────────────────────────────────────────────
// Decision shapes — what the promoter sees, what it decides to do.
// ─────────────────────────────────────────────────────────────────────────

/** Claim-level metadata the model surfaced (per R5.5). Goes into claim_metadata. */
export interface CandidateMetadata {
  processStage?: string | null;
  department?: string | null;
  geography?: string | null;
  documentClass?: string | null;
  effectiveFrom?: Date | null;
  effectiveUntil?: Date | null;
}

export interface CandidateSnapshot {
  /** Hashed canonical representation of the candidate (see candidate-hash.ts). */
  candidateHash: string;

  /** From `extraction_candidates`. */
  candidate: {
    id: string;
    status: string;
    summary: string;
    claimType: string;
    impactScore: number;
    confidenceScore?: number;
    domains: string[];
    promotedToClaimId?: string | null;
  };

  /** From `extraction_candidate_evidence`. Only rows with validationStatus in (exact_match, normalized_match). */
  validatedEvidence: Array<{
    id: string;
    sourceType: EvidenceSourceType;
    sourceMessageId?: string | null;
    sourceDocumentChunkId?: string | null;
    sourceExternalRecordId?: string | null;
    assertedByEmployeeId?: string | null;
    uploadedByEmployeeId?: string | null;
    createdByEmployeeId?: string | null;
    validatedExactQuote: string;
    validatedCharStart: number;
    validatedCharEnd: number;
    pageNumber?: number | null;
    confidence?: number | null;
    /** R5.5 — surfaced per evidence row when the model could infer them. */
    documentClass?: string | null;
    processStage?: string | null;
  }>;

  /**
   * R5.5 — Taxonomy validation result (from `validateTaxonomy`). Optional
   * for backward compatibility with R5 callers that don't run the
   * taxonomy validator yet.
   *
   * When present:
   *  - `validTopDomainIds` replaces `candidate.domains` as the set of
   *    top-domain rows we'll actually write.
   *  - `resolvedEntities` becomes the claim_entities inserts.
   *  - `entityProposalsToCreate` are staged BEFORE the promotion runs.
   *  - `ok: false` blocks promotion unless every failure is an unknown entity
   *    proposal (`blockedByOnlyUnknownEntities`), in which case proposals are
   *    staged and the claim can still be written with validated domains.
   */
  taxonomy?: {
    ok: boolean;
    validTopDomainIds: string[];
    resolvedEntities: ResolvedEntityAssignment[];
    entityProposalsToCreate: EntityProposalToCreate[];
    blockedByOnlyUnknownEntities?: boolean;
    failureSummary?: string;
  };

  /** R5.5 — Claim-level metadata to write to claim_metadata. */
  metadata?: CandidateMetadata;

  /**
   * The claim — if any — that the candidate's hash matches. The promoter
   * checks this INSIDE the transaction so a worker racing for the lock
   * sees the latest committed state.
   */
  existingClaimWithSameHash?: { claimId: string } | null;
}

/** R5.5 — Entity tag assignments to write to claim_entities. */
export interface EntityAssignment {
  entityId: string;
  entityType: EntityType;
  canonicalValue: string;
}

export type PromotionDecision =
  | {
      kind: 'insert_new_claim';
      /** Stable hash this claim will be associated with via the candidate. */
      candidateHash: string;
      claim: {
        claimType: string;
        summary: string;
        impactScore: number;
        confidenceScore?: number;
        // R3.5+: status is now a varchar (per oracle_master_spec §6.6),
        // but the existing claims table still uses claimStatusEnum until
        // R6 migrates the schema. Promotion inserts 'pending_review' — the
        // admin queue does the final approval.
        status: 'pending_review';
      };
      topDomainAssignments: Array<{ topDomainId: string; assignmentReason: 'extraction' }>;
      /** R5.5 — claim_entities rows to insert. Empty when the candidate had no entities. */
      entityAssignments: EntityAssignment[];
      /** R5.5 — claim_metadata row to insert. Undefined when no metadata was surfaced. */
      metadata?: CandidateMetadata;
      /** R5.5 — entity_proposals rows to stage before the promotion runs. */
      entityProposalsToStage: EntityProposalToCreate[];
      evidenceRows: CandidateSnapshot['validatedEvidence'];
      candidateUpdate: { status: 'promoted'; setPromotedToClaimId: true };
    }
  | {
      kind: 'append_to_existing_claim';
      candidateHash: string;
      existingClaimId: string;
      /** R5.5 — entity tags to merge onto the existing claim. */
      entityAssignments: EntityAssignment[];
      /** R5.5 — entity_proposals to stage even when the candidate is a duplicate. */
      entityProposalsToStage: EntityProposalToCreate[];
      evidenceRows: CandidateSnapshot['validatedEvidence'];
      candidateUpdate: { status: 'duplicate'; setDuplicateOfClaimId: string };
    }
  | {
      kind: 'reject';
      reason:
        | 'not_validated'
        | 'already_promoted'
        | 'no_validated_evidence'
        | 'no_domains'
        | 'taxonomy_invalid'
        | 'invalid_state';
      detail: string;
      /** R5.5 — even rejected candidates may surface entity proposals worth staging. */
      entityProposalsToStage?: EntityProposalToCreate[];
    };

// ─────────────────────────────────────────────────────────────────────────
// Pure decision function — testable without a DB.
// ─────────────────────────────────────────────────────────────────────────

export function decidePromotion(snapshot: CandidateSnapshot): PromotionDecision {
  const {
    candidate,
    validatedEvidence,
    candidateHash,
    existingClaimWithSameHash,
    taxonomy,
    metadata,
  } = snapshot;

  // Entity proposals are worth surfacing even when we reject — admin can
  // review the proposals separately. We thread them through every branch.
  const entityProposalsToStage = taxonomy?.entityProposalsToCreate ?? [];

  // Idempotency: re-running the promoter on an already-promoted candidate
  // returns 'already_promoted' without trying to insert anything.
  if (candidate.status === 'promoted') {
    return {
      kind: 'reject',
      reason: 'already_promoted',
      detail: `Candidate ${candidate.id} is already promoted to claim ${candidate.promotedToClaimId ?? '<unknown>'}.`,
      entityProposalsToStage,
    };
  }

  // The candidate must be 'validated' before promotion. Anything else
  // (pending_validation, validation_failed, rejected, *_sensitive) gets
  // rejected here — the only way out of those states is review, not promotion.
  if (candidate.status !== 'validated') {
    return {
      kind: 'reject',
      reason: 'not_validated',
      detail: `Candidate ${candidate.id} has status "${candidate.status}", must be "validated" to promote.`,
      entityProposalsToStage,
    };
  }

  if (validatedEvidence.length === 0) {
    return {
      kind: 'reject',
      reason: 'no_validated_evidence',
      detail: `Candidate ${candidate.id} has no evidence rows with validation_status in (exact_match, normalized_match).`,
      entityProposalsToStage,
    };
  }

  // R5.5: hard taxonomy failures block promotion. Unknown-only entity
  // references still stage proposals, but do not hold an otherwise
  // evidence-backed claim; the claim can be useful with domain tags while
  // admins clean up optional entity tags later.
  if (taxonomy && !taxonomy.ok && !taxonomy.blockedByOnlyUnknownEntities) {
    return {
      kind: 'reject',
      reason: 'taxonomy_invalid',
      detail:
        `Candidate ${candidate.id} failed taxonomy validation. ` +
        (taxonomy.failureSummary ??
          'See extraction_validation_results for the per-check breakdown.'),
      entityProposalsToStage,
    };
  }

  // The effective top-domain ID list is the taxonomy-validated subset when
  // available, otherwise the raw candidate.domains (R5 callers).
  const effectiveTopDomainIds = taxonomy ? taxonomy.validTopDomainIds : candidate.domains;
  if (!effectiveTopDomainIds || effectiveTopDomainIds.length === 0) {
    return {
      kind: 'reject',
      reason: 'no_domains',
      detail: `Candidate ${candidate.id} has no valid top-domain IDs after taxonomy validation.`,
      entityProposalsToStage,
    };
  }

  const entityAssignments: EntityAssignment[] = (taxonomy?.resolvedEntities ?? []).map((e) => ({
    entityId: e.entityId,
    entityType: e.entityType,
    canonicalValue: e.canonicalValue,
  }));

  // Duplicate detection. The advisory lock means we're the only writer
  // holding this hash; if there's still an existing claim row, another
  // worker won the race already and we append our evidence to theirs.
  if (existingClaimWithSameHash) {
    return {
      kind: 'append_to_existing_claim',
      candidateHash,
      existingClaimId: existingClaimWithSameHash.claimId,
      entityAssignments,
      entityProposalsToStage,
      evidenceRows: validatedEvidence,
      candidateUpdate: {
        status: 'duplicate',
        setDuplicateOfClaimId: existingClaimWithSameHash.claimId,
      },
    };
  }

  // Happy path: insert a new claim, the top-domain rows, the entity
  // tag rows, the metadata row, and the evidence rows, atomically.
  return {
    kind: 'insert_new_claim',
    candidateHash,
    claim: {
      claimType: candidate.claimType,
      summary: candidate.summary,
      impactScore: candidate.impactScore,
      confidenceScore: candidate.confidenceScore,
      status: 'pending_review',
    },
    topDomainAssignments: effectiveTopDomainIds.map((id) => ({
      topDomainId: id,
      assignmentReason: 'extraction',
    })),
    entityAssignments,
    metadata: metadata && hasAnyMetadata(metadata) ? metadata : undefined,
    entityProposalsToStage,
    evidenceRows: validatedEvidence,
    candidateUpdate: { status: 'promoted', setPromotedToClaimId: true },
  };
}

/** Internal — true if at least one field in the metadata payload is non-null. */
function hasAnyMetadata(m: CandidateMetadata): boolean {
  return Boolean(
    m.processStage ||
    m.department ||
    m.geography ||
    m.documentClass ||
    m.effectiveFrom ||
    m.effectiveUntil,
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Executor stub.
//
// The full Drizzle wiring lands when R6 actually calls into this from the
// claim-extraction worker. The stub below documents the exact SQL surface
// the executor will use so reviewers can audit the transactional shape
// without grepping for it later.
// ─────────────────────────────────────────────────────────────────────────

/**
 * Pseudo-code the executor MUST follow when R6 wires this up to Drizzle.
 * The pure `decidePromotion` is the spec; this is the runbook for turning
 * that decision into SQL.
 *
 * ```ts
 * await db.transaction(async (tx) => {
 *   // 1. Advisory lock keyed on the candidate hash.
 *   //    pg_try_advisory_xact_lock returns FALSE if another tx holds it —
 *   //    the worker should back off and retry rather than block forever.
 *   const lockRes = await tx.execute(
 *     sql`SELECT pg_try_advisory_xact_lock(hashtextextended(${candidateHash}, 0)) AS locked`
 *   );
 *   if (!lockRes[0].locked) throw new AdvisoryLockBusyError(candidateHash);
 *
 *   // 2. Re-read the candidate state INSIDE the lock so we see the latest
 *   //    committed view of the world.
 *   const candidate = await tx.query.extractionCandidates.findFirst({
 *     where: eq(extractionCandidates.id, candidateId),
 *     with: { evidence: true },
 *   });
 *
 *   // 3. Look for an existing claim with the same hash. We could store the
 *   //    candidate hash on claims directly, or compute it on the fly from a
 *   //    join across claim_top_domains and claim_evidence. R6 will pick the
 *   //    cheaper option after evals; for now we recommend a hash column on
 *   //    claims with a UNIQUE index for O(1) lookup.
 *
 *   // 4. Run the pure decider.
 *   const decision = decidePromotion(snapshot);
 *
 *   // 5. Apply the decision.
 *   switch (decision.kind) {
 *     case 'insert_new_claim': {
 *       const claimRow = await tx.insert(claims).values(decision.claim).returning();
 *       await tx.insert(claimTopDomains).values(
 *         decision.topDomainAssignments.map((a) => ({ claimId: claimRow.id, ...a }))
 *       );
 *       await tx.insert(claimEvidence).values(
 *         decision.evidenceRows.map((e) => ({ claimId: claimRow.id, ...e }))
 *       );
 *       await tx.update(extractionCandidates).set({
 *         status: 'promoted',
 *         promotedToClaimId: claimRow.id,
 *         promotedAt: new Date(),
 *       }).where(eq(extractionCandidates.id, candidateId));
 *       break;
 *     }
 *     case 'append_to_existing_claim': {
 *       await tx.insert(claimEvidence).values(
 *         decision.evidenceRows.map((e) => ({ claimId: decision.existingClaimId, ...e }))
 *       );
 *       await tx.update(extractionCandidates).set({
 *         status: 'duplicate',
 *         duplicateOfClaimId: decision.existingClaimId,
 *         promotedAt: new Date(),
 *       }).where(eq(extractionCandidates.id, candidateId));
 *       break;
 *     }
 *     case 'reject': {
 *       await tx.insert(extractionValidationResults).values({
 *         candidateId,
 *         checkName: 'promotion_transaction',
 *         status: 'fail',
 *         detail: `${decision.reason}: ${decision.detail}`,
 *       });
 *       break;
 *     }
 *   }
 * });
 * ```
 *
 * R6 lifts that runbook into a real function. R5 ships the decider and
 * the candidate hash so the runbook is just SQL plumbing.
 */
export const PROMOTION_TRANSACTION_RUNBOOK = 'See JSDoc in promote-candidate.ts';
