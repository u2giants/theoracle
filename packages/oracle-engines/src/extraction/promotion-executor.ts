/**
 * R6/R7 — Promotion executor (race-safe in-lock snapshot version).
 *
 * Turns a validated extraction candidate into permanent
 * `claims` / `claim_top_domains` / `claim_entities` / `claim_metadata` /
 * `claim_evidence` rows inside a single transaction. Uses
 * `pg_try_advisory_xact_lock(hashtextextended($1, 0))` to serialize
 * concurrent workers racing for the same candidate hash.
 *
 * Spec: docs/oracle/03-candidate-before-claim-validation.md
 * "Candidate promotion transaction (Concurrency Locked)".
 *
 * Race-safety scope
 * -----------------
 * After acquiring the advisory lock, the executor re-reads the candidate
 * row AND its validated evidence inside the transaction. The caller's
 * `auxiliaryInputs` (taxonomy validation result + claim metadata) are
 * passed through as-is. This is intentional:
 *
 *   - candidate + evidence: race-safe (re-read inside the lock)
 *   - existing-claim-by-hash lookup: race-safe (executed inside the lock)
 *   - taxonomy validation: NOT race-safe against registry drift
 *     (e.g. a `knowledge_top_domains` row retired between caller-side
 *     `validateTaxonomy()` and executor promotion). Taxonomy mutations
 *     are admin-paced (minutes/hours) via `/admin/taxonomy`, not
 *     worker-paced (ms), so this race window is tolerated until production
 *     traffic shows it actually fires.
 *
 * Failure semantics
 * -----------------
 * - Advisory lock not acquirable → throws `AdvisoryLockBusyError`.
 *   Worker should retry after backoff or move on.
 * - Candidate row missing inside the lock → returns
 *   `recorded_rejection` with reason `invalid_state` WITHOUT writing to
 *   `extraction_validation_results` (the FK target would be missing).
 *   The caller logs the anomaly via `job_runs.error` / `model_runs.error`.
 *   This is the ONLY `reject` branch that skips the validation_results
 *   audit row.
 * - Candidate status != 'validated' (e.g. another worker promoted it,
 *   or sensitivity gate fired) → `reject(already_promoted)` or
 *   `reject(not_validated)` via `decidePromotion` with the FRESH state.
 * - Different candidate already committed a claim with the same hash →
 *   `append_to_existing_claim` (the in-lock hash-lookup branch). The
 *   candidate itself is still 'validated' in the DB; the duplicate is
 *   detected by the `claims.candidate_hash` partial UNIQUE index.
 * - Any DB error during inserts → transaction rolls back; advisory lock
 *   is released automatically (it's an *xact* lock).
 */

import { and, eq, isNotNull, sql } from 'drizzle-orm';
import {
  claims,
  claimEvidence,
  claimEntities,
  claimMetadata,
  claimTopDomains,
  employees,
  entityProposals,
  extractionCandidates,
  extractionCandidateEvidence,
  extractionValidationResults,
  type OracleDb,
} from '@oracle/db';
import { coerceLocale, DEFAULT_LOCALE } from '@oracle/shared';
import { decidePromotion, type CandidateMetadata, type CandidateSnapshot, type PromotionDecision } from './promote-candidate';

export class AdvisoryLockBusyError extends Error {
  constructor(public readonly candidateHash: string) {
    super(
      `Could not acquire advisory lock for candidate hash ${candidateHash.slice(0, 12)}…. Another worker is promoting this candidate; back off and retry.`,
    );
    this.name = 'AdvisoryLockBusyError';
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Row shape types — local mirrors of the @oracle/db schema columns the
// loader SELECTs. Kept local (rather than re-exporting Drizzle row types)
// so the mappers can be unit-tested with hand-built fixtures.
// ─────────────────────────────────────────────────────────────────────────

export interface ExtractionCandidateRow {
  id: string;
  status: string;
  summary: string;
  claim_type: string;
  impact_score: number;
  confidence_score: number | null;
  domains: unknown; // jsonb — array of strings
  promoted_to_claim_id: string | null;
}

export interface ExtractionCandidateEvidenceRow {
  id: string;
  source_type: 'message' | 'document_chunk' | 'external_system' | 'manual_admin';
  source_message_id: string | null;
  source_document_chunk_id: string | null;
  source_external_record_id: string | null;
  asserted_by_employee_id: string | null;
  uploaded_by_employee_id: string | null;
  created_by_employee_id: string | null;
  validation_status: string;
  validated_exact_quote: string | null;
  validated_char_start: number | null;
  validated_char_end: number | null;
  page_number: number | null;
  confidence: number | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Pure mappers — exported for unit testing.
// ─────────────────────────────────────────────────────────────────────────

/**
 * Map a row from `extraction_candidates` into the `CandidateSnapshot.candidate`
 * shape decidePromotion expects.
 *
 * Returns `null` when:
 *   - The row is missing (executor's "candidate vanished inside the lock" path)
 *
 * Pure — no DB access. The caller does the SELECT; this just maps shape.
 */
export function mapCandidateRowToSnapshotCandidate(
  row: ExtractionCandidateRow | undefined | null,
): CandidateSnapshot['candidate'] | null {
  if (!row) return null;
  return {
    id: row.id,
    status: row.status,
    summary: row.summary,
    claimType: row.claim_type,
    impactScore: row.impact_score,
    // NULL must become undefined, not 0. R5 smoke covers this distinction.
    confidenceScore: row.confidence_score == null ? undefined : row.confidence_score,
    // jsonb null defends as []; non-array jsonb (defensive) also defaults to [].
    domains: Array.isArray(row.domains) ? (row.domains as string[]) : [],
    promotedToClaimId: row.promoted_to_claim_id,
  };
}

/**
 * Map a row from `extraction_candidate_evidence` into a
 * `CandidateSnapshot.validatedEvidence` entry.
 *
 * Returns `null` when:
 *   - validation_status is not in ('exact_match', 'normalized_match') —
 *     the evidence didn't pass the R5 quote validator
 *   - any of the validated_* fields is null even though status passed —
 *     defensive against DB rows in an inconsistent state (this shouldn't
 *     exist because of the 13_extraction_constraints.sql
 *     extraction_candidate_evidence_validated_fields_check CHECK, but the
 *     mapper refuses to fabricate values regardless)
 *
 * Pure — no DB access. Callers compose `.map(...).filter((x): x is NonNull => x != null)`.
 */
export function mapEvidenceRowToValidatedEvidence(
  row: ExtractionCandidateEvidenceRow,
): CandidateSnapshot['validatedEvidence'][number] | null {
  if (row.validation_status !== 'exact_match' && row.validation_status !== 'normalized_match') {
    return null;
  }
  if (
    row.validated_exact_quote == null ||
    row.validated_char_start == null ||
    row.validated_char_end == null
  ) {
    return null;
  }
  return {
    id: row.id,
    sourceType: row.source_type,
    sourceMessageId: row.source_message_id,
    sourceDocumentChunkId: row.source_document_chunk_id,
    sourceExternalRecordId: row.source_external_record_id,
    assertedByEmployeeId: row.asserted_by_employee_id,
    uploadedByEmployeeId: row.uploaded_by_employee_id,
    createdByEmployeeId: row.created_by_employee_id,
    validatedExactQuote: row.validated_exact_quote,
    validatedCharStart: row.validated_char_start,
    validatedCharEnd: row.validated_char_end,
    pageNumber: row.page_number,
    confidence: row.confidence,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// In-lock snapshot loader — thin wrapper over the two SELECTs + mappers.
// ─────────────────────────────────────────────────────────────────────────

/**
 * Inside an active transaction (after the advisory lock has been acquired),
 * re-read the candidate row + its validated evidence. The returned shapes
 * are exactly what `decidePromotion` consumes.
 *
 * Generic over the Drizzle tx type so this works with either `OracleDb`
 * or the transaction object passed into the `db.transaction((tx) => ...)`
 * callback.
 */
async function loadCandidateSnapshotInLock(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  tx: any,
  candidateId: string,
): Promise<{
  candidate: CandidateSnapshot['candidate'] | null;
  validatedEvidence: CandidateSnapshot['validatedEvidence'];
}> {
  const candidateRows = await tx
    .select({
      id: extractionCandidates.id,
      status: extractionCandidates.status,
      summary: extractionCandidates.summary,
      claim_type: extractionCandidates.claimType,
      impact_score: extractionCandidates.impactScore,
      confidence_score: extractionCandidates.confidenceScore,
      domains: extractionCandidates.domains,
      promoted_to_claim_id: extractionCandidates.promotedToClaimId,
    })
    .from(extractionCandidates)
    .where(eq(extractionCandidates.id, candidateId))
    .limit(1);

  const candidate = mapCandidateRowToSnapshotCandidate(
    candidateRows[0] as ExtractionCandidateRow | undefined,
  );

  if (!candidate) {
    return { candidate: null, validatedEvidence: [] };
  }

  const evidenceRows = await tx
    .select({
      id: extractionCandidateEvidence.id,
      source_type: extractionCandidateEvidence.sourceType,
      source_message_id: extractionCandidateEvidence.sourceMessageId,
      source_document_chunk_id: extractionCandidateEvidence.sourceDocumentChunkId,
      source_external_record_id: extractionCandidateEvidence.sourceExternalRecordId,
      asserted_by_employee_id: extractionCandidateEvidence.assertedByEmployeeId,
      uploaded_by_employee_id: extractionCandidateEvidence.uploadedByEmployeeId,
      created_by_employee_id: extractionCandidateEvidence.createdByEmployeeId,
      validation_status: extractionCandidateEvidence.validationStatus,
      validated_exact_quote: extractionCandidateEvidence.validatedExactQuote,
      validated_char_start: extractionCandidateEvidence.validatedCharStart,
      validated_char_end: extractionCandidateEvidence.validatedCharEnd,
      page_number: extractionCandidateEvidence.pageNumber,
      confidence: extractionCandidateEvidence.confidence,
    })
    .from(extractionCandidateEvidence)
    .where(eq(extractionCandidateEvidence.candidateId, candidateId));

  const validatedEvidence = (evidenceRows as ExtractionCandidateEvidenceRow[])
    .map((row) => mapEvidenceRowToValidatedEvidence(row))
    .filter((v): v is NonNullable<typeof v> => v != null);

  return { candidate, validatedEvidence };
}

// ─────────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────────

/**
 * Inputs to `executePromotion`.
 *
 * The candidate row, its validated evidence, and the existing-claim-by-hash
 * lookup are ALL re-read inside the advisory lock — callers do NOT pass them.
 *
 * The caller-side fields (`auxiliaryInputs`) carry only the data that isn't
 * reconstructable from candidate-table state:
 *   - `taxonomy`: the R5.5 TaxonomyValidationResult derived from the live
 *     `entities` + `knowledge_top_domains` registries at decision time
 *   - `metadata`: caller-computed claim_metadata fields
 *
 * Registry drift between caller-side validation and executor promotion is
 * intentionally NOT solved here. See the file header "Race-safety scope".
 */
export interface ExecutePromotionInput {
  db: OracleDb;
  candidateId: string;
  candidateHash: string;
  auxiliaryInputs?: {
    taxonomy?: CandidateSnapshot['taxonomy'];
    metadata?: CandidateMetadata;
  };
  /** Stamped on entity_proposals rows for provenance. */
  modelRunId?: string;
}

export interface ExecutePromotionResult {
  outcome: 'inserted_new_claim' | 'appended_to_existing_claim' | 'recorded_rejection';
  claimId?: string;
  appendedEvidenceCount?: number;
  stagedEntityProposalIds: string[];
  /** The decision the executor actually applied (built from the in-lock snapshot). */
  appliedDecision: PromotionDecision;
}

/**
 * Execute a promotion against the live DB.
 *
 * Race-safe pattern:
 *   1. Acquire advisory lock or throw AdvisoryLockBusyError.
 *   2. Re-read candidate + validated evidence INSIDE the lock (the race
 *      window between caller-side reads and lock acquisition is closed).
 *   3. If candidate missing → return invalid_state WITHOUT writing
 *      validation_results (FK target wouldn't exist).
 *   4. Re-look-up existing claim by candidate_hash INSIDE the lock.
 *   5. Build snapshot from fresh DB reads + caller's auxiliaryInputs
 *      (taxonomy + metadata).
 *   6. Call `decidePromotion`.
 *   7. Apply decision (insert / append / reject branches).
 */
export async function executePromotion(input: ExecutePromotionInput): Promise<ExecutePromotionResult> {
  const { db, candidateId, candidateHash, modelRunId } = input;

  return db.transaction(async (tx) => {
    // 1. Advisory lock.
    const lockRes = await tx.execute<{ locked: boolean }>(
      sql`SELECT pg_try_advisory_xact_lock(hashtextextended(${candidateHash}, 0)) AS locked`,
    );
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const lockRows: Array<{ locked: boolean }> = (lockRes as any).rows ?? (lockRes as any);
    if (lockRows[0]?.locked !== true) throw new AdvisoryLockBusyError(candidateHash);

    // 2. Re-read candidate + validated evidence inside the lock.
    const fresh = await loadCandidateSnapshotInLock(tx, candidateId);

    // 3. Missing candidate: return WITHOUT writing extraction_validation_results.
    //    The FK target candidate_id would be missing; we cannot create the
    //    audit row. Caller logs the anomaly via job_runs.error.
    if (!fresh.candidate) {
      const decision: PromotionDecision = {
        kind: 'reject',
        reason: 'invalid_state',
        detail: `Candidate ${candidateId} not found inside the advisory lock.`,
        entityProposalsToStage: [],
      };
      return {
        outcome: 'recorded_rejection',
        stagedEntityProposalIds: [],
        appliedDecision: decision,
      };
    }

    // 4. Race-safe existing-claim-by-hash lookup. Partial UNIQUE on
    //    claims.candidate_hash means at most one row matches.
    const existingByHash = await tx
      .select({ id: claims.id })
      .from(claims)
      .where(and(eq(claims.candidateHash, candidateHash), isNotNull(claims.candidateHash)))
      .limit(1);
    const existingClaimWithSameHash =
      existingByHash[0] ? { claimId: existingByHash[0].id } : null;

    // 5. Build snapshot from FRESH candidate + evidence + caller's auxiliary
    //    inputs (taxonomy validation result + metadata). The decider sees
    //    the latest committed view of the candidate row + the in-lock hash
    //    lookup.
    const decision = decidePromotion({
      candidateHash,
      candidate: fresh.candidate,
      validatedEvidence: fresh.validatedEvidence,
      taxonomy: input.auxiliaryInputs?.taxonomy,
      metadata: input.auxiliaryInputs?.metadata,
      existingClaimWithSameHash,
    });

    // 6. Stage any entity_proposals first — useful to admin regardless of
    //    which decision branch we take.
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

    // 7. Branch on the decision.
    switch (decision.kind) {
      case 'insert_new_claim': {
        // Bilingual (china_imp.md): stamp the claim's source language from the
        // authoring employee's locale, so a claim extracted from a China-group
        // employee's Chinese content is marked 'zh-CN' (canonical Chinese) and
        // the translation worker generates the English rendering — and vice
        // versa. Falls back to the default locale ('en') when unknown.
        const authoringEmployeeId =
          decision.evidenceRows.find((e) => e.assertedByEmployeeId)?.assertedByEmployeeId ??
          decision.evidenceRows.find((e) => e.createdByEmployeeId)?.createdByEmployeeId ??
          decision.evidenceRows.find((e) => e.uploadedByEmployeeId)?.uploadedByEmployeeId ??
          null;
        let sourceLang: string = DEFAULT_LOCALE;
        if (authoringEmployeeId) {
          const [emp] = await tx
            .select({ locale: employees.locale })
            .from(employees)
            .where(eq(employees.id, authoringEmployeeId))
            .limit(1);
          sourceLang = coerceLocale(emp?.locale);
        }
        const [newClaim] = await tx
          .insert(claims)
          .values({
            claimType: decision.claim.claimType,
            summary: decision.claim.summary,
            impactScore: decision.claim.impactScore,
            confidenceScore: decision.claim.confidenceScore ?? 5,
            status: 'pending_review',
            sourceLang,
            candidateHash,
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
        // The candidate row IS present (we returned early above when it
        // wasn't), so the FK target for extraction_validation_results.candidate_id
        // is valid and we can safely write the audit row.

        let newCandidateStatus: string | undefined;
        switch (decision.reason) {
          case 'taxonomy_invalid':
          case 'no_validated_evidence':
          case 'no_domains':
          case 'invalid_state':
            newCandidateStatus = 'validation_failed';
            break;
          case 'not_validated':
          case 'already_promoted':
            // Terminal status set by another worker — don't overwrite.
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
