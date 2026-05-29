# Deployment

This file describes the current deploy and release path that exists in the repo today.

## Runtime targets

| Target | What runs there | Source of truth |
|---|---|---|
| Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `apps/web` | `vercel.json`, GitHub integration |
| Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn` | `apps/workers` | `apps/workers/trigger.config.ts` |
| Supabase project from env | Postgres, Auth, Storage, Realtime | `.env.local` / runtime env |

## Current release flow

### Web app

1. Push to `main`.
2. GitHub Actions runs `.github/workflows/pr-check.yml` (build + verify guards + migration-drift check) for visibility.
3. Vercel builds using `vercel.json`. The `buildCommand` runs the static verify guards **before** the web build, so a guard failure (or a build failure) fails the Vercel build and **blocks the deploy** — the previous production deployment stays live. This is the hard deploy gate; it lives in Vercel's own build, not in a separate CI deploy step.
4. Vercel deploys the Next.js app only if that build succeeds.

`vercel.json` is part of the deploy contract:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "nextjs",
  "buildCommand": "pnpm --filter @oracle/ai verify:retrieval-filter-parity && pnpm --filter @oracle/ai verify:vertex-file-cache && pnpm --filter @oracle/web build",
  "installCommand": "pnpm install --frozen-lockfile=false",
  "outputDirectory": "apps/web/.next"
}
```

The verify guards are DB-free and network-free (the Vertex guard stubs its clients), so they run inside the Vercel build with no extra secrets. The migration-drift check is intentionally NOT in the Vercel build — it needs prod DB credentials and stays in `pr-check.yml` as an advisory check.

### Workers

Workers are not deployed automatically by CI today.

Current deploy command:

```bash
pnpm --filter @oracle/workers run deploy
```

The `run` keyword is required: pnpm reserves the bare `pnpm deploy` form for its own
package-deployment subcommand, so `pnpm --filter @oracle/workers deploy` fails with
`ERR_PNPM_INVALID_DEPLOY_TARGET`. The script under the hood is
`npx trigger.dev@latest deploy` against the checked-in `apps/workers/trigger.config.ts`.

### Database

Database migrations are also manual today:

```bash
pnpm db:migrate
```

Run migrations before pushing code that depends on them.

To keep `pnpm db:migrate` reliable, **never apply a generated
`packages/db/migrations/0NNN_*.sql` outside this runner** (no Supabase MCP
`apply_migration`, no SQL editor, no `drizzle-kit push`). Doing so creates a
journal-vs-reality drift that makes the runner refuse to start. See
`CLAUDE.md` → "Drizzle journal hygiene" for the rule and reconciliation steps
if drift is ever suspected. One such drift was reconciled on 2026-05-28
(migration `0006_magical_revanche` had been applied without a journal row).

## CI workflow that currently exists

Only one workflow is present:

- `.github/workflows/pr-check.yml`

What it does:

- checks out the repo
- installs `pnpm` 9.5.0
- uses Node 24
- runs `pnpm install --frozen-lockfile=false`
- runs `pnpm --filter @oracle/web build`

There is no checked-in workflow for DB migrations or worker deploys.

## Environment management

Runtime env vars currently live in:

- Vercel project environment settings
- Trigger.dev project env/secrets
- local `.env.local`

Use `docs/configuration.md` for the exact variable list.

## Rollback

### Web

- Use the Vercel dashboard to promote a previous deployment.

### Workers

- Redeploy from a previous commit or use Trigger.dev version rollback tools.

### Database

- There is no automatic rollback.
- Ship a compensating migration if a schema/data change must be reversed.

## Operational notes

- SSH is not part of the normal release workflow.
- No Docker, Compose, Coolify, or VPS deployment path exists in this repo.
- If oversized Vertex file-backed caches are needed in production, provision `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` and related access before expecting that path to activate.
- If Vertex Batch Prediction is enabled (D14), provision `GOOGLE_VERTEX_BATCH_GCS_BUCKET` in the same region as the Vertex endpoint and grant the worker service account `roles/storage.objectAdmin`. OpenAI and Anthropic batch routes need no extra infrastructure — the provider hosts the input + results. The two-phase worker (`claim-extraction-batch-submit` + `claim-extraction-batch-drain`) is enabled by flipping `extraction_dispatch_mode` to `'batch'` in `/admin/settings`.
