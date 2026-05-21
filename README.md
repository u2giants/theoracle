# The Oracle

AI-powered Enterprise Knowledge Graph for POP Creations / Spruce Line.

> Authoritative product spec: [`oracle_master_spec.md`](oracle_master_spec.md).
> Developer guide: [`AGENTS.md`](AGENTS.md).
> Assumption / decision log: [`DECISIONS.md`](DECISIONS.md) — read after AGENTS.
> Live in-flight state for a new contributor: [`HANDOFF.md`](HANDOFF.md).

## Stack

- **Next.js 16** App Router (`apps/web`) on **Vercel** (Fluid Compute, Node 24)
- **Tailwind** + **shadcn/ui** + **lucide-react**
- **Supabase Cloud** — Postgres + pgvector, Auth, Realtime, Storage
- **Drizzle ORM** (`packages/db`) — schema + migrations
- **Trigger.dev v3** (`apps/workers`) — background workers (deployed, version `20260521.1`)
- **Vercel AI SDK** + **OpenRouter** (`packages/ai`) — LLM calls
- **OpenAI** `text-embedding-3-small` — vector embeddings (1536-dim, locked)
- **Brevo** SMTP — magic-link delivery (configured in Supabase Auth)

## Repo layout

```
apps/
  web/        Next.js app — chat UI, admin dashboard, /api/chat
  workers/    Trigger.dev v3 tasks (Phase 4 scaffolds)
packages/
  shared/     constants + types (KNOWLEDGE_DOMAINS, enums)
  db/         Drizzle schema, hand-written SQL (RLS, views, constraints), seed
  auth/       Supabase auth helpers + multi-identity linker
  ai/         system prompt, OpenRouter wrapper, embeddings, retrieval
  oracle-engines/  interjection rules (Phase 6 scaffold)
docs/
  architecture.md, development.md, configuration.md, deployment.md
```

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

Sign in at http://localhost:3000 with Google or Microsoft 365 (must be an
allowlisted email). Magic-link is also available as a fallback.

For full setup details including platform-specific gotchas, see [`docs/development.md`](docs/development.md).

## Phase status

| Phase | Status |
|---|---|
| 0 — Bootstrap | done |
| 1 — Foundation (schema, RLS, auth, seed) | **wet-tested** |
| 2 — Realtime chat + admin dashboard | code complete, **partial wet-test** (RLS cross-channel isolation needs second loginable employee) |
| 3 — Oracle chat route + tools | **wet-tested** — Claude Sonnet 4.6, 6.3 s, 2001/98 tokens |
| 4 — Trigger.dev workers | **deployed** — version `20260521.1`, 7 tasks running in production |
| 5 — Admin review dashboards | placeholder pages only |
| 6 — Interjection engine | empty module with spec rules as JSDoc |

The Phase 2 RLS gate ("Employee A cannot see Channel X") needs a second
real loginable employee. The seeded `test-employee@oracle.local` is not a
real mailbox; replace it with a `+`-aliased gmail or a second real account
before testing.

## What needs attention next

See [`HANDOFF.md`](HANDOFF.md) for the full punch list with context.
The short version:

- **Next build: Phase 5** — admin review dashboards (claims, gaps,
  contradictions, brain). Placeholders exist under `apps/web/app/admin/`.
  Workers are running and will produce data; dashboards are needed to
  review and approve extracted claims before synthesis can run.
- Delete the deprecated `auth_user_id` / `auth_provider` / `auth_provider_subject`
  columns from `employees` once consumers are confirmed migrated
  (DECISIONS.md D2.multi-identity).
- Rotate the Vercel token that was pasted into the build transcript.
