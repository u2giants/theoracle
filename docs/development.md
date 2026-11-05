# Development

This file covers local setup and the routine commands that reflect the current repo.

## Prerequisites

- Node.js 20+; current CI uses Node 24
- `pnpm` 9.x
- Git access to `u2giants/theoracle`
- A local `.env.local` at the repo root
- Supabase access for the target project
- Python 3.12 and `uv` if you work on `apps/brain`

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
pnpm typecheck
pnpm lint
pnpm build
pnpm format
```

Workspace-specific commands:

```bash
pnpm --filter @oracle/web dev
pnpm --filter @oracle/web build
pnpm --filter @oracle/db generate
pnpm --filter @oracle/db migrate
```

## Verification gates

Run these before pushing changes that affect runtime code:

```bash
pnpm typecheck
pnpm --filter @oracle/web build
```

`pnpm verify:vercel-contract` checks that `vercel.json` delegates to `build:vercel`.
For the brain service, run its tests from `apps/brain` (`uv run pytest`); CI runs them in `brain-ci.yml`.

### Lint

`pnpm lint` works again as of 2026-06-04. `apps/web` was migrated from `next lint` (removed in Next 16) to the ESLint 9 flat config in `apps/web/eslint.config.mjs`, which imports `eslint-config-next/core-web-vitals` directly (NOT via `FlatCompat` — that hits a circular-structure bug with eslint-config-next v16). Running it currently reports ~10 pre-existing violations (unescaped entities, `react-hooks/set-state-in-effect`, stale `eslint-disable` directives) that the previously-broken script had been masking — see AGENTS.md §14. Lint is NOT part of the Vercel build gate (`vercel.json` runs the verify guards + `build`, not lint).

## Working on database changes

1. Edit `packages/db/src/schema.ts`.
2. Run `pnpm db:generate` if the schema shape changed.
3. Add a hand-written SQL file under `packages/db/migrations/sql/` if the change needs constraints, RLS, views, or data migration logic.
4. Run `pnpm db:migrate`. This is the ONLY path that should apply generated `0NNN_*.sql` files — do not use Supabase MCP `apply_migration`, the dashboard SQL editor, or `drizzle-kit push` for those, or the journal drifts (see AGENTS.md incident 2026-05-28).
5. Update docs if the data model or operations changed.

Useful at any time: `pnpm db:check-drift` compares on-disk migration hashes against `drizzle.__drizzle_migrations` in the live DB and reports any mismatch. CI runs the same check on every push.

Do not edit previously applied migration files.

Oracle 2, the provider-adapter package, the deterministic engines package and the Trigger.dev workers were removed in #398 (2026-11-04). Company Map model calls live in `apps/brain`.

## Useful inspection scripts

- `scripts/verify-catalog.ts` — inspects provider model-list fetching and OpenRouter enrichment
- `scripts/refresh-catalog.ts` — refreshes `model_capabilities` in the real DB
- `packages/db/src/verify-identities.ts` — GAP-10 identity cleanup gate. Run `pnpm --filter @oracle/db verify:identity-cleanup -- --contract-only` for the network-free fixtures, owned-reader scan, and exact migration checks. The credentialed mode recognizes exactly two valid database states: all three legacy columns present for the aggregate pre-drop audit, or all three absent for a clear post-drop pass. Any partial state fails loudly. Migration 98, its second-run safety, and protected post-drop authentication were released and verified on 2026-07-29.
- `packages/db/src/inspect-auth-users.ts` — Supabase auth user inspection
- `scripts/test-teams-transcript-access.ps1` — PowerShell probe (no deps); checks whether the tenant grants the app transcript access (token → directory read → transcript read). Reads `AZURE_*` from `.env.local`.
- `scripts/diagnose-transcripts.ps1` — tries several `getAllTranscripts` variants for a given organizer (proves scheduled-meeting transcripts work; ad-hoc calls won't appear here — that's why ingestion uses a subscription).
- `scripts/create-adhoc-subscription.ps1` — one-off creation of the `adhocCalls/getAllTranscripts` subscription (needs the webhook deployed first + the cert in the temp dir). The production path is the `teams-subscription-manager` worker, not this script.
