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

1. Add a route config module under `packages/ai/src/routes/`.
2. Define `OracleModelRoute` type.
3. Define cost-aware default routes:
   - interview: `anthropic_claude_haiku_interview_primary`;
   - extraction: `vertex_gemini_flash_lite_extraction_primary`;
   - synthesis: `vertex_gemini_flash_synthesis_primary`.
4. Define balanced alternate routes:
   - interview: `anthropic_claude_haiku_interview_primary`;
   - extraction: `vertex_gemini_flash_extraction_primary`;
   - synthesis: `anthropic_claude_haiku_synthesis_primary`.
5. Define escalation/manual-only routes from `01-model-roles-and-routes.md`.
6. Update Admin Settings so model pickers select route IDs, not arbitrary OpenRouter model IDs.
7. Keep old settings keys during migration, but mark them deprecated.
8. Add new settings keys:
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
12. Expire/delete explicit caches by policy, not immediate `finally` deletion when retries/follow-up passes are expected.
13. Always clean up temporary Google file resources when their TTL/policy expires.

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
- Vertex temporary file/cache resources are tracked;
- cached content resource metadata is stored;
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
- document extraction can use Vertex caching;
- synthesis uses provider-native cost-aware routes;
- model runs include cache and context-pack metrics;
- admin can inspect cost, failures, validation, and context;
- eval metrics can compare routes by cost per useful validated result;
- retrieval can route by domain, source type, entity, process stage, department, and document class.
