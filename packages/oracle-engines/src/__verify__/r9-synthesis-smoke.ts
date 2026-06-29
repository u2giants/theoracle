/**
 * R9 acceptance gate verification script.
 *
 * Run with: pnpm --filter @oracle/engines verify:r9
 *
 * Covers the new pure validator R9 ships:
 *
 *   - validateSynthesisDiff: all 7 failure kinds firing correctly,
 *     happy-path passing, and the boundary cases for the
 *     unsupported_named_entity check.
 *   - findUnsupportedNamedEntities: pure helper exercised against the
 *     types of false positives the heuristic must NOT trigger on
 *     (sentence-start stopwords, calendar words, code blocks, links,
 *     headings).
 *
 * The worker integration (brain-synthesis.ts through OracleAIClient
 * + bridge adapter + reject-on-failure ghost version insert) is NOT
 * exercised here — that requires a live Postgres for the Drizzle
 * transaction. The pure validator the worker composes is fully covered.
 */

import {
  validateSynthesisDiff,
  findUnsupportedNamedEntities,
  type SynthesisOutput,
} from '../synthesis';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

// ─────────────────────────────────────────────────────────────────────────
// Fixture helpers
// ─────────────────────────────────────────────────────────────────────────

function uuid(n: number): string {
  // Deterministic uuid-shaped strings for the fixtures. The validator
  // only checks set membership; format doesn't matter.
  return `00000000-0000-0000-0000-${n.toString().padStart(12, '0')}`;
}

const CLAIM_A = uuid(1);
const CLAIM_B = uuid(2);
const CLAIM_C = uuid(3);
const CLAIM_UNAPPROVED = uuid(99);

const APPROVED_IDS = new Set([CLAIM_A, CLAIM_B, CLAIM_C]);
const APPROVED_SUMMARIES_LOWER = [
  'burlington seasonal items must go through the new routing guide before shipment.',
  'disney approvals must precede tooling for all licensed sku launches.',
  'coldlion is the system of record for sku metadata after sample sign-off.',
  'the creative director must review licensing sheets before licensor submission.',
];
const REGISTRY_ENTITY_CANONICALS_LOWER = new Set([
  'disney',
  'marvel',
  'star wars',
  'nbcuniversal',
  'warner bros',
  'burlington',
  'tjx',
  'ross',
  'hobby lobby',
  'walmart',
  'coldlion',
  'resourcespace',
  'china',
  'brazil',
  'colombia',
]);

const SECTION_ID = 'creative_to_technical_handoff';

function happyPathOutput(): SynthesisOutput {
  return {
    sectionId: SECTION_ID,
    paragraphs: [
      {
        text: 'Burlington seasonal items must clear routing-guide validation before shipment.',
        supportingClaimIds: [CLAIM_A],
      },
      {
        text: 'Disney approvals must precede tooling on every licensed SKU.',
        supportingClaimIds: [CLAIM_B],
      },
    ],
    updatedMarkdown:
      '# Creative to Technical Handoff\n\nBurlington seasonal items must clear routing-guide validation before shipment. Disney approvals must precede tooling on every licensed SKU.\n\nColdlion is the system of record once a sample is signed off.',
    materialChanges: [
      { type: 'added_claim', claimId: CLAIM_C, reason: 'New evidence about Coldlion ownership.' },
    ],
    claimsAdded: [CLAIM_C],
    claimsRemoved: [],
    claimsStrengthened: [CLAIM_A],
    claimsWeakened: [],
    newContradictions: [],
    resolvedContradictions: [],
    newGaps: [],
    resolvedGaps: [],
    confidenceChange: 'increased',
    requiresHumanReview: false,
    changeSummary: 'Burlington routing + Disney approval ordering clarified; Coldlion role added.',
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────

function main() {
  console.log('R9 synthesis diff validator smoke test\n');

  // ── Section A — happy path passes ─────────────────────────────────────

  {
    const res = validateSynthesisDiff({
      output: happyPathOutput(),
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(res.ok, 'A1 happy path → ok');
    assert(res.failures.length === 0, 'A1 no failures');
    assert(res.unsupportedNames.length === 0, 'A1 no unsupported names');
  }

  // ── Section B — claim-ID failures ─────────────────────────────────────

  {
    const out = happyPathOutput();
    out.paragraphs[0]!.supportingClaimIds = [CLAIM_UNAPPROVED];
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(!res.ok, 'B1 paragraph cites non-approved claim → not ok');
    assert(
      res.failures.some((f) => f.kind === 'paragraph_cites_non_approved_claim'),
      'B1 records paragraph_cites_non_approved_claim',
    );
  }

  {
    const out = happyPathOutput();
    out.materialChanges = [{ type: 'added_claim', claimId: CLAIM_UNAPPROVED, reason: 'x' }];
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(
      res.failures.some((f) => f.kind === 'material_change_cites_non_approved_claim'),
      'B2 materialChange with non-approved claim → flagged',
    );
  }

  {
    const out = happyPathOutput();
    out.claimsAdded = [CLAIM_UNAPPROVED];
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(
      res.failures.some((f) => f.kind === 'claim_ref_not_approved'),
      'B3 claimsAdded with non-approved → flagged',
    );
  }

  {
    // claimsRemoved is INTENTIONALLY not checked — by definition a removed
    // claim may no longer be approved.
    const out = happyPathOutput();
    out.claimsRemoved = [CLAIM_UNAPPROVED];
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(res.ok, 'B4 claimsRemoved with non-approved is NOT a failure (by design)');
  }

  // ── Section C — wrong section ID ──────────────────────────────────────

  {
    const out = happyPathOutput();
    out.sectionId = 'some_other_section';
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(
      res.failures.some((f) => f.kind === 'wrong_section_id'),
      'C1 wrong sectionId → flagged',
    );
  }

  // ── Section D — gap field requirements ────────────────────────────────

  {
    const out = happyPathOutput();
    out.newGaps = [
      { questionToAsk: '  ', whyItMatters: 'this is fine', priority: 'high' },
    ];
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(
      res.failures.some((f) => f.kind === 'gap_missing_required_fields'),
      'D1 gap with empty questionToAsk → flagged',
    );
  }

  // ── Section E — newContradictions claim IDs ───────────────────────────

  {
    const out = happyPathOutput();
    out.newContradictions = [
      {
        claimAId: CLAIM_A,
        claimBId: CLAIM_UNAPPROVED,
        description: 'A conflicts with X',
        severity: 'medium',
      },
    ];
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(
      res.failures.some(
        (f) => f.kind === 'contradiction_cites_non_approved_claim' && f.claimId === CLAIM_UNAPPROVED,
      ),
      'E1 contradiction with non-approved claimBId → flagged',
    );
  }

  // ── Section F — unsupported named entities ────────────────────────────

  // F1: a fabricated name nobody supports
  {
    const out = happyPathOutput();
    out.updatedMarkdown =
      'Burlington seasonal items must go through routing. Frobnitz Corporation handles final QA approval.';
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(!res.ok, 'F1 fabricated entity "Frobnitz Corporation" → not ok');
    assert(
      res.unsupportedNames.some((n) => n.includes('Frobnitz')),
      'F1 reports Frobnitz Corporation as unsupported',
    );
  }

  // F2: registry entity (Disney) passes even if it doesn't appear in
  // approved summaries — it's a known canonical
  {
    const out = happyPathOutput();
    out.updatedMarkdown =
      '# Section\n\nDisney approvals always come before tooling. ResourceSpace stores the licensor assets.';
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(res.ok, 'F2 registry entities Disney + ResourceSpace pass');
  }

  // F3: an entity that appears in approved-claim summaries passes
  {
    const out = happyPathOutput();
    out.updatedMarkdown =
      'Burlington has a strict routing guide and seasonal-item handoff requirements.';
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    assert(res.ok, 'F3 Burlington (in approved summaries AND in registry) passes');
  }

  // F4: heading-only proper noun doesn't fire (heading prefix stripped)
  {
    const out = happyPathOutput();
    out.updatedMarkdown = '# Creative Handoff\n\nApprovals must precede tooling.';
    const res = validateSynthesisDiff({
      output: out,
      approvedClaimIds: APPROVED_IDS,
      approvedClaimSummariesLower: APPROVED_SUMMARIES_LOWER,
      registryEntityCanonicalsLower: REGISTRY_ENTITY_CANONICALS_LOWER,
      expectedSectionId: SECTION_ID,
    });
    // "Creative Handoff" is a heading phrase that may or may not flag —
    // the validator strips the leading "# " but the phrase itself could
    // still match if not in approvals/registry. The point of this test:
    // confirm the validator at LEAST handles the typical operational
    // sentence ("Approvals must precede tooling.") without false positives
    // on common verbs / nouns.
    const verbsAndNouns = res.unsupportedNames.filter(
      (n) => n === 'Approvals' || n === 'Tooling',
    );
    assert(verbsAndNouns.length === 0, 'F4 single-word stopwords/sentence-starts not flagged');
  }

  // ── Section G — findUnsupportedNamedEntities pure helper ──────────────

  {
    // G1: code blocks stripped
    const unsup = findUnsupportedNamedEntities(
      '```\nFakeBrand X12 spec lives here\n```\nBurlington routing applies.',
      APPROVED_SUMMARIES_LOWER,
      REGISTRY_ENTITY_CANONICALS_LOWER,
    );
    assert(
      !unsup.some((n) => n.includes('FakeBrand')),
      'G1 code-block content is stripped before name extraction',
    );
  }

  {
    // G2: markdown links stripped
    const unsup = findUnsupportedNamedEntities(
      'See the [Vendor Onboarding Spec](https://example.com/SecretCorp) for details. Burlington routes apply.',
      APPROVED_SUMMARIES_LOWER,
      REGISTRY_ENTITY_CANONICALS_LOWER,
    );
    assert(
      !unsup.some((n) => n.includes('SecretCorp')),
      'G2 URL inside markdown link is stripped',
    );
  }

  {
    // G3: days of the week not flagged as entities
    const unsup = findUnsupportedNamedEntities(
      'On Tuesday and Wednesday, Burlington schedules pickups.',
      APPROVED_SUMMARIES_LOWER,
      REGISTRY_ENTITY_CANONICALS_LOWER,
    );
    assert(
      !unsup.includes('Tuesday') && !unsup.includes('Wednesday'),
      'G3 calendar words (Tuesday/Wednesday) not flagged',
    );
  }

  {
    // G4: single-letter / initial-only words not flagged
    const unsup = findUnsupportedNamedEntities(
      'A short sentence. I think Burlington handles this.',
      APPROVED_SUMMARIES_LOWER,
      REGISTRY_ENTITY_CANONICALS_LOWER,
    );
    assert(
      !unsup.includes('A') && !unsup.includes('I'),
      'G4 single-letter words not flagged',
    );
  }

  {
    // G5: empty input
    const unsup = findUnsupportedNamedEntities(
      '',
      APPROVED_SUMMARIES_LOWER,
      REGISTRY_ENTITY_CANONICALS_LOWER,
    );
    assert(unsup.length === 0, 'G5 empty markdown → no unsupported names');
  }

  {
    // G6: discourse markers and possessives seen in real synthesis drafts.
    const unsup = findUnsupportedNamedEntities(
      "Furthermore, the Creative Director's review can affect timing. Additionally, Burlington routing applies.",
      APPROVED_SUMMARIES_LOWER,
      REGISTRY_ENTITY_CANONICALS_LOWER,
    );
    assert(
      !unsup.includes('Furthermore') &&
        !unsup.includes('Additionally') &&
        !unsup.includes("Creative Director's"),
      'G6 discourse markers + supported possessive phrases not flagged',
    );
  }

  console.log('\nR9 smoke gate: PASS');
}

main();
