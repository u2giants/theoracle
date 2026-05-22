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
2. Read all docs in `docs/oracle/`.
3. Update root onboarding docs as needed so AI agents know OpenRouter is legacy for production AI work.
4. Do not change runtime code in this phase unless necessary to keep docs accurate.

Acceptance gate:

- README points to the new Oracle addenda.
- CLAUDE.md tells Claude Code to read the new addenda before touching AI code.
- AGENTS.md or a linked doc clearly states that OpenRouter is legacy for production background workers.

## Phase R1: Model route configuration

Goal: replace arbitrary OpenRouter model strings with curated Big 3 route IDs.

Tasks:

1. Add a route config module under `packages/ai/src/routes/`.
2. Define `OracleModelRoute` type.
3. Define default routes:
   - interview: `anthropic_claude_sonnet_interview_primary`;
   - extraction: `vertex_gemini_flash_extraction_primary`;
   - synthesis: `anthropic_claude_sonnet_synthesis_primary`.
4. Define fallback/escalation routes from `01-model-roles-and-routes.md`.
5. Update Admin Settings so model pickers select route IDs, not arbitrary OpenRouter model IDs.
6. Keep old settings keys during migration, but mark them deprecated.
7. Add new settings keys:
   - `default_interview_route`;
   - `default_extraction_route`;
   - `default_synthesis_route`.

Acceptance gate:

- TypeScript route config compiles.
- Admin Settings shows curated route choices.
- Existing settings rows are migrated or gracefully mapped.
- OpenRouter catalog browsing is no longer the production model selection path.

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
   - Google Vertex/Gemini SDK chosen during implementation.

Acceptance gate:

- Adapters compile.
- `OracleAIClient` can perform at least one mocked or test-mode call per provider shape.
- No production worker is migrated yet.
- Existing chat route still works through legacy path until replaced.

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
5. Add indexes for status, batch, source IDs, promoted claim ID, and creation date.
6. Add check constraints for evidence source type/pointer consistency.
7. Add unique/idempotency constraints where safe.
8. Export schema from `@oracle/db`.

Acceptance gate:

- Migrations apply cleanly.
- Existing claim/evidence tables remain unchanged.
- Staging rows can be inserted and queried.
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
4. Add tests or script-level verification fixtures for:
   - exact match;
   - missing quote;
   - repeated quote;
   - wrong source ID;
   - whitespace normalization;
   - multiline quote;
   - duplicate promotion retry.

Acceptance gate:

- Invalid quotes never promote.
- Promotion creates claim, domains, and evidence in one transaction.
- Duplicate retries do not create duplicate permanent claims.
- Validation errors are stored and inspectable.

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

Acceptance gate:

- worker no longer inserts directly into `claims` before validation;
- every model call has model run, usage details, and context pack;
- valid candidates promote transactionally;
- invalid candidates remain staged;
- cron can safely retry.

## Phase R7: Refactor document ingestion worker

Goal: use Vertex/Gemini direct for document-heavy extraction and explicit context caching where justified.

Tasks:

1. Parse documents into chunks as before.
2. Choose implicit vs explicit Vertex caching based on document size/reuse policy.
3. Store explicit cached content resources in `provider_cached_content`.
4. Run extraction against chunk/page/document context.
5. Stage candidates just like message extraction.
6. Validate quotes against document chunks.
7. Promote only validated candidates.
8. Expire/delete explicit caches by policy, not immediate `finally` deletion.

Acceptance gate:

- large document extraction can use explicit Vertex cached content;
- cached content resource metadata is stored;
- document evidence links to chunk IDs;
- invalid quotes fail validation;
- costs/cache metrics are visible.

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
2. Default to Anthropic Sonnet; allow Opus escalation.
3. Compile stable synthesis prompt/schema before dynamic claims.
4. Use explicit Anthropic cache breakpoints where available.
5. Generate structured synthesis diff.
6. Validate every material paragraph maps to approved claim IDs.
7. Reject unsupported named people, systems, customers, stages, departments, or process rules.
8. Do not update current Brain version if validation fails.
9. Store failed synthesis output for review.

Acceptance gate:

- synthesis never updates Brain without validation;
- every material statement maps to approved claim IDs;
- failed validation is inspectable;
- cache/usage/context metrics are logged.

## Phase R10: Admin observability dashboards

Goal: make the AI system measurable.

Tasks:

1. Add AI runs dashboard.
2. Add context pack viewer.
3. Add cache dashboard.
4. Add extraction candidate review dashboard.
5. Add model route comparison panel.
6. Add eval results dashboard placeholder if evals not implemented yet.

Acceptance gate:

- Albert can see cost per valid claim;
- Albert can inspect failed candidates;
- Albert can see which model route produced which candidates;
- Albert can inspect cache hits/misses;
- Albert can see why a Brain update was accepted or rejected.

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
- synthesis uses provider-native Anthropic route;
- model runs include cache and context-pack metrics;
- admin can inspect cost, failures, validation, and context;
- eval metrics can compare routes by cost per useful validated result.
