# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-26 (late session)
**Repo:** https://github.com/u2giants/theoracle
**Current state:** **AI retrofit complete + all 6 external review items closed.** R0 → R11.4 done. Both proactive interjection paths post live chat messages by default. External review pass (P1 #1–4, P2 #1–2) completed: settings overhaul with model pool UI, sensitivity flags, entity extraction prompt, full RetrievalPlan + hybrid RRF, requireAdmin on intelligence actions, and honest R10.5 scaffold labels.

The next milestone is no longer code — it's **operational tuning + real-world observation**. See "What's next" at the bottom.

---

## TL;DR

- R0 → R10.5 done.
- **R-providers done** — direct `@anthropic-ai/sdk` / `@google/genai` / `openai` adapters wired. `@ai-sdk/*` and OpenRouter both retired entirely.
- **Wet-test passed** — first real `claims` rows landed in the live Supabase project on 2026-05-26 17:35 UTC. 2 claims from one synthetic message, 0 errors, 8.3s elapsed. Real Vertex Gemini Flash call, native JSON-schema enforcement, advisory-locked promotion all working.
- **R11.0 done** — `contradiction-watcher` refactored through `OracleAIClient`. Last `getOpenRouter()` call site retired.
- **R11.1 done** — pure `decideLullInterjection` + `decideContradictionInterjection` in `packages/oracle-engines/src/interjection.ts`; 33-assertion smoke gate `verify:r11.1`.
- **R11.2 done** — `apps/workers/src/trigger/lull-interjection.ts` cron task: posts live chat messages drafted through the Anthropic Haiku 4.5 interview route when a channel goes quiet and there's a relevant open gap.
- **R11.3 done** — `contradiction-watcher` posts live chat messages when `decideContradictionInterjection` returns `live` (severity=high + confidence≥80 + cooldown clear + rate cap clear + suggested question present + channel resolvable). Migration `50_enable_live_contradiction_interjections.sql` flips the setting ON in the live DB.
- **R11.4 done** — this docs pass.

---

## Pre-production security reminders

The session that landed R-providers and the wet-test required pasting API keys into chat for dev convenience. The keys live in `.env.local` (gitignored) and work fine for development. **Before the app goes live:**

- Rotate `ANTHROPIC_API_KEY` at https://console.anthropic.com/settings/keys
- Rotate `OPENAI_API_KEY` at https://platform.openai.com/api-keys
- Revoke the now-unused OpenRouter key at https://openrouter.ai/keys (it appeared in tool output during R11.0; OpenRouter is no longer used by any code path but the key still works against OpenRouter's API)

Both keys will be re-pasted into `.env.local` once rotated; nothing in the codebase needs to change.

---

## Read this in order

1. `HANDOFF.md` — this file.
2. `AGENTS.md` — developer guide and repo conventions.
3. `CLAUDE.md` — Claude Code-specific notes (short; points to AGENTS).
4. `oracle_master_spec.md` — product/business contract.
5. `DECISIONS.md` — assumptions and historical decisions (D6 + D9 explain why no Vercel AI SDK, no OpenRouter).
6. `docs/oracle/00-buildout-index.md` — index for the AI retrofit docs.
7. The specific `docs/oracle/0N-*.md` file the active task needs — do NOT bulk-read.

---

## Phase status

| Phase | Status | Commit | Notes |
|---|---|---|---|
| R0 — Doc reset | ✅ done | (prior) | `docs/oracle/00–07` |
| R1 — Curated route catalog | ✅ done | `91e44ea` | `packages/ai/src/routes/` |
| R2 — OracleAIClient + adapters scaffolding | ✅ done | `3c51c9b` | Adapter stubs replaced in R-providers |
| R3 — Observability schema | ✅ done | `1e345d3` | `oracle_context_packs` + `model_run_usage_details` + `provider_cached_content` |
| R3.5 — Knowledge taxonomy schema | ✅ done | `c529594` | 15 taxonomy tables + 12 top-domains seeded + 56 entities seeded |
| R4 — Candidate staging schema | ✅ done | `fe60304` | 4 staging tables + 13 CHECK constraints |
| R5 — Quote validator + promotion decision | ✅ done | `70339c6` | Pure functions in `packages/oracle-engines/src/extraction/` |
| R5.5 — Entity resolver + taxonomy validator | ✅ done | `8cad256` | — |
| R6 — Claim extraction worker | ✅ done | `b46131d` | — |
| R7 — Document ingestion + cache infra | ✅ done | `a8a8586` | + race-safe executor |
| R8 — Chat route through OracleAIClient | ✅ done | `8a38fbd` | — |
| R9 — Synthesis worker + diff validator | ✅ done | `8343c2d` | — |
| R10 — Admin AI observability dashboards | ✅ done | `ea33d66` | `/admin/ai/*` |
| R10.5 — Taxonomy governance | ✅ done | `533f39b` | `/admin/taxonomy/*` + re-eval scaffold |
| **Live DB migrations applied** | ✅ done | (this session, via Supabase MCP) | 6 Drizzle (0000–0005) + 18 hand-written SQL (10–17, 20–21, 30–31, 40–42, 48, **49 security hardening**). 51 public tables now exist. Supabase advisor: 36 → 2 findings. |
| **R-providers — direct provider adapters** | ✅ done | `bfc0821` + `51a33ff` | `VertexGeminiAdapter` (`@google/genai`), `AnthropicAdapter` (`@anthropic-ai/sdk`), `OpenAIAdapter` (`openai`). All workers + chat route switched. Real-provider smoke: 6/6 green. |
| **Wet-test** | ✅ done | `51a33ff` | 1 synthetic message → 2 claims promoted, 0 errors, 8.3s. Real Vertex `provider_request_id` captured. |
| **R11.0 — Contradiction-watcher refactor** | ✅ done | `b01e514` | Last `getOpenRouter()` retired. OpenRouter completely removed from codebase. |
| **R11.1 — Pure decision functions** | ✅ done | `c9d0efe` | `decideLullInterjection` + `decideContradictionInterjection` in `packages/oracle-engines/src/interjection.ts` + 33-assertion smoke gate (`verify:r11.1`) |
| **R11.2 — Lull-interjection task** | ✅ done | `bf7cad7` | `apps/workers/src/trigger/lull-interjection.ts` — cron `* * * * *`, picks top open gap for the channel, drafts via Anthropic Haiku 4.5 interview route, posts live message + records `oracle_interventions` |
| **R11.3 — Live contradiction interjection** | ✅ done | `bf7cad7` | `contradiction-watcher` extended: resolves channel from `claim_evidence → messages`, computes cooldown + rate-cap inputs, calls `decideContradictionInterjection`, drafts + posts on 'live' / queues gap on 'queue'. Migration `50_enable_live_contradiction_interjections.sql` flips the setting ON. |
| **R11.4 — Final docs cleanup** | ✅ done | (this commit) | HANDOFF / DECISIONS / AGENTS / architecture / retrofit packet updated. |
| **P1 #4 — requireAdmin on intelligence actions** | ✅ done | (prior session) | `requireAdmin()` guard on claims/gaps/contradictions server actions. |
| **P2 #2 — Honest R10.5 scaffold labels** | ✅ done | (prior session) | UI comments/labels accurately reflect what's shipped vs scaffolded. |
| **P1 #2 + P2 #1 — Sensitivity flags + entity extraction** | ✅ done | `191b791` | `EXTRACTION_PROMPT_VERSION=2.0.0`, `ExtractionSensitivityFlagsSchema`, `ExtractionEntityProposalSchema`, sensitivity gate + entity proposal staging block in workers. |
| **P1 #3 — Full RetrievalPlan + hybrid RRF** | ✅ done | `6a02e36` | `packages/ai/src/retrieval-plan.ts`, `searchWithRetrievalPlan()` with pgvector+tsvector RRF, wired into chat route + contradiction-watcher. Migration `51_claims_fts_index.sql` applied. |
| **P1 #1 — Settings overhaul + model pool** | ✅ done | `a6affc6` | Correct `ROUTE_SETTING_KEYS` throughout; `/admin/settings/model-pool` checkbox UI; `/api/admin/model-catalog` (OpenRouter Big-3 proxy); `resolveModelRoute()` in all 6 workers. |
| **Retrieval enforcement — `RetrievalPlanSearchScope` + `global_fallback` logging** | ✅ done | `aec13ed` | `searchScope` field on every `RetrievalPlan`; `global_fallback` emits structured warning + audit tag in `oracle_context_packs.selected_domains`; `buildDomainScopedPlan` / `buildGlobalRetrievalPlan` factory functions; contradiction-watcher ANN refactored through `searchWithRetrievalPlan`. |

---

## What's next (post-R11)

The AI retrofit is code-complete. Remaining work is operational, not architectural:

1. **Observe what the interjection engine actually does in production.** Both lull and live-contradiction paths post real messages. Admin should watch `/admin/ai/runs` (filter `taskType=lull-interjection` or `contradiction-live-interjection`) and `oracle_interventions` for the first week and tune:
   - `lull_window_seconds` (default 60) — lower if 60s feels too eager
   - `oracle_cooldown_minutes` (default 10) — raise if rooms feel pestered
   - `max_oracle_interjections_per_hour` (default 3) — raise/lower per channel feel
   - `CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD` (constant in `packages/oracle-engines/src/interjection.ts`, default 80) — adjust if misfires happen

2. **Pre-production credential rotation** (carried from earlier in this doc):
   - Rotate `ANTHROPIC_API_KEY` at https://console.anthropic.com/settings/keys
   - Rotate `OPENAI_API_KEY` at https://platform.openai.com/api-keys
   - Revoke the now-unused OpenRouter key at https://openrouter.ai/keys

3. ~~**Trigger.dev deploy.**~~ Done — version `20260527.1` deployed (11 tasks — added `taxonomy-reclassification`). Previous: `20260526.4` (10 tasks).

4. ~~**Vertex production credentials.**~~ Done — `GOOGLE_APPLICATION_CREDENTIALS_JSON` for `oracle-trigger-worker@vertex-ai-497120.iam.gserviceaccount.com` was already set in the Trigger.dev project env from a prior session.

5. **Deferred items** carried forward (not blocking anything but worth knowing):
   - ~~R5.5 entity-extraction prompt rewrite~~ — done in P1 #2 (sensitivity flags + entity proposals in extraction prompt v2.0.0).
   - ~~`RetrievalPlan` + hybrid pgvector/tsvector RRF~~ — done in P1 #3 (`searchWithRetrievalPlan`, wired into chat route + contradiction-watcher).
   - ~~`searchScope` retrieval enforcement~~ — done (commit `aec13ed`; `buildDomainScopedPlan` / `buildGlobalRetrievalPlan`; contradiction-watcher ANN refactored).
   - ~~**`precomputedVector` support in `RetrievalPlan`**~~ — done. `RetrievalPlan.precomputedVector?: number[]` added; `searchWithRetrievalPlan` skips `embedText` when provided; contradiction-watcher passes the stored claim embedding through the plan.
   - ~~**DOMAIN_KEYWORDS tuning** (round 1)~~ — done. Added ~50 keywords across all 10 domains (IT tooling, logistics trade terms, product materials, finance payment, customer compliance). Production `global_fallback` rate should drop significantly. Extend further as gaps emerge.
   - Real Vertex explicit cache creation (round 2 of R-providers).
   - ~~**R10.5 clustering body**~~ — done. `taxonomy-reevaluation.ts` now runs k-means (pure TS, cosine, k=min(8,max(2,round(√(N/4)))), 30 iters) per domain at activation threshold. Novel clusters (cosine sim < 0.88 to any existing sub-topic centroid) are named via Gemini Flash and written as `create_sub_topic` proposals. Payload includes `topDomainId` + `clusterCentroid` + `representativeClaimIds` for the reclassifier.
   - ~~**R10.5 reclassification job**~~ — done. `apps/workers/src/trigger/taxonomy-reclassification.ts` (Trigger.dev task id: `taxonomy-reclassification`) processes approved proposals deferred with `queuedFor: taxonomy-reclassification-worker`. Handles: `create_sub_topic`, `reassign_claims`, `merge_sub_topics`, `retire_sub_topic`, `merge_top_domains`. `split_top_domain` and `split_sub_topic` are logged as manual-intervention-required. Each run appends a `reclassification_applied_*` or `reclassification_skipped_*` change-log row for idempotency.
   - R10.5 batch-approve UX.
   - `docs/oracle/02-provider-native-ai-architecture.md` and `docs/oracle/05-ai-retrofit-phase-packet.md` still describe the bridge adapter as the current production path — both need a sweep; deferred to a separate `docs(retrofit-reference)` commit.
   - `docs/wet-test-walkthrough.md` is historical now that the wet-test ran. Either delete or convert to "how to repeat against a new transcript."

6. ~~**Realtime presence in lull-interjection.**~~ Done — `typing_indicators` table (schema + migration `52_typing_indicators.sql`). `channel-chat.tsx` upserts on typing-start / deletes on typing-stop. Lull worker queries `typing_indicators WHERE expires_at > NOW()` instead of hardcoding `false`. Outstanding: topical gap relevance (embedding-based) is still round 2.

---

## R11.1 — Pure decision functions (reference)

Documented here for archival — what landed:

**Files (now landed):**
- `packages/oracle-engines/src/interjection.ts` — the two pure functions
- `packages/oracle-engines/src/__verify__/r11-1-interjection-decision-smoke.ts` — 33 assertions covering every gate path, boundary condition, gate-ordering case

Run with: `pnpm --filter @oracle/engines verify:r11.1`

**Decision functions:**
- `decideLullInterjection` — 6 gates: group-chat kill switch → lull window → typing → cooldown → rate cap → relevant gap. Each skip returns a stable `reasonCode` for dashboard grouping.
- `decideContradictionInterjection` — 6 gates: live setting → severity=high → confidence ≥ `CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD` (80) → cooldown → rate cap → suggested question present. Each queue returns a stable `reasonCode`.

## R11.2 — Lull-interjection task (reference)

**File (now landed):** `apps/workers/src/trigger/lull-interjection.ts`

**Cron:** `* * * * *` (every minute). The gates inside `decideLullInterjection` (cooldown + rate cap) handle actual frequency — the cron just ensures we check often enough that a 60s lull window can fire promptly.

**Per channel:**
1. Fetch `secondsSinceLastUserMessage` from `messages` (latest non-deleted user message).
2. Fetch `minutesSinceLastOracleInterjection` from `oracle_interventions` (most recent for this channel).
3. Count `oracle_interventions` rows in this channel in the last 60 minutes.
4. Fetch top open gap whose `targetEmployeeId` is null OR a channel participant, ordered by priority (urgent → high → medium → low) then by recency.
5. Call `decideLullInterjection` with the four `settings` values + the above.
6. On `decision === 'ask'`:
   - Draft via `OracleAIClient.runText` on the interview route (Anthropic Haiku 4.5).
   - Insert assistant message into `messages` (employeeId=null, role='assistant', metadataJson tags source).
   - Insert `oracle_interventions` row with `trigger_type='lull_gap'`, `was_live_interjection=true`, `interjection_message_id` set.
   - Update gap: `status='asked'`, `askedInMessageId` set.

**Round-1 simplifications (round-2 follow-ups):**
- `isAnyoneTyping` hardcoded to `false`. Real Supabase Realtime presence query is round 2.
- Top relevant gap = highest-priority gap with targetEmployeeId-null-or-participant. Embedding-based topical relevance against recent messages is round 2.

## R11.3 — Live contradiction interjection (reference)

**Files (now landed):**
- `apps/workers/src/trigger/contradiction-watcher.ts` (extended)
- `packages/db/migrations/sql/50_enable_live_contradiction_interjections.sql` (flips the setting ON; idempotent)

**Per adjudicated contradiction:**
1. Find channel: join `claim_evidence` → `messages` on either claim, pick the most-recent message-sourced channel. Null = both claims sourced from document chunks only, no channel → forced to queue.
2. If channel found: compute `cooldownMin` + `interjectionsInLastHour` for that channel.
3. Call `decideContradictionInterjection`.
4. Insert `contradictions` row with the decision label (`live_interjection` or `queued_gap`).
5. On `decision === 'live'` AND channel found:
   - Draft via `OracleAIClient.runText` on the interview route (Anthropic Haiku 4.5).
   - Post assistant message to the channel; update `oracle_interventions` row with the real channelId + interjection_message_id.
   - On drafting failure: fall through to queue.
6. On `decision === 'queue'` (or live failed):
   - Create the `contradiction_gap` so the question still gets asked through the normal gap pipeline.
   - `oracle_interventions.was_live_interjection = false`.

**Migration `50_enable_live_contradiction_interjections.sql`** is idempotent and was applied to the live DB via Supabase MCP this session. The seed will receive a follow-up to default new installs to true (small change; not blocking).

---

## Architectural rules in force (read these before any AI code change)

These are load-bearing — undoing any of them silently breaks correctness or observability.

1. **No direct provider SDK calls outside `packages/ai/src/providers/`.** Every production model call goes through `OracleAIClient`. Production adapters are `AnthropicAdapter` / `VertexGeminiAdapter` / `OpenAIAdapter` using the providers' raw SDKs. **The Vercel AI SDK is forbidden** inside `packages/ai/src/providers/` (DECISIONS.md D6 + D9). **OpenRouter has been removed entirely** (commit `b01e514`).
2. **No extracted claim writes to permanent tables.** Stage → validate → promote, always. `executePromotion` in `packages/oracle-engines/src/extraction/promotion-executor.ts` is the only path that can insert into `claims` / `claim_top_domains` / `claim_entities` / `claim_evidence` / `claim_metadata`.
3. **No global vector search.** Every retrieval that lands must go through a `RetrievalPlan` with metadata pre-filter, then hybrid pgvector + tsvector RRF.
4. **`licensor` is NOT `vendor`.** Structural enforcement via CHECK constraint + entity resolver `type_mismatch` detection.
5. **Sensitive material never reaches `claims`.** Quarantined at the candidate stage. `/admin/ai/candidates` hides sensitive rows from the standard queue.
6. **Vertex explicit caches require a tracked reuse policy.** `recordCacheCreation` / `recordCacheTermination` is the only correct path.
7. **Stable prompt prefix MUST precede dynamic content.** `ContextCompiler` throws if a stable block appears after a dynamic block.
8. **Advisory-locked, race-safe promotion.** `executePromotion` acquires `pg_try_advisory_xact_lock(hashtextextended(candidateHash, 0))` AND re-reads the candidate + validated evidence INSIDE the transaction. The same-hash claim lookup also happens inside the lock.
9. **Synthesis output is rejected when unsupported named entities appear.** Every capitalized proper-noun-shaped name in `updatedMarkdown` must be backed by an approved claim summary OR the canonical entity registry.
10. **Taxonomy changes are admin-gated.** The re-evaluation worker writes only to `taxonomy_proposals`.

---

## What runs through `OracleAIClient` today

```
apps/workers/src/trigger/claim-extraction.ts      ✅  R6 + R-providers — direct adapters
apps/workers/src/trigger/document-ingestion.ts    ✅  R7 + R-providers — direct adapters
apps/web/app/api/chat/route.ts                    ✅  R8 + R-providers — direct adapters
apps/workers/src/trigger/brain-synthesis.ts       ✅  R9 + R-providers — direct adapters
apps/workers/src/trigger/contradiction-watcher.ts ✅  R11.0 — direct adapters
apps/workers/src/trigger/taxonomy-reevaluation.ts ⬜  scaffold only; clustering body deferred
apps/workers/src/trigger/lull-interjection.ts     ✅  R11.2 — cron task; direct Anthropic (interview route)
```

**Required env vars** (in repo-root `.env.local`):
- `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
- `GOOGLE_CLOUD_PROJECT=vertex-ai-497120`, `GOOGLE_CLOUD_LOCATION=us-central1` + working ADC (`gcloud auth application-default login`)
- `ANTHROPIC_API_KEY=sk-ant-…`
- `OPENAI_API_KEY=sk-proj-…`
- `TRIGGER_SECRET_KEY`, `TRIGGER_PROJECT_REF=proj_wgpzsvhmsopqhvwqaycn`

Full table with sources: `docs/configuration.md`.

---

## Smoke gates

All run without API keys, database, or network access:

```bash
pnpm --filter @oracle/ai      verify:r2     # OracleAIClient pipeline
pnpm --filter @oracle/engines verify:r5     # quote validator + decider
pnpm --filter @oracle/engines verify:r5.5   # entity resolver + taxonomy validator
pnpm --filter @oracle/engines verify:r6     # circuit breaker
pnpm --filter @oracle/engines verify:r7     # cache profitability
pnpm --filter @oracle/engines verify:r9     # synthesis diff validator
pnpm --filter @oracle/ai      eval:extraction   # mock-mode extraction eval (4 fixtures)
```

Real-provider smoke (~$0.003 against the real APIs):

```bash
pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts all
```

End-to-end wet-test (writes to the live DB; requires the message to be inserted first):

```bash
pnpm --filter @oracle/workers tsx src/wet-test/run-claim-extraction-once.ts <run-label>
```

Pre-push gate:

```bash
pnpm typecheck                              # all 7 packages
pnpm --filter @oracle/web build             # production Next build
```

---

## Live database state (2026-05-26)

Supabase project `vokucjpanhvqunimlvsp` (`theoracle`, Postgres 17, us-east-2).

- **51 public tables** (all retrofit migrations applied via Supabase MCP this session).
- **6 Drizzle migrations** recorded in `drizzle.__drizzle_migrations`.
- **49 raw SQL files** in `packages/db/migrations/sql/` are idempotent and source-of-truth.
- **2 real `claims` rows** (from the wet-test). `extraction_batches`, `extraction_candidates`, `extraction_candidate_evidence`, `model_runs`, `model_run_usage_details`, `oracle_context_packs` all have at least one real row.
- **Supabase advisor: 2 informational warnings** (vector extension in public schema; Supabase Auth leaked-password protection disabled). Both are config recommendations, not vulnerabilities.

If you need to re-run migrations from a fresh checkout, `pnpm db:migrate` is idempotent and a no-op against this DB.

---

## What's deliberately deferred (not blocking R11)

- **Real Vertex explicit cache creation.** Round 1 of R-providers uses implicit caching only; explicit `cachedContent` resource lifecycle is round 2.
- **R10.5 clustering / drift detection body.** `taxonomy-reevaluation.ts:68` returns `proposalsWritten: 0` as a *literal type* — the worker counts claims per domain and reports against the activation threshold, but does not write any proposals. Until claim density crosses the threshold this is fine; once it does, the worker needs the embedding-clustering body to start emitting `create_sub_topic` / `split_top_domain` proposals.
- **R10.5 reclassification job for merge/split/reassign proposals.** `create_top_domain` proposals apply transactionally on approval. **Merge/split/reassign/sub-topic approvals log an audit entry in `taxonomy_change_log` but don't actually reclassify any claims** — the dedicated reclassification job is the next R10.5 follow-up.
- **R10.5 batch-approve UX.**

---

## Resume prompt for the next Claude Code session

```text
I'm continuing work on The Oracle. Read HANDOFF.md, AGENTS.md, CLAUDE.md,
oracle_master_spec.md, DECISIONS.md, then docs/oracle/00-buildout-index.md.
Do not bulk-read docs/oracle/* — read only the specific files the active
task needs (per CLAUDE.md routing).

State: AI retrofit is COMPLETE. R0 → R11.4 all done. Wet-test passed.
Both interjection paths live. The remaining work is operational tuning
(setting values, observation, threshold adjustment) plus the
deferred-items list in HANDOFF.md "What's next".

Hard rules: production AI calls go through OracleAIClient with the three
direct provider adapters (Anthropic + Vertex + OpenAI raw SDKs). No
Vercel AI SDK. No OpenRouter. Sensitive content quarantined at candidate
stage. Stable prefix before dynamic in ContextCompiler. Advisory-locked
promotion. Synthesis rejects unsupported named entities. Taxonomy
mutations admin-gated.

Pre-push gate: pnpm typecheck && pnpm --filter @oracle/web build &&
pnpm --filter @oracle/ai verify:r2 && pnpm --filter @oracle/engines
verify:r5 && pnpm --filter @oracle/engines verify:r5.5 &&
pnpm --filter @oracle/engines verify:r6 && pnpm --filter @oracle/engines
verify:r7 && pnpm --filter @oracle/engines verify:r9 &&
pnpm --filter @oracle/engines verify:r11.1.
```

---

## When is this HANDOFF.md eligible for deletion?

Per the user's documentation rule: "Delete HANDOFF.md once the work it describes is complete."

The work this file describes (R11.x) is complete. **But** the document still serves three purposes that aren't quite "describing in-flight work":

1. The "What's next (post-R11)" section lists operational tasks the user needs to do (rotate keys, deploy workers to Trigger.dev, provision Vertex prod credentials). These aren't "unfinished code" but they ARE unfinished work.
2. The reference sections (R11.1, R11.2, R11.3) capture decisions made this session in a form that's easier to find than scrolling the commit history.
3. The deferred-items list keeps the future-work backlog in one place.

**Recommendation:** keep HANDOFF.md until items 2-3 above are merged into either AGENTS.md §15 (pending work) or DECISIONS.md, and item 1 is either completed or migrated to AGENTS.md. After that, delete it.
