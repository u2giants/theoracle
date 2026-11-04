# The Oracle

The Oracle is the Company Map for POP Creations / Spruce Line: it reads company sources and meeting transcripts into a map of how the business works, answers questions from it, and interviews employees to fill gaps. Current plan: `plan_oracle_company_map.md` (read STATUS first).

Start here:

- `AGENTS.md` — primary developer and AI-session operating guide
- `HANDOFF.md` — active unfinished work, when present
- `plan_repo_reliability_and_release_gaps.md` — known reliability and release problems
- `plan_deferred_product_and_infrastructure_gaps.md` — known product and infrastructure gaps
- `docs/architecture.md` — current system design and data flow
- `docs/development.md` — local setup and verification workflow
- `docs/configuration.md` — env vars and runtime config
- `docs/deployment.md` — release/deploy process
- `DECISIONS.md` — architectural decisions and constraints
- `oracle_master_spec.md` — product contract

## Repo map

- `apps/web/` — Next.js 16 web app: login, `/admin/employees`, Company Map pages (`/map/*`), `/api/brain` proxy, Teams bot (`/api/teams/bot/*`), Recall live Teams endpoints (`/api/teams/live/*`)
- `apps/brain/` — Python FastAPI Company Map service (Coolify service `oracle-brain`)
- `packages/db/` — Drizzle schema, migrations, seed, DB client
- `packages/auth/` — auth linking helpers
- `packages/shared/` — shared types/constants

Oracle 2 and the old workers were removed in #398 (2026-11-04).

## Current runtime shape

- Web app: Vercel via `vercel.json`
- Brain service: Coolify, image `ghcr.io/u2giants/theoracle-brain`
- Database/Auth/Storage: Supabase Cloud

## Fast start

```bash
pnpm install
pnpm typecheck
pnpm --filter @oracle/web build
pnpm dev
```

For a real local setup you also need `.env.local`, Supabase access. Use `docs/development.md` and `docs/configuration.md` for the exact steps.

## Notes

- `HANDOFF.md` should exist only when work is unfinished. If it is missing, there is no active handoff file.
- `AGENTS.md` is the canonical guide for future sessions. Keep it current when behavior or operations change.
