# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-25
**Repo:** https://github.com/u2giants/theoracle
**Current priority:** AI architecture retrofit. **R9 — Synthesis worker refactor is the next code phase.**
**Continuing on a different machine:** clone fresh, `pnpm install`, pull `.env.local` (see `AGENTS.md` §12), then read the files below in order.

---

## Read this in order

1. `HANDOFF.md` — this file.
2. `AGENTS.md` — developer guide and repo conventions.
3. `CLAUDE.md` — Claude Code-specific instructions.
4. `oracle_master_spec.md` — product/business contract.
5. `DECISIONS.md` — assumptions and historical decisions.
6. `docs/oracle/00-buildout-index.md` — index for the AI retrofit docs (lists 01–07).
7. The specific `docs/oracle/0N-*.md` files required for the active task (do not bulk-read).

---

## AI retrofit phase status

| Phase | Status | Commit | What landed |
|---|---|---|---|
| R0 — Doc reset | ✅ done | (prior sessions) | `docs/oracle/00–07` |
| R1 — Curated route catalog | ✅ done | `91e44ea` | `packages/ai/src/routes/` — strict 1 Primary + 1 Fallback per role |
| R2 — OracleAIClient + adapters | ✅ done | `3c51c9b` | `packages/ai/src/{client,context,routing,providers,usage,validation}/` + 16-assertion smoke gate |
| R3 — Observability schema | ✅ done | `1e345d3` | `oracle_context_packs`, `model_run_usage_details`, `provider_cached_content` + view |
| R3.5 — Knowledge taxonomy schema | ✅ done | `c529594` | 15 taxonomy tables + 12 top-domains seeded + 56 entities seeded + backfill |
| R4 — Candidate staging schema | ✅ done | `fe60304` | 4 staging tables + 13 CHECK constraints |
| R5 — Quote validator + promotion decision | ✅ done | `70339c6` | `packages/oracle-engines/src/extraction/` — pure validator + decider + 33-assertion smoke |
| R5.5 — Entity resolver + taxonomy validator | ✅ done | `8cad256` | Entity resolver + taxonomy validator + extended decision shape + 45-assertion smoke |
| R6 — Claim extraction worker refactor | ✅ done | `b46131d` | Worker through staging pipeline + circuit breaker + promotion executor + 30-assertion smoke |
| R7 — Document ingestion + cache infra | ✅ done | `a8a8586` | Worker through staging + `claims.candidate_hash` + cache profitability/lifecycle + 19-assertion smoke + race-safe executor |
| R8 — Chat route through OracleAIClient | ✅ done | `8a38fbd` | `apps/web/app/api/chat/route.ts` through `OracleAIClient.runText` with `providerOptions` escape hatch for tools/multi-turn |
| **R9 — Synthesis worker refactor** | **⬜ next code phase** | — | Refactor `apps/workers/src/trigger/brain-synthesis.ts` through `OracleAIClient`; strict "every material paragraph maps to approved claim IDs" validator |
| R10 — Admin observability dashboards | ⬜ | — | Cost / cache traffic-light UX / candidate review reading from `model_runs_with_usage` view |
| R10.5 — Taxonomy admin + re-eval worker | ⬜ | — | Compact `taxonomy_proposals` / `entity_proposals` review UI |
| R11 — Resume interjection engine | ⬜ | — | Only after R9–R10.5 lands |

---

## Architectural rules in force

These are load-bearing — undoing any of them silently breaks correctness or observability.

1. **No direct provider SDK calls outside `packages/ai/src/providers/`.** Every model call goes through `OracleAIClient` (or its adapters). R6/R7/R8 all comply; R9's `brain-synthesis.ts` is the last legacy `getOpenRouter()` caller.
2. **No extracted claim writes to permanent tables.** Stage → validate → promote, always. The promotion executor in `packages/oracle-engines/src/extraction/promotion-executor.ts` is the only path that can insert into `claims` / `claim_top_domains` / `claim_entities` / `claim_evidence` / `claim_metadata`. Workers R6 and R7 already comply; R9 will when synthesis is refactored.
3. **No global vector search.** Every retrieval that does land must go through a `RetrievalPlan` with metadata pre-filter, then hybrid pgvector + tsvector RRF. (R8's chat route still uses the legacy `searchApprovedClaims` helper; full `RetrievalPlan` wiring is a follow-up.)
4. **`licensor` is NOT `vendor`.** Disney/Marvel/Star Wars/NBCUniversal/Warner Bros are seeded as `entity_type='licensor'`. The CHECK constraint on `entities.entity_type` + the entity resolver's type-mismatch detection structurally enforce the split.
5. **Sensitive material (HR / personal conflict / disciplinary) never reaches `claims`.** Quarantined at the candidate stage; CHECK constraint requires `rejected_sensitive` / `quarantined_sensitive` candidates to set at least one sensitivity flag.
6. **Vertex explicit caches require a tracked reuse policy and cleanup lifecycle.** `recordCacheCreation` / `recordCacheTermination` in `packages/oracle-engines/src/extraction/cache-lifecycle.ts` is the only correct path; `provider_cached_content.status` CHECK enforces `deleted_at IS NULL iff status='active'`.
7. **Stable prompt prefix MUST precede dynamic content.** `ContextCompiler.compile()` throws if a `stable_*` block appears after a `dynamic_input` block — busts prefix caching permanently otherwise.
8. **Advisory-locked, race-safe promotion.** `executePromotion` (R7) acquires `pg_try_advisory_xact_lock(hashtextextended(candidateHash, 0))` and looks up `claims WHERE candidate_hash = $hash` inside the transaction. The partial UNIQUE index on `claims.candidate_hash` enforces "no two distinct claims share the same canonicalized hash."

---

## What runs through `OracleAIClient` today (R6–R8)

```
apps/workers/src/trigger/claim-extraction.ts     ✅  via OpenRouterBridgeAdapter (R6)
apps/workers/src/trigger/document-ingestion.ts   ✅  via OpenRouterBridgeAdapter (R7)
apps/web/app/api/chat/route.ts                   ✅  via OpenRouterBridgeAdapter (R8)
apps/workers/src/trigger/brain-synthesis.ts      ⬜  still calls getOpenRouter() — R9
apps/workers/src/trigger/contradiction-watcher.ts ⬜  not yet refactored (Phase 6 / R11 territory)
```

The `OpenRouterBridgeAdapter` wears whichever provider hat (anthropic / vertex / openai) the curated route requires; under the hood it still uses OpenRouter + Vercel AI SDK. Real provider-native SDKs (`@anthropic-ai/sdk`, `@google/genai`, `openai`) are NOT yet wired — they land per-adapter in R9+ as each worker needs them.

---

## Smoke gates available

Every phase that ships runtime logic has a self-contained smoke test that runs without API keys, database, or network access.

```bash
pnpm --filter @oracle/ai      verify:r2     # 16/16 — pipeline + bridge wiring
pnpm --filter @oracle/engines verify:r5     # 33/33 — quote validator + decider
pnpm --filter @oracle/engines verify:r5.5   # 45/45 — entity resolver + taxonomy validator
pnpm --filter @oracle/engines verify:r6     # 30/30 — circuit breaker + domain mapping
pnpm --filter @oracle/engines verify:r7     # 19/19 — cache profitability + estimate
```

Standard pre-push gate:

```bash
pnpm typecheck                              # 7/7 packages
pnpm --filter @oracle/web build             # production Next build
pnpm --filter @oracle/ai      verify:r2
pnpm --filter @oracle/engines verify:r5
pnpm --filter @oracle/engines verify:r5.5
pnpm --filter @oracle/engines verify:r6
pnpm --filter @oracle/engines verify:r7
```

R6's worker logic isn't covered by a smoke test that exercises the full Drizzle pipeline (that requires a live Postgres). R5/R5.5/R6/R7 pure pieces have 127 assertions between them.

---

## DB migrations — current state

The following migrations exist in `packages/db/migrations/` but have **NOT been applied to the live Supabase DB yet** (only the SQL files are in the repo):

| Drizzle migration | Phase | What it ships |
|---|---|---|
| `0000_smart_jackpot.sql` | (initial) | Initial Phase 1 schema — already applied historically |
| `0001_hot_johnny_blaze.sql` | R3 | Observability tables + Drizzle meta catch-up for `employee_identities` |
| `0002_demonic_kid_colt.sql` | R3.5 | 15 taxonomy tables |
| `0003_magenta_lionheart.sql` | R4 | 4 candidate staging tables |
| `0004_simple_tomas.sql` | R5.5 | `extraction_candidate_evidence.documentClass` + `processStage` columns |
| `0005_kind_nekra.sql` | R7 | `claims.candidate_hash` column + index |

Hand-written SQL files in `packages/db/migrations/sql/` (run AFTER the Drizzle migrations on every `pnpm db:migrate`, all idempotent):

| File | Phase |
|---|---|
| `11_observability_constraints.sql` | R3 — value-whitelists + `updated_at` trigger on `provider_cached_content` |
| `12_taxonomy_constraints.sql` | R3.5 — `licensor`/`vendor` whitelist, taxonomy proposal/status whitelists, consistency rules |
| `13_extraction_constraints.sql` | R4 — 13 CHECK constraints on the staging tables |
| `14_claims_candidate_hash_unique.sql` | R7 — partial UNIQUE on `claims.candidate_hash WHERE candidate_hash IS NOT NULL` |
| `16_knowledge_top_domains_seed.sql` | R3.5 — 12 domains with boundary rules |
| `17_entities_seed.sql` | R3.5 — 56 entities (customers, licensors, systems, departments, geographies, process stages, document classes) |
| `31_observability_views.sql` | R3 — `model_runs_with_usage` view |
| `42_claim_top_domains_backfill.sql` | R3.5 — idempotent backfill from legacy `claim_domains` |
| `48_taxonomy_vector_indexes.sql` | R3.5 — HNSW on `knowledge_sub_topics.centroid` |

When `pnpm db:migrate` is run next, it will apply `0001`–`0005` in order then (re)apply every hand-written file. **No existing data is touched.** The legacy `claim_domains` table and `claims.knowledge_domain` enum column are intentionally preserved during transition; both will be dropped only after R9+ wiring is fully in place.

---

## What's deliberately deferred

- **Real `@anthropic-ai/sdk` / `@google/genai` / `openai` SDK wiring.** The `OpenRouterBridgeAdapter` satisfies the architectural rule ("everything through OracleAIClient"); real per-provider SDKs land when cloud credentials + a wet-test path are arranged. R9 may wire Anthropic direct first since synthesis is the cost-sensitive path.
- **R5.5 entity-extraction prompt rewrite.** R5.5 ships the validator + resolver; the worker calls them with empty entity lists today. Updating `EXTRACTION_SYSTEM_PROMPT` to emit entities is its own prompt-engineering pass with its own evals.
- **`RetrievalPlan` + hybrid pgvector/tsvector RRF in the chat route.** R8's chat route uses the legacy `searchApprovedClaims` helper. The `RetrievalPlan` infrastructure is documented in `docs/oracle/02-provider-native-ai-architecture.md` but is not yet a runtime concern.
- **Real Vertex explicit cache creation.** R7 ships the profitability heuristic + `provider_cached_content` bookkeeping; cache resources themselves aren't created until `@google/genai` is wired.

---

## Next: R9 — Synthesis worker refactor

Per `docs/oracle/05-ai-retrofit-phase-packet.md` Phase R9:

**Tasks:**

1. Route through `OracleAIClient` via the same `OpenRouterBridgeAdapter` pattern as R6/R7/R8 (or wire `@anthropic-ai/sdk` if the cost case justifies it now).
2. Use the curated `default_synthesis_route` setting (R1 key), with fallback to `anthropic_claude_3_5_sonnet_synthesis_primary`.
3. Frontier models (Sonnet/Opus, Gemini Pro) remain escalation/manual-only routes.
4. Compile stable synthesis prompt + output schema BEFORE dynamic claim list (the prefix-cache rule R6/R7/R8 already follow).
5. Generate structured synthesis diff matching the spec Part 9.8 shape.
6. Validate every material paragraph maps to approved claim IDs — the synthesis equivalent of R5's quote validator.
7. Reject unsupported named people / systems / customers / process stages / departments.
8. On validation failure: do NOT update `brain_sections.currentVersionId`; store failed output for review.

**Acceptance gate** (per the retrofit packet):

- Synthesis no longer writes Brain versions without backend validation.
- Every model call has a `model_runs` + `model_run_usage_details` + `oracle_context_packs` row.
- Failed synthesis output is preserved + inspectable.
- `pnpm typecheck` + `pnpm --filter @oracle/web build` + all prior smoke gates still pass.

---

## Security reminders

- This repo is public. Never commit secrets.
- Rotate any Vercel / Supabase / provider API key that appeared in a transcript.
- Keep `.env.local` untracked.
- Service-role Supabase access must remain server-side only.
- Employee-facing UI must never directly expose intelligence tables.

---

## Resume prompt for Claude Code

```text
I'm continuing work on The Oracle on a fresh machine. Read HANDOFF.md,
AGENTS.md, CLAUDE.md, oracle_master_spec.md, DECISIONS.md, then
docs/oracle/00-buildout-index.md. Do not bulk-read docs/oracle/* — read
only the specific files the active task needs (per CLAUDE.md routing).

R0–R8 of the AI retrofit are done. The next code phase is R9 — Synthesis
worker refactor. Refactor apps/workers/src/trigger/brain-synthesis.ts
through OracleAIClient using the OpenRouterBridgeAdapter pattern (same
as R6/R7/R8 workers). Add the "every material paragraph maps to approved
claim IDs" validator per docs/oracle/05-ai-retrofit-phase-packet.md
Phase R9. Reject unsupported named entities. On validation failure,
preserve the failed output and do NOT update brain_sections.currentVersionId.

Hard rules in force: no direct provider SDK calls outside OracleAIClient;
no extracted claim writes to permanent tables (stage → validate → promote);
licensor is a first-class entity type distinct from vendor; sensitive
material is quarantined at the candidate stage; stable prefix MUST
precede dynamic content in ContextCompiler.

Run all smoke gates after R9 lands: pnpm typecheck && pnpm --filter
@oracle/web build && pnpm --filter @oracle/ai verify:r2 && pnpm --filter
@oracle/engines verify:r5 && pnpm --filter @oracle/engines verify:r5.5
&& pnpm --filter @oracle/engines verify:r6 && pnpm --filter @oracle/engines
verify:r7.
```
