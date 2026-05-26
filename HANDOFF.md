# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-26 (evening session)
**Repo:** https://github.com/u2giants/theoracle
**Current state:** Full AI retrofit complete through R11.0 + wet-test passed. **R11.1–R11.4 (interjection engine completion) is the next work item.**

---

## TL;DR

- R0 → R10.5 done.
- **R-providers done** — direct `@anthropic-ai/sdk` / `@google/genai` / `openai` adapters wired. `@ai-sdk/*` and OpenRouter both retired entirely.
- **Wet-test passed** — first real `claims` rows landed in the live Supabase project on 2026-05-26 17:35 UTC. 2 claims from one synthetic message, 0 errors, 8.3s elapsed. Real Vertex Gemini Flash call, native JSON-schema enforcement, advisory-locked promotion all working.
- **R11.0 done** — `contradiction-watcher` refactored through `OracleAIClient`. Last `getOpenRouter()` call site retired.
- **Next:** R11.1 (pure decision functions for lull + contradiction interjection) → R11.2 (lull-interjection Trigger.dev task with live message posts) → R11.3 (live contradiction interjection posting) → R11.4 (HANDOFF + DECISIONS final cleanup).

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
| **R11.1 — Pure decision functions** | ⬜ next | — | `decideLullInterjection()` + `decideContradictionInterjection()` in `packages/oracle-engines/src/interjection.ts` + smoke gate |
| **R11.2 — Lull-interjection task** | ⬜ | — | `apps/workers/src/trigger/lull-interjection.ts` — cron, picks gap, drafts via Anthropic, **posts live messages** |
| **R11.3 — Live contradiction interjection** | ⬜ | — | Extend contradiction-watcher to post live messages when `enable_live_contradiction_interjections=true` + severity=high |
| **R11.4 — Final docs cleanup** | ⬜ | — | HANDOFF + DECISIONS + retrofit packet final pass |

---

## R11.1+ — the next session's exact work

User decisions already locked in (this session, 2026-05-26):

1. **Live message posts** — both lull-interjection and contradiction-interjection POST real messages into the chat channel. No dry-run gating. Admin reviews via `oracle_interventions` after the fact.
2. **`enable_live_contradiction_interjections = true`** is the default going forward. Currently the seed has it as `false`; R11.3 includes a migration to flip it.
3. **Human-facing message drafting uses the interview route (Anthropic Claude Haiku 4.5).** The contradiction-watcher's adjudication call uses the extraction route (Vertex Gemini Flash) — that's fine because it's machine-internal.

### R11.1 — Pure decision functions

Currently `packages/oracle-engines/src/interjection.ts` is a 39-line stub with JSDoc-only spec comments. Replace with two pure functions + a smoke gate.

```ts
// decideLullInterjection(input) — pure, no DB
//
// Inputs (all numeric / boolean, no I/O):
//   - secondsSinceLastUserMessage: number
//   - lullWindowSeconds: number          (from settings)
//   - isAnyoneTyping: boolean            (caller queries Realtime presence)
//   - minutesSinceLastOracleInterjection: number | null
//   - oracleCooldownMinutes: number      (from settings)
//   - interjectionsInLastHour: number    (caller counts oracle_interventions)
//   - maxOracleInterjectionsPerHour: number (from settings)
//   - enableGroupChatLullQuestions: boolean (from settings)
//   - isGroupChat: boolean
//   - topRelevantOpenGap: { id, priority, questionToAsk, whyItMatters } | null
//
// Output:
//   { decision: 'ask' | 'skip', reason: string, gapId?: string }

// decideContradictionInterjection(input) — pure, no DB
//
// Inputs:
//   - detectionConfidence: number       (0-100; LLM-reported)
//   - severity: 'low' | 'medium' | 'high'
//   - enableLiveContradictionInterjections: boolean
//   - minutesSinceLastOracleInterjection: number | null
//   - oracleCooldownMinutes: number
//   - interjectionsInLastHour: number
//   - maxOracleInterjectionsPerHour: number
//   - suggestedQuestion: string | null
//
// Output:
//   { decision: 'live' | 'queue', reason: string }
```

Smoke gate at `packages/oracle-engines/src/__verify__/r11-1-interjection-decision-smoke.ts` exercising both functions across the gate cases (lull window not yet, lull window passed but rate-capped, lull window passed all gates pass, contradiction below severity threshold, contradiction setting off, contradiction above threshold and setting on, etc.).

### R11.2 — Lull-interjection task

`apps/workers/src/trigger/lull-interjection.ts`:

- `schedules.task` with cron `* * * * *` (every minute).
- Per channel: query last user-message time, last Oracle-interjection time, count of interjections in last hour, presence (or skip the presence check for now — Realtime presence query is a separate path).
- Call `decideLullInterjection`.
- If decision = 'ask': resolve top relevant open gap (pgvector against recent message embeddings → gaps embeddings). Draft the natural-language question via `OracleAIClient.runText` on the interview route (Anthropic Claude Haiku 4.5) with the gap as input. Insert assistant message into `messages`. Insert `oracle_interventions` row with `was_live_interjection=true`, `interjection_message_id=<the new message id>`, `trigger_type='lull_gap'`, `related_gap_id=<gap>`.
- Update `gaps.status='asked'` + `gaps.askedInMessageId`.

Build the OracleAIClient module-singleton at the top of the file (same pattern as the other workers).

### R11.3 — Live contradiction interjection

Modify `apps/workers/src/trigger/contradiction-watcher.ts`:

- After inserting the `contradictions` row + queued gap, if `decision === 'live_interjection'`:
  - Resolve the channel context (the contradiction-watcher currently has none — needs to either look up via the most-recent `claim_evidence.source_message_id` for one of the two claims, or accept a `channelId` payload on the per-claim task).
  - Draft the contradiction surfacing message via `OracleAIClient.runText` on the **interview route** (`object.suggestedQuestion` as input).
  - Insert assistant message; update the `oracle_interventions` row's `channelId` + `interjection_message_id`.

Also write a migration `50_enable_live_contradiction_interjections.sql` that flips the setting:

```sql
UPDATE settings
SET value = 'true'::jsonb, updated_at = now()
WHERE key = 'enable_live_contradiction_interjections';
```

### R11.4 — Final cleanup

- Update `HANDOFF.md` — strike R11.1/R11.2/R11.3 from "next", record completion commits, mark **the AI retrofit complete**.
- Update `DECISIONS.md` with any new D10/D11 entries that emerged.
- Update `docs/oracle/05-ai-retrofit-phase-packet.md` final completion checklist.
- Update `docs/architecture.md` `### 7. Interjection engine` section to show both paths live.

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
apps/workers/src/trigger/lull-interjection.ts     ⬜  to be created in R11.2
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

- **R5.5 entity-extraction prompt rewrite.** R5.5 ships the validator + resolver; the workers call them with empty entity lists. Updating `EXTRACTION_SYSTEM_PROMPT` to emit entities is its own prompt-engineering pass with its own evals.
- **`RetrievalPlan` + hybrid pgvector/tsvector RRF in the chat route.** R8's chat route uses the legacy `searchApprovedClaims` helper.
- **Real Vertex explicit cache creation.** Round 1 of R-providers uses implicit caching only; explicit `cachedContent` resource lifecycle is round 2.
- **R10.5 clustering / drift detection body.** The re-evaluation worker scaffold exists.
- **R10.5 reclassification job for merge/split/reassign proposals.** `create_top_domain` proposals apply transactionally on approval. Merge/split/reassign approvals are audited but the actual reclassification mutation is queued.
- **R10.5 batch-approve UX.**
- **Vertex production credentials.** Local dev uses developer ADC. Cloud runtime needs a service-account JSON mounted via `GOOGLE_APPLICATION_CREDENTIALS` — currently not wired in the Vercel / Trigger.dev project.

---

## Resume prompt for the next Claude Code session

```text
I'm continuing work on The Oracle. Read HANDOFF.md, AGENTS.md, CLAUDE.md,
oracle_master_spec.md, DECISIONS.md, then docs/oracle/00-buildout-index.md.
Do not bulk-read docs/oracle/* — read only the specific files the active
task needs (per CLAUDE.md routing).

State: R0 → R11.0 + wet-test all done. The AI retrofit is functionally
complete; what's left is R11.1 (pure decision functions for interjection)
through R11.4 (final docs).

Next task: R11.1. Implement decideLullInterjection() and
decideContradictionInterjection() in packages/oracle-engines/src/
interjection.ts. Pure functions, no DB. Add a smoke gate
packages/oracle-engines/src/__verify__/r11-1-interjection-decision-smoke.ts.
See HANDOFF.md "R11.1 — Pure decision functions" for the exact input
shape and decision logic.

After R11.1: R11.2 (lull-interjection Trigger.dev task with live message
posts, interview route for drafting), R11.3 (live contradiction
interjection from contradiction-watcher), R11.4 (final docs cleanup).

Hard rules: production AI calls go through OracleAIClient with the three
direct provider adapters; no Vercel AI SDK, no OpenRouter. Sensitive
content quarantined at candidate stage. Stable prefix before dynamic in
ContextCompiler. Advisory-locked promotion. Synthesis rejects
unsupported named entities. Taxonomy mutations admin-gated.

Pre-push gate: pnpm typecheck && pnpm --filter @oracle/web build &&
pnpm --filter @oracle/ai verify:r2 && pnpm --filter @oracle/engines
verify:r5 && pnpm --filter @oracle/engines verify:r5.5 &&
pnpm --filter @oracle/engines verify:r6 && pnpm --filter @oracle/engines
verify:r7 && pnpm --filter @oracle/engines verify:r9.
```
