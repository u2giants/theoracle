# The Oracle

AI-powered Enterprise Knowledge Graph for POP Creations / Spruce Line.

> Authoritative product spec: [`oracle_master_spec.md`](oracle_master_spec.md).
> Developer guide: [`AGENTS.md`](AGENTS.md).
> Claude Code notes: [`CLAUDE.md`](CLAUDE.md).
> Assumption / decision log: [`DECISIONS.md`](DECISIONS.md).
> Live in-flight state: [`HANDOFF.md`](HANDOFF.md).
> AI retrofit reference docs: [`docs/oracle/00-buildout-index.md`](docs/oracle/00-buildout-index.md).

## What this is

A living, evidence-backed Enterprise Knowledge Graph for an 18-person home-decor company with 1,500 SKUs and Disney/Marvel/Star Wars/NBCUniversal/Warner Bros licensing relationships. It interviews employees in chat, extracts operational claims with verbatim quote evidence, validates them through a deterministic candidate-before-claim pipeline, and synthesizes a Brain of approved Markdown sections with claim-level traceability.

The master spec (`oracle_master_spec.md`) is the contract for what The Oracle is and is not. The retrofit packet in `docs/oracle/` is the implementation contract for how the AI layer is wired.

## Architecture & tech stack

- **Frontend:** Next.js 16 App Router (`apps/web`) on Vercel (Fluid Compute, Node 24), Tailwind CSS, shadcn/ui.
- **Database & Auth:** Supabase Cloud Postgres 17, pgvector 0.8, Drizzle ORM.
- **Background workers:** Trigger.dev Cloud v3 (`apps/workers`).
- **AI execution layer:** `OracleAIClient` (`packages/ai/src/client/`) → `ContextCompiler` → `ModelRouter` → direct provider adapters.
  - **Anthropic direct** via `@anthropic-ai/sdk` — interview chat (Claude Haiku 4.5).
  - **Google Vertex AI direct** via `@google/genai` — extraction + synthesis (Gemini 2.5 Flash).
  - **OpenAI direct** via `openai` — fallback + schema repair (GPT-4o-mini).
  - **No Vercel AI SDK in the production AI path** (DECISIONS.md D6 / D9). No OpenRouter (retired R11.0).
- **Embeddings:** OpenAI `text-embedding-3-small` — 1536-dim, locked. Used for hybrid retrieval and contradiction ANN search.
- **Auth providers:** Google + Microsoft 365 + magic-link (Brevo SMTP).

## Repo layout

```
apps/
  web/        Next.js app — chat UI, admin dashboards (/admin/ai, /admin/taxonomy), /api/chat
  workers/    Trigger.dev v3 tasks (extraction, ingestion, synthesis, contradiction-watcher, taxonomy-reevaluation)
packages/
  shared/         constants + types (KNOWLEDGE_DOMAINS, TOP_LEVEL_DOMAINS, ENTITY_TYPES, enums)
  db/             Drizzle schema, hand-written SQL (01–49 raw files for RLS / views / constraints / seeds), seed runner
  auth/           Supabase auth helpers + multi-identity linker
  ai/             OracleAIClient + ContextCompiler + ModelRouter + 3 direct provider adapters + curated route catalog
  oracle-engines/ pure functions: quote validator, taxonomy validator, entity resolver, promotion decider + executor, synthesis-diff validator
docs/
  architecture.md, development.md, configuration.md, deployment.md, wet-test-walkthrough.md
  oracle/         AI retrofit reference docs (00–07)
```

## AI retrofit reference docs

Before modifying `packages/ai`, `apps/workers`, `apps/web/app/api/chat/route.ts`, model settings, extraction, synthesis, validation, retrieval, or evals, read the relevant addendum from `docs/oracle/`:

1. `00-buildout-index.md` — index + reading order
2. `01-model-roles-and-routes.md` — three model roles, curated route IDs, escalation routes (incl. Warmth)
3. `02-provider-native-ai-architecture.md` — `OracleAIClient` pipeline, hybrid retrieval, Vertex cache heuristic
4. `03-candidate-before-claim-validation.md` — staging tables, sensitivity gate, advisory-locked promotion, circuit breaker
5. `04-context-packs-observability.md` — context packs, `model_run_usage_details`, cache health dashboard
6. `05-ai-retrofit-phase-packet.md` — R0–R11 implementation order
7. `06-evaluation-framework.md` — CLI evals, fixture schemas, metric formulas, phase gates
8. `07-knowledge-segmentation.md` — three-layer taxonomy, entity registry, `RetrievalPlan`

## Getting started

```bash
git clone git@github.com:u2giants/theoracle.git oracle
cd oracle
pnpm install
npx vercel@latest link --project prj_rP6Jlima7iK1paffEPhLqxlswGsC --yes
npx vercel@latest env pull .env.local --environment=development --yes
# Then add the direct-provider keys to .env.local manually (see docs/configuration.md):
#   GOOGLE_CLOUD_PROJECT=vertex-ai-497120
#   GOOGLE_CLOUD_LOCATION=us-central1
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-proj-...
gcloud auth application-default login   # Vertex direct uses ADC
pnpm db:generate     # only after schema.ts changes
pnpm db:migrate      # all 6 Drizzle + 18 raw SQL migrations are already applied to the live DB
pnpm --filter @oracle/web dev
```

Sign in at http://localhost:3000 with Google, Microsoft 365, or magic-link (must be an allowlisted email).

Full setup details: [`docs/development.md`](docs/development.md). All env vars: [`docs/configuration.md`](docs/configuration.md).

## Phase status

| Phase | Status | Reference |
|---|---|---|
| 0 — Bootstrap | done | — |
| 1 — Foundation (schema, RLS, auth, seed) | wet-tested | — |
| 2 — Realtime chat + admin dashboard | code complete | — |
| 3 — Oracle chat route + tools | wet-tested (now on direct Anthropic adapter) | `R8` + `R-providers` |
| 4 — Trigger.dev workers | deployed (5 tasks) | — |
| 5 — Admin review dashboards | claims / gaps / contradictions / brain pages live | — |
| R0 — AI retrofit doc reset | done | docs `00–07` in `docs/oracle/` |
| R1 — Curated model route catalog | done | `packages/ai/src/routes/` (commit `91e44ea`) |
| R2 — OracleAIClient + ContextCompiler + ModelRouter | done | `packages/ai/src/{client,context,routing,…}/` (commit `3c51c9b`) |
| R3 — Observability schema | done | `oracle_context_packs` + `model_run_usage_details` + `provider_cached_content` (commit `1e345d3`) |
| R3.5 — Knowledge taxonomy schema | done | 15 tables + 12 top-domains seeded + 56 entities seeded (commit `c529594`) |
| R4 — Candidate staging schema | done | 4 staging tables + 13 CHECK constraints (commit `fe60304`) |
| R5 — Quote validator + promotion decision | done | `packages/oracle-engines/src/extraction/` (commit `70339c6`) |
| R5.5 — Entity resolver + taxonomy validator | partial | Pure validators landed (commit `8cad256`, 45-assertion smoke). **Workers still pass `proposedEntities: []` + `entityRegistry: []`** — model is not yet asked to emit entities. Wiring deferred to a prompt-rewrite pass. |
| R6 — Claim extraction worker refactor | done | `apps/workers/src/trigger/claim-extraction.ts` (commit `b46131d`) |
| R7 — Document ingestion + cache infra | done | (commit `a8a8586`) |
| R8 — Chat route through OracleAIClient | done | `apps/web/app/api/chat/route.ts` (commit `8a38fbd`) |
| R9 — Synthesis worker + diff validator | done | `apps/workers/src/trigger/brain-synthesis.ts` (commit `8343c2d`) |
| R10 — Admin AI observability dashboards | done | `/admin/ai/*` (commit `ea33d66`) |
| R10.5 — Taxonomy governance dashboard | partial | `/admin/taxonomy/*` admin pages + `create_top_domain` server action are live (commit `533f39b`). **Re-evaluation worker is a scaffold** — counts claims per domain and returns `proposalsWritten: 0` literal; clustering/drift detection deferred until claim density justifies it. **Merge/split/reassign proposal approvals audit but don't actually reclassify** — reclassification job deferred. |
| R-providers — Direct provider adapters | done | `VertexGeminiAdapter` via `@google/genai`, `AnthropicAdapter` via `@anthropic-ai/sdk`, `OpenAIAdapter` via `openai` (commits `bfc0821` + `51a33ff`) |
| **Wet-test** | done | First real claims landed in `claims` table 2026-05-26 — 2 claims from one synthetic message, 0 errors, 8.3s elapsed (commit `51a33ff`) |
| R11.0 — Contradiction-watcher through OracleAIClient | done | Last `getOpenRouter()` call site retired (commit `b01e514`) |
| R11.1 — Pure decision functions | done | `decideLullInterjection` + `decideContradictionInterjection` + 33-assertion smoke gate (commit `c9d0efe`) |
| R11.2 — Lull-interjection task | done | `apps/workers/src/trigger/lull-interjection.ts` — cron every minute, posts live chat messages (commit `bf7cad7`) |
| R11.3 — Live contradiction interjection | done | `contradiction-watcher` extended to draft + post live messages; migration `50_enable_live_contradiction_interjections.sql` (commit `bf7cad7`) |
| R11.4 — Final docs cleanup | done | This README, AGENTS, HANDOFF, DECISIONS (D10 + D11), docs/architecture |
| **AI retrofit** | **complete** | Remaining work is operational tuning, not architecture. See `HANDOFF.md` "What's next". |

## Smoke gates — run any time

```bash
pnpm typecheck                              # 7/7 packages
pnpm --filter @oracle/web build             # production Next build
pnpm --filter @oracle/ai      verify:r2     # OracleAIClient
pnpm --filter @oracle/engines verify:r5     # quote validator + promotion decision
pnpm --filter @oracle/engines verify:r5.5   # entity resolver + taxonomy validator
pnpm --filter @oracle/engines verify:r6     # circuit breaker
pnpm --filter @oracle/engines verify:r7     # cache profitability
pnpm --filter @oracle/engines verify:r9     # synthesis diff validator
pnpm --filter @oracle/engines verify:r11.1  # lull + contradiction interjection deciders
pnpm --filter @oracle/ai      eval:extraction  # mock-mode extraction eval (4 fixtures)
```

All deterministic smoke runs are pure functions — no API keys, no DB, no network.

## Real-provider smoke

```bash
pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts all
```

Fires generateText + generateObject against each of the 3 direct providers. Costs ~$0.003 total. Requires the four env vars listed above.

## Security reminders

- Repo is public. Never commit secrets.
- `.env.local` is gitignored; never paste keys into chat or build transcripts.
- Rotate any provider key that appears in a transcript, screenshot, or support ticket.
