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

## Stack

- **Next.js 16** App Router (`apps/web`) on **Vercel** (Fluid Compute, Node 24)
- **Tailwind** + **shadcn/ui** + **lucide-react**
- **Supabase Cloud** — Postgres + pgvector, Auth, Realtime, Storage
- **Drizzle ORM** (`packages/db`) — schema + migrations
- **Trigger.dev v3** (`apps/workers`) — background workers
- **Direct Big 3 AI provider adapters** target architecture in `packages/ai`
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
8. [`docs/oracle/07-knowledge-segmentation.md`](docs/oracle/07-knowledge-segmentation.md) — three-layer taxonomy, entity registry, `RetrievalPlan`, monthly re-evaluation worker

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
| **R1 — Model route configuration** | **next code phase** — see `docs/oracle/05-ai-retrofit-phase-packet.md` |
| R2–R10.5 — rest of AI architecture retrofit | not started |
| 6 — Interjection engine | paused until AI retrofit and validation pipeline are complete |

## What needs attention next

See [`HANDOFF.md`](HANDOFF.md) and [`docs/oracle/05-ai-retrofit-phase-packet.md`](docs/oracle/05-ai-retrofit-phase-packet.md).

The short version:

- **Next build: AI architecture retrofit**, not proactive interjection.
- R1 — curated `OracleModelRoute` IDs in `packages/ai/src/routes/`; admin picker selects route IDs, not raw OpenRouter model strings.
- R2 — `OracleAIClient` with Anthropic / Vertex-Gemini / OpenAI direct adapters.
- R3 + R3.5 — context packs, model-run usage details, provider cached-content tracking, three-layer knowledge taxonomy tables.
- R4 + R5 + R5.5 — candidate-before-claim staging, deterministic quote validator, concurrency-locked promotion, entity-tag extraction.
- R6 → R9 — refactor each worker and the chat route through `OracleAIClient`.
- R10 + R10.5 — observability dashboards, taxonomy governance, monthly re-evaluation worker.
- R11 — resume the interjection engine, on top of trustworthy claims.

Security reminders:

- The repo is public. Never commit secrets.
- Rotate any token that was pasted into build transcripts.
- Keep `.env.local` gitignored.
