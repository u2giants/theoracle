# Deployment

How commits get to production. There is no Docker, no VPS, no Coolify, no SSH — everything is fully managed cloud per spec Part 2.5.

## Topology

| Component | Hosted on | Triggered by |
|---|---|---|
| `apps/web` (Next.js 16) | Vercel | Push to GitHub |
| `apps/workers` (Trigger.dev tasks) | Trigger.dev Cloud | Manual `pnpm --filter @oracle/workers deploy` (CI later) |
| Database, Auth, Storage, Realtime | Supabase Cloud | Manual `pnpm db:migrate` |
| Magic-link email delivery | Brevo SMTP | Per request, via Supabase Auth |
| LLM inference | OpenRouter (chat/extract/synthesis) + OpenAI (embeddings) | At runtime, per request |

## Web app — Vercel

**Project ID:** `prj_rP6Jlima7iK1paffEPhLqxlswGsC`

### `vercel.json` — required for this monorepo

The repo root holds a small `vercel.json` that **must not be deleted**:

```json
{
  "framework": "nextjs",
  "buildCommand": "pnpm --filter @oracle/web build",
  "installCommand": "pnpm install --frozen-lockfile=false",
  "outputDirectory": "apps/web/.next"
}
```

Why it exists: Vercel's auto-detection treats this repo as a single-app layout and looks for `.next` at the repo root. The Next app actually lives at `apps/web/`, so Turbo writes `.next` to `apps/web/.next`. Without `outputDirectory` pointing there, **every production deploy errors at the finalize step** with `The Next.js output directory ".next" was not found at "/vercel/path0/.next"` even though the build itself succeeds. The `buildCommand` makes Turbo build the right workspace; the `installCommand` survives lockfile churn from local dev.

An alternative is to set the **Root Directory** to `apps/web` in the Vercel dashboard, but committing `vercel.json` makes the contract live in the repo and survive project recreation.

### Production deploys

1. Push to `main` on `github.com/u2giants/theoracle`.
2. Vercel detects the push (Git integration) and starts a Production build using the `vercel.json` contract above.
3. Effective build flow: `pnpm install` at the repo root, then `pnpm --filter @oracle/web build` (which delegates to Turbo, which runs `next build` in `apps/web`).
4. Output: Next.js 16 App Router on Vercel Fluid Compute, Node.js 24 runtime, picked up from `apps/web/.next`.
5. Production URL: whatever's configured in Vercel → Settings → Domains.

### Pre-push checklist — production tsc is stricter than dev

`next dev` (Turbopack) does NOT run TypeScript. `next build` does, with full strict checking. A type error that the dev server happily ignores will fail the Vercel production build. **Before pushing changes that could affect types**, run:

```bash
pnpm --filter @oracle/web build
```

If that passes locally, Vercel will compile cleanly. The two type errors that caused production deploys to fail for ~an hour on 2026-05-20 (`OracleDb` vs `Db` in retrieval helpers, implicit-any on `@supabase/ssr` cookie adapter) would both have been caught by this single command.

`pnpm typecheck` is not a sufficient substitute because it skips some Next-specific type generation. Always use `pnpm --filter @oracle/web build` as the pre-push gate.

### Preview deploys

Every PR / non-`main` branch push gets its own preview URL automatically. Preview environment env vars apply (Vercel → Settings → Environment Variables → Preview scope).

### Runtime environment variables

Managed in Vercel → Settings → Environment Variables. Scoped per environment (Production / Preview / Development). See `docs/configuration.md` for the full list and the Sensitive-vs-Encrypted caveat.

### Rollback

Vercel dashboard → Deployments → find the prior good deployment → **Promote to Production**. That's the whole story. No CLI step needed.

For an instant disable in a real emergency, the Vercel dashboard supports pausing deployments, and you can revert the GitHub commit, which will re-trigger a deploy.

### Domain configuration

Currently using the default `*.vercel.app` URL. Custom domain config is a TODO in `AGENTS.md` pending work.

### Next.js 16 config notes

`apps/web/next.config.ts` uses `serverExternalPackages` (Next 16) rather than the deprecated `experimental.serverComponentsExternalPackages`. The `eslint` config block is gone — Next 16 uses ESLint flat config and lint runs through `pnpm lint` in CI, not as a build step.

## Workers — Trigger.dev

**Project ref:** `proj_wgpzsvhmsopqhvwqaycn` (set as `TRIGGER_PROJECT_REF` in Vercel env + `.env.local`).
**Current deployed version:** `20260521.1`. 7 task exports across 4 files in `apps/workers/src/trigger/`:

| File | Exports | Trigger |
|---|---|---|
| `claim-extraction.ts` | `claimExtractionTask` | scheduled (cron) |
| `document-ingestion.ts` | `documentIngestionTask`, `documentIngestionSweepTask` | one-off + scheduled |
| `contradiction-watcher.ts` | `contradictionWatcherTask`, `contradictionWatcherSweepTask` | one-off + scheduled |
| `brain-synthesis.ts` | `brainSynthesisTask`, `brainSynthesisScheduledTask` | one-off + scheduled |

**Dashboard:** https://cloud.trigger.dev/projects/v3/proj_wgpzsvhmsopqhvwqaycn

### Deploying tasks

```bash
pnpm --filter @oracle/workers deploy   # invokes `npx trigger.dev@latest deploy`
```

Trigger.dev v3 packages and uploads the task definitions. They run on Trigger.dev's cloud infrastructure — no servers to manage.

There is no CI integration yet — deploy manually after task code changes. `workers-deploy.yml` is planned (see GitHub Actions table below).

### Rollback

Trigger.dev dashboard → task → version history → roll back. Or redeploy from a prior commit.

### Runtime env vars

Set in the Trigger.dev project dashboard (not Vercel). Current workers need: `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY` (workers use service-role to bypass RLS), `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `TRIGGER_SECRET_KEY`.

When R7 (document ingestion refactor) lands, the document-ingestion worker also needs the Vertex / Gemini direct env vars (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_CLIENT_EMAIL`, `GOOGLE_PRIVATE_KEY`). See `docs/configuration.md` → "Future env vars". Do not add these to the Trigger.dev project until R7 actually starts; placeholder values would mask a misconfiguration.

## Database — Supabase migrations

```bash
pnpm db:migrate
```

This runs the runner in `packages/db/src/migrate.ts`, which applies, in order:

1. `packages/db/migrations/sql/01_extensions.sql` (pgvector, pgcrypto, uuid-ossp).
2. Drizzle-generated migrations under `packages/db/migrations/0NNN_*.sql` (created by `pnpm db:generate` whenever `schema.ts` changes).
3. All other files in `packages/db/migrations/sql/` in lex order — extensions are excluded (already applied in step 1) and the vector indexes file (`99_vector_indexes.sql`) is opt-in via `ORACLE_RUN_VECTOR_INDEXES=1`.
4. Seed (`packages/db/src/seed.ts`) — settings table + admin employee + test employee. Idempotent.

The runner is idempotent end-to-end. Safe to re-run.

For the ordering convention inside `migrations/sql/`, see `packages/db/migrations/sql/README.md`.

**There is no automated migration step in CI yet.** When migrations are needed, run `pnpm db:migrate` locally **before** pushing the corresponding app code to `main`. Otherwise the deployed app may query columns that don't exist.

### Production migration order

1. Make schema changes in `packages/db/src/schema.ts` and any hand-written SQL files.
2. `pnpm db:generate` to create the Drizzle migration.
3. Commit (do not push yet).
4. `pnpm db:migrate` against the production database — verify it succeeds.
5. Push to `main` → Vercel deploys the new app code.

For dangerous migrations (drops, type changes on populated columns) — pause Vercel deploys, run the migration manually, validate, then resume.

### Rollback

There's no automatic rollback. Schema changes are written defensively (additive, not destructive) so rollback is rare. When required:

1. Hand-write a reverse SQL file in `packages/db/migrations/sql/`.
2. Apply it via `psql $DIRECT_URL -f <file>`.
3. Revert the schema.ts change in code.

## Supabase Auth — provider + SMTP configuration

Provider config (Google, Microsoft 365 / Azure, future Authentik) and SMTP config (Brevo) live in the **Supabase Dashboard**, not in this repo. The repo's only OAuth-flow responsibility is the login form's scope list and the callback route. See `docs/configuration.md` → "Supabase Auth providers" + "Supabase Auth SMTP — Brevo" for the exact values.

When rotating the Brevo SMTP key, update **Supabase Auth → SMTP Settings**; nothing in this repo needs to change.

## Secrets management

| Secret | Where it lives | Rotation |
|---|---|---|
| Supabase keys (anon, service role) | Supabase dashboard → Project Settings → API → Reset | Reset in Supabase, then update Vercel + Trigger.dev + `.env.local`. |
| Supabase database password | Supabase → Project Settings → Database → Reset Database Password | Triggers a one-time display. Update `DATABASE_URL` + `DIRECT_URL` in Vercel + Trigger.dev + `.env.local`. |
| OpenRouter key | https://openrouter.ai/keys | Revoke + recreate; update Vercel + Trigger.dev + `.env.local`. |
| OpenAI key | https://platform.openai.com/api-keys | Same. |
| Trigger.dev secret key | Trigger.dev dashboard | Same. |
| Brevo SMTP key | https://app.brevo.com → SMTP & API → SMTP | Revoke + recreate; update **Supabase Auth → SMTP Settings**. No env var change needed. |
| Vercel token | https://vercel.com/account/tokens | Rotate after every shared session that exposed it. |
| Google OAuth client secret | Google Cloud Console → APIs & Services → Credentials | Recreate; update Supabase → Authentication → Providers → Google. |
| Microsoft Entra client secret | Entra → App registrations → Certificates & secrets | Microsoft only shows the value once; copy on creation. Update Supabase → Authentication → Providers → Azure. |
| GitHub PAT (if used) | https://github.com/settings/tokens | We use `gh` CLI's stored credential; rotate via `gh auth refresh` or recreating the token. |

## GitHub Actions

| Workflow | Status | Trigger | What it does |
|---|---|---|---|
| `.github/workflows/pr-check.yml` | **live** | PRs to `main` + pushes to `main` | `pnpm install && pnpm --filter @oracle/web build` on Node 24 / pnpm 9.5.0. Mirrors what Vercel runs so production-only tsc errors surface before merge. Uses placeholder env vars — App Router pages with `cookies()` are dynamic and don't execute at build, so real secrets aren't needed. |
| `migrate.yml` | planned | manual dispatch | `pnpm db:migrate` against production with required approval. |
| `workers-deploy.yml` | planned | push to `main` touching `apps/workers/**` | `pnpm --filter @oracle/workers deploy`. |

Workflow files live under `.github/workflows/` (owned code per `AGENTS.md` §4).
