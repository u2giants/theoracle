/**
 * Extraction eval runner — mock mode.
 *
 * For each fixture in `evals/fixtures/extraction/*.json`:
 *   1. Load the paired canned LLM output from `evals/mocks/canned-extraction-outputs/`.
 *   2. For each claim in the canned output, run the real R5/R5.5 validators
 *      against the fixture's transcript content (no network, no DB):
 *        - validateSourcePointer
 *        - validateQuote against the actual message/chunk text in the fixture
 *        - validateTaxonomy against the fixture's activeTopDomainIds + entityRegistry
 *   3. Compose a CandidateSnapshot and run decidePromotion.
 *   4. Compare the resulting per-claim outcomes against the fixture's
 *      `expected.claims` block.
 *   5. Roll up metrics.
 *
 * Run with: pnpm --filter @oracle/ai eval:extraction
 *
 * This is a deterministic pipeline check, not a live LLM test. The eval
 * confirms that GIVEN a particular model output, the validators + decider
 * produce the right verdicts. It does NOT verify that the model actually
 * produces those outputs — that's what live-mode (a future addition) would do.
 */

import {
  validateQuote,
  validateSourcePointer,
  validateTaxonomy,
  computeCandidateHash,
  decidePromotion,
  mapLegacyDomainsToTopDomains,
  type CandidateSnapshot,
  type RegistryEntity,
} from '@oracle/engines';
import type { KnowledgeDomain } from '@oracle/shared';
import {
  loadExtractionFixtures,
  type ExtractionFixture,
  type CannedExtractionOutput,
  type CannedExtractionClaim,
} from './shared/fixture-loader';
import {
  aggregateExtractionMetrics,
  summaryMatch,
  type ExtractionMetrics,
} from './shared/metrics';
import { printExtractionSummary, writeExtractionReport } from './shared/report';

interface PerClaimOutcome {
  cannedClaim: CannedExtractionClaim;
  quoteValid: boolean;
  sourceValid: boolean;
  taxonomyValid: boolean;
  /** True iff the claim is well-formed enough to be promoted in principle. */
  passesAllValidators: boolean;
  /** True if the candidate would be quarantined for sensitivity. */
  isSensitive: boolean;
  promotionDecisionKind: 'insert_new_claim' | 'append_to_existing_claim' | 'reject';
  matchedExpectedSummary: string | null;
  topDomainMapped: string[];
  notes: string[];
}

function defaultActiveTopDomainIds(): string[] {
  // Match the active domains seeded by migrations/sql/16_knowledge_top_domains_seed.sql
  // plus additive follow-up domain migrations.
  // Fixtures may override via inputs.activeTopDomainIds.
  return [
    'business_process',
    'customer_ops',
    'licensing_approvals',
    'product_development',
    'creative_design',
    'design_file_operations',
    'supply_chain',
    'it_systems',
    'operations_systems',
    'production_lifecycle',
    'finance_pricing',
    'people_org',
    'vendor_management',
    'logistics_shipping',
    'import_compliance',
  ];
}

function buildSourceTextLookup(fixture: ExtractionFixture): Map<string, string> {
  const lookup = new Map<string, string>();
  if (fixture.inputs.messages) {
    for (const m of fixture.inputs.messages) lookup.set(m.messageId, m.text);
  }
  if (fixture.inputs.documentChunk) {
    lookup.set(fixture.inputs.documentChunk.chunkId, fixture.inputs.documentChunk.text);
  }
  return lookup;
}

function runOneClaim(
  cannedClaim: CannedExtractionClaim,
  fixture: ExtractionFixture,
  sourceTextByPointer: Map<string, string>,
  activeTopDomainIds: string[],
  registry: RegistryEntity[],
): PerClaimOutcome {
  const notes: string[] = [];

  // ── 1. Source pointer validation
  const isMessageSource = !!cannedClaim.evidence.sourceMessageId;
  const sourcePtr = validateSourcePointer({
    sourceType: isMessageSource ? 'message' : 'document_chunk',
    sourceMessageId: isMessageSource ? cannedClaim.evidence.sourceMessageId : undefined,
    sourceDocumentChunkId: isMessageSource ? undefined : cannedClaim.evidence.sourceMessageId,
  });
  if (!sourcePtr.ok) notes.push(`source_pointer: ${sourcePtr.detail}`);

  // ── 2. Quote validation against the actual fixture transcript text
  const sourceText = sourceTextByPointer.get(cannedClaim.evidence.sourceMessageId) ?? '';
  const quoteRes = validateQuote({
    sourceText,
    exactQuoteProvided: cannedClaim.evidence.exactQuote,
  });
  const quoteValid =
    quoteRes.verdict === 'exact_match' || quoteRes.verdict === 'normalized_match';
  if (!quoteValid) notes.push(`quote: ${quoteRes.verdict} — ${quoteRes.detail}`);

  // ── 3. Top-domain mapping + taxonomy validation
  const topDomainIds = mapLegacyDomainsToTopDomains(cannedClaim.domains as KnowledgeDomain[]);
  const taxRes = validateTaxonomy({
    proposedTopDomainIds: topDomainIds,
    activeTopDomainIds,
    proposedEntities: [],
    entityRegistry: registry,
  });
  if (!taxRes.ok) notes.push(`taxonomy: ${taxRes.failures.map((f) => f.detail).join('; ')}`);

  // ── 4. Sensitivity gate
  const sensitive =
    !!cannedClaim.sensitivityFlags?.containsSensitivePersonalData ||
    !!cannedClaim.sensitivityFlags?.containsSensitiveHRData ||
    !!cannedClaim.sensitivityFlags?.isPersonalConflict;
  if (sensitive) notes.push('sensitivity: candidate flagged sensitive → would be quarantined');

  // ── 5. decidePromotion if validators pass
  const passesAllValidators = sourcePtr.ok && quoteValid && taxRes.ok && !sensitive;
  let promotionDecisionKind: PerClaimOutcome['promotionDecisionKind'] = 'reject';

  if (passesAllValidators) {
    const validatedQuote = quoteRes.validatedExactQuote ?? cannedClaim.evidence.exactQuote;
    const candidateHash = computeCandidateHash({
      summary: cannedClaim.summary,
      topDomainIds: taxRes.validTopDomainIds,
      validatedQuotes: [validatedQuote],
      sourcePointers: [`message:${cannedClaim.evidence.sourceMessageId}`],
    });
    const snapshot: CandidateSnapshot = {
      candidateHash,
      candidate: {
        id: 'eval-candidate',
        status: 'validated',
        summary: cannedClaim.summary,
        claimType: cannedClaim.claimType,
        impactScore: cannedClaim.impactScore,
        confidenceScore: cannedClaim.confidenceScore,
        domains: taxRes.validTopDomainIds,
      },
      validatedEvidence: [
        {
          id: 'eval-evidence',
          sourceType: 'message',
          sourceMessageId: cannedClaim.evidence.sourceMessageId,
          validatedExactQuote: validatedQuote,
          validatedCharStart: quoteRes.validatedCharStart ?? 0,
          validatedCharEnd: quoteRes.validatedCharEnd ?? validatedQuote.length,
          confidence: cannedClaim.evidence.confidence,
        },
      ],
      taxonomy: taxRes,
      existingClaimWithSameHash: null,
    };
    const decision = decidePromotion(snapshot);
    promotionDecisionKind = decision.kind;
  }

  // ── 6. Match against expected.claims by summary similarity
  let matchedExpected: string | null = null;
  for (const expected of fixture.expected.claims) {
    if (summaryMatch(cannedClaim.summary, expected.summary)) {
      matchedExpected = expected.summary;
      break;
    }
  }

  return {
    cannedClaim,
    quoteValid,
    sourceValid: sourcePtr.ok,
    taxonomyValid: taxRes.ok,
    passesAllValidators,
    isSensitive: sensitive,
    promotionDecisionKind,
    matchedExpectedSummary: matchedExpected,
    topDomainMapped: topDomainIds,
    notes,
  };
}

function scoreFixture(
  fixture: ExtractionFixture,
  cannedOutput: CannedExtractionOutput,
  outcomes: PerClaimOutcome[],
): ExtractionMetrics {
  const expectedClaims = fixture.expected.claims.length;
  const extractedClaims = cannedOutput.claims.length;
  const validExtractedClaims = outcomes.filter((o) => o.passesAllValidators).length;
  const truePositives = outcomes.filter(
    (o) => o.passesAllValidators && o.matchedExpectedSummary != null,
  ).length;

  const precision = extractedClaims === 0 ? null : truePositives / extractedClaims;
  const recall = expectedClaims === 0 ? null : truePositives / expectedClaims;
  const f1 =
    precision == null || recall == null
      ? null
      : precision + recall === 0
        ? 0
        : (2 * precision * recall) / (precision + recall);

  const validQuotes = outcomes.filter((o) => o.quoteValid).length;
  const quoteValidity = extractedClaims === 0 ? null : validQuotes / extractedClaims;

  // Wrong-domain rate: a claim whose top-domain set does NOT overlap with any
  // expected claim's domain set, AND which was extracted (passed quote +
  // sensitivity), counts as wrong-domain.
  const wrongDomain = outcomes.filter((o) => {
    if (!o.quoteValid || o.isSensitive) return false;
    const expected = fixture.expected.claims.find((c) =>
      summaryMatch(o.cannedClaim.summary, c.summary),
    );
    if (!expected) return false;
    // Map expected domains to top-domain IDs the same way.
    const expectedTopDomains = mapLegacyDomainsToTopDomains(
      expected.domains as KnowledgeDomain[],
    );
    return !o.topDomainMapped.some((td) => expectedTopDomains.includes(td));
  }).length;
  const wrongDomainRate = extractedClaims === 0 ? null : wrongDomain / extractedClaims;

  // Sensitive quarantine pass: every expected claim with mustBeQuarantined=true
  // OR mustBeFlaggedSensitive=true must have a matching outcome that was
  // either rejected by sensitivity or never reached promotion.
  const expectedSensitive = fixture.expected.claims.filter(
    (c) => c.mustBeQuarantined || c.mustBeFlaggedSensitive,
  );
  let sensitiveQuarantinePass = true;
  for (const sensitiveExp of expectedSensitive) {
    const matched = outcomes.find((o) =>
      summaryMatch(o.cannedClaim.summary, sensitiveExp.summary),
    );
    if (!matched) {
      // No matching extracted output AT ALL → counts as quarantined-by-omission, which is fine.
      continue;
    }
    if (matched.passesAllValidators) {
      sensitiveQuarantinePass = false;
      break;
    }
  }

  // Promotion expectations: every expected claim with mustBePromoted=true
  // must have a matching outcome whose decision was insert_new_claim.
  const failureNotes: string[] = [];
  for (const expected of fixture.expected.claims) {
    const matched = outcomes.find((o) => summaryMatch(o.cannedClaim.summary, expected.summary));
    if (expected.mustBePromoted && (!matched || matched.promotionDecisionKind !== 'insert_new_claim')) {
      failureNotes.push(
        `expected.mustBePromoted="${shortPreview(expected.summary)}" did not result in insert_new_claim (got ${matched?.promotionDecisionKind ?? 'no-match'}).`,
      );
    }
    if (expected.mustBeQuarantined) {
      if (matched?.passesAllValidators) {
        failureNotes.push(
          `expected.mustBeQuarantined="${shortPreview(expected.summary)}" passed all validators (should have been quarantined).`,
        );
      }
    }
  }

  // forbiddenClaims: any extracted claim that quotes a forbidden span fails.
  for (const forbidden of fixture.expected.forbiddenClaims ?? []) {
    for (const o of outcomes) {
      const quote = o.cannedClaim.evidence.exactQuote;
      if (forbidden.spans?.some((s) => quote.includes(s))) {
        if (o.passesAllValidators) {
          failureNotes.push(
            `forbiddenClaims violated (${forbidden.reason}): extracted claim quotes forbidden span "${quote.slice(0, 60)}".`,
          );
        }
      }
    }
  }

  // expectedSensitivityFlags: any expected-true flag must be reflected somewhere.
  const flags = fixture.expected.expectedSensitivityFlags;
  if (flags) {
    const anyHR = outcomes.some((o) => o.cannedClaim.sensitivityFlags?.containsSensitiveHRData);
    const anyPersonal = outcomes.some(
      (o) => o.cannedClaim.sensitivityFlags?.containsSensitivePersonalData,
    );
    const anyConflict = outcomes.some((o) => o.cannedClaim.sensitivityFlags?.isPersonalConflict);
    if (flags.anyContainsSensitiveHRData === true && !anyHR) {
      failureNotes.push('expectedSensitivityFlags.anyContainsSensitiveHRData=true but no canned output flagged it.');
    }
    if (flags.anyContainsSensitivePersonalData === true && !anyPersonal) {
      failureNotes.push('expectedSensitivityFlags.anyContainsSensitivePersonalData=true but no canned output flagged it.');
    }
    if (flags.anyIsPersonalConflict === true && !anyConflict) {
      failureNotes.push('expectedSensitivityFlags.anyIsPersonalConflict=true but no canned output flagged it.');
    }
  }

  // scoringRules gates
  const rules = fixture.scoringRules ?? {};
  if (rules.minPrecision != null && precision != null && precision < rules.minPrecision) {
    failureNotes.push(`precision ${precision.toFixed(3)} < minPrecision ${rules.minPrecision}`);
  }
  if (rules.minRecall != null && recall != null && recall < rules.minRecall) {
    failureNotes.push(`recall ${recall.toFixed(3)} < minRecall ${rules.minRecall}`);
  }
  if (rules.minQuoteValidity != null && quoteValidity != null && quoteValidity < rules.minQuoteValidity) {
    failureNotes.push(`quoteValidity ${quoteValidity.toFixed(3)} < minQuoteValidity ${rules.minQuoteValidity}`);
  }
  if (
    rules.maxWrongDomainRate != null &&
    wrongDomainRate != null &&
    wrongDomainRate > rules.maxWrongDomainRate
  ) {
    failureNotes.push(`wrongDomainRate ${wrongDomainRate.toFixed(3)} > maxWrongDomainRate ${rules.maxWrongDomainRate}`);
  }
  if (!sensitiveQuarantinePass) {
    failureNotes.push('sensitive-quarantine gate failed (a sensitive expected claim was not quarantined).');
  }

  return {
    fixtureId: fixture.fixtureId,
    expectedClaims,
    extractedClaims,
    validExtractedClaims,
    truePositives,
    precision,
    recall,
    f1,
    quoteValidity,
    wrongDomainRate,
    sensitiveQuarantinePass,
    duplicateRate: 0, // no DB; cross-fixture dedup not exercised here
    schemaValidity: 1, // canned outputs are JSON-schema-conformant by construction
    gateStatus: failureNotes.length === 0 ? 'PASS' : 'FAIL',
    failureNotes,
  };
}

function shortPreview(s: string, n = 50): string {
  return s.length <= n ? s : `${s.slice(0, n)}…`;
}

async function main() {
  console.log('Extraction eval runner — mock mode\n');

  const fixtures = await loadExtractionFixtures();
  if (fixtures.length === 0) {
    console.error('No fixtures found under packages/ai/evals/fixtures/extraction/.');
    process.exit(1);
  }

  // Build the registry once. Fixtures may override via inputs.entityRegistry,
  // but a small default keeps the runner usable without per-fixture wiring.
  const defaultRegistry: RegistryEntity[] = [];

  const perFixture = fixtures.map((loaded) => {
    const sourceText = buildSourceTextLookup(loaded.fixture);
    const activeIds =
      loaded.fixture.inputs.activeTopDomainIds ?? defaultActiveTopDomainIds();
    const registry: RegistryEntity[] =
      (loaded.fixture.inputs.entityRegistry as RegistryEntity[] | undefined) ?? defaultRegistry;

    const outcomes = loaded.cannedOutput.claims.map((claim) =>
      runOneClaim(claim, loaded.fixture, sourceText, activeIds, registry),
    );
    return scoreFixture(loaded.fixture, loaded.cannedOutput, outcomes);
  });

  const aggregate = aggregateExtractionMetrics(perFixture);

  // The route under test is whichever route ID the first fixture declared,
  // since all fixtures in one run should target the same route.
  const routeId = fixtures[0]!.fixture.inputs.routeId;

  const { runDir } = await writeExtractionReport({
    perFixture,
    aggregate,
    mode: 'mock',
    routeId,
  });

  printExtractionSummary({
    perFixture,
    aggregate,
    mode: 'mock',
    routeId,
    runDir,
  });

  if (aggregate.fixturesFailed > 0) {
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
