# Development

This file covers local setup and the routine commands that reflect the current repo.

## Prerequisites

- Node.js 20+; current CI uses Node 24
- `pnpm` 9.x
- Git access to `u2giants/theoracle`
- A local `.env.local` at the repo root
- Supabase access for the target project
- Google Cloud ADC if you need Vertex locally: `gcloud auth application-default login`

## First-time setup

```bash
git clone git@github.com:u2giants/theoracle.git
cd theoracle
pnpm install
npx vercel@latest link --project prj_rP6Jlima7iK1paffEPhLqxlswGsC --yes
npx vercel@latest env pull .env.local --environment=development --yes
pnpm db:migrate
```

Then fill in any direct-provider variables that are not available through the pulled Vercel development env. See `docs/configuration.md`.

## Daily commands

From the repo root:

```bash
pnpm dev
pnpm dev:all
pnpm workers:dev
pnpm typecheck
pnpm lint
pnpm build
pnpm format
```

Workspace-specific commands:

```bash
pnpm --filter @oracle/web dev
pnpm --filter @oracle/web build
pnpm --filter @oracle/workers deploy
pnpm --filter @oracle/db generate
pnpm --filter @oracle/db migrate
pnpm --filter @oracle/db seed
```

## Verification gates

Run these before pushing changes that affect runtime code:

```bash
pnpm typecheck
pnpm --filter @oracle/web build
```

If you changed AI runtime logic, also run the relevant deterministic gates:

```bash
pnpm --filter @oracle/ai verify:r2
pnpm --filter @oracle/engines verify:r5
pnpm --filter @oracle/engines verify:r5.5
pnpm --filter @oracle/engines verify:r6
pnpm --filter @oracle/engines verify:r7
pnpm --filter @oracle/engines verify:r9
```

If you need the mock extraction eval:

```bash
pnpm --filter @oracle/ai eval:extraction
```

## Working on database changes

1. Edit `packages/db/src/schema.ts`.
2. Run `pnpm db:generate` if the schema shape changed.
3. Add a hand-written SQL file under `packages/db/migrations/sql/` if the change needs constraints, RLS, views, or data migration logic.
4. Run `pnpm db:migrate`. This is the ONLY path that should apply generated `0NNN_*.sql` files — do not use Supabase MCP `apply_migration`, the dashboard SQL editor, or `drizzle-kit push` for those, or the journal drifts (see AGENTS.md incident 2026-05-28).
5. Update docs if the data model or operations changed.

Useful at any time: `pnpm db:check-drift` compares on-disk migration hashes against `drizzle.__drizzle_migrations` in the live DB and reports any mismatch. CI runs the same check on every push.

Do not edit previously applied migration files.

## Working on provider adapters

Relevant files:

- `packages/ai/src/providers/*.ts`
- `packages/ai/src/client/standard-adapters.ts`
- `packages/ai/src/routes/{types,resolve}.ts`
- `packages/ai/src/providers/cache-utils.ts`

Rules:

- Do not call provider SDKs directly from routes or workers.
- Register providers through `buildStandardAdapters()`.
- Keep provider-specific cache behavior inside the adapters.
- Update docs when adapter behavior changes.

## Working on workers

Worker entrypoints live in `apps/workers/src/trigger/`.

Current task files:

- `claim-extraction.ts`
- `document-ingestion.ts`
- `brain-synthesis.ts`
- `lull-interjection.ts`
- `contradiction-watcher.ts`
- `taxonomy-reevaluation.ts`
- `taxonomy-reclassification.ts`

Routine expectations:

- workers insert `job_runs`
- model calls insert `model_runs` and `model_run_usage_details`
- prompt plans insert `oracle_context_packs`

## Useful inspection scripts

- `scripts/verify-catalog.ts` — inspects provider model-list fetching and OpenRouter enrichment
- `scripts/refresh-catalog.ts` — refreshes `model_capabilities` in the real DB
- `packages/db/src/verify-identities.ts` — employee/identity inspection
- `packages/db/src/inspect-auth-users.ts` — Supabase auth user inspection

## Current incomplete areas you may encounter

- `apps/web/app/admin/taxonomy/_actions.ts` queues some proposal types for later reclassification instead of applying them inline.
- Oversized Vertex file-backed caching only activates when `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` is configured.
- `RetrievalPlan.requiredEntities` is enforced as disjunctive (any-of) and has no production populator yet; the any-of-vs-all-of decision is deliberately deferred (AGENTS.md §14).

(`taxonomy-reevaluation.ts` is no longer a scaffold — it runs real k-means clustering + LLM cluster-naming + writes `taxonomy_proposals`.)
