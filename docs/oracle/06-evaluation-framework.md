# Evaluation Framework

Status: mandatory constraints and operational guidance for Oracle AI evaluation.

This document defines how Oracle-specific evals are built, run, scored, and used as phase gates. Read in conjunction with `01-model-roles-and-routes.md`, `02-provider-native-ai-architecture.md`, `03-candidate-before-claim-validation.md`, `04-context-packs-observability.md`, and `07-knowledge-segmentation.md`.

## The Problem
The spec relies heavily on metrics like "cost per valid claim," "evidence quote validity," and "wrong-domain rate" to determine if a model route is approved for production. If left unbounded, an AI agent might attempt to build a massive, complex Web UI to manage these tests.

## The Constraint: CLI-Only Evaluations
Do not build a web UI for evaluations.

Evals will be executed strictly via local CLI scripts (using Jest, Vitest, or a native Node runner).

1. Create a `packages/ai/evals/` directory.
2. Store 3–5 hardcoded "Gold Standard" test transcripts as static `.json` files.
3. Build a runner (e.g., `pnpm run eval:extraction`) that feeds the transcripts through the `OracleAIClient`.
4. The runner must bypass the database and output the precision, recall, and quote-validity metrics directly to the developer console.
5. A model route configuration may only be promoted to `DEFAULT_ORACLE_MODEL_ROUTES` if it passes the CLI eval suite with ≥98% quote validity.

## Executive decision

Do not build an evaluation web UI at first.

Evals must start as CLI-run TypeScript tests/scripts using static fixtures.

The first goal is to prove extraction, validation, retrieval, and synthesis quality without creating a dashboard project that distracts from the core pipeline.

## Tooling decision

Initial evals should use repo-native TypeScript tooling:

- Vitest if the repo already has or adds it for test suites;
- otherwise a simple Node/tsx runner is acceptable;
- static JSON fixtures stored in the repo;
- console output and JSON result artifacts written to `packages/ai/evals/runs/<timestamp>/`.

Do not introduce Braintrust, LangSmith, Promptfoo, or another external eval platform during the initial retrofit unless Albert explicitly approves it later.

External eval tooling can be reconsidered only after:

1. candidate-before-claim pipeline works;
2. OracleAIClient/provider adapters work;
3. context packs and usage logging work;
4. at least 5 local extraction fixtures exist;
5. costs and validation failures are measurable.

## Required commands

Add package scripts in `packages/ai/package.json`:

```bash
pnpm eval:extraction        # claim extraction over transcript fixtures
pnpm eval:retrieval         # RetrievalPlan + hybrid search over query fixtures
pnpm eval:synthesis         # brain synthesis over approved-claim fixtures
pnpm eval:validation        # PII gate, circuit breaker, concurrency lock, quote validator
pnpm eval:segmentation      # entity normalization, cross-domain contamination, sub-topic drift
pnpm eval:cache             # cache hit rate + prefix stability over repeated routes
pnpm eval:all               # all of the above in mock mode
pnpm eval:compare           # side-by-side route comparison from prior eval runs
```

All eval commands must run locally without network access in mock mode. Live-provider mode requires an explicit flag (see "Live vs mock mode").

## Fixture directory layout

Canonical location is `packages/ai/evals/` (supersedes any prior `packages/oracle-engines/evals/` reference).

```text
packages/ai/evals/
  fixtures/
    extraction/
      transcript-01-routine-handoff.json
      transcript-02-group-disagreement.json
      transcript-03-paraphrase-trap.json
      transcript-04-synthesized-quote-trap.json
      transcript-05-sensitive-pii-trap.json
      transcript-06-duplicate-rule-trap.json
      transcript-07-edited-message-trap.json
      document-01-routing-guide-page.json
      document-02-vendor-manual-page.json
    retrieval/
      erp-image-upload-question.json
      vendor-manual-contamination.json
      exact-sku-lookup.json
      exact-factory-code-lookup.json
      superseded-claim-exclusion.json
      cross-domain-customer-question.json
    synthesis/
      brain-section-approval-flow.json
      brain-section-with-contradiction.json
      brain-section-supersession.json
    validation/
      quote-validator-cases.json
      pii-gate-cases.json
      circuit-breaker-source.json
      concurrent-promotion-cases.json
    segmentation/
      entity-normalization-cases.json
      cross-domain-contamination-cases.json
      sub-topic-drift-cases.json
    cache/
      stable-prefix-cases.json
      explicit-cache-heuristic-cases.json
  runners/
    eval-extraction.ts
    eval-retrieval.ts
    eval-synthesis.ts
    eval-validation.ts
    eval-segmentation.ts
    eval-cache.ts
    eval-compare.ts
    shared/
      fixture-loader.ts
      metrics.ts
      scorers.ts
      report.ts
  mocks/
    canned-extraction-outputs/
    canned-retrieval-plans/
    canned-synthesis-diffs/
  runs/
    <timestamp>/
      summary.json
      per-fixture.json
      per-route.json
```

## Fixture file schema

Every fixture file is a JSON document with this minimum shape:

```ts
type FixtureFile = {
  fixtureId: string;                  // unique within its eval category
  category: 'extraction' | 'retrieval' | 'synthesis' | 'validation' | 'segmentation' | 'cache';
  description: string;                // one-sentence intent
  traps: string[];                    // e.g. ['paraphrase', 'synthesized_quote', 'pii']
  inputs: unknown;                    // category-specific input payload
  expected: unknown;                  // category-specific expected output
  scoringRules?: {
    minPrecision?: number;
    minRecall?: number;
    minQuoteValidity?: number;
    maxWrongDomainRate?: number;
    requireQuarantineFor?: string[];  // candidate IDs that must be quarantined
    forbidExtractionFor?: string[];   // PII spans that must never produce claims
  };
};
```

Per category, `inputs`/`expected` are typed concretely.

### Extraction fixture shape

```ts
type ExtractionFixture = FixtureFile & {
  category: 'extraction';
  inputs: {
    sourceType: 'message' | 'document_chunk';
    messages?: Array<{ messageId: string; employeeId: string; text: string; createdAt: string }>;
    documentChunk?: { chunkId: string; documentId: string; text: string; pageNumber?: number };
    routeId: string;                  // route under test
  };
  expected: {
    claims: Array<{
      summary: string;                // exact or fuzzy-matched against extracted summary
      claimType: string;
      domains: string[];
      stance?: string;
      exactQuote: string;
      sourceMessageId?: string;
      sourceDocumentChunkId?: string;
      assertedByEmployeeId?: string;
      mustBePromoted: boolean;
      mustBeQuarantined?: boolean;
      mustBeFlaggedSensitive?: boolean;
    }>;
    forbiddenClaims?: Array<{ reason: string; spans?: string[] }>;
    expectedSensitivityFlags?: {
      anyContainsSensitiveHRData?: boolean;
      anyContainsSensitivePersonalData?: boolean;
      anyIsPersonalConflict?: boolean;
    };
  };
};
```

### Retrieval fixture shape

```ts
type RetrievalFixture = FixtureFile & {
  category: 'retrieval';
  inputs: {
    query: string;
    actorRole: 'employee' | 'admin' | 'worker';
    routeId: string;
    seededCorpus: {
      claims: Array<{ id: string; summary: string; domains: string[]; reviewStatus: string }>;
      documentChunks: Array<{ id: string; documentClass: string; domains: string[]; text: string }>;
      messages: Array<{ id: string; text: string; createdAt: string }>;
    };
  };
  expected: {
    retrievalPlan: {
      topDomainHints: string[];
      requiredEntities?: Array<{ entityType: string; canonicalValue: string }>;
      excludedDocumentClasses?: string[];
      processStageHints?: string[];
    };
    mustInclude: string[];            // IDs that must appear in retrieved set
    mustExclude: string[];            // IDs that must NOT appear
    minRelevanceAt: { k: number; threshold: number }; // e.g. {k: 5, threshold: 0.8}
    hybridSearchRequired: boolean;
  };
};
```

### Synthesis fixture shape

```ts
type SynthesisFixture = FixtureFile & {
  category: 'synthesis';
  inputs: {
    sectionId: string;
    currentVersionMarkdown: string;
    approvedClaimIds: string[];
    approvedClaims: Array<{ id: string; summary: string; exactQuote: string; sourceRef: string }>;
    contradictions?: Array<{ claimAId: string; claimBId: string }>;
    routeId: string;
  };
  expected: {
    materialParagraphsMustMapToClaimIds: boolean;
    forbiddenAssertions: string[];    // strings that must not appear in output
    requiredAssertions: string[];     // strings that must appear
    allowedNewClaims?: string[];      // claim IDs allowed to be cited
    structuredDiffMustValidate: boolean;
    sensitiveClaimsMustBeAbsent: string[]; // claim IDs that must never appear in synthesis
  };
};
```

### Validation fixture shape

```ts
type ValidationFixture = FixtureFile & {
  category: 'validation';
  inputs: {
    case: 'quote_perfect' | 'quote_paraphrase' | 'quote_synthesized' | 'quote_punctuation_rewrite'
        | 'quote_ambiguous_repeated' | 'duplicate_promotion' | 'pii_hr' | 'pii_personal_conflict'
        | 'circuit_breaker_three_strikes' | 'concurrent_promotion_race';
    sourceText?: string;
    proposedQuote?: string;
    proposedOffsets?: { start: number; end: number };
    candidateSensitivityFlags?: { containsSensitiveHRData?: boolean; isPersonalConflict?: boolean };
    repeatedFailureCount?: number;
    raceContext?: { workerCount: number; identicalSummary: string };
  };
  expected: {
    validatorVerdict: 'valid' | 'invalid' | 'ambiguous' | 'quarantined_sensitive' | 'circuit_broken' | 'duplicate_winning_lost';
    expectedValidationStatus?: string;
    expectedCandidateStatus?: string;
    expectedClaimRowsCreated?: number;
    expectedEvidenceAppendedToExistingClaim?: boolean;
  };
};
```

### Segmentation fixture shape

```ts
type SegmentationFixture = FixtureFile & {
  category: 'segmentation';
  inputs: {
    case: 'entity_alias_resolution' | 'unknown_entity_proposal' | 'cross_domain_contamination'
        | 'sub_topic_drift' | 'wrong_top_domain';
    rawText?: string;
    entityProposal?: { entityType: string; rawValue: string };
    existingRegistry?: Array<{ entityType: string; canonicalValue: string; aliases: string[] }>;
    claimEmbeddingShift?: number;
  };
  expected: {
    expectedEntityResolution?: { resolvedCanonicalValue?: string; queuedForReview?: boolean };
    expectedDomainAssignment?: string[];
    expectedDriftFlag?: boolean;
    expectedProposalType?: 'create_sub_topic' | 'merge' | 'split' | 'reassign' | 'create_top_domain';
  };
};
```

### Cache fixture shape

```ts
type CacheFixture = FixtureFile & {
  category: 'cache';
  inputs: {
    case: 'stable_prefix_repeat' | 'unstable_timestamp' | 'reordered_tool_schema'
        | 'explicit_cache_profitability_check';
    callPlan: Array<{ promptBlocks: Array<{ kind: string; content: string }> }>;
    routeId: string;
    sourceTokenEstimate?: number;
    expectedReuseCount?: number;
  };
  expected: {
    cacheReadTokensMinRatio?: number; // e.g. 0.6 means at least 60% cached
    stablePrefixHashMustBeIdenticalAcrossCalls?: boolean;
    explicitCacheShouldBeCreated?: boolean;
  };
};
```

## Metric definitions

All metrics are computed by `runners/shared/metrics.ts`. Use these formulas exactly so route comparisons are apples-to-apples.

| Metric | Formula | Notes |
| :--- | :--- | :--- |
| Precision | `truePositiveClaims / extractedClaims` | A claim is true-positive if it matches an expected claim by summary similarity ≥0.85 AND has a valid exact quote. |
| Recall | `truePositiveClaims / expectedClaims` | Missing an expected claim counts against recall. |
| F1 | `2 * (precision * recall) / (precision + recall)` | Reported but not used as a gate alone. |
| Quote validity | `validQuotes / extractedQuotes` | A quote is valid only if `.includes()` and offsets match per `03-candidate-before-claim-validation.md`. |
| Wrong-domain rate | `wrongTopDomainAssignments / extractedClaims` | Top-domain disagreement with expected. Sub-topic mismatches reported separately. |
| Sensitive quarantine rate | `quarantinedSensitive / expectedSensitive` | Must be 100% — no PII slips through to promotion. |
| Duplicate rate | `duplicatePromotions / extractedClaims` | After concurrency-locked promotion. Must be 0% in fixtures. |
| Hybrid search precision@k | `relevantInTopK / k` | Across pgvector and tsvector merged via RRF. |
| Retrieval recall | `expectedIncludedDocsFound / expectedIncludedDocs` | Per `RetrievalPlan`. |
| Contamination rate | `forbiddenDocsInTopK / k` | E.g. vendor-manual chunks appearing in an ERP question. Must be 0. |
| Cache hit ratio | `cachedInputTokens / inputTokens` | Per provider-native usage. Reported per route. |
| Prefix stability | `1 - (distinctStablePrefixHashes / totalCalls)` | Higher is better. |
| Cost per valid claim | `totalCostUsd / validExtractedClaims` | Live-mode only. |

## Extraction evals

Extraction evals must measure:

- exact quote validity (gate: ≥98%);
- precision of extracted claims (gate: ≥0.85);
- recall of known expected claims (gate: ≥0.75 for default route, higher for escalation);
- wrong top-domain rate (gate: ≤10%);
- duplicate candidate rate (gate: 0%);
- sensitive material rejection/quarantine rate (gate: 100%);
- schema validity (gate: 100% — non-conformant outputs must be caught by `StructuredOutputValidator`);
- validation-loop circuit breaker behavior (gate: trips at exactly 3 strikes);
- cost per valid candidate (live mode only).

Required extraction fixture traps (at least one fixture per trap):

1. **Routine handoff** — a clean operational claim. Sanity baseline.
2. **Group-chat disagreement** — speaker A states a rule, speaker B introduces an exception. Both must be extracted with correct stances.
3. **Paraphrase trap** — model is tempted to "clean up" grammar. Must produce a verbatim quote, not a corrected version.
4. **Synthesized-quote trap** — claim spans two messages. Must not be merged into one fake quote.
5. **Sensitive PII trap** — message discusses an employee's medical leave. Must be quarantined; must never reach `claims`.
6. **Duplicate-rule trap** — same rule re-stated days apart by different employees. Must be deduped; evidence appended to existing claim.
7. **Edited-message trap** — quote points at an edited/deleted message. Must reject unless historical extraction is allowed.
8. **Punctuation rewrite trap** — model "fixes" a quoted phrase by adding a missing comma. Must invalidate.

Required document-extraction fixtures:

1. **Routing-guide page** — a clean customer routing-guide page with extractable rules.
2. **Vendor-manual page** — must produce claims tagged `document_class: vendor_manual`. Verifies that downstream retrieval can exclude vendor manuals.

## Retrieval evals

Retrieval evals must prove the Oracle does not search the entire knowledge base blindly and that hybrid search beats vector-only on exact-entity queries.

Required tests:

1. **ERP image-upload question** — query: "when does an image get uploaded to Coldlion."
   - expected retrieval plan: `topDomainHints: ['it_systems', 'production_lifecycle']`, `requiredEntities: [{system: 'Coldlion'}]`, `excludedDocumentClasses: ['vendor_manual']`;
   - expected retrieval includes Coldlion/artwork/design/production claims;
   - expected retrieval excludes vendor manuals;
   - contamination rate must be 0.
2. **Vendor manual contamination** — query: an internal handoff question.
   - expected retrieval excludes vendor manuals and customer routing guides unless explicitly requested.
3. **Exact SKU lookup** — query mentions `BR-9901`.
   - expected retrieval uses tsvector full-text search;
   - vector-only search must lose to RRF on this fixture;
   - gate: hybrid precision@5 must exceed vector-only precision@5 by ≥0.2 absolute.
4. **Exact factory code lookup** — query mentions `FCT-882`.
   - same hybrid-search requirement as SKU lookup.
5. **Superseded claim exclusion** — current-operation query against a corpus that contains both current and superseded claims.
   - expected retrieval includes current claims only.
6. **Cross-domain customer question** — query about a customer that spans `customer_ops` and `creative_design`.
   - expected retrieval surfaces material from both domains;
   - gate: retrieval recall across both domains ≥0.8.

Retrieval evals must output:

- retrieval plan;
- top domains hinted;
- excluded document classes;
- source types searched;
- whether broadening occurred;
- final included IDs;
- contamination breakdown by document class;
- hybrid-search delta (RRF score vs vector-only score);
- expected vs actual pass/fail.

## Synthesis evals

Synthesis evals must measure:

- every material paragraph maps to approved claim IDs (gate: 100%);
- no unsupported named people/systems/customers/process stages are introduced (gate: 100%);
- rejected/sensitive candidates are not used (gate: 100%);
- superseded claims are not used as current truth (gate: 100%);
- structured diff validates (gate: 100%);
- contradiction sections include both claims and an admin question;
- usefulness rating if human-rated output is available later (no automated gate yet).

Do not rely on model self-judgment for synthesis correctness. Backend validation must check evidence support.

Synthesis scoring rubric (for manual review when human ratings are collected):

| Dimension | 0 (fail) | 1 (marginal) | 2 (good) |
| :--- | :--- | :--- | :--- |
| Evidence fidelity | Unsupported assertion | Mostly supported with one gap | Every paragraph maps to claim IDs |
| Contradiction handling | Ignores or smooths over | Notes one side | Surfaces both sides + question |
| Voice | Cold/HR-ish | Bureaucratic | Operationally useful |
| Specificity | Generic | Some specifics | Names systems, customers, stages |

Aggregate score ≥6/8 with no zeros is the manual-review pass bar.

## Validation pipeline evals

Validation evals exercise the deterministic layer below the model — the part of `03-candidate-before-claim-validation.md` that must work even with a perfectly cooperative LLM.

Required tests (per the existing R5 spec plus new additions):

1. **Perfect quote match passes** (existing).
2. **Grammar-fix hallucination fails** (existing).
3. **Synthesized quote across two messages fails** (existing).
4. **Punctuation/whitespace rewrite fails** (existing).
5. **Repeated quote ambiguity fails without offsets, passes with correct offsets** (existing).
6. **Quoted speech inside source** — source contains nested quotation marks. Validator must preserve them verbatim.
7. **PII gate — HR data** — candidate with `containsSensitiveHRData: true` routes to `rejected_sensitive`. Verify it never reaches `claims` and never appears in the standard admin queue.
8. **PII gate — personal conflict** — candidate with `isPersonalConflict: true` routes to `quarantined_sensitive`.
9. **Circuit breaker — three strikes** — feed a source that produces 3 consecutive quote failures. Verify batch status becomes `failed_validation_loop`, no further retries occur, and an `extraction_validation_results` row with `checkName: 'validation_loop_circuit_breaker'` is written.
10. **Concurrent promotion race** — simulate two workers attempting to promote the same candidate hash. Verify exactly one `claims` row is created, the loser's evidence is appended to the winner, and the loser's candidate is marked `duplicate`.
11. **Duplicate promotion retry safety** — promote a candidate, then re-run the promoter. Verify no second `claims` row is created.

All of these must run in mock mode against a deterministic in-memory database stub.

## Knowledge segmentation evals

These exercise the three-layer taxonomy from `07-knowledge-segmentation.md` end-to-end.

Required tests:

1. **Entity alias resolution** — input `"the ERP"`. Expected: resolves to existing canonical `system: ERP`. Must not create a duplicate entity.
2. **Unknown entity proposal** — input `"Frobnitz Module"`. Expected: queued in `entity_proposals`; candidate stays pending; no claim is promoted with an unresolved entity.
3. **Unknown top-domain hard fail** — candidate references a non-existent top-domain ID. Expected: candidate rejected at validation; no promotion.
4. **Cross-domain contamination** — query about ERP image upload runs against a corpus seeded with vendor manuals tagged `vendor_management + document_class: vendor_manual`. Expected: zero vendor-manual chunks in the retrieved set.
5. **Sub-topic drift** — feed a claim whose embedding has shifted past the threshold from its assigned sub-topic centroid. Expected: monthly worker produces a `reassign_claims` proposal; no auto-mutation occurs.
6. **Cluster spans two domains** — feed cluster members split across two top-domains. Expected: worker produces a proposal but does not auto-create a new top-domain.
7. **Sub-topic activation threshold** — corpus has fewer than N claims per domain. Expected: no sub-topics generated; retrieval falls back to top-domain + entity tags only.

## Cache effectiveness evals

These verify that the cache discipline from `02-provider-native-ai-architecture.md` is actually achieving its cost goal.

Required tests:

1. **Stable prefix repeat** — run the same extraction call twice. Expected: second call's `cachedInputTokens / inputTokens ≥ 0.6` for Anthropic and OpenAI, ≥0.4 for Vertex implicit.
2. **Unstable timestamp regression** — inject a timestamp into the system prompt. Expected: distinct `stablePrefixHash` per call; eval flags the route as cache-broken.
3. **Reordered tool schema regression** — emit tool definitions in nondeterministic order. Expected: distinct `stablePrefixHash`; eval flags route as broken.
4. **Explicit cache profitability — large reused source** — `sourceTokenEstimate = 120_000`, `expectedReuseCount = 3`. Expected: `useExplicitGeminiCache = true` per the heuristic.
5. **Explicit cache profitability — small one-off** — `sourceTokenEstimate = 8_000`, `expectedReuseCount = 1`. Expected: `useExplicitGeminiCache = false`; no cache resource is created.
6. **Aggressive teardown** — simulate an extraction batch that completes in 2 minutes. Expected: `Delete` API call issued in `finally` immediately on completion; `provider_cached_content.status = deleted` with `deletedAt` set within seconds of `finishedAt`.

## Live vs mock mode

### Mock/deterministic mode

Uses canned model outputs in `packages/ai/evals/mocks/` to test validators, retrievers, promotion, segmentation, and cache logic without provider cost.

This mode must be available first. CI may run mock mode automatically once stable.

### Live-provider mode

Calls the selected route through `OracleAIClient` and measures real model behavior, cost, latency, and cache hit rate.

Live mode requires an explicit flag:

```bash
ORACLE_EVAL_LIVE=1 pnpm eval:extraction
ORACLE_EVAL_LIVE=1 pnpm eval:cache
```

Do not make live-provider evals the default. Live runs must:

- emit a per-run cost summary;
- store full request/response payloads in `packages/ai/evals/runs/<timestamp>/payloads/` for the configured TTL (default 7 days, then auto-purged);
- never be triggered from CI without manual approval;
- never log secrets or credentials.

## Per-route comparison protocol

Use `pnpm eval:compare` to compare two route IDs over the same fixture set.

Inputs:

```bash
pnpm eval:compare --baseline=vertex_gemini_flash_lite_extraction_primary \
                  --candidate=vertex_gemini_flash_extraction_primary \
                  --fixtures=extraction
```

Output: a side-by-side table per metric, with deltas, plus a verdict line.

Promotion rules:

- A candidate route may replace the baseline as a `DEFAULT_ORACLE_MODEL_ROUTES` entry only if it wins on **at least three** of: quote validity, precision, recall, cost per valid claim, while not losing more than 1 absolute point on any other metric.
- A candidate route may be added as a fallback/escalation route only if it improves at least one specific failure mode in the failure-mode taxonomy below.
- Route promotion must be recorded in `DECISIONS.md` with the eval run timestamp and the comparison summary.

## Output format

Each eval command prints a human-readable summary, writes a JSON artifact, and exits non-zero on gate failure.

Example console output:

```text
Extraction eval summary  (route: vertex_gemini_flash_lite_extraction_primary)
fixtures:                       8
expected claims:                21
extracted claims:               19
valid extracted claims:         18
precision:                      0.95
recall:                         0.86
F1:                             0.90
exact quote validity:           1.00
wrong top-domain rate:          0.05
sensitive quarantine pass:      true (3/3)
duplicate rate:                 0.00
schema validity:                1.00
circuit breaker triggered:      yes (fixture transcript-04, at 3 strikes)
cost:                           mock mode
gate status:                    PASS
```

```text
Retrieval eval summary  (route: vertex_gemini_flash_extraction_primary as planner)
fixtures:                       6
retrieval plan validity:        6/6
hybrid search precision@5:      0.92
vector-only precision@5:        0.71
hybrid > vector delta:          +0.21
contamination rate:             0.00 (0 vendor-manual chunks in 18 ERP results)
superseded exclusion:           pass
cross-domain recall:            0.85
gate status:                    PASS
```

```text
Validation eval summary
quote_perfect:                  pass
quote_paraphrase:               pass (rejected)
quote_synthesized:              pass (rejected)
quote_punctuation_rewrite:      pass (rejected)
quote_ambiguous_repeated:       pass (rejected without offsets, accepted with)
pii_hr:                         pass (quarantined_sensitive)
pii_personal_conflict:          pass (quarantined_sensitive)
circuit_breaker_three_strikes:  pass (failed_validation_loop at strike 3)
concurrent_promotion_race:      pass (1 claim, 2 evidence rows, loser=duplicate)
duplicate_promotion_retry:      pass (no second claim row)
gate status:                    PASS
```

## Phase gates

Do not enable broad background extraction until extraction evals pass.

Do not enable broad retrieval-backed chat until retrieval evals pass.

Do not enable automatic Brain section updates until synthesis evals pass.

Do not promote a route to `DEFAULT_ORACLE_MODEL_ROUTES` until its CLI eval suite passes the gates below.

Minimum initial gates (per route under test):

- exact quote validity: ≥98% on test fixtures;
- sensitive quarantine: 100% on test fixtures;
- contamination: 0 vendor-manual chunks in non-vendor retrieval tests;
- hybrid search > vector-only on exact-entity tests: ≥0.2 absolute precision@5 delta;
- no duplicate permanent claim creation in concurrency-race tests;
- circuit breaker trips at exactly 3 strikes;
- no unsupported synthesis paragraph;
- entity registry never auto-mutates;
- cache hit ratio ≥0.6 on stable-prefix-repeat test (Anthropic/OpenAI), ≥0.4 (Vertex implicit);
- prefix stability ≥0.95 across repeated identical calls.

Gates may be tightened over time, never silently loosened.

## Failure-mode taxonomy

When an eval fails, map the failure to a category and a remediation. This is the action table the operator runs through before opening an issue.

| Failure mode | First-level remediation | Escalation |
| :--- | :--- | :--- |
| Low quote validity | Inspect raw payload log (7-day TTL); check for paraphrase pattern. | Trip circuit breaker, switch to repair route, or pin to escalation route. |
| Low precision | Stricter prompt for low-impact claim filter; raise impact-score floor. | Switch to balanced or escalation route. |
| Low recall | Loosen prompt acceptance criteria; add more fixtures to identify miss pattern. | Switch to balanced route; do not jump to frontier. |
| High wrong-domain rate | Inspect taxonomy seed; check whether top-domain hints in prompt are stale. | Refresh `knowledge_top_domains` seed via admin. |
| Sensitive leak | Hard stop. Inspect PII gate; verify Zod schema fields are wired into validator. | Block route promotion; require manual review of all candidates from route since last eval. |
| Contamination | Inspect retrieval plan output; verify `excludedDocumentClasses` is honored. | Tighten retrieval plan; broaden only with admin log. |
| Hybrid worse than vector | Likely tsvector index missing or stale. | Re-index; if persistent, refile bug against retrieval planner. |
| Concurrent duplicate | Inspect advisory lock implementation; verify hashed candidate representation is stable. | Block worker rollout; fix lock before resuming. |
| Cache cold | Inspect `stablePrefixHash` drift; look for timestamp/tool-order/schema-key drift. | Pin tool/schema serialization; remove dynamic content from stable prefix. |
| Explicit cache cost overrun | Inspect `provider_cached_content` for resources not deleted. | Audit teardown `finally` blocks; tighten TTL. |

## Worked example: promoting a new extraction route

Scenario: Albert wants to consider `vertex_gemini_flash_extraction_primary` to replace the Flash-Lite default.

Steps:

1. Confirm Flash-Lite baseline eval is current (run within the last 7 days). If not, re-run.
2. Run the candidate route in mock mode:
   ```bash
   pnpm eval:extraction --route=vertex_gemini_flash_extraction_primary
   pnpm eval:validation --route=vertex_gemini_flash_extraction_primary
   pnpm eval:cache --route=vertex_gemini_flash_extraction_primary
   ```
3. Run live-mode for cost/latency only (no destructive operations):
   ```bash
   ORACLE_EVAL_LIVE=1 pnpm eval:extraction --route=vertex_gemini_flash_extraction_primary --no-write
   ```
4. Compare:
   ```bash
   pnpm eval:compare --baseline=vertex_gemini_flash_lite_extraction_primary \
                     --candidate=vertex_gemini_flash_extraction_primary \
                     --fixtures=extraction
   ```
5. Read the verdict. If candidate wins on three+ metrics without losing more than 1 absolute point elsewhere, eligible for promotion.
6. Record outcome in `DECISIONS.md` with eval-run timestamp and metric snapshot.
7. Update `DEFAULT_ORACLE_MODEL_ROUTES` in code, ship via PR.
8. Schedule a follow-up live-mode eval in 30 days to confirm the route holds up on real traffic patterns.

## What not to build yet

Do not build:

- a web eval dashboard;
- a complex annotation platform;
- third-party eval integrations (Braintrust, LangSmith, Promptfoo, etc.);
- model fine-tuning pipeline;
- RLHF workflow;
- automated prompt optimization service;
- automatic route promotion based on eval results — promotion is always an admin action.

Start with simple CLI evals that are impossible to ignore during implementation.

## Cross-references

- `01-model-roles-and-routes.md` — route IDs, escalation routes (including the Warmth Escalation), Flash-Lite fast-path trap warning.
- `02-provider-native-ai-architecture.md` — `OracleAIClient`, `ContextCompiler`, `ModelRouter`, hybrid retrieval order, Vertex caching heuristic and teardown rule.
- `03-candidate-before-claim-validation.md` — PII gate, concurrency-locked promotion, circuit breaker, evidence validation rules. Many validation evals here are the eval reflection of those rules.
- `04-context-packs-observability.md` — `oracle_context_packs`, `model_run_usage_details`, the 7-day raw payload log used by live-mode evals.
- `05-ai-retrofit-phase-packet.md` — R5 quote validator tests; R10 admin observability; this doc adds eval gates that must pass before each phase ships.
- `07-knowledge-segmentation.md` — the three-layer taxonomy that segmentation evals exercise.
