# AI Retrofit Phase Packet

Status: next implementation packet before building more intelligence features.

This file tells Claude Code exactly how to retrofit the existing codebase from the old OpenRouter-centered AI implementation to the Big 3 provider-native architecture.

## Do not implement Phase 6 interjection yet

The old `HANDOFF.md` may say Phase 6 interjection engine is next.

That is now superseded.

The next work is the AI architecture retrofit.

Reason:

- interjection depends on trustworthy claims;
- trustworthy claims depend on candidate-before-claim validation;
- candidate validation depends on context packs, model runs, and provider-native routes;
- provider-native routes require replacing the old OpenRouter-centered AI layer.

Do not build proactive interjections on top of direct-to-claim extraction.

## Phase R0: Documentation reset

Goal: ensure future AI coding agents follow the correct architecture.

Tasks:

1. Read `docs/oracle/00-buildout-index.md`.
2. Read only the specific docs needed for the active task. Do not use wildcard reads.
3. Update root onboarding docs as needed so AI agents know OpenRouter is legacy for production AI work.
4. Do not change runtime code in this phase unless necessary to keep docs accurate.

Acceptance gate:

- README points to the new Oracle addenda.
- CLAUDE.md tells Claude Code to read specific addenda before touching AI code.
- AGENTS.md or a linked doc clearly states that OpenRouter is legacy for production background workers.

## Phase R1: Model route configuration

Goal: replace arbitrary OpenRouter model strings with curated Big 3 route IDs.

Tasks:

1. Deprecate OpenRouter raw string usage — remove all production references to arbitrary OpenRouter model ID strings.
2. Define exactly 1 Primary Route and 1 Fallback Route for each of the 3 roles (Interview, Extraction, Synthesis) as specified in `01-model-roles-and-routes.md`. Do not define "balanced alternate routes" or multiple competing defaults.
3. Build the internal escalation subroutes (Triage, Warmth, Schema Repair) inside `OracleAIClient` — do not expose them as admin-selectable defaults.
4. Remove any existing code referencing "balanced alternate routes" or multiple defaults.
5. Add a route config module under `packages/ai/src/routes/`.
6. Define `OracleModelRoute` type.
7. Update Admin Settings so model pickers select route IDs, not arbitrary OpenRouter model IDs.
8. Keep old settings keys during migration, but mark them deprecated.
9. Add new settings keys:
   - `default_interview_route`;
   - `default_extraction_route`;
   - `default_synthesis_route`.

Acceptance gate:

- TypeScript route config compiles.
- Admin Settings shows curated route choices.
- Existing settings rows are migrated or gracefully mapped.
- OpenRouter catalog browsing is no longer the production model selection path.
- Frontier models are not default routes for cron workers or routine chat.

## Phase R2: Provider-native OracleAIClient

Goal: all future model calls go through one provider-neutral client with Big 3 direct adapters.

Tasks:

1. Add `packages/ai/src/oracle-ai-client.ts`.
2. Add `packages/ai/src/context/context-compiler.ts`.
3. Add `packages/ai/src/model-router.ts`.
4. Add provider adapters:
   - `packages/ai/src/providers/anthropic-adapter.ts`;
   - `packages/ai/src/providers/vertex-gemini-adapter.ts`;
   - `packages/ai/src/providers/openai-adapter.ts`.
5. Add usage normalization:
   - `packages/ai/src/usage/usage-normalizer.ts`.
6. Add validation gateway:
   - `packages/ai/src/validation/structured-output-validator.ts`;
   - `packages/ai/src/validation/evidence-validator.ts`.
7. Keep `packages/ai/src/openrouter.ts` temporarily but mark it deprecated.
8. Add dependencies only when needed:
   - `@anthropic-ai/sdk`;
   - `openai`;
   - `@google/genai` or the officially supported Google SDK chosen during implementation.

Acceptance gate:

- Adapters compile.
- `OracleAIClient` can perform at least one mocked or test-mode call per provider shape.
- No production worker is migrated yet.
- Existing chat route still works through legacy path until replaced.
- Provider credentials are read from environment without writing credentials to disk.

## Phase R3: Context packs and usage logging schema

Goal: add database support for observability before worker migration.

Tasks:

1. Add `oracle_context_packs` table.
2. Add `model_run_usage_details` table.
3. Add `provider_cached_content` table.
4. Add indexes for task type, route ID, context pack, and creation date.
5. Add raw SQL constraints where Drizzle is weak.
6. Update migration docs.
7. Update admin views or add new views if useful.

Acceptance gate:

- Migrations apply cleanly through the custom migration runner.
- Existing model runs remain readable.
- No old data is dropped.
- Schema is exported from `@oracle/db`.

## Phase R3.5: Knowledge taxonomy schema

Goal: install the three-layer knowledge taxonomy from `07-knowledge-segmentation.md` before extraction starts producing entity tags.

This phase is schema-only. No worker behavior changes here.

Tasks:

1. Add `knowledge_top_domains` table and support an approved seed set from the system's bootstrap domain-proposal pass. The system may propose top-level domains from company context and early evidence; admin approval activates them. Each row must include boundary fields: belongs-here examples, does-not-belong-here examples, common entity hints, default excluded document classes, and neighboring domains.
2. Add `knowledge_sub_topics` table with `review_status` constraint and centroid vector column. Empty on install.
3. Add `claim_top_domains`, `document_top_domains`, `document_chunk_top_domains`, `message_top_domains`, and `claim_sub_topics` join tables so retrieval can filter raw documents/messages before claims are promoted.
4. Add `entities` canonical registry, seeded with the initial known customers, licensors, vendors, and systems. `licensor` is a first-class entity type distinct from `vendor`.
5. Add `claim_entities`, `document_chunk_entities`, and `message_entities` join tables.
6. Add `claim_metadata` table for process stage, department, geography, document class, time validity, supersession pointer.
7. Add `taxonomy_proposals` queue and `taxonomy_change_log` audit table. Proposal types must include top-level domain creation/merge/split, sub-topic creation/merge/split, claim reassignment, and retirement. The `payload` shape must follow the proposal-card contract in `07-knowledge-segmentation.md`, including evidence IDs, snippets, affected counts, suggested exclusions, recommended action, confidence, and rollback/preview metadata.
8. Add `entity_proposals` queue for unknown entity references surfaced by extraction.
9. Add indexes on every join table by the non-claim side.
10. Add HNSW index on `knowledge_sub_topics.centroid`.
11. Backfill `claim_top_domains` from the existing `knowledge_domain` enum column on `claims`. Do not drop the old column yet.
12. Export new schema from `@oracle/db`.
13. Update `docs/oracle/07-knowledge-segmentation.md` with the final SQL if anything diverged from the sketch.

Acceptance gate:

- migrations apply cleanly through the custom migration runner;
- `knowledge_top_domains` is seeded from an approved proposal set;
- the admin has a compact way to approve/rename/merge/reject proposed top-level domains without reading long source text;
- `knowledge_top_domains` rows include boundary rules, not just names;
- `entities` is seeded with the initial known customers/licensors/vendors/systems;
- documents, chunks, messages, and claims can all be tagged by top-level domain;
- existing claims have a corresponding `claim_top_domains` row via backfill;
- no claim is silently dropped;
- the legacy `knowledge_domain` enum column on `claims` is still present and readable;
- nothing in extraction or chat code has changed yet.

## Phase R4: Candidate-before-claim staging schema

Goal: add staging tables before changing extraction behavior.

Tasks:

1. Add `extraction_batches`.
2. Add `extraction_candidates`.
3. Add `extraction_candidate_evidence`.
4. Add `extraction_validation_results`.
5. Add fields needed for retry safety and circuit breakers:
   - validation attempt count;
   - consecutive quote failure count;
   - failed validation loop status;
   - route/model-run IDs attempted.
6. Add indexes for status, batch, source IDs, promoted claim ID, and creation date.
7. Add check constraints for evidence source type/pointer consistency.
8. Add unique/idempotency constraints where safe.
9. Export schema from `@oracle/db`.

Acceptance gate:

- Migrations apply cleanly.
- Existing claim/evidence tables remain unchanged.
- Staging rows can be inserted and queried.
- Circuit-breaker fields exist before worker behavior changes.
- No worker behavior has been changed yet.

## Phase R5: Exact quote validator and promotion service

Goal: implement deterministic validation and transactional promotion.

Tasks:

1. Add `packages/oracle-engines/src/extraction/quote-validator.ts`.
2. Add `packages/oracle-engines/src/extraction/promote-candidate.ts`.
3. Add functions:
   - validate candidate source pointers;
   - validate exact quote;
   - compute char offsets;
   - detect repeated/ambiguous quote;
   - apply allowed normalization only when configured;
   - record validation results;
   - promote valid candidate in transaction.
4. Add isolated validation tests before wiring workers.

Required validation tests:

1. Perfect match passes:
   - source: `I talked to Adam yesterday and we agreed that Burlington seasonal items need to go through the new routing guide.`
   - quote: `Burlington seasonal items need to go through the new routing guide.`
   - expected: valid.
2. Grammar-fix hallucination fails:
   - source: `the fctry cant ship til thursday because of the storm.`
   - quote: `The factory cannot ship until Thursday because of the storm.`
   - expected: invalid.
3. Synthesized quote fails:
   - source message 1: `We need approval from Disney.`
   - source message 2: `And we need it before Friday.`
   - quote: `We need approval from Disney before Friday.`
   - expected: invalid because the quote combines two messages.
4. Punctuation/whitespace rewrite fails:
   - source: `Wait... let me check Coldlion.`
   - quote: `Wait let me check Coldlion.`
   - expected: invalid.
5. Repeated quote ambiguity fails unless offsets disambiguate:
   - source contains the same quote twice;
   - quote is present but no offsets are supplied;
   - expected: ambiguous.
6. Duplicate promotion retry does not create duplicate permanent claims.

Acceptance gate:

- All validation tests pass.
- Invalid quotes never promote.
- Promotion creates claim, domains, and evidence in one transaction.
- Duplicate retries do not create duplicate permanent claims.
- Validation errors are stored and inspectable.
- Do not proceed to Trigger.dev worker wiring until isolated validator tests pass.

## Phase R5.5: Entity and metadata extraction in the candidate pipeline

Goal: extract knowledge taxonomy tags alongside each claim candidate in the same model run, so that promotion writes claims with their full metadata atomically.

This phase extends the extraction prompt and the candidate schema. No worker is wired yet; that happens in R6.

Tasks:

1. Extend the candidate extraction prompt to also produce, per claim candidate:
   - one or more `top_domain_id` references;
   - zero or more entity references with `entity_type` and `canonical_value` (or proposed new entity);
   - optional `process_stage`, `department`, `geography`, `document_class`, `time_validity`.
2. Extend `extraction_candidates` schema to hold proposed top-domain IDs, proposed entity references, and proposed metadata.
3. Extend `extraction_candidate_evidence` to carry the document_class and process_stage if the model surfaced them.
4. Extend document ingestion and message preprocessing to write `document_top_domains`, `document_chunk_top_domains`, and `message_top_domains` before claim promotion, using the same validator and proposal flow.
5. Extend the deterministic validator from R5:
   - validate that every proposed `top_domain_id` exists in `knowledge_top_domains`;
   - validate that every proposed entity either resolves in `entities` or is queued as a proposal in `entity_proposals`;
   - validate that licensor references resolve to `entity_type = 'licensor'`, not `vendor`;
   - reject candidates whose top-domain or entity references cannot be resolved or proposed cleanly.
6. Extend the promotion service from R5 to write `claim_top_domains`, `claim_entities`, and `claim_metadata` in the same transaction that creates the claim and its evidence.
7. Add isolated tests for entity normalization (alias resolution to canonical value) before wiring workers.

Required tests:

1. Known entity alias resolves: `"the ERP"` resolves to the existing canonical `system: ERP`.
2. Unknown entity is staged, not auto-created: `"Frobnitz"` produces an `entity_proposals` row, candidate stays pending until reviewed or promoted with `unknown_entity_allowed` flag false.
3. Unknown top-level domain is staged for review: candidates referencing a non-existent `top_domain_id` never promote directly; they create or link to a `taxonomy_proposals` row.
4. Licensor is not vendor: `"Disney approval"` resolves to `entity_type = 'licensor'`, not `vendor`.
5. Pre-claim chunk retrieval works: a tagged document chunk can be included/excluded by top-domain and entity filters before any claim has been promoted from it.
6. Promotion is transactional: a failure writing `claim_entities` rolls back the claim, evidence, and domain rows.

Acceptance gate:

- candidate schema and validator changes compile and pass tests;
- entity proposals appear in the admin queue when extraction encounters unknown entities;
- no production worker has been wired yet;
- no claim has been promoted with missing required taxonomy fields.

## Phase R6: Refactor claim extraction worker

Goal: stop writing directly from model output to permanent truth tables.

Tasks:

1. Replace OpenRouter `generateObject` call with `OracleAIClient` route `default_extraction_route`.
2. Compile context with `ContextCompiler`.
3. Insert context pack before or during model call.
4. Store model output in `extraction_batches` and `extraction_candidates`.
5. Store proposed evidence in `extraction_candidate_evidence`.
6. Run deterministic validation.
7. Promote only validated candidates.
8. Update messages extraction status based on batch result.
9. Log model run and usage details.
10. Preserve failed candidates for review.
11. Implement validation-loop circuit breaker:
    - if a source batch fails deterministic quote validation more than 3 times in a row, stop retrying it;
    - mark the batch and affected candidates `failed_validation_loop`;
    - record the route IDs, model run IDs, source hash, failed quotes, and retry count;
    - move on to the next independent batch.

Acceptance gate:

- worker no longer inserts directly into `claims` before validation;
- every model call has model run, usage details, and context pack;
- valid candidates promote transactionally;
- invalid candidates remain staged;
- cron can safely retry;
- validation loops cannot run forever.

## Phase R7: Refactor document ingestion worker

Goal: use Vertex/Gemini direct for document-heavy extraction and explicit context caching where justified.

Storage bridge requirement:

The durable source of uploaded company documents remains Supabase Storage. Vertex explicit context caching may require a Google-native file handle, Cloud Storage URI, or SDK upload depending on the final SDK/API path. Therefore, the worker must include a secure Supabase-to-Vertex bridge.

Tasks:

1. Parse documents into chunks as before.
2. For large document extraction, stream the source file from private Supabase Storage server-side using service-role access.
3. Do not expose document bytes to the browser.
4. Upload the file to the Google/Vertex temporary file mechanism or Google Cloud Storage path selected by the official SDK/API implementation.
5. Create explicit cached content only when the same large source context will be reused.
6. Store explicit cached content resources in `provider_cached_content`.
7. Store temporary Google file/resource metadata needed for cleanup.
8. Run extraction against chunk/page/document context.
9. Stage candidates just like message extraction.
10. Validate quotes against document chunks.
11. Promote only validated candidates.
12. Attach every explicit cache to a reuse policy: expected reuse count, latest planned reuse step, hard expiration, cleanup owner, and cleanup status.
13. Delete explicit caches immediately in `finally` only when the planned reuse window is complete and no retry/follow-up pass is expected.
14. Keep explicit caches only until the last planned reuse or short TTL expiration when retries, validation repair, synthesis, or follow-up passes are expected.
15. Always clean up temporary Google file resources when their TTL/policy expires, and record cleanup success/failure in Postgres.

Credentials rule:

Do not write a physical `credentials.json` file to disk in Trigger.dev.

Preferred authentication options, in order:

1. workload identity or managed identity if available for the deployment setup;
2. service-account credentials supplied through secure environment variables and constructed in memory;
3. provider-supported ADC-style environment variables if confirmed by the selected SDK.

The implementation must verify the chosen SDK's exact Vertex authentication behavior before assuming that environment variables such as `GOOGLE_CLIENT_EMAIL` and `GOOGLE_PRIVATE_KEY` are auto-discovered.

Recommended env surface, subject to SDK verification:

```text
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLIENT_EMAIL=
GOOGLE_PRIVATE_KEY=
```

If `GOOGLE_PRIVATE_KEY` is stored with escaped newlines, the implementation must convert `\\n` to real newline characters in memory.

Acceptance gate:

- large document extraction can use explicit Vertex cached content;
- Supabase remains the durable document store;
- Vertex temporary file/cache resources are tracked with lifecycle status;
- cached content resource metadata is stored;
- cache cleanup runs on both success and failure paths;
- document evidence links to chunk IDs;
- invalid quotes fail validation;
- costs/cache metrics are visible;
- credentials are never written to disk or committed.

## Phase R8: Refactor chat route

Goal: route live Oracle chat through `OracleAIClient` while preserving product behavior.

Tasks:

1. Keep current auth, channel membership, and retrieval constraints.
2. Replace direct OpenRouter usage with interview route through `OracleAIClient`.
3. Keep context small: recent messages, employee profile, highest-priority relevant gaps, strictly relevant claims.
4. Do not load full Brain sections by default.
5. Preserve tools:
   - search company knowledge;
   - check open gaps.
6. Log model run, usage, and context pack.

Acceptance gate:

- Oracle chat still responds to direct mentions and DMs;
- group chat direct-mention gate still works;
- no full Brain stuffing;
- context pack exists for each model call;
- OpenRouter is not used for normal chat unless explicit fallback is enabled.

## Phase R9: Refactor synthesis worker

Goal: make Brain synthesis evidence-strict and provider-native.

Tasks:

1. Use synthesis route through `OracleAIClient`.
2. Default to the cost-aware synthesis route from `01-model-roles-and-routes.md`.
3. Keep Claude Sonnet/Opus or other frontier models as escalation/manual-only routes.
4. Compile stable synthesis prompt/schema before dynamic claims.
5. Use provider-native caching for the chosen route.
6. Generate structured synthesis diff.
7. Validate every material paragraph maps to approved claim IDs.
8. Reject unsupported named people, systems, customers, stages, departments, or process rules.
9. Do not update current Brain version if validation fails.
10. Store failed synthesis output for review.

Acceptance gate:

- synthesis never updates Brain without validation;
- every material statement maps to approved claim IDs;
- failed validation is inspectable;
- cache/usage/context metrics are logged;
- frontier synthesis is not run by default.

## Phase R10: Admin observability dashboards

Goal: make the AI system measurable.

Tasks:

1. Add AI runs dashboard.
2. Add context pack viewer.
3. Add cache dashboard.
4. Add extraction candidate review dashboard.
5. Add model route comparison panel.
6. Add eval results dashboard placeholder if evals not implemented yet.
7. Add domain/source-type retrieval diagnostics so Albert can see whether retrieval searched the right knowledge area.

Acceptance gate:

- Albert can see cost per valid claim;
- Albert can inspect failed candidates;
- Albert can see which model route produced which candidates;
- Albert can inspect cache hits/misses;
- Albert can see why a Brain update was accepted or rejected;
- Albert can see which domains/source types were searched for an Oracle answer.

## Phase R10.5: Taxonomy governance dashboard and maturity-based re-evaluation worker

Goal: give the admin tooling to govern the knowledge taxonomy and run the maturity-based re-evaluation worker.

Tasks:

1. Add a Trigger.dev scheduled task `taxonomy-reevaluation` that runs on a maturity-based cadence and can be triggered manually by admin. During early learning, run weekly or after enough new evidence lands; once stable, run monthly or quarterly.
2. Implement the worker steps described in `07-knowledge-segmentation.md`:
   - per-domain density clustering on stored claim embeddings;
   - cluster naming via cheap synthesis call;
   - overlap analysis against current sub-topic centroids;
   - drift detection per claim;
   - cross-domain pattern check;
   - proposal writing to `taxonomy_proposals` only, including top-level domain proposals when current domains do not fit;
   - proposal payloads that include compact-card fields and boundary-rule previews;
   - no auto-mutation of taxonomy.
3. Add admin dashboard `/admin/taxonomy` with tabs:
   - top-level domains: proposal cards, list, add, rename, merge, split, retire (with safeguards);
   - sub-topics: list per domain, view members, view centroid drift;
   - entity registry: list, edit aliases, add `domain_hints`, retire, and distinguish licensors from vendors;
   - proposals queue: review compact taxonomy proposal cards, approve in batches, rename/merge/split, reject, defer;
   - entity proposals queue: review unknown entities surfaced by extraction;
   - change log: read-only view of `taxonomy_change_log`.
4. Implement the transactional reclassification job, triggered only by approved proposals:
   - updates `claim_sub_topics` rows;
   - writes `taxonomy_change_log` entries;
   - optionally queues targeted Brain synthesis re-runs for affected sections;
   - preserves `claim_evidence` unchanged.
5. Add retrieval diagnostics so the admin can see, for any Oracle answer, which top-level domains, sub-topics, entities, and document classes were searched. Tie this into the `oracle_context_packs` viewer from R10.

Acceptance gate:

- the re-evaluation worker produces proposals on real data without auto-mutating taxonomy;
- top-level domain proposals are compact and evidence-backed enough for admin review without reading long raw documents;
- proposal cards include boundary rules and default retrieval exclusions;
- admin can approve, reject, and batch-process proposals;
- reclassification is transactional and audited;
- entity proposal queue is reviewable and prevents auto-creation;
- retrieval diagnostics show domain/entity/document-class filters per Oracle answer.

## Phase R11: Resume interjection engine

Only after R1-R10 are complete should the project resume Phase 6 interjection.

Reason:

- live interjection uses claims/contradictions/gaps;
- those must be trustworthy;
- trustworthy intelligence requires the validation pipeline.

Acceptance gate before interjection:

- candidate pipeline live;
- at least one test transcript processed;
- claims reviewed and approved;
- contradiction watcher tested on validated claims;
- admin can audit every AI call that contributed to the contradiction or gap.

## Do not do these during the retrofit

- Do not rewrite the whole app.
- Do not replace Supabase/Postgres.
- Do not introduce LangChain, LangGraph, Python, Docker, or VPS services.
- Do not remove existing auth/RLS logic.
- Do not drop old settings or model run columns before migration.
- Do not build proactive interjection before the validation pipeline.
- Do not let a provider SDK leak into route handlers/workers outside `OracleAIClient`.

## Completion definition

The AI retrofit is complete when:

- Big 3 direct adapters exist;
- model routes are selected by curated route ID;
- OpenRouter is legacy fallback only;
- extraction uses candidates before claims;
- extraction also produces entity, top-domain, and metadata tags atomically with each claim;
- the three-layer knowledge taxonomy is live (top-level domains, sub-topics, entity registry);
- the maturity-based taxonomy worker writes proposals that admin reviews and approves;
- document extraction can use Vertex caching;
- synthesis uses provider-native cost-aware routes;
- model runs include cache and context-pack metrics;
- admin can inspect cost, failures, validation, context, and taxonomy diagnostics;
- eval metrics can compare routes by cost per useful validated result;
- retrieval routes every query through a `RetrievalPlan` with metadata pre-filter before vector search;
- no global vector search path remains in chat, synthesis, contradiction review, or interjection code.
