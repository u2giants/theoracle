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
# OracleAIClient smoke (adapter dispatch, mock providers, fallback)
pnpm --filter @oracle/ai verify:r2

# Retrieval filter parity — both SQL branches must stay in lockstep (also runs in CI)
pnpm --filter @oracle/ai verify:retrieval-filter-parity

# Vertex file-cache multi-turn guard — cached prefix must not collapse conversation history (also runs in CI)
pnpm --filter @oracle/ai verify:vertex-file-cache

# Deterministic extraction/validation/promotion logic
pnpm --filter @oracle/engines verify:r5
pnpm --filter @oracle/engines verify:r5.5
pnpm --filter @oracle/engines verify:r6
pnpm --filter @oracle/engines verify:r7

# Synthesis diff-validator
pnpm --filter @oracle/engines verify:r9

# Lull/interjection decision logic
pnpm --filter @oracle/engines verify:r11.1
```

The two guards also run inside Vercel's production build command (`vercel.json` `buildCommand`), so a commit that breaks them will fail the Vercel deploy and leave the previous production deployment live.

If you need the mock extraction eval:

```bash
pnpm --filter @oracle/ai eval:extraction
```

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

- `claim-extraction.ts` — sync extraction (runs when `extraction_dispatch_mode = 'sync'`)
- `claim-extraction-batch-submit.ts` — batch mode: gathers pending messages and submits to provider Batch API (runs when `extraction_dispatch_mode = 'batch'`)
- `claim-extraction-batch-drain.ts` — batch mode: polls `provider_batch_jobs`, runs validation + promotion on completed batches (always scheduled; handles in-flight batches even if mode flips back to sync)
- `document-ingestion.ts`
- `brain-synthesis.ts`
- `lull-interjection.ts`
- `contradiction-watcher.ts`
- `taxonomy-reevaluation.ts`
- `taxonomy-reclassification.ts`
- `teams-subscription-manager.ts` — keeps the Teams ad-hoc transcript Graph subscription alive (renew cron `*/30` + webhook-lifecycle repair task). No-ops when the `TEAMS_*`/`AZURE_*` env isn't set.
- `teams-transcript-ingestion.ts` — webhook-triggered; fetches a call's WebVTT and writes each speaker turn as a `messages` row (extraction_status=pending) in a per-call channel, then the existing `claim-extraction` cron takes over. See `docs/architecture.md` § "Teams transcript ingestion".

Routine expectations:

- workers insert `job_runs`
- model calls insert `model_runs` and `model_run_usage_details`
- prompt plans insert `oracle_context_packs`

## Useful inspection scripts

- `scripts/verify-catalog.ts` — inspects provider model-list fetching and OpenRouter enrichment
- `scripts/refresh-catalog.ts` — refreshes `model_capabilities` in the real DB
- `packages/db/src/verify-identities.ts` — employee/identity inspection
- `packages/db/src/inspect-auth-users.ts` — Supabase auth user inspection
- `scripts/test-teams-transcript-access.ps1` — PowerShell probe (no deps); checks whether the tenant grants the app transcript access (token → directory read → transcript read). Reads `AZURE_*` from `.env.local`.
- `scripts/diagnose-transcripts.ps1` — tries several `getAllTranscripts` variants for a given organizer (proves scheduled-meeting transcripts work; ad-hoc calls won't appear here — that's why ingestion uses a subscription).
- `scripts/create-adhoc-subscription.ps1` — one-off creation of the `adhocCalls/getAllTranscripts` subscription (needs the webhook deployed first + the cert in the temp dir). The production path is the `teams-subscription-manager` worker, not this script.

## Current incomplete areas you may encounter

- `apps/web/app/admin/taxonomy/_actions.ts` queues some proposal types for later reclassification instead of applying them inline.
- Oversized Vertex file-backed caching only activates when `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` is configured.
- `RetrievalPlan.requiredEntities` is disjunctive (any-of — settled) but has no production populator yet; pinning specific entities needs a recognition+resolution step that isn't built (deferred feature, AGENTS.md §14).

(`taxonomy-reevaluation.ts` is no longer a scaffold — it runs real k-means clustering + LLM cluster-naming + writes `taxonomy_proposals`.)
