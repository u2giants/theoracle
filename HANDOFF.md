# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-25
**Repo:** https://github.com/u2giants/theoracle
**Current priority:** AI architecture retrofit. **R5 — Exact quote validator and promotion service is the next phase.**
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

## Current priority

The AI architecture retrofit is well underway. **Do NOT build proactive interjection yet** — that's R11, after the validation pipeline is wired.

The remaining sequence is in `docs/oracle/05-ai-retrofit-phase-packet.md`.

---

## AI retrofit phase status

| Phase | Status | Landed in commit | What it ships |
|---|---|---|---|
| R0 — Doc reset | ✅ done | (prior sessions) | `docs/oracle/00–07` |
| R1 — Curated route catalog | ✅ done | `91e44ea` | `packages/ai/src/routes/` with strict 1 Primary + 1 Fallback per role |
| R2 — OracleAIClient + Adapters | ✅ done | `3c51c9b` | `packages/ai/src/{client,context,routing,providers,usage,validation}/` + 16-assertion smoke gate |
| R3 — Observability schema | ✅ done | `1e345d3` | `oracle_context_packs`, `model_run_usage_details`, `provider_cached_content` + CHECK constraints + `model_runs_with_usage` view |
| R3.5 — Knowledge taxonomy schema | ✅ done | `c529594` | 15 taxonomy tables (top-domains with boundary rules, sub-topics, entities, proposals, change log) + seeds + backfill |
| R4 — Candidate staging schema | ✅ done | `fe60304` | `extraction_batches`, `extraction_candidates`, `extraction_candidate_evidence`, `extraction_validation_results` + 13 CHECK constraints |
| **R5 — Quote validator + promotion service** | **⬜ next code phase** | — | `packages/oracle-engines/src/extraction/{quote-validator,promote-candidate}.ts` + isolated tests for the 6 cases in R5 |
| R5.5 — Entity/metadata extraction | ⬜ | — | Extend candidate schema + validator to atomically promote claim + tags |
| R6 — Refactor claim extraction worker | ⬜ | — | Stage candidates, validate, promote; hook circuit breaker |
| R7 — Refactor document ingestion worker | ⬜ | — | Vertex/Gemini direct + explicit context caching with profitability heuristic and tracked lifecycle |
| R8 — Refactor chat route | ⬜ | — | Route through `OracleAIClient`; use `RetrievalPlan` + hybrid pgvector + tsvector RRF |
| R9 — Refactor synthesis worker | ⬜ | — | Vertex/Anthropic direct + strict synthesis validation |
| R10 — Admin observability dashboards | ⬜ | — | AI runs, context packs, cache traffic-light UX, candidate review, 7-day payload log |
| R10.5 — Taxonomy admin + re-eval worker | ⬜ | — | Compact `taxonomy_proposals` / `entity_proposals` review UI; maturity-based clustering |
| R11 — Resume interjection engine | ⬜ | — | Only after the validation/segmentation pipeline is live |

---

## What landed in the R1–R4 push (2026-05-25)

### R1 — Curated Oracle model route catalog (`packages/ai/src/routes/`)

Strict rule per `docs/oracle/01-model-roles-and-routes.md`: each of the 3 production roles has exactly 1 Primary + 1 Fallback. No "balanced alternates" or competing defaults.

**Default routes:**

```ts
interview:  'anthropic_claude_haiku_4_5_interview_primary'
extraction: 'vertex_gemini_2_5_flash_extraction_primary'
synthesis:  'anthropic_claude_3_5_sonnet_synthesis_primary'
```

**Fallbacks:** OpenAI GPT-4o for interview, OpenAI GPT-4o-mini for extraction schema repair, Vertex Gemini Flash for synthesis Markdown-diff failures.

**Internal escalation subroutes** (not exposed as admin-selectable defaults): Flash-Lite triage, Haiku warmth escalation, GPT-4o-mini schema repair.

### R2 — OracleAIClient pipeline (`packages/ai/src/`)

The new production gateway for every model call. After R2 is in place, **no route handler or worker may call a provider SDK directly.** Production code goes through:

```
OracleAIClient
  → ContextCompiler   (assemble OraclePromptPlan; enforce stable-before-dynamic)
  → ModelRouter       (resolve routeId → adapter; dispatch with fallback)
  → ProviderAdapter   (Anthropic | Vertex | OpenAI | Mock)
```

Layout:

```
packages/ai/src/
├── routes/                    R1
├── client/types.ts            OraclePromptPlan, OracleUsage, PromptBlock, OracleTaskType
├── client/oracle-ai-client.ts Main entry point; test mode auto-wires mock adapters
├── context/prompt-blocks.ts   sha256 hashing, token estimate, KIND_ORDER
├── context/context-compiler.ts ContextCompiler; throws if dynamic precedes stable
├── routing/model-router.ts    Adapter dispatch; falls back on 429/timeout/NotImplemented
├── providers/types.ts         OracleProviderAdapter interface + NotImplemented sentinel
├── providers/mock-adapter.ts  Canned-output adapter for tests
├── providers/anthropic-adapter.ts   Stub — throws NotImplemented until R3+ wires SDK
├── providers/vertex-gemini-adapter.ts  Stub
├── providers/openai-adapter.ts Stub
├── usage/usage-normalizer.ts  Provider-specific usage → OracleUsage
├── validation/structured-output-validator.ts  Zod check, discriminated result
├── validation/evidence-validator.ts           Verbatim .includes + offsets; ambiguity guard
└── __verify__/oracle-ai-client-smoke.ts  16-assertion R2 acceptance gate
```

Run the gate any time:

```bash
pnpm --filter @oracle/ai verify:r2
```

The 3 real production adapters are stubs that throw `ProviderAdapterNotImplementedError`. The `ModelRouter` recognizes this as fallback-eligible, so cross-provider fallback works today even though the providers themselves aren't wired. **R3+ replaces the stubs with real SDK calls.**

### R3 — Observability schema

Three new Drizzle-managed tables for AI cost/cache/fallback dashboards:

- `oracle_context_packs` — full `OraclePromptPlan` per call (block list, hashes, retrieval plan, included record IDs). `model_run_id` is nullable so the pack can be created before the run.
- `model_run_usage_details` — 1:1 child of `model_runs`; `cached_input_tokens`, `cache_write_tokens`, `reasoning_tokens`, `provider_request_id`, `raw_usage_json`, `fell_back_from_route_id`, `fallback_reason`.
- `provider_cached_content` — explicit Vertex cache tracking with `expected_reuse_count`, `latest_planned_reuse_step`, `hard_expiration_at`, `cleanup_owner`, `status` ∈ `(active, deleted, expired, failed, orphaned)`. A CHECK constraint enforces `status='active' iff deleted_at IS NULL`.

Plus `migrations/sql/11_observability_constraints.sql` (CHECK constraints + `updated_at` trigger) and `migrations/sql/31_observability_views.sql` (the `model_runs_with_usage` denormalized view with a derived `cache_hit_ratio`).

### R3.5 — Three-layer knowledge taxonomy

15 new tables installing the segmentation spec from `docs/oracle/07-knowledge-segmentation.md`:

- **Layer 1:** `knowledge_top_domains` (text PK; carries boundary rules: `belongs_here`, `does_not_belong_here`, `common_entity_hints`, `default_excluded_document_classes`, `neighboring_domain_ids`). Seeded with 12 domains via `migrations/sql/16_knowledge_top_domains_seed.sql`.
- **Layer 2:** `knowledge_sub_topics` (empty on install; HNSW index on `centroid`).
- **Layer 1/2 joins:** `claim_top_domains`, `document_top_domains`, `document_chunk_top_domains`, `message_top_domains`, `claim_sub_topics` — so retrieval can scope BEFORE claims exist.
- **Layer 3:** `entities` canonical registry. `licensor` is a first-class entity type **distinct from `vendor`** — Disney/Marvel/Star Wars/NBCUniversal/Warner Bros are licensors. Operating vendors are further split into `factory`, `freight_provider`, `testing_lab`, `packaging_supplier`, `service_provider`, with `vendor` as the residual bucket. Seeded with 56 entities via `migrations/sql/17_entities_seed.sql`.
- **Layer 3 joins:** `claim_entities`, `document_chunk_entities`, `message_entities`.
- **Metadata:** `claim_metadata` (process_stage, department, geography, document_class, **`effective_from` + `effective_until`** — two columns rather than `tstzrange` for Drizzle queryability; half-open `[from, until)` semantics, `until IS NULL` means "currently in effect").
- **Governance:** `taxonomy_proposals` (queue; auto-mutation prohibited), `taxonomy_change_log` (audit), `entity_proposals` (unknown entities).

Plus `migrations/sql/12_taxonomy_constraints.sql` (status whitelists + reviewed-consistency + merge-consistency CHECKs), `42_claim_top_domains_backfill.sql` (idempotent backfill from the legacy `claim_domains` enum with an explicit mapping table inline), and `48_taxonomy_vector_indexes.sql` (HNSW on `knowledge_sub_topics.centroid`; always-on because the table is empty on install).

### R4 — Candidate-before-claim staging schema

4 staging tables installing the pipeline spec from `docs/oracle/03-candidate-before-claim-validation.md`:

- `extraction_batches` — one row per extraction job segment. Includes the circuit-breaker fields: `validation_attempt_count`, `consecutive_quote_failure_count`, `model_run_ids_attempted` (JSONB array), `route_ids_attempted`.
- `extraction_candidates` — one row per proposed claim, with full sensitivity/PII flag set (`contains_sensitive_personal_data`, `contains_sensitive_hr_data`, `is_personal_conflict`, `sensitivity_reason`), proposed entities for R5.5, and dedup pointers.
- `extraction_candidate_evidence` — stores both model-provided AND validator-confirmed quote/offsets.
- `extraction_validation_results` — one row per deterministic check executed.

Plus `migrations/sql/13_extraction_constraints.sql` — 13 CHECK constraints including:
- `promoted_consistency`: `status='promoted'` iff `promoted_at + promoted_to_claim_id` both set
- `sensitive_consistency`: `rejected_sensitive`/`quarantined_sensitive` requires at least one sensitivity flag TRUE — catches workers trying to quarantine without saying why
- `validated_fields_required_on_pass`: passing validation requires the validator to populate the validated quote, offsets, and timestamp — no silent passes
- `source_type/pointer consistency` mirroring the spec 6.8 rule from `claim_evidence`

### Other work landed in this push

- **Docs gap fixes** (commit `b9caa7f`): 5 contradictions in the older docs cleaned up: `openrouter/retrieval` reference in `AGENTS.md` decision tree, raw model strings in `oracle_master_spec.md` §6.2 (now `default_*_route` with route IDs), "balanced alternate routes" language removed from R1 task list, corroboration tier semantics added to `oracle_master_spec.md` §6.6 and to retrieval behavior in `07-knowledge-segmentation.md`, freshness/staleness eval added to `06-evaluation-framework.md`.

- **`07-knowledge-segmentation.md` taxonomy expansion** (commit `665201b`): added boundary rules per domain, made `licensor` first-class, added pre-claim retrieval (document/chunk/message tagging), added more entity types (factory/freight_provider/testing_lab/etc).

- **Default interview model changed to Haiku 4.5** (commit `c98094a`): the prior plan had Sonnet 3.5 as the primary interview route, which would have been an unnecessary cost burden for a pre-production system. Haiku 4.5 is the right cost-aware default until eval data justifies escalating.

---

## Next: R5 — Exact quote validator and promotion service

R5 is the first phase that ships **runtime code in `packages/oracle-engines/src/extraction/`**, not just schema. Per `docs/oracle/05-ai-retrofit-phase-packet.md` Phase R5:

**Tasks:**

1. `packages/oracle-engines/src/extraction/quote-validator.ts` — lift/extend the R2 `EvidenceValidator`:
   - validate source pointers (message / chunk / external / manual)
   - validate exact quote with `.includes()` + offset confirmation
   - compute offsets when the model omits them
   - detect repeated/ambiguous quote (must reject without offsets)
   - allowed-normalization policy (CRLF, whitespace, smart quotes — only when configured)
   - record results into `extraction_validation_results`

2. `packages/oracle-engines/src/extraction/promote-candidate.ts` — the concurrency-locked promotion transaction:
   - advisory lock or `SELECT ... FOR UPDATE` on a hashed candidate representation
   - duplicate detection inside the transaction (loser's evidence appended to winner's claim)
   - inserts into `claims`, `claim_top_domains`, `claim_evidence` atomically
   - idempotent retry behavior — re-running with the same candidate hash does NOT create a duplicate claim

3. Isolated tests (CLI, no DB needed for the validator unit tests):
   - perfect match passes
   - grammar-fix hallucination fails
   - synthesized quote across two messages fails
   - punctuation/whitespace rewrite fails (when normalization is OFF)
   - repeated-quote ambiguity fails without offsets, passes with correct offsets
   - duplicate promotion retry safety

**Acceptance gate** (per the retrofit packet):
- All validation tests pass.
- Invalid quotes never promote.
- Promotion creates claim, top-domains, and evidence in one transaction.
- Duplicate retries do not create duplicate permanent claims.
- Validation errors are stored and inspectable.
- **Do not proceed to Trigger.dev worker wiring (R6) until isolated validator tests pass.**

---

## DB migrations — current state

The following migrations exist but have **NOT been applied to the live Supabase DB yet** (only the SQL files are in the repo):

| Drizzle migration | What it ships |
|---|---|
| `0000_smart_jackpot.sql` | Initial schema (Phase 1) — already applied historically |
| `0001_hot_johnny_blaze.sql` | R3 observability tables + Drizzle meta catch-up for `employee_identities` |
| `0002_demonic_kid_colt.sql` | R3.5 taxonomy tables (15 tables) |
| `0003_magenta_lionheart.sql` | R4 candidate staging tables (4 tables) |

Hand-written SQL files run AFTER the Drizzle migrations on every `pnpm db:migrate`. All are idempotent. New additions:

- `11_observability_constraints.sql` (R3)
- `12_taxonomy_constraints.sql` (R3.5)
- `13_extraction_constraints.sql` (R4)
- `16_knowledge_top_domains_seed.sql` (R3.5 — 12 domains with boundary rules)
- `17_entities_seed.sql` (R3.5 — 56 entities)
- `31_observability_views.sql` (R3 — `model_runs_with_usage` view)
- `42_claim_top_domains_backfill.sql` (R3.5 — backfill from legacy `claim_domains`)
- `48_taxonomy_vector_indexes.sql` (R3.5 — HNSW on `knowledge_sub_topics.centroid`)

**Whenever the live DB is migrated next, `pnpm db:migrate` will apply `0001`, `0002`, `0003` in order and (re)apply every hand-written file.** No existing data is touched. The legacy `claim_domains` table and `claims.knowledge_domain` enum column are intentionally preserved during transition; both will be dropped only after R6+ wiring is in place.

---

## Code that still needs refactor (post-R4)

These will get touched during R6–R9:

- `packages/ai/src/openrouter.ts` — mark legacy; replace production usage with `OracleAIClient`.
- `apps/workers/src/trigger/claim-extraction.ts` — currently writes directly to permanent claims; route through staging tables.
- `apps/workers/src/trigger/document-ingestion.ts` — switch to Vertex/Gemini direct adapter; implement Supabase → Vertex storage bridge.
- `apps/workers/src/trigger/brain-synthesis.ts` — switch to Anthropic direct adapter; add strict synthesis validation.
- `apps/web/app/api/chat/route.ts` — call `OracleAIClient.runText` for interview role; remove direct OpenRouter usage.
- Admin model picker (`apps/web/app/admin/settings/`) — surface curated `OracleModelRoute.routeId`s instead of arbitrary OpenRouter model IDs.

---

## Architectural rules in force

These were established or hardened during the R1–R4 push. Treat them as load-bearing:

1. **No direct provider SDK calls outside `packages/ai/src/providers/`.** Everything goes through `OracleAIClient`.
2. **No extracted claim writes to permanent tables.** Stage → validate → promote, always.
3. **No global vector search.** Every retrieval goes through a `RetrievalPlan` with metadata pre-filter, then hybrid pgvector + tsvector RRF.
4. **`licensor` is NOT `vendor`.** Disney/Marvel/Star Wars/NBCUniversal/Warner Bros are licensors and govern approvals, brand rules, and legal permissions — not capacity or freight.
5. **Sensitive material (HR / personal conflict / disciplinary) never reaches `claims`.** It's quarantined at the candidate stage and never appears in the standard admin queue.
6. **Vertex explicit caches require a tracked reuse policy and cleanup lifecycle.** No "create and forget."
7. **Stable prompt prefix MUST come before any dynamic content.** `ContextCompiler` throws if this invariant is violated — busts prefix caching permanently otherwise.

---

## Do not do yet

- Proactive contradiction interjection (R11).
- Lull-based Oracle questions (R11).
- Live group-chat interjection (R11).
- Aggressive automatic claim approval.
- Brain synthesis from unreviewed or weakly validated claims.

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

R0–R4 of the AI retrofit are done. The next code phase is R5 — Exact
quote validator and promotion service. Build packages/oracle-engines/src/
extraction/{quote-validator,promote-candidate}.ts per docs/oracle/05-ai-
retrofit-phase-packet.md Phase R5. Add isolated tests for the 6 cases
specified there. Do NOT wire the Trigger.dev workers (R6) until R5 tests
pass.

Hard rules in force: no direct provider SDK calls outside OracleAIClient;
no extracted claim writes to permanent tables (stage → validate → promote);
no global vector search (every retrieval through a RetrievalPlan); licensor
is a first-class entity type distinct from vendor; sensitive material is
quarantined at the candidate stage and never reaches claims.
```
