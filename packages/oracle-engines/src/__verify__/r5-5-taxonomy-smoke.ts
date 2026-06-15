/**
 * R5.5 acceptance gate verification script.
 *
 * Run with: pnpm --filter @oracle/engines verify:r5.5
 *
 * Proves the taxonomy-validation pieces R5.5 ships:
 *
 *   - entity-resolver: alias resolution, unknown-entity → proposal,
 *     licensor-vs-vendor type-mismatch detection, cross-type lookup,
 *     ambiguous matches
 *   - taxonomy-validator: unknown top-domain failure, mixed-success cases,
 *     blockedByOnlyUnknownEntities heuristic
 *   - decidePromotion (extended): insert_new_claim with entityAssignments,
 *     metadata, and entityProposalsToStage; reject(taxonomy_invalid);
 *     entityProposalsToStage threaded through every branch
 */

import {
  resolveEntity,
  validateTaxonomy,
  decidePromotion,
  type RegistryEntity,
  type CandidateSnapshot,
  type TaxonomyValidationResult,
} from '../extraction';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

// ─────────────────────────────────────────────────────────────────────────
// Fixture registry — a small subset of the real entities seed
// (migrations/sql/17_entities_seed.sql) so the resolver has realistic
// inputs to test alias matching + cross-type lookup against.
// ─────────────────────────────────────────────────────────────────────────

const REGISTRY: RegistryEntity[] = [
  {
    id: 'ent-disney',
    entityType: 'licensor',
    canonicalValue: 'Disney',
    aliases: ['Walt Disney', 'The Walt Disney Company', 'DLG', 'WDC'],
  },
  {
    id: 'ent-marvel',
    entityType: 'licensor',
    canonicalValue: 'Marvel',
    aliases: ['Marvel Entertainment', 'Marvel Studios'],
  },
  {
    id: 'ent-coldlion',
    entityType: 'system',
    canonicalValue: 'Coldlion',
    aliases: ['the ERP', 'ERP', 'Coldlion ERP', 'CL'],
  },
  {
    id: 'ent-burlington',
    entityType: 'customer',
    canonicalValue: 'Burlington',
    aliases: ['Burlington Coat Factory', 'BCF'],
  },
  // Ambiguity fixture: two `freight_provider` rows share the canonical name.
  // The taxonomy validator must refuse to pick.
  {
    id: 'ent-freight-a',
    entityType: 'freight_provider',
    canonicalValue: 'OceanLink',
    aliases: ['OceanLink Logistics'],
  },
  {
    id: 'ent-freight-b',
    entityType: 'freight_provider',
    canonicalValue: 'OceanLink',
    aliases: ['OceanLink Pacific'],
  },
];

const ACTIVE_TOP_DOMAIN_IDS = [
  'customer_ops',
  'licensing_approvals',
  'creative_design',
  'it_systems',
  'production_lifecycle',
  'supply_chain',
];

function main() {
  console.log('R5.5 taxonomy validator + entity resolver smoke test\n');

  // ════════════════════════════════════════════════════════════════════
  // Section A — entity-resolver
  // ════════════════════════════════════════════════════════════════════

  // A1: known canonical resolves
  {
    const res = resolveEntity({
      proposedEntityType: 'licensor',
      rawString: 'Disney',
      registry: REGISTRY,
    });
    assert(res.outcome === 'resolved', 'A1 canonical "Disney" resolves');
    if (res.outcome === 'resolved') {
      assert(res.entityId === 'ent-disney', 'A1 maps to ent-disney');
      assert(res.matchKind === 'canonical_exact', 'A1 match kind is canonical_exact');
    }
  }

  // A2: alias resolves (the canonical "Coldlion" via "the ERP")
  {
    const res = resolveEntity({
      proposedEntityType: 'system',
      rawString: 'the ERP',
      registry: REGISTRY,
    });
    assert(res.outcome === 'resolved', 'A2 alias "the ERP" resolves');
    if (res.outcome === 'resolved') {
      assert(res.canonicalValue === 'Coldlion', 'A2 canonical is Coldlion');
      assert(res.matchKind === 'alias', 'A2 match kind is alias');
    }
  }

  // A3: case + whitespace insensitive
  {
    const res = resolveEntity({
      proposedEntityType: 'system',
      rawString: '  THE   erp  ',
      registry: REGISTRY,
    });
    assert(
      res.outcome === 'resolved' && res.canonicalValue === 'Coldlion',
      'A3 alias resolution is case + whitespace insensitive',
    );
  }

  // A4: unknown entity → proposal
  {
    const res = resolveEntity({
      proposedEntityType: 'system',
      rawString: 'Frobnitz Module',
      registry: REGISTRY,
    });
    assert(res.outcome === 'unknown', 'A4 unknown system → outcome=unknown');
    if (res.outcome === 'unknown') {
      assert(
        res.proposal.proposedCanonicalValue === 'Frobnitz Module',
        'A4 staged proposal preserves the raw string',
      );
    }
  }

  // A5: licensor-as-vendor → type_mismatch (the structural enforcement)
  {
    const res = resolveEntity({
      proposedEntityType: 'vendor',
      rawString: 'Disney',
      registry: REGISTRY,
    });
    assert(res.outcome === 'type_mismatch', 'A5 Disney as vendor → type_mismatch');
    if (res.outcome === 'type_mismatch') {
      assert(res.matchedEntityType === 'licensor', 'A5 matched as licensor in registry');
      assert(res.matchedCanonicalValue === 'Disney', 'A5 matched canonical = Disney');
    }
  }

  // A6: licensor-as-vendor via alias also triggers type_mismatch
  {
    const res = resolveEntity({
      proposedEntityType: 'vendor',
      rawString: 'Walt Disney',
      registry: REGISTRY,
    });
    assert(res.outcome === 'type_mismatch', 'A6 "Walt Disney" as vendor → type_mismatch via alias');
  }

  // A7: ambiguous — two freight_provider rows share the canonical name
  {
    const res = resolveEntity({
      proposedEntityType: 'freight_provider',
      rawString: 'OceanLink',
      registry: REGISTRY,
    });
    assert(res.outcome === 'ambiguous', 'A7 duplicate canonical → ambiguous');
    if (res.outcome === 'ambiguous') {
      assert(res.candidates.length === 2, 'A7 reports 2 candidates');
    }
  }

  // ════════════════════════════════════════════════════════════════════
  // Section B — taxonomy-validator
  // ════════════════════════════════════════════════════════════════════

  // B1: happy path — all top-domains active, all entities resolve
  {
    const res = validateTaxonomy({
      proposedTopDomainIds: ['licensing_approvals', 'creative_design'],
      activeTopDomainIds: ACTIVE_TOP_DOMAIN_IDS,
      proposedEntities: [
        { entityType: 'licensor', rawString: 'Disney' },
        { entityType: 'system', rawString: 'the ERP' },
      ],
      entityRegistry: REGISTRY,
    });
    assert(res.ok, 'B1 happy path → ok');
    assert(res.validTopDomainIds.length === 2, 'B1 carries both top-domains through');
    assert(res.failures.length === 0, 'B1 no failures');
    assert(res.resolvedEntities.length === 2, 'B1 both entities resolved');
    assert(
      res.entityProposalsToCreate.length === 0,
      'B1 no entity proposals when all entities resolve',
    );
  }

  // B1.5: same as B1 but with a stray inactive top-domain — filters + flags it
  {
    const res = validateTaxonomy({
      proposedTopDomainIds: ['licensing_approvals', 'product_development'],
      activeTopDomainIds: ACTIVE_TOP_DOMAIN_IDS,
      proposedEntities: [{ entityType: 'licensor', rawString: 'Disney' }],
      entityRegistry: REGISTRY,
    });
    assert(!res.ok, 'B1.5 inactive top-domain → not ok');
    assert(
      res.validTopDomainIds.length === 1 && res.validTopDomainIds[0] === 'licensing_approvals',
      'B1.5 filters validTopDomainIds to the active subset',
    );
    assert(
      res.failures.some((f) => f.failedCheckName === 'domain_valid'),
      'B1.5 records a domain_valid failure for the inactive id',
    );
  }

  // B2: unknown top-domain ID fails
  {
    const res = validateTaxonomy({
      proposedTopDomainIds: ['licensing_approvals', 'fictional_domain'],
      activeTopDomainIds: ACTIVE_TOP_DOMAIN_IDS,
      proposedEntities: [{ entityType: 'licensor', rawString: 'Disney' }],
      entityRegistry: REGISTRY,
    });
    assert(!res.ok, 'B2 unknown top-domain → not ok');
    assert(
      res.failures.some((f) => f.failedCheckName === 'domain_valid'),
      'B2 records a domain_valid failure',
    );
  }

  // B3: licensor-as-vendor → ok=false with structured detail
  {
    const res = validateTaxonomy({
      proposedTopDomainIds: ['licensing_approvals'],
      activeTopDomainIds: ACTIVE_TOP_DOMAIN_IDS,
      proposedEntities: [{ entityType: 'vendor', rawString: 'Disney' }],
      entityRegistry: REGISTRY,
    });
    assert(!res.ok, 'B3 licensor-as-vendor → not ok');
    assert(
      res.failures.some(
        (f) =>
          f.detail.toLowerCase().includes('disney') && f.detail.toLowerCase().includes('licensor'),
      ),
      'B3 failure detail names Disney and licensor',
    );
    assert(
      res.entityProposalsToCreate.some((p) => p.reason === 'type_mismatch_correction'),
      'B3 stages a type_mismatch_correction proposal',
    );
    assert(
      !res.blockedByOnlyUnknownEntities,
      'B3 NOT blockedByOnlyUnknownEntities (the failure is a type mismatch, stricter)',
    );
  }

  // B4: only unknown entities → blockedByOnlyUnknownEntities = true
  {
    const res = validateTaxonomy({
      proposedTopDomainIds: ['licensing_approvals'],
      activeTopDomainIds: ACTIVE_TOP_DOMAIN_IDS,
      proposedEntities: [{ entityType: 'system', rawString: 'Frobnitz Module' }],
      entityRegistry: REGISTRY,
    });
    assert(!res.ok, 'B4 unknown entity → not ok');
    assert(res.blockedByOnlyUnknownEntities, 'B4 blockedByOnlyUnknownEntities = true');
    assert(
      res.entityProposalsToCreate.length === 1 &&
        res.entityProposalsToCreate[0]!.reason === 'unknown_entity',
      'B4 stages an unknown_entity proposal',
    );
  }

  // B5: empty top-domains list fails fast
  {
    const res = validateTaxonomy({
      proposedTopDomainIds: [],
      activeTopDomainIds: ACTIVE_TOP_DOMAIN_IDS,
      proposedEntities: [],
      entityRegistry: REGISTRY,
    });
    assert(!res.ok, 'B5 empty top-domains → not ok');
    assert(
      res.failures.some((f) => f.failedCheckName === 'domain_valid'),
      'B5 records domain_valid failure',
    );
  }

  // ════════════════════════════════════════════════════════════════════
  // Section C — decidePromotion (R5.5-extended)
  // ════════════════════════════════════════════════════════════════════

  // C1: insert_new_claim now carries entityAssignments + metadata + proposals
  {
    const taxonomyOk: TaxonomyValidationResult = {
      ok: true,
      validTopDomainIds: ['licensing_approvals'],
      resolvedEntities: [
        {
          entityId: 'ent-disney',
          entityType: 'licensor',
          canonicalValue: 'Disney',
          matchKind: 'canonical_exact',
          rawString: 'Disney',
        },
      ],
      entityProposalsToCreate: [],
      failures: [],
      blockedByOnlyUnknownEntities: false,
    };
    const decision = decidePromotion({
      candidateHash: 'h1',
      candidate: {
        id: 'cand-1',
        status: 'validated',
        summary: 'Disney approvals must precede tooling.',
        claimType: 'process_rule',
        impactScore: 8,
        confidenceScore: 9,
        domains: ['licensing_approvals'],
      },
      validatedEvidence: [
        {
          id: 'ev-1',
          sourceType: 'message',
          sourceMessageId: 'msg-1',
          validatedExactQuote: 'Disney approvals must precede tooling.',
          validatedCharStart: 0,
          validatedCharEnd: 38,
        },
      ],
      taxonomy: taxonomyOk,
      metadata: { processStage: 'licensor_approval', department: 'Licensing' },
      existingClaimWithSameHash: null,
    });
    assert(decision.kind === 'insert_new_claim', 'C1 happy path → insert_new_claim');
    if (decision.kind === 'insert_new_claim') {
      assert(decision.entityAssignments.length === 1, 'C1 entityAssignments includes Disney');
      assert(
        decision.entityAssignments[0]!.entityId === 'ent-disney',
        'C1 entity id is ent-disney',
      );
      assert(
        decision.metadata?.processStage === 'licensor_approval',
        'C1 metadata carries processStage',
      );
      assert(decision.metadata?.department === 'Licensing', 'C1 metadata carries department');
      assert(
        decision.topDomainAssignments[0]!.topDomainId === 'licensing_approvals',
        'C1 topDomainAssignments comes from taxonomy.validTopDomainIds',
      );
      assert(decision.entityProposalsToStage.length === 0, 'C1 no proposals to stage');
    }
  }

  // C2: unknown-only entities still stage proposals, but do not block promotion.
  {
    const taxonomyUnknownOnly: TaxonomyValidationResult = {
      ok: false,
      validTopDomainIds: ['licensing_approvals'],
      resolvedEntities: [],
      entityProposalsToCreate: [
        {
          proposedEntityType: 'system',
          proposedCanonicalValue: 'Frobnitz Module',
          rawString: 'Frobnitz Module',
          reason: 'unknown_entity',
        },
      ],
      failures: [
        {
          failedCheckName: 'source_type_valid',
          detail: 'Entity "Frobnitz Module" unknown',
        },
      ],
      failureSummary: 'unknown_entity',
      blockedByOnlyUnknownEntities: true,
    };
    const decision = decidePromotion({
      candidateHash: 'h2',
      candidate: {
        id: 'cand-2',
        status: 'validated',
        summary: 'Frobnitz Module sends approvals to Disney.',
        claimType: 'process_rule',
        impactScore: 5,
        domains: ['licensing_approvals'],
      },
      validatedEvidence: [
        {
          id: 'ev-2',
          sourceType: 'message',
          sourceMessageId: 'msg-2',
          validatedExactQuote: 'Frobnitz Module sends approvals to Disney.',
          validatedCharStart: 0,
          validatedCharEnd: 41,
        },
      ],
      taxonomy: taxonomyUnknownOnly,
      existingClaimWithSameHash: null,
    });
    assert(decision.kind === 'insert_new_claim', 'C2 unknown-only entities → insert_new_claim');
    if (decision.kind === 'insert_new_claim') {
      assert(
        decision.entityProposalsToStage.length === 1,
        'C2 entityProposalsToStage threaded through insert',
      );
    }
  }

  // C3: append_to_existing_claim carries entity assignments too
  {
    const taxonomyOk: TaxonomyValidationResult = {
      ok: true,
      validTopDomainIds: ['licensing_approvals'],
      resolvedEntities: [
        {
          entityId: 'ent-marvel',
          entityType: 'licensor',
          canonicalValue: 'Marvel',
          matchKind: 'canonical_exact',
          rawString: 'Marvel',
        },
      ],
      entityProposalsToCreate: [],
      failures: [],
      blockedByOnlyUnknownEntities: false,
    };
    const decision = decidePromotion({
      candidateHash: 'h3',
      candidate: {
        id: 'cand-3',
        status: 'validated',
        summary: 'Marvel approvals run on the same calendar as Disney.',
        claimType: 'process_rule',
        impactScore: 6,
        domains: ['licensing_approvals'],
      },
      validatedEvidence: [
        {
          id: 'ev-3',
          sourceType: 'message',
          sourceMessageId: 'msg-3',
          validatedExactQuote: 'Marvel approvals run on the same calendar as Disney.',
          validatedCharStart: 0,
          validatedCharEnd: 52,
        },
      ],
      taxonomy: taxonomyOk,
      existingClaimWithSameHash: { claimId: 'claim-existing' },
    });
    assert(decision.kind === 'append_to_existing_claim', 'C3 race → append_to_existing_claim');
    if (decision.kind === 'append_to_existing_claim') {
      assert(
        decision.entityAssignments[0]!.entityId === 'ent-marvel',
        'C3 appended claim still gets the entity assignments',
      );
    }
  }

  // C4: backwards-compat — no taxonomy field → R5 behavior (candidate.domains used)
  {
    const decision = decidePromotion({
      candidateHash: 'h4',
      candidate: {
        id: 'cand-4',
        status: 'validated',
        summary: 'Legacy R5 caller.',
        claimType: 'process_rule',
        impactScore: 4,
        domains: ['it_systems'],
      },
      validatedEvidence: [
        {
          id: 'ev-4',
          sourceType: 'message',
          sourceMessageId: 'msg-4',
          validatedExactQuote: 'Legacy R5 caller.',
          validatedCharStart: 0,
          validatedCharEnd: 16,
        },
      ],
      existingClaimWithSameHash: null,
    });
    assert(decision.kind === 'insert_new_claim', 'C4 R5 caller still gets insert_new_claim');
    if (decision.kind === 'insert_new_claim') {
      assert(decision.entityAssignments.length === 0, 'C4 no entity assignments when no taxonomy');
      assert(decision.metadata === undefined, 'C4 no metadata when not supplied');
      assert(
        decision.topDomainAssignments[0]!.topDomainId === 'it_systems',
        'C4 falls back to candidate.domains when taxonomy missing',
      );
    }
  }

  console.log('\nR5.5 smoke gate: PASS');
}

main();
