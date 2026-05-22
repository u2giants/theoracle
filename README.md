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

Before modifying `packages/ai`, `apps/workers`, `apps/web/app/api/chat/route.ts`, model settings, extraction, synthesis, or validation, read:

1. [`docs/oracle/00-buildout-index.md`](docs/oracle/00-buildout-index.md)
2. [`docs/oracle/01-model-roles-and-routes.md`](docs/oracle/01-model-roles-and-routes.md)
3. [`docs/oracle/02-provider-native-ai-architecture.md`](docs/oracle/02-provider-native-ai-architecture.md)
4. [`docs/oracle/03-candidate-before-claim-validation.md`](docs/oracle/03-candidate-before-claim-validation.md)
5. [`docs/oracle/04-context-packs-observability.md`](docs/oracle/04-context-packs-observability.md)
6. [`docs/oracle/05-ai-retrofit-phase-packet.md`](docs/oracle/05-ai-retrofit-phase-packet.md)

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
| 4 — Trigger.dev workers | deployed on legacy AI path |
| 5 — Admin review dashboards | code present; verify against current handoff |
| R0-R11 — AI architecture retrofit | **current priority before Phase 6 interjection** |
| 6 — Interjection engine | pause until AI retrofit and validation pipeline are complete |

## What needs attention next

See [`HANDOFF.md`](HANDOFF.md) and [`docs/oracle/05-ai-retrofit-phase-packet.md`](docs/oracle/05-ai-retrofit-phase-packet.md).

The short version:

- **Next build: AI architecture retrofit**, not proactive interjection.
- Add Big 3 direct provider adapters and `OracleAIClient`.
- Add context packs, usage details, and provider cached-content tracking.
- Add candidate-before-claim staging tables.
- Refactor claim/document extraction to stage and validate candidates before permanent claims.
- Then resume the interjection engine.

Security reminders:

- The repo is public. Never commit secrets.
- Rotate any token that was pasted into build transcripts.
- Keep `.env.local` gitignored.
