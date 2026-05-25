/**
 * R5.5 — Canonical entity resolver.
 *
 * Resolves a model-proposed entity reference against the canonical
 * `entities` registry. Pure function: takes the proposal + the registry
 * subset the caller fetched, returns one of four outcomes.
 *
 * Critically: this resolver REFUSES to silently accept a licensor-named
 * entity proposed under `entity_type = 'vendor'`. That structural
 * enforcement is the new docs/oracle/07-knowledge-segmentation.md rule
 * ("licensor is a first-class type distinct from vendor"). The registry
 * is the source of truth — if the proposal's name resolves under a
 * different `entity_type`, the resolver returns `type_mismatch` so the
 * candidate is held instead of writing the wrong row.
 *
 * Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R5.5.
 */

import type { EntityType } from '@oracle/shared';
import { canonicalizeSummary } from './candidate-hash';

// ─────────────────────────────────────────────────────────────────────────
// Registry shape
// ─────────────────────────────────────────────────────────────────────────

/**
 * Registry row the caller fetched from `entities`. Only the fields the
 * resolver needs are required; callers can include more.
 */
export interface RegistryEntity {
  id: string;
  entityType: EntityType;
  canonicalValue: string;
  /** Optional aliases array. Treated case-insensitively + whitespace-collapsed. */
  aliases?: string[] | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Inputs and outputs
// ─────────────────────────────────────────────────────────────────────────

export interface ResolveEntityInput {
  /** The entity type the model proposed for this reference. */
  proposedEntityType: EntityType;
  /** The raw string the model surfaced (could be canonical or an alias). */
  rawString: string;
  /**
   * The subset of the registry the caller fetched. The caller decides how
   * to scope this — for performance it's typically the union of:
   *   1. all entities matching `entity_type = proposedEntityType`
   *   2. plus any entities whose canonical_value matches `rawString` case-
   *      insensitively across ANY type (so type-mismatch detection works)
   */
  registry: RegistryEntity[];
}

export type ResolveEntityResult =
  | {
      outcome: 'resolved';
      entityId: string;
      entityType: EntityType;
      canonicalValue: string;
      matchKind: 'canonical_exact' | 'alias';
    }
  | {
      outcome: 'unknown';
      /** No registry entry matched — caller should stage an entity_proposals row. */
      proposal: {
        proposedEntityType: EntityType;
        proposedCanonicalValue: string;
        rawString: string;
      };
    }
  | {
      outcome: 'type_mismatch';
      /**
       * The name resolves in the registry but under a different
       * entity_type. This catches "Disney as vendor" type errors —
       * Disney is a `licensor`, not a `vendor`. The candidate is held
       * until an admin reviews.
       */
      matchedEntityId: string;
      matchedEntityType: EntityType;
      matchedCanonicalValue: string;
      proposedEntityType: EntityType;
      rawString: string;
    }
  | {
      outcome: 'ambiguous';
      /** Multiple registry entries match the alias under the same type. */
      candidates: Array<{ entityId: string; canonicalValue: string }>;
      proposedEntityType: EntityType;
      rawString: string;
    };

// ─────────────────────────────────────────────────────────────────────────
// Resolver
// ─────────────────────────────────────────────────────────────────────────

/**
 * Resolve a single entity reference. See the ResolveEntityResult shape
 * for the full set of outcomes.
 */
export function resolveEntity(input: ResolveEntityInput): ResolveEntityResult {
  const { proposedEntityType, rawString, registry } = input;
  const normalizedRaw = canonicalizeSummary(rawString);

  // ── 1. Match within the proposed type by canonical value, then aliases.
  const sameType = registry.filter((e) => e.entityType === proposedEntityType);
  const canonicalExact = sameType.filter(
    (e) => canonicalizeSummary(e.canonicalValue) === normalizedRaw,
  );

  if (canonicalExact.length === 1) {
    return {
      outcome: 'resolved',
      entityId: canonicalExact[0]!.id,
      entityType: canonicalExact[0]!.entityType,
      canonicalValue: canonicalExact[0]!.canonicalValue,
      matchKind: 'canonical_exact',
    };
  }
  if (canonicalExact.length > 1) {
    return {
      outcome: 'ambiguous',
      candidates: canonicalExact.map((e) => ({ entityId: e.id, canonicalValue: e.canonicalValue })),
      proposedEntityType,
      rawString,
    };
  }

  const aliasMatches = sameType.filter((e) =>
    (e.aliases ?? []).some((a) => canonicalizeSummary(a) === normalizedRaw),
  );
  if (aliasMatches.length === 1) {
    return {
      outcome: 'resolved',
      entityId: aliasMatches[0]!.id,
      entityType: aliasMatches[0]!.entityType,
      canonicalValue: aliasMatches[0]!.canonicalValue,
      matchKind: 'alias',
    };
  }
  if (aliasMatches.length > 1) {
    return {
      outcome: 'ambiguous',
      candidates: aliasMatches.map((e) => ({ entityId: e.id, canonicalValue: e.canonicalValue })),
      proposedEntityType,
      rawString,
    };
  }

  // ── 2. Cross-type lookup: did the model put Disney under `vendor`?
  // We search across ALL types for a canonical or alias match. If we find
  // one under a different type, we surface a `type_mismatch` rather than
  // silently creating a new entity_proposals row.
  for (const e of registry) {
    if (e.entityType === proposedEntityType) continue;
    if (canonicalizeSummary(e.canonicalValue) === normalizedRaw) {
      return {
        outcome: 'type_mismatch',
        matchedEntityId: e.id,
        matchedEntityType: e.entityType,
        matchedCanonicalValue: e.canonicalValue,
        proposedEntityType,
        rawString,
      };
    }
    if ((e.aliases ?? []).some((a) => canonicalizeSummary(a) === normalizedRaw)) {
      return {
        outcome: 'type_mismatch',
        matchedEntityId: e.id,
        matchedEntityType: e.entityType,
        matchedCanonicalValue: e.canonicalValue,
        proposedEntityType,
        rawString,
      };
    }
  }

  // ── 3. Nothing matched. Stage as an entity_proposals row. The proposed
  // canonical value defaults to the raw string trimmed; admin review can
  // rename it during approval.
  return {
    outcome: 'unknown',
    proposal: {
      proposedEntityType,
      proposedCanonicalValue: rawString.trim(),
      rawString,
    },
  };
}
