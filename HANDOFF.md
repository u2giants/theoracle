# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-25
**Repo:** https://github.com/u2giants/theoracle
**Current state:** AI retrofit code complete (R0–R10.5). **The next step is a wet-test, not more code.** R11 (interjection engine) is gated on running the candidate-before-claim pipeline against real data first.

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
| R2 — OracleAIClient + adapters | ✅ done | `3c51c9b` | `packages/ai/src/{client,context,routing,providers,usage,validation}/` + 16-assertion smoke |
| R3 — Observability schema | ✅ done | `1e345d3` | `oracle_context_packs`, `model_run_usage_details`, `provider_cached_content` + view |
| R3.5 — Knowledge taxonomy schema | ✅ done | `c529594` | 15 taxonomy tables + 12 top-domains seeded + 56 entities seeded + backfill |
| R4 — Candidate staging schema | ✅ done | `fe60304` | 4 staging tables + 13 CHECK constraints |
| R5 — Quote validator + promotion decision | ✅ done | `70339c6` | Pure validator + decider + 33-assertion smoke |
| R5.5 — Entity resolver + taxonomy validator | ✅ done | `8cad256` | Entity resolver + taxonomy validator + extended decision shape + 45-assertion smoke |
| R6 — Claim extraction worker refactor | ✅ done | `b46131d` | Worker through staging pipeline + circuit breaker + promotion executor + 30-assertion smoke |
| R7 — Document ingestion + cache infra | ✅ done | `a8a8586` | Worker through staging + `claims.candidate_hash` + cache profitability/lifecycle + 19-assertion smoke + race-safe executor |
| R8 — Chat route through OracleAIClient | ✅ done | `8a38fbd` | `apps/web/app/api/chat/route.ts` through `OracleAIClient.runText` with `providerOptions` escape hatch |
| R9 — Synthesis worker refactor | ✅ done | `8343c2d` | `brain-synthesis.ts` through `OracleAIClient` + `validateSynthesisDiff` (claim ID + unsupported-named-entity check) + rejected-version preservation + 21-assertion smoke |
| R10 — Admin observability dashboards | ✅ done | `ea33d66` | 6 read-only pages under `/admin/ai`: dashboard, runs list, run detail (context pack viewer), cache, candidates, evals placeholder |
| R10.5 — Taxonomy admin + re-eval worker | ✅ done | `533f39b` | 5 pages under `/admin/taxonomy` + 4 transactional approve/reject server actions + scheduled `taxonomy-reevaluation` worker scaffold |
| **R11 — Resume interjection engine** | ⬜ **gated on wet-test** | — | Architectural prerequisites met; needs real claim data before tuning interjection thresholds |

---

## Architectural rules in force

These are load-bearing — undoing any of them silently breaks correctness or observability.

1. **No direct provider SDK calls outside `packages/ai/src/providers/`.** Every production model call goes through `OracleAIClient`. R6/R7/R8/R9 all comply. The `getOpenRouter()` import is now only used internally by `OpenRouterBridgeAdapter`.
2. **No extracted claim writes to permanent tables.** Stage → validate → promote, always. `executePromotion` in `packages/oracle-engines/src/extraction/promotion-executor.ts` is the only path that can insert into `claims` / `claim_top_domains` / `claim_entities` / `claim_evidence` / `claim_metadata`.
3. **No global vector search.** Every retrieval that lands must go through a `RetrievalPlan` with metadata pre-filter, then hybrid pgvector + tsvector RRF.
4. **`licensor` is NOT `vendor`.** Structural enforcement via CHECK constraint + entity resolver `type_mismatch` detection.
5. **Sensitive material never reaches `claims`.** Quarantined at the candidate stage. The `/admin/ai/candidates` page deliberately hides sensitive rows from the standard queue; they appear ONLY in the explicit "Sensitive" filter tab.
6. **Vertex explicit caches require a tracked reuse policy.** `recordCacheCreation` / `recordCacheTermination` is the only correct path. CHECK constraint enforces `deleted_at IS NULL iff status='active'`.
7. **Stable prompt prefix MUST precede dynamic content.** `ContextCompiler` throws if a stable block appears after a dynamic block.
8. **Advisory-locked, race-safe promotion.** `executePromotion` acquires `pg_try_advisory_xact_lock(hashtextextended(candidateHash, 0))` and looks up existing claims by hash INSIDE the transaction. Partial UNIQUE index on `claims.candidate_hash` is the belt-and-suspenders pair.
9. **Synthesis output is rejected when unsupported named entities appear.** Every capitalized proper-noun-shaped name in `updatedMarkdown` must be backed by an approved claim summary OR the canonical entity registry. Rejected versions are inserted with `reviewStatus='rejected'` and `currentVersionId` is left unchanged.
10. **Taxonomy changes are admin-gated.** The re-evaluation worker writes only to `taxonomy_proposals`. No auto-mutation. Approval flows through `/admin/taxonomy/proposals` and `/admin/taxonomy/entity-proposals` server actions.

---

## What runs through `OracleAIClient` today (R6–R9 complete)

```
apps/workers/src/trigger/claim-extraction.ts      ✅  R6 via OpenRouterBridgeAdapter
apps/workers/src/trigger/document-ingestion.ts    ✅  R7 via OpenRouterBridgeAdapter
apps/web/app/api/chat/route.ts                    ✅  R8 via OpenRouterBridgeAdapter
apps/workers/src/trigger/brain-synthesis.ts       ✅  R9 via OpenRouterBridgeAdapter
apps/workers/src/trigger/contradiction-watcher.ts ⬜  Phase 6 / R11 territory
apps/workers/src/trigger/taxonomy-reevaluation.ts ⬜  scaffold only; clustering body deferred
```

The `OpenRouterBridgeAdapter` wears whichever provider hat (anthropic / vertex / openai) the curated route requires; under the hood it still uses OpenRouter + Vercel AI SDK. Real provider-native SDKs (`@anthropic-ai/sdk`, `@google/genai`, `openai`) are NOT yet wired — they get swapped in per-adapter when there's a wet-test path for them.

---

## Smoke gates available

Every phase that ships runtime logic has a self-contained smoke test that runs without API keys, database, or network access.

```bash
pnpm --filter @oracle/ai      verify:r2     # 16/16 — pipeline + bridge wiring
pnpm --filter @oracle/engines verify:r5     # 33/33 — quote validator + decider
pnpm --filter @oracle/engines verify:r5.5   # 45/45 — entity resolver + taxonomy validator
pnpm --filter @oracle/engines verify:r6     # 30/30 — circuit breaker + domain mapping
pnpm --filter @oracle/engines verify:r7     # 19/19 — cache profitability + estimate
pnpm --filter @oracle/engines verify:r9     # 21/21 — synthesis diff validator
```

**164 deterministic assertions** across the AI retrofit pure-function modules.

Pre-push gate:

```bash
pnpm typecheck                              # 7/7 packages
pnpm --filter @oracle/web build             # production Next build
pnpm --filter @oracle/ai      verify:r2
pnpm --filter @oracle/engines verify:r5
pnpm --filter @oracle/engines verify:r5.5
pnpm --filter @oracle/engines verify:r6
pnpm --filter @oracle/engines verify:r7
pnpm --filter @oracle/engines verify:r9
```

Total runs in ~30 seconds because the pure smokes complete in milliseconds.

---

## Admin observability surface (R10 + R10.5)

| Route | What it shows | Reads from |
|---|---|---|
| `/admin/ai` | Top-level dashboard: 12 metric cards (runs 24h/7d, success rate, cache hit ratio, fallback rate, token averages, latency, active caches, candidate counts), route usage breakdown, recent runs | `model_runs_with_usage` view + R4 staging + `provider_cached_content` |
| `/admin/ai/runs` | Paginated runs list with 4 filters (all / success / failed / fallback) + task-type chip filter | `model_runs_with_usage` |
| `/admin/ai/runs/[id]` | One-run detail: run summary, usage breakdown, full prompt plan (block-by-block), retrieval diagnostics (selected domains / source types / process stages / entity IDs + included record counts), linked extraction batches, linked provider caches | `model_runs_with_usage` + `oracle_context_packs` + `extraction_batches` + `provider_cached_content` |
| `/admin/ai/cache` | Cache rows filterable by status + provider hit-ratio table | `provider_cached_content` + `model_runs_with_usage` |
| `/admin/ai/candidates` | Extraction candidates with 8 filter tabs. **Sensitive candidates are hidden by default** and only appear under the explicit "Sensitive" tab. | `extraction_candidates` + `extraction_validation_results` |
| `/admin/ai/evals` | Placeholder per R10 task 6. Lists the CLI smoke gates with assertion counts. | — |
| `/admin/taxonomy` | Top-level domains list with full boundary rules + usage counts | `knowledge_top_domains` + all `*_top_domains` join tables |
| `/admin/taxonomy/proposals` | Taxonomy proposals review queue with approve/reject controls | `taxonomy_proposals` |
| `/admin/taxonomy/entities` | Entity registry grouped by type (licensor distinct from vendor) | `entities` + `claim_entities` |
| `/admin/taxonomy/entity-proposals` | Unknown-entity review queue. Approval refines canonical + auto-merges on conflict | `entity_proposals` |
| `/admin/taxonomy/change-log` | Append-only audit (latest 200 events) | `taxonomy_change_log` |

---

## DB migrations — current state

5 Drizzle migrations + 9 hand-written SQL files exist in `packages/db/migrations/` but have **NOT been applied to the live Supabase DB yet**:

| Drizzle migration | Phase | What it ships |
|---|---|---|
| `0000_smart_jackpot.sql` | (initial) | Already applied historically |
| `0001_hot_johnny_blaze.sql` | R3 | Observability tables + Drizzle meta catch-up |
| `0002_demonic_kid_colt.sql` | R3.5 | 15 taxonomy tables |
| `0003_magenta_lionheart.sql` | R4 | 4 candidate staging tables |
| `0004_simple_tomas.sql` | R5.5 | `extraction_candidate_evidence.documentClass` + `processStage` |
| `0005_kind_nekra.sql` | R7 | `claims.candidate_hash` column + index |

Hand-written SQL in `packages/db/migrations/sql/` (idempotent, run after Drizzle):

| File | Phase |
|---|---|
| `11_observability_constraints.sql` | R3 |
| `12_taxonomy_constraints.sql` | R3.5 |
| `13_extraction_constraints.sql` | R4 |
| `14_claims_candidate_hash_unique.sql` | R7 |
| `16_knowledge_top_domains_seed.sql` | R3.5 |
| `17_entities_seed.sql` | R3.5 |
| `31_observability_views.sql` | R3 |
| `42_claim_top_domains_backfill.sql` | R3.5 |
| `48_taxonomy_vector_indexes.sql` | R3.5 |

When `pnpm db:migrate` is run next, all of these apply in order. **No existing data is touched.** Legacy `claim_domains` + `claims.knowledge_domain` are preserved during transition.

---

## R11 — what's blocking and what's already done

R11 is the proactive interjection engine (the original Phase 6 work paused at the start of the retrofit). The retrofit packet's acceptance gate for R11 (`05-ai-retrofit-phase-packet.md` line 488):

| Prerequisite | Status |
|---|---|
| Candidate pipeline live | ✅ R4–R7 done; needs migration applied |
| At least one test transcript processed | ⬜ requires wet test |
| Claims reviewed and approved | ⬜ requires wet test |
| Contradiction watcher tested on validated claims | ⬜ requires wet test |
| Admin can audit every AI call that contributed to the contradiction or gap | ✅ R10 done |

**Two of four are gated on real data flowing.** Writing R11 code today without that data means guessing at interjection thresholds with no ground truth to tune against. The architectural prerequisites are met; the empirical ones aren't.

**Recommended next step:**
1. Apply migrations (`pnpm db:migrate` against the live Supabase DB).
2. Wet-test the R6 worker on real messages.
3. Wet-test the R7 worker on a real document upload.
4. Review the resulting claims via `/admin/claims`.
5. Re-run synthesis (R9) and review the rejected versions if any.
6. THEN attempt R11 with informed defaults.

---

## What's deliberately deferred

- **Real `@anthropic-ai/sdk` / `@google/genai` / `openai` SDK wiring.** The `OpenRouterBridgeAdapter` satisfies the architectural rule today. Real per-provider SDKs land when cloud credentials + a wet-test path are arranged.
- **R5.5 entity-extraction prompt rewrite.** R5.5 ships the validator + resolver; the workers call them with empty entity lists. Updating `EXTRACTION_SYSTEM_PROMPT` to emit entities is its own prompt-engineering pass with its own evals.
- **`RetrievalPlan` + hybrid pgvector/tsvector RRF in the chat route.** R8's chat route uses the legacy `searchApprovedClaims` helper. The `RetrievalPlan` infrastructure is documented in `docs/oracle/02-provider-native-ai-architecture.md` but not yet a runtime concern.
- **Real Vertex explicit cache creation.** R7 ships the profitability heuristic + `provider_cached_content` bookkeeping; cache resources themselves aren't created until `@google/genai` is wired.
- **R10.5 clustering / drift detection body.** The re-evaluation worker scaffold exists; the actual density clustering + cluster naming + drift detection pipeline waits for real claim density (the worker currently counts claims per domain and reports "not enough data yet").
- **R10.5 reclassification job for merge/split/reassign proposals.** `create_top_domain` proposals apply transactionally on approval. Merge/split/reassign approvals are audited but the actual reclassification mutation is queued — the dedicated job lands when those proposal types start arriving.
- **R10.5 batch-approve UX.** Individual approve/reject work today.

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

The AI retrofit code is complete: R0–R10.5 are done. R11 is the
remaining phase but is gated on a wet-test (apply migrations, run the
extraction worker on real messages, review the resulting claims). Until
that happens, R11 implementation is guessing at thresholds.

If the next task is the wet-test path:
  1. Apply migrations: pnpm db:migrate (5 Drizzle + 9 hand-written SQL
     files; all idempotent; no existing data touched).
  2. Trigger a real extraction run (cron auto-fires, or trigger manually).
  3. Review via /admin/ai/runs, /admin/ai/candidates, /admin/claims.

If the next task is filling in deferred work:
  - Real provider SDK adapter (R9+ in @anthropic-ai/sdk or @google/genai).
  - R5.5 entity-extraction prompt rewrite.
  - RetrievalPlan + hybrid pgvector/tsvector RRF in the chat route.
  - R10.5 clustering / drift detection body in the re-evaluation worker.
  - R10.5 reclassification job for merge/split/reassign proposals.

Hard rules in force: no direct provider SDK calls outside OracleAIClient;
no extracted claim writes to permanent tables (stage → validate → promote);
licensor is a first-class entity type distinct from vendor; sensitive
material is quarantined at the candidate stage; stable prefix MUST
precede dynamic content in ContextCompiler; synthesis output is
rejected when unsupported named entities appear; taxonomy changes are
admin-gated.

Run all smoke gates before pushing: pnpm typecheck && pnpm --filter
@oracle/web build && pnpm --filter @oracle/ai verify:r2 && pnpm --filter
@oracle/engines verify:r5 && pnpm --filter @oracle/engines verify:r5.5 &&
pnpm --filter @oracle/engines verify:r6 && pnpm --filter @oracle/engines
verify:r7 && pnpm --filter @oracle/engines verify:r9.
```
