# The Oracle

AI-powered Enterprise Knowledge Graph for POP Creations / Spruce Line.

> Authoritative spec: `oracle_master_spec.md` in this repo.
> Build log + decisions: `DECISIONS.md` — **read this first.**

## Stack

- Next.js 15 App Router (apps/web) on Vercel
- Tailwind + shadcn/ui + lucide-react
- Supabase Cloud — Postgres, pgvector, Realtime, Storage, Auth
- Drizzle ORM (packages/db) for schema + migrations
- Trigger.dev v3 (apps/workers) for background workers (Phase 4 stub)
- Vercel AI SDK + OpenRouter (packages/ai) for LLM calls

## Repo layout

```
apps/
  web/        Next.js app — chat, admin dashboard, /api/chat route
  workers/    Trigger.dev v3 tasks (Phase 4 stubs)
packages/
  shared/     KNOWLEDGE_DOMAINS, enums, types
  db/         Drizzle schema, raw SQL migrations, RLS, views, seed
  auth/       Supabase auth helpers + first-login linker (spec 4.4)
  ai/         System prompt (Part 10), OpenRouter, embeddings, retrieval
  oracle-engines/  Interjection rules (Phase 6 stub)
```

## Getting started

1. **Enable Windows Developer Mode** (Settings → For Developers) — required for pnpm symlinks. See DECISIONS.md D0.6.
2. Install dependencies: `pnpm install`.
3. Pull env vars: `npx vercel@latest env pull .env.local --environment=development --token <YOUR_VERCEL_TOKEN> --yes`. The eight required env vars exist on the Vercel project as empty strings — populate them first. See DECISIONS.md D0.4.
4. Generate Drizzle migrations: `pnpm db:generate`.
5. Push schema + RLS + seed: `pnpm db:migrate`.
6. Dev: `pnpm dev`.

## Phase status

- Phase 0 — Bootstrap: done
- Phase 1 — Foundation (schema, RLS, auth, seed): code complete; pending wet test
- Phase 2 — Realtime chat + admin dashboard: code complete; pending wet test
- Phase 3 — Oracle chat route + tools: code complete; pending wet test
- Phase 4 — Trigger.dev workers: stubbed with spec comments
- Phase 5 — Admin review dashboard: stubbed (placeholder pages)
- Phase 6 — Interjection engine: stubbed (spec rules as JSDoc)

## What needs your attention

See the top of `DECISIONS.md` — the security note and the two blockers (empty Vercel env vars, no symlink permission) need action before the schema can be deployed.
