# The Oracle

AI-powered Enterprise Knowledge Graph for POP Creations / Spruce Line.

> Authoritative product spec: [`oracle_master_spec.md`](oracle_master_spec.md).
> Developer guide: [`AGENTS.md`](AGENTS.md).
> Claude Code notes: [`CLAUDE.md`](CLAUDE.md).
> Assumption / decision log: [`DECISIONS.md`](DECISIONS.md) — read after AGENTS.
> Live in-flight state for a new contributor: [`HANDOFF.md`](HANDOFF.md).
> AI architecture retrofit docs: [`docs/oracle/00-buildout-index.md`](docs/oracle/00-buildout-index.md).

## Current architecture direction

The root product spec remains authoritative for what The Oracle is: a living, evidence-backed Enterprise Knowledge Graph, not a task manager.

The AI implementation is being refit to the Big 3 direct-provider architecture:

- **Anthropic direct** — interview/chat and synthesis quality routes.
- **Google Vertex AI / Gemini direct** — high-volume extraction and document-heavy workflows.
- **OpenAI direct** — structured-output fallback, validation repair, and admin explanation routes.

The old Vercel AI SDK + OpenRouter path is legacy implementation debt for production AI workloads. Do not extend it for background extraction, document ingestion, synthesis, or other cache-sensitive work. Read `docs/oracle/` before changing AI code.

## Architecture & Tech Stack

- **Frontend:** Next.js App Router, Tailwind CSS, shadcn/ui.
- **Database & Auth:** Supabase Cloud PostgreSQL, pgvector, Drizzle ORM.
- **Background Workers:** Trigger.dev Cloud v3.
- **AI Execution Layer:** Provider-Native Adapter Pattern (`OracleAIClient`).
  - *No OpenRouter for production tasks.* The Oracle talks directly to the "Big 3" to maximize explicit and implicit caching:
  - **Anthropic Direct** (`@anthropic-ai/sdk`)
  - **Google Vertex AI Direct** (`@google/genai`)
  - **OpenAI Direct** (`openai`)
- **Next.js 16** App Router (`apps/web`) on **Vercel** (Fluid Compute, Node 24)
- **OpenAI** `text-embedding-3-small` — vector embeddings (1536-dim, locked)
- **Brevo** SMTP — magic-link delivery (configured in Supabase Auth)

## Repo layout

```
apps/
  web/        Next.js app — chat UI, admin dashboard, /api/chat
  workers/    Trigger.dev v3 tasks
packages/
  shared/     constants + types (KNOWLEDGE_DOMAINS, enums)
  db/         Drizzle schema, hand-written SQL (RLS, views, constraints), seed
  auth/       Supabase auth helpers + multi-identity linker
  ai/         OracleAIClient target package; legacy OpenRouter wrapper still exists during retrofit
  oracle-engines/  validation, extraction, interjection, synthesis engine code
docs/
  architecture.md, development.md, configuration.md, deployment.md
  oracle/     mandatory AI buildout addenda
```

## Required AI buildout docs

Before modifying `packages/ai`, `apps/workers`, `apps/web/app/api/chat/route.ts`, model settings, extraction, synthesis, validation, retrieval, or evals, read:

1. [`docs/oracle/00-buildout-index.md`](docs/oracle/00-buildout-index.md) — index, reading order, conflict rules
2. [`docs/oracle/01-model-roles-and-routes.md`](docs/oracle/01-model-roles-and-routes.md) — three model roles, curated route IDs, escalation routes (including Warmth)
3. [`docs/oracle/02-provider-native-ai-architecture.md`](docs/oracle/02-provider-native-ai-architecture.md) — `OracleAIClient`, hybrid (pgvector + tsvector) retrieval, Vertex caching heuristic + teardown rule
4. [`docs/oracle/03-candidate-before-claim-validation.md`](docs/oracle/03-candidate-before-claim-validation.md) — staging tables, PII gate, concurrency-locked promotion, circuit breaker
5. [`docs/oracle/04-context-packs-observability.md`](docs/oracle/04-context-packs-observability.md) — context packs, model-run usage details, 7-day payload log, cache health dashboard
6. [`docs/oracle/05-ai-retrofit-phase-packet.md`](docs/oracle/05-ai-retrofit-phase-packet.md) — R0–R11 implementation order (includes R3.5 taxonomy, R5.5 entity extraction, R10.5 taxonomy admin)
7. [`docs/oracle/06-evaluation-framework.md`](docs/oracle/06-evaluation-framework.md) — CLI-only evals, fixture schemas, metric formulas, phase gates
8. [`docs/oracle/07-knowledge-segmentation.md`](docs/oracle/07-knowledge-segmentation.md) — three-layer taxonomy, entity registry, `RetrievalPlan`, maturity-based re-evaluation worker

## Getting started

```bash
git clone git@github.com:u2giants/theoracle.git oracle
cd oracle
pnpm install
npx vercel@latest link --project prj_rP6Jlima7iK1paffEPhLqxlswGsC --yes
npx vercel@latest env pull .env.local --environment=development --yes
pnpm db:generate     # only after schema.ts changes
pnpm db:migrate
pnpm --filter @oracle/web dev
```

Sign in at http://localhost:3000 with Google or Microsoft 365 (must be an allowlisted email). Magic-link is also available as a fallback.

For full setup details including platform-specific gotchas, see [`docs/development.md`](docs/development.md).

## Phase status

| Phase | Status |
|---|---|
| 0 — Bootstrap | done |
| 1 — Foundation (schema, RLS, auth, seed) | wet-tested |
| 2 — Realtime chat + admin dashboard | code complete, partial wet-test |
| 3 — Oracle chat route + tools | wet-tested on legacy OpenRouter path |
| 4 — Trigger.dev workers | deployed on legacy AI path (7 tasks, version `20260521.1`) |
| 5 — Admin review dashboards | claims / gaps / contradictions / brain pages with server actions are live on `main`; channel + employee admin CRUD UI not in scope |
| R0 — AI retrofit doc reset | done — docs 00–07 in `docs/oracle/` |
| R1 — Curated model route catalog | done — `packages/ai/src/routes/` (commit `91e44ea`) |
| R2 — OracleAIClient + ContextCompiler + ModelRouter + adapter stubs | done — `packages/ai/src/{client,context,routing,providers,usage,validation}/` (commit `3c51c9b`); 16-assertion smoke gate passes (`pnpm --filter @oracle/ai verify:r2`) |
| R3 — Observability schema | done — `oracle_context_packs` + `model_run_usage_details` + `provider_cached_content` (commit `1e345d3`) |
| R3.5 — Knowledge taxonomy schema | done — 15 tables incl. boundary rules + licensor entity type + seeds + backfill (commit `c529594`) |
| R4 — Candidate-before-claim staging schema | done — `extraction_batches` + `extraction_candidates` + `extraction_candidate_evidence` + `extraction_validation_results` (commit `fe60304`) |
| R5 — Quote validator + promotion decision | done — `packages/oracle-engines/src/extraction/` pure validator + decider (commit `70339c6`); 33-assertion smoke gate `pnpm --filter @oracle/engines verify:r5` |
| R5.5 — Entity resolver + taxonomy validator | done — extends `decidePromotion` with `entityAssignments` + `metadata` + `entityProposalsToStage` (commit `8cad256`); 45-assertion smoke `verify:r5.5` |
| R6 — Claim extraction worker refactor | done — `apps/workers/src/trigger/claim-extraction.ts` through staging pipeline + circuit breaker + promotion executor (commit `b46131d`); 30-assertion smoke `verify:r6` |
| R7 — Document ingestion + cache infra | done — `apps/workers/src/trigger/document-ingestion.ts` through staging + `claims.candidate_hash` + race-safe executor + cache profitability/lifecycle (commit `a8a8586`); 19-assertion smoke `verify:r7` |
| R8 — Chat route through OracleAIClient | done — `apps/web/app/api/chat/route.ts` through `OracleAIClient.runText` with `providerOptions` escape hatch for tools/multi-turn (commit `8a38fbd`) |
| R9 — Synthesis worker refactor + diff validator | done — `apps/workers/src/trigger/brain-synthesis.ts` through `OracleAIClient` + `validateSynthesisDiff` (claim ID + unsupported-named-entity check) + rejected-version preservation (commit `8343c2d`); 21-assertion smoke `verify:r9` |
| R10 — Admin AI observability dashboards | done — 6 read-only pages under `/admin/ai`: dashboard, runs list, run detail (context pack viewer), cache, candidates, evals placeholder (commit `ea33d66`) |
| R10.5 — Taxonomy governance dashboard + re-eval worker | done — 5 pages under `/admin/taxonomy` + 4 transactional approve/reject server actions + scheduled `taxonomy-reevaluation` worker scaffold (commit `533f39b`) |
| **R11 — Resume interjection engine** | **gated on wet-test** — architectural prerequisites met; needs real claim data flowing through the pipeline before tuning interjection thresholds |

## What needs attention next

See [`HANDOFF.md`](HANDOFF.md) and [`docs/oracle/05-ai-retrofit-phase-packet.md`](docs/oracle/05-ai-retrofit-phase-packet.md).

The short version:

- **R0–R10.5 are done. The AI retrofit code is complete.** `packages/ai/src/` has the full `OracleAIClient` pipeline (R2). The DB has observability tables (R3), the three-layer knowledge taxonomy (R3.5), candidate-before-claim staging (R4 + R7), and the `claims.candidate_hash` race guard (R7). The pure validator / promoter / entity-resolver / synthesis-diff-validator lives in `packages/oracle-engines/src/extraction/` and `packages/oracle-engines/src/synthesis/` (R5 + R5.5 + R9). All four workers + the chat route dispatch through `OracleAIClient` via the `OpenRouterBridgeAdapter` (R6 / R7 / R8 / R9). Admin dashboards for AI observability live at `/admin/ai` (R10); taxonomy governance lives at `/admin/taxonomy` (R10.5).
- **R11 is next but is gated on a wet-test.** The architectural prerequisites (candidate pipeline live + admin audit surface) are met. The empirical prerequisites (test transcript processed + claims reviewed and approved) need real data flowing through the pipeline first. See `HANDOFF.md` for the recommended next-step sequence.

Pre-push gate — run any time:

```bash
pnpm typecheck                              # 7/7 packages
pnpm --filter @oracle/web build             # production Next build
pnpm --filter @oracle/ai      verify:r2     # 16/16
pnpm --filter @oracle/engines verify:r5     # 33/33
pnpm --filter @oracle/engines verify:r5.5   # 45/45
pnpm --filter @oracle/engines verify:r6     # 30/30
pnpm --filter @oracle/engines verify:r7     # 19/19
pnpm --filter @oracle/engines verify:r9     # 21/21
```

Total: 164 deterministic assertions across the AI retrofit pure-function modules. All run in milliseconds without API keys, database, or network access.

Security reminders:

- The repo is public. Never commit secrets.
- Rotate any token that was pasted into build transcripts.
- Keep `.env.local` gitignored.
