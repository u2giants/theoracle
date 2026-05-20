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

### Production deploys

1. Push to `main` on `github.com/u2giants/theoracle`.
2. Vercel detects the push (Git integration) and starts a Production build.
3. Build command (auto-detected by Vercel; can be overridden in project settings): `pnpm install && pnpm --filter @oracle/web build`.
4. Output: Next.js 16 App Router on Vercel Fluid Compute, Node.js 24 runtime.
5. Production URL: whatever's configured in Vercel → Settings → Domains.

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

**Project name / id:** set in `apps/workers/trigger.config.ts` and through `TRIGGER_SECRET_KEY` in the env.

### Deploying tasks

```bash
pnpm --filter @oracle/workers deploy   # invokes `npx trigger.dev@latest deploy`
```

Trigger.dev v3 packages and uploads the task definitions. They run on Trigger.dev's infrastructure.

There is no CI integration yet — deploy manually after task code changes. Adding this to GitHub Actions is in the pending work list.

### Rollback

Trigger.dev dashboard → task → version history → roll back. Or redeploy from a prior commit.

### Runtime env vars

Set in the Trigger.dev project dashboard. Mirror the production set: `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY` (workers bypass RLS), `OPENROUTER_API_KEY`, `OPENAI_API_KEY`.

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

Currently none. Planned workflows (in pending work):

1. `pr-check.yml` — on PR: `pnpm install && pnpm typecheck && pnpm build`.
2. `migrate.yml` — manual dispatch: `pnpm db:migrate` against production with required approval.
3. `workers-deploy.yml` — on `main` push that changes `apps/workers/**`: `pnpm --filter @oracle/workers deploy`.

When added they live under `.github/workflows/` (which is owned code per `AGENTS.md` §4).
