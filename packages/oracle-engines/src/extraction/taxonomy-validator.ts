/**
 * R5.5 — Taxonomy validator.
 *
 * Pure function. Given a candidate's proposed top-domain IDs and entity
 * references, plus the relevant registry slices, returns:
 *
 *   - resolved entity assignments (ready for claim_entities inserts)
 *   - entity proposals to stage in entity_proposals
 *   - validation failures that should hold the candidate
 *
 * Workers call this after R5's quote validation and before R5's
 * decidePromotion, then feed the results into decidePromotion via the
 * extended snapshot shape.
 *
 * Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R5.5 task 5.
 */

import type { EntityType, ValidationCheckName } from '@oracle/shared';
import { resolveEntity, type RegistryEntity, type ResolveEntityResult } from './entity-resolver';

// ─────────────────────────────────────────────────────────────────────────
// Inputs / outputs
// ─────────────────────────────────────────────────────────────────────────

export interface ProposedEntityReference {
  entityType: EntityType;
  rawString: string;
}

export interface ValidateTaxonomyInput {
  /** Top-domain IDs proposed by the model. */
  proposedTopDomainIds: string[];
  /** Currently-active top-domain IDs from `knowledge_top_domains`. */
  activeTopDomainIds: string[];
  /** Entity references the model surfaced. */
  proposedEntities: ProposedEntityReference[];
  /** The entity registry slice the worker fetched (see entity-resolver). */
  entityRegistry: RegistryEntity[];
}

export interface ResolvedEntityAssignment {
  entityId: string;
  entityType: EntityType;
  canonicalValue: string;
  matchKind: 'canonical_exact' | 'alias';
  /** The raw string the model surfaced, kept for audit. */
  rawString: string;
}

export interface EntityProposalToCreate {
  proposedEntityType: EntityType;
  proposedCanonicalValue: string;
  rawString: string;
  /** Why this proposal was created. */
  reason: 'unknown_entity' | 'type_mismatch_correction';
  /** When type_mismatch, the entity that matched under the wrong type. */
  matchedEntityId?: string;
  matchedEntityType?: EntityType;
}

export interface TaxonomyValidationFailure {
  failedCheckName: ValidationCheckName;
  detail: string;
  /** Optional structured payload for `extraction_validation_results.metadata_json`. */
  metadata?: unknown;
}

export interface TaxonomyValidationResult {
  ok: boolean;
  /** Top-domain IDs the worker should write to claim_top_domains. */
  validTopDomainIds: string[];
  /** Entities the worker should write to claim_entities. */
  resolvedEntities: ResolvedEntityAssignment[];
  /** Entity proposals to insert before promotion (best-effort; admin reviews later). */
  entityProposalsToCreate: EntityProposalToCreate[];
  /** Failures that should block promotion. */
  failures: TaxonomyValidationFailure[];
  /**
   * If true, the candidate has unresolved entity references but ALL of
   * them are merely unknown (not type-mismatches and not ambiguous).
   * Workers may choose to stage the proposals and still hold the candidate
   * as `pending_validation` rather than reject.
   */
  blockedByOnlyUnknownEntities: boolean;
  /**
   * Optional short human-readable summary of the failure mix, suitable
   * for `extraction_validation_results.detail` and for surfacing in the
   * promotion decision's reject message.
   */
  failureSummary?: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Validator
// ─────────────────────────────────────────────────────────────────────────

export function validateTaxonomy(input: ValidateTaxonomyInput): TaxonomyValidationResult {
  const { proposedTopDomainIds, activeTopDomainIds, proposedEntities, entityRegistry } = input;

  const failures: TaxonomyValidationFailure[] = [];
  const resolvedEntities: ResolvedEntityAssignment[] = [];
  const entityProposalsToCreate: EntityProposalToCreate[] = [];
  let blockedByOnlyUnknownEntities = false;

  // ── 1. Top-domain validation
  const activeSet = new Set(activeTopDomainIds);
  const validTopDomainIds: string[] = [];
  const unknownTopDomains: string[] = [];
  for (const id of proposedTopDomainIds) {
    if (activeSet.has(id)) validTopDomainIds.push(id);
    else unknownTopDomains.push(id);
  }

  if (proposedTopDomainIds.length === 0) {
    failures.push({
      failedCheckName: 'domain_valid',
      detail: 'Candidate proposed no top-domain IDs.',
    });
  }
  if (unknownTopDomains.length > 0) {
    failures.push({
      failedCheckName: 'domain_valid',
      detail: `Proposed top-domain IDs not present in knowledge_top_domains: ${unknownTopDomains.join(', ')}. Candidate is held; admin should create or remap the missing domain via taxonomy_proposals.`,
      metadata: { unknownTopDomains, activeTopDomainIdsSampled: activeTopDomainIds.slice(0, 12) },
    });
  }

  // ── 2. Entity resolution
  let unknownCount = 0;
  let nonUnknownFailureCount = 0;
  for (const ref of proposedEntities) {
    const res: ResolveEntityResult = resolveEntity({
      proposedEntityType: ref.entityType,
      rawString: ref.rawString,
      registry: entityRegistry,
    });
    switch (res.outcome) {
      case 'resolved':
        resolvedEntities.push({
          entityId: res.entityId,
          entityType: res.entityType,
          canonicalValue: res.canonicalValue,
          matchKind: res.matchKind,
          rawString: ref.rawString,
        });
        break;

      case 'unknown':
        unknownCount += 1;
        entityProposalsToCreate.push({
          proposedEntityType: res.proposal.proposedEntityType,
          proposedCanonicalValue: res.proposal.proposedCanonicalValue,
          rawString: res.proposal.rawString,
          reason: 'unknown_entity',
        });
        failures.push({
          failedCheckName: 'source_type_valid',
          detail: `Entity "${ref.rawString}" (type=${ref.entityType}) does not resolve in the registry. Staged as entity_proposals; candidate is held until reviewed.`,
        });
        break;

      case 'type_mismatch':
        nonUnknownFailureCount += 1;
        entityProposalsToCreate.push({
          proposedEntityType: res.proposedEntityType,
          proposedCanonicalValue: ref.rawString.trim(),
          rawString: ref.rawString,
          reason: 'type_mismatch_correction',
          matchedEntityId: res.matchedEntityId,
          matchedEntityType: res.matchedEntityType,
        });
        failures.push({
          failedCheckName: 'source_type_valid',
          detail:
            `Entity "${ref.rawString}" was proposed as ${ref.entityType} but resolves in the registry as ${res.matchedEntityType} (canonical "${res.matchedCanonicalValue}"). ` +
            `The candidate is held; this is most likely a licensor-vs-vendor confusion that needs admin attention.`,
          metadata: {
            proposedEntityType: ref.entityType,
            matchedEntityType: res.matchedEntityType,
            matchedEntityId: res.matchedEntityId,
            matchedCanonicalValue: res.matchedCanonicalValue,
          },
        });
        break;

      case 'ambiguous':
        nonUnknownFailureCount += 1;
        failures.push({
          failedCheckName: 'source_type_valid',
          detail:
            `Entity "${ref.rawString}" (type=${ref.entityType}) is ambiguous — matches multiple registry rows. Worker must disambiguate before promotion.`,
          metadata: { candidates: res.candidates },
        });
        break;
    }
  }

  blockedByOnlyUnknownEntities =
    failures.length > 0 &&
    failures.every((f) => f.failedCheckName === 'source_type_valid') &&
    nonUnknownFailureCount === 0 &&
    unknownCount > 0 &&
    unknownTopDomains.length === 0;

  return {
    ok: failures.length === 0,
    validTopDomainIds,
    resolvedEntities,
    entityProposalsToCreate,
    failures,
    blockedByOnlyUnknownEntities,
  };
}
