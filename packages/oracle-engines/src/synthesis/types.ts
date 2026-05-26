/**
 * R9 synthesis pipeline types.
 *
 * Shared shapes for the pure synthesis-diff validator and the worker that
 * composes it with Drizzle I/O.
 *
 * Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R9.
 */

// ─────────────────────────────────────────────────────────────────────────
// Synthesis output (the schema the model generates)
// ─────────────────────────────────────────────────────────────────────────
//
// This mirrors the SynthesisOutputSchema in
// apps/workers/src/trigger/brain-synthesis.ts. Kept here in untyped form
// (the worker still owns the canonical Zod schema) so the validator can
// be DB-agnostic and worker-agnostic.

export interface SynthesisOutputParagraph {
  text: string;
  supportingClaimIds: string[];
}

export interface SynthesisMaterialChange {
  type: 'added_claim' | 'removed_claim' | 'strengthened_claim' | 'weakened_claim';
  claimId: string;
  reason: string;
}

export interface SynthesisNewGap {
  questionToAsk: string;
  whyItMatters: string;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  targetDepartment?: string;
}

export interface SynthesisNewContradiction {
  claimAId: string;
  claimBId: string;
  description: string;
  severity: 'low' | 'medium' | 'high';
}

export interface SynthesisOutput {
  sectionId: string;
  paragraphs: SynthesisOutputParagraph[];
  updatedMarkdown: string;
  materialChanges: SynthesisMaterialChange[];
  claimsAdded: string[];
  claimsRemoved: string[];
  claimsStrengthened: string[];
  claimsWeakened: string[];
  newContradictions: SynthesisNewContradiction[];
  resolvedContradictions: string[];
  newGaps: SynthesisNewGap[];
  resolvedGaps: string[];
  confidenceChange: 'increased' | 'stable' | 'decreased';
  requiresHumanReview: boolean;
  changeSummary: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Validator input / output
// ─────────────────────────────────────────────────────────────────────────

export interface SynthesisValidationInput {
  output: SynthesisOutput;
  /** Set of claim IDs the worker fetched as approved + relevant to the section. */
  approvedClaimIds: Set<string>;
  /** All approved claim summaries (lowercased once by the caller). The validator scans for entity mentions in this corpus. */
  approvedClaimSummariesLower: string[];
  /**
   * Canonical entity names from `entities` (R3.5 registry). Used by the
   * unsupported-names check to whitelist entities the model can reference
   * EVEN IF no approved claim mentions them by name. This is the safety
   * valve for boundary entities like "Coldlion" or "Disney" that may be
   * implicit in the section's topic.
   */
  registryEntityCanonicalsLower: Set<string>;
  /**
   * Section's own ID — used to detect the "model echoed sectionId in
   * output but a different ID" failure mode.
   */
  expectedSectionId: string;
}

export type SynthesisFailureKind =
  | 'wrong_section_id'
  | 'paragraph_cites_non_approved_claim'
  | 'material_change_cites_non_approved_claim'
  | 'claim_ref_not_approved'
  | 'gap_missing_required_fields'
  | 'unsupported_named_entity'
  | 'contradiction_cites_non_approved_claim';

export interface SynthesisValidationFailure {
  kind: SynthesisFailureKind;
  detail: string;
  /** For unsupported_named_entity: the offending name. */
  name?: string;
  /** For *_cites_non_approved_claim: the offending claim ID. */
  claimId?: string;
}

export interface SynthesisValidationResult {
  ok: boolean;
  failures: SynthesisValidationFailure[];
  /** All distinct names that failed the unsupported-named-entity check. */
  unsupportedNames: string[];
}
