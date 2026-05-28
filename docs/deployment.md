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
2. GitHub Actions runs `.github/workflows/pr-check.yml`.
3. Vercel builds using `vercel.json`.
4. Vercel deploys the Next.js app.

`vercel.json` is part of the deploy contract:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": "nextjs",
  "buildCommand": "pnpm --filter @oracle/web build",
  "installCommand": "pnpm install --frozen-lockfile=false",
  "outputDirectory": "apps/web/.next"
}
```

### Workers

Workers are not deployed automatically by CI today.

Current deploy command:

```bash
pnpm --filter @oracle/workers deploy
```

That uses Trigger.dev and the checked-in `apps/workers/trigger.config.ts`.

### Database

Database migrations are also manual today:

```bash
pnpm db:migrate
```

Run migrations before pushing code that depends on them.

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
