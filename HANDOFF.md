# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-24
**Repo:** https://github.com/u2giants/theoracle
**Current priority:** AI architecture retrofit before any more proactive interjection work.
**Continuing on a different machine:** clone fresh, `pnpm install`, pull `.env.local` (see AGENTS.md §12), then read the files below in order.

---

## Read this in order

1. `HANDOFF.md` — this file.
2. `AGENTS.md` — developer guide and repo conventions.
3. `CLAUDE.md` — Claude Code-specific instructions. This now contains the current AI retrofit priority.
4. `oracle_master_spec.md` — product/business contract.
5. `DECISIONS.md` — assumptions and historical decisions.
6. `docs/oracle/00-buildout-index.md` — index for the AI retrofit docs (lists 01–07).
7. The specific `docs/oracle/0N-*.md` files required for the active task (do not bulk-read).

---

## Critical update

Older handoff text said Phase 6, the interjection engine, was next.

That is now superseded.

**Do not implement proactive interjection yet.**

The next work is the AI architecture retrofit described in `docs/oracle/05-ai-retrofit-phase-packet.md`.

Reason:

- interjection depends on trustworthy claims;
- trustworthy claims depend on candidate-before-claim validation;
- candidate validation depends on context packs, model run observability, and provider-native model routes;
- provider-native model routes require replacing the old OpenRouter-centered AI layer.

Building proactive interjection before the AI retrofit would build on the wrong foundation.

---

## Current repo reality

The repo already has useful working foundation code:

- pnpm + Turborepo TypeScript monorepo;
- Next.js app under `apps/web`;
- Trigger.dev workers under `apps/workers`;
- Supabase/Postgres/Drizzle schema under `packages/db`;
- Supabase auth helpers under `packages/auth`;
- current AI helpers under `packages/ai`;
- admin dashboards and chat UI scaffolding;
- worker scaffolds and some deployed worker logic.

Do not start over.

This is a major AI/backend retrofit, not a full rebuild.

---

## Current architectural correction

The old implementation uses:

```text
Vercel AI SDK + OpenRouter
```

That path is now legacy for production AI workloads.

Target production architecture:

```text
OracleAIClient
  -> ContextCompiler
  -> ModelRouter
  -> Provider Adapter
      -> Anthropic direct
      -> Google Vertex AI / Gemini direct
      -> OpenAI direct
  -> UsageLogger / CostTracker / ContextPack
```

OpenRouter may remain temporarily for legacy runtime compatibility or experiments, but do not extend it for production extraction, document ingestion, synthesis, or cache-sensitive AI work.

---

## Model-role decision

The app should keep three primary model roles:

1. **Interview model** — human-facing Oracle chat/interviews.
2. **Extraction model** — high-volume claim candidate extraction from messages/documents.
3. **Synthesis model** — Brain section synthesis, contradiction reasoning, and admin-facing operational synthesis.

Cost-aware default routes (current target per `01-model-roles-and-routes.md`):

```ts
interview: 'anthropic_claude_haiku_interview_primary'
extraction: 'vertex_gemini_flash_lite_extraction_primary'
synthesis: 'vertex_gemini_flash_synthesis_primary'
```

Balanced alternate if evals show the cheap defaults are insufficient:

```ts
interview: 'anthropic_claude_haiku_interview_primary'
extraction: 'vertex_gemini_flash_extraction_primary'
synthesis: 'anthropic_claude_haiku_synthesis_primary'
```

Escalation routes (used selectively, not by default):

- `anthropic_claude_sonnet_interview_escalation` — reasoning/quality
- `anthropic_claude_haiku_45_interview_warmth_escalation` — emotional sensitivity (frustrated/defensive/confused/worried sentiment, personnel-conflict/blame/error-source/customer-issue topics)
- `anthropic_claude_sonnet_synthesis_escalation` — high-impact Brain updates
- `openai_mini_structured_extraction_fallback` — schema repair when Gemini fails

Top choices for each role are defined in `docs/oracle/01-model-roles-and-routes.md`.

---

## Next build sequence

Follow `docs/oracle/05-ai-retrofit-phase-packet.md`.

Summary (R3.5, R5.5, R10.5 were inserted after the original packet was written — see commit `88fdc22`):

1. **R0 Documentation reset** — ✅ done. Docs 00–07 are in `docs/oracle/`. CLAUDE.md and AGENTS.md route to them. R0 acceptance gate is met.
2. **R1 Model route configuration** — ⬜ next code phase. Add `packages/ai/src/routes/`, define `OracleModelRoute` type, seed curated routes, update Admin Settings to select by `routeId`.
3. **R2 Provider-native OracleAIClient** — adapters for Anthropic, Vertex/Gemini, OpenAI.
4. **R3 Context packs and usage logging schema** — add observability tables.
5. **R3.5 Knowledge taxonomy schema** — three-layer taxonomy from doc 07 (`knowledge_top_domains`, `knowledge_sub_topics`, `entities`, claim join tables, `taxonomy_proposals`, `taxonomy_change_log`). Schema-only; no worker behavior changes.
6. **R4 Candidate-before-claim staging schema** — add staging tables.
7. **R5 Exact quote validator and promotion service** — deterministic validation and transaction promotion. Includes PII gate enforcement and concurrency-locked promotion.
8. **R5.5 Entity and metadata extraction in the candidate pipeline** — extends candidate schema + validator to atomically promote claim + tags. `entity_proposals` queue for unknown entities.
9. **R6 Refactor claim extraction worker** — stage candidates, validate, then promote. Hooks the validation-loop circuit breaker.
10. **R7 Refactor document ingestion worker** — Vertex/Gemini direct, explicit context caching with profitability heuristic and tracked lifecycle cleanup.
11. **R8 Refactor chat route** — route through `OracleAIClient`. Use the `RetrievalPlan` + hybrid (pgvector + tsvector) RRF retrieval.
12. **R9 Refactor synthesis worker** — Vertex/Anthropic direct, strict synthesis validation.
13. **R10 Admin observability dashboards** — AI runs, context packs, cache dashboard (with traffic-light UX from doc 04), candidate review, 7-day payload log.
14. **R10.5 Taxonomy governance dashboard + maturity-based re-evaluation worker** — admin reviews compact `taxonomy_proposals` and `entity_proposals`; no auto-mutation of taxonomy.
15. **R11 Resume interjection engine** — only after the validation/segmentation pipeline is live and a test transcript has been processed end-to-end.

---

## What landed this session

Admin model picker fixes (2026-05-24, commits `76971c7`, `7606e35`):

- **OpenRouter proxy corrected to `/models/user`** (`apps/web/app/api/admin/models/route.ts`): the proxy was calling `/api/v1/models` (all of OpenRouter's public catalog) instead of `/api/v1/models/user` (only models the API key has been granted access to). Dropdowns were showing thousands of models the account cannot call. Fixed. DECISIONS.md `D4.openrouter-capability-fields` updated to reflect this.
- **Model dropdowns filtered by required capabilities**: each of the three role pickers now hides any model that doesn't meet every capability the role requires (interview/extraction: `tools + vision + files`; synthesis: `tools + reasoning`). Implemented via a new `requiredCaps` prop on `ModelPicker`.
- **Dropdown sorted by input price**: models now listed cheapest-first (`promptPer1M` ascending; undisclosed prices sorted to the end) instead of alphabetically.

Phase 5 admin dashboards (already on `main` from commit `e80d4d7`):

- `/admin/claims` — review queue with lateral join to primary evidence + employee name, status filter tabs, Approve/Reject server actions.
- `/admin/gaps` — Drizzle query joined with employees, priority + status badges, Resolve/Stale actions.
- `/admin/contradictions` — card layout with side-by-side claim summaries, Confirm/Dismiss actions.
- `/admin/brain` — sections joined to current version, scrollable markdown preview, review status badge. Read-only; re-synthesis is post-retrofit.

AI retrofit doc work (commits `88fdc22`, `a5ddd1f`, `c195dcf`):

- **New: `docs/oracle/07-knowledge-segmentation.md`** — three-layer taxonomy (top-level domains, sub-topics, orthogonal entity tags), cold-start strategy, maturity-based re-evaluation worker, concrete `RetrievalPlan` shape, full schema sketch.
- Inserted phases R3.5 (taxonomy schema), R5.5 (entity & metadata extraction in candidate pipeline), R10.5 (taxonomy admin + maturity-based worker).
- `01-model-roles-and-routes.md` — added Warmth Escalation route alongside Sonnet reasoning escalation; Flash-Lite Fast-Path Trap warning with the 15% validation-failure threshold.
- `02-provider-native-ai-architecture.md` — Retrieval execution order now requires Hybrid Search via RRF (pgvector + tsvector). New Vertex `useExplicitGeminiCache` profitability heuristic. Explicit caches now require a tracked reuse policy and cleanup lifecycle instead of unconditional immediate deletion.
- `03-candidate-before-claim-validation.md` — added PII/Sensitivity Gate as validation item 11; replaced promotion section with "Concurrency Locked" version (advisory lock or `SELECT ... FOR UPDATE` on hashed candidate; mid-transaction duplicate detection appends evidence rather than inserting a duplicate).
- `04-context-packs-observability.md` — added AI Cache Health traffic-light dashboard spec and the 7-Day Raw Payload Log requirement.
- `06-evaluation-framework.md` — expanded ~5× with metric formulas, fixture file schemas per category, validation-pipeline evals (PII gate, circuit breaker, concurrent promotion), knowledge-segmentation evals, cache effectiveness evals, per-route comparison protocol, failure-mode taxonomy, worked example.

## Existing code that likely needs refactor

High priority:

- `packages/ai/src/openrouter.ts` — mark legacy; replace production usage with `OracleAIClient`.
- `apps/workers/src/trigger/claim-extraction.ts` — currently writes too directly to permanent claims; refactor to candidates first.
- `apps/workers/src/trigger/document-ingestion.ts` — should use Vertex/Gemini direct for document-heavy extraction.
- `apps/workers/src/trigger/brain-synthesis.ts` — should use Anthropic direct and strict validation.
- `apps/web/app/api/chat/route.ts` — should call `OracleAIClient`, not OpenRouter directly.
- Admin model picker — should select curated `OracleModelRoute.routeId`, not arbitrary OpenRouter model IDs.

Medium priority:

- add `oracle_context_packs`, `model_run_usage_details`, `provider_cached_content`;
- add `extraction_batches`, `extraction_candidates`, `extraction_candidate_evidence`, `extraction_validation_results`;
- add AI cost/cache dashboards;
- update `.env.example` and `docs/configuration.md` with Big 3 provider variables.

---

## Do not do yet

Do not build these until the AI retrofit and validation pipeline are in place:

- proactive contradiction interjection;
- lull-based Oracle questions;
- live group-chat interjection;
- aggressive automatic claim approval;
- Brain synthesis from unreviewed or weakly validated claims.

---

## Security reminders

- This repo is public. Never commit secrets.
- Rotate any Vercel token or provider API key that appeared in transcripts.
- Keep `.env.local` untracked.
- Service-role Supabase access must remain server-side only.
- Employee-facing UI must never directly expose intelligence tables.

---

## Resume prompt for Claude Code

```text
I'm continuing work on The Oracle on a fresh machine. Read HANDOFF.md, AGENTS.md, CLAUDE.md, oracle_master_spec.md, DECISIONS.md, then docs/oracle/00-buildout-index.md. Do not bulk-read docs/oracle/* — read only the specific files the active task needs (per CLAUDE.md routing).

Phase 5 admin dashboards are landed. R0 documentation reset is done.

The next code phase is R1 — Model route configuration. Add packages/ai/src/routes/ with the OracleModelRoute type, seed the curated routes (cost-aware defaults + escalation routes including the Warmth Escalation), and update Admin Settings to select by routeId instead of raw OpenRouter model IDs. Then continue through R2, R3, R3.5, R4, R5, R5.5 in the order specified by docs/oracle/05-ai-retrofit-phase-packet.md.

Do not call any provider SDK outside the OracleAIClient. Do not write extracted claims directly to permanent claim tables. Do not run global vector search anywhere — every retrieval goes through a RetrievalPlan with metadata pre-filter, then hybrid pgvector + tsvector RRF.
```
