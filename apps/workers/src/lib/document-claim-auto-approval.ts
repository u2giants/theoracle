import { and, eq } from 'drizzle-orm';
import type { ExtractionOutput } from '@oracle/ai';
import { claims, extractionCandidates, extractionValidationResults, type OracleDb } from '@oracle/db';
import type { ExecutePromotionResult } from '@oracle/engines';

const AUTO_APPROVE_MIN_CONFIDENCE = 9;
const AUTO_APPROVE_MAX_IMPACT = 6;
const AUTO_APPROVE_CLAIM_TYPES = new Set([
  'process_rule',
  'dependency',
  'workaround',
  'system_limitation',
]);

type ExtractedClaim = ExtractionOutput['claims'][number];
type AutoApprovalDecision = { approve: true; reason: string } | { approve: false; reason: string };

function hasSensitivityFlags(claim: ExtractedClaim): boolean {
  return (
    claim.sensitivityFlags?.containsSensitiveHRData === true ||
    claim.sensitivityFlags?.containsSensitivePersonalData === true ||
    claim.sensitivityFlags?.isPersonalConflict === true
  );
}

export function decideDocumentClaimAutoApproval(input: {
  extracted: ExtractedClaim;
  result: ExecutePromotionResult;
  quoteVerdict: string;
  validTopDomainIds: string[];
}): AutoApprovalDecision {
  const { extracted, result, quoteVerdict, validTopDomainIds } = input;

  if (result.outcome === 'recorded_rejection') {
    return { approve: false, reason: 'promotion executor recorded a rejection' };
  }
  if (!result.claimId) {
    return { approve: false, reason: 'promotion executor did not return a claim id' };
  }
  if (result.stagedEntityProposalIds.length > 0) {
    return { approve: false, reason: 'claim staged new entity proposals for human review' };
  }
  if (!AUTO_APPROVE_CLAIM_TYPES.has(extracted.claimType)) {
    return { approve: false, reason: `claim type ${extracted.claimType} requires human review` };
  }
  if (extracted.requiresReview) {
    return { approve: false, reason: 'extractor marked the claim as requiring review' };
  }
  if (hasSensitivityFlags(extracted)) {
    return { approve: false, reason: 'claim has sensitivity flags' };
  }
  if (extracted.confidenceScore < AUTO_APPROVE_MIN_CONFIDENCE) {
    return {
      approve: false,
      reason: `confidence ${extracted.confidenceScore} is below ${AUTO_APPROVE_MIN_CONFIDENCE}`,
    };
  }
  if (extracted.impactScore > AUTO_APPROVE_MAX_IMPACT) {
    return {
      approve: false,
      reason: `impact ${extracted.impactScore} is above ${AUTO_APPROVE_MAX_IMPACT}`,
    };
  }
  if (!['exact_match', 'normalized_match'].includes(quoteVerdict)) {
    return { approve: false, reason: `quote verdict ${quoteVerdict} is not auto-approvable` };
  }
  if (validTopDomainIds.length === 0) {
    return { approve: false, reason: 'no valid top-domain assignments' };
  }

  return {
    approve: true,
    reason:
      'validated document claim met conservative auto-approval policy: high confidence, low/medium impact, supported quote, valid taxonomy, no sensitivity flags, no entity proposals',
  };
}

export async function autoApproveDocumentClaimIfEligible(input: {
  db: OracleDb;
  candidateId: string;
  extracted: ExtractedClaim;
  result: ExecutePromotionResult;
  quoteVerdict: string;
  validTopDomainIds: string[];
}): Promise<boolean> {
  const { db, candidateId, extracted, result, quoteVerdict, validTopDomainIds } = input;
  const decision = decideDocumentClaimAutoApproval({
    extracted,
    result,
    quoteVerdict,
    validTopDomainIds,
  });
  const metadataJson = {
    policy: 'document_claim_auto_approval_v1',
    decision: decision.approve ? 'approve' : 'skip',
    reason: decision.reason,
    outcome: result.outcome,
    claimId: result.claimId ?? null,
    claimType: extracted.claimType,
    confidenceScore: extracted.confidenceScore,
    impactScore: extracted.impactScore,
    requiresReview: extracted.requiresReview,
    quoteVerdict,
    validTopDomainIds,
    stagedEntityProposalIds: result.stagedEntityProposalIds,
  };

  if (!decision.approve || !result.claimId) {
    await db.insert(extractionValidationResults).values({
      candidateId,
      checkName: 'promotion_transaction',
      status: 'skipped',
      detail: `Auto-approval skipped: ${decision.reason}.`,
      metadataJson,
    });
    return false;
  }

  const [currentClaim] = await db
    .select({ id: claims.id, status: claims.status })
    .from(claims)
    .where(eq(claims.id, result.claimId))
    .limit(1);

  if (!currentClaim) {
    await db.insert(extractionValidationResults).values({
      candidateId,
      checkName: 'promotion_transaction',
      status: 'skipped',
      detail: `Auto-approval skipped: claim ${result.claimId} was not found after promotion.`,
      metadataJson,
    });
    return false;
  }

  if (currentClaim.status !== 'pending_review') {
    await db.insert(extractionValidationResults).values({
      candidateId,
      checkName: 'promotion_transaction',
      status: 'skipped',
      detail: `Auto-approval skipped: claim ${result.claimId} is already ${currentClaim.status}.`,
      metadataJson,
    });
    return false;
  }

  await db
    .update(claims)
    .set({
      status: 'approved',
      claimKindReviewStatus: 'model_labeled',
    })
    .where(and(eq(claims.id, result.claimId), eq(claims.status, 'pending_review')));
  await db.insert(extractionValidationResults).values({
    candidateId,
    checkName: 'promotion_transaction',
    status: 'pass',
    detail: `Auto-approved claim ${result.claimId}: ${decision.reason}.`,
    metadataJson,
  });
  await db
    .update(extractionCandidates)
    .set({ promotedAt: new Date() })
    .where(eq(extractionCandidates.id, candidateId));

  return true;
}
