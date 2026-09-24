<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 13. Deployment

Current deployment path:

- GitHub repo: `u2giants/theoracle`
- CI workflows: `.github/workflows/pr-check.yml` and `.github/workflows/task-gates.yml`
- Web deploy target: Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`
- Worker deploy target: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`
- Database/auth/storage target: Supabase project configured through env

How deployment works today:

1. Merge or push to `main`.
2. GitHub Actions runs `pr-check.yml`: installs dependencies, runs `verify:vercel-contract`, builds `@oracle/web`, runs retrieval parity, entity-aware retrieval, network-free Chinese retrieval, China translation review, Vertex file-cache, MCP, Vertex inline-image, auxiliary defaults, R0 reader, R1 cross-shape, taxonomy, and isolated fresh-database guards, then runs `pnpm db:check-drift` against production (requires `PROD_DIRECT_URL`; skips gracefully if absent). The credentialed `verify:chinese-retrieval-live` command is a separate release gate and never runs in CI.
3. Vercel auto-deploys the web app from GitHub using `vercel.json`.
4. Trigger.dev workers are deployed manually with `pnpm --filter @oracle/workers run deploy` (the `run` keyword is required — `pnpm` reserves the bare `deploy` form for its own subcommand).
5. Database migrations are applied manually with `pnpm db:migrate` before shipping code that depends on them. Hand-written `migrations/sql/*.sql` files MAY be applied via Supabase MCP `apply_migration`; generated `0NNN_*.sql` files MUST go through `pnpm db:migrate` (otherwise the journal drifts — see incident 2026-05-28).

Rollback:

- Web: promote a previous Vercel deployment.
- Workers: redeploy from a previous commit or roll back in Trigger.dev.
- DB: ship a compensating SQL migration; there is no automatic rollback layer.

Runtime env vars live in:

- Vercel project environment settings
- Trigger.dev project secrets/env
- local `.env.local`

SSH:

- SSH is not part of the normal deployment path.
- No VPS/container SSH workflow exists in this repo.

### Release & CI/CD policy (the rules that actually apply here)

This repo is a **managed-platform** deployment — Vercel (web) + Trigger.dev (workers) + Supabase (DB/auth/storage). There are **no containers, no Dockerfiles, no container registry, no Coolify, no production VPS, and no SSH deploy**. Generic container/registry/Coolify/SSH CI-CD rules are therefore **Not Applicable** unless this repo ever adopts a self-hosted containerized model. The rules that DO apply:

- **Single-branch model: work on `main` only.** Do **not** create feature, staging, or release branches, and do not open PRs as a routine workflow — this repo has no promotion model. Commit straight to `main`. (Push to `main` only when Albert says push — see CLAUDE.md.)
- **One release path, repo-driven:** push to `main` → Vercel builds/deploys the web app from `vercel.json`; workers ship via `pnpm --filter @oracle/workers run deploy`; DB via `pnpm db:migrate`. No alternate routine deploy method.
- **CI verifies, never deploys.** `pr-check.yml` only builds + runs the static verify guards + checks migration drift. It must not deploy, SSH, mutate production, or publish artifacts.
- **The deploy gate is native to Vercel's build.** `vercel.json` uses the short `pnpm run build:vercel` command because Vercel caps `buildCommand` at 256 characters. That root script runs these ten network-free guards before `@oracle/web build`: `verify:retrieval-filter-parity`, `verify:chinese-retrieval`, `verify:vertex-file-cache`, `verify:chat-attachment-safety`, `verify:claim-translation-review`, `verify:eval-results-dashboard`, `verify:provider-capability-parity`, `verify:model-coverage-conversion`, `verify:lull-topical`, and `verify:mcp`. `verify:vercel-contract` protects the length and exact delegation contract in CI. The credentialed `verify:chinese-retrieval-live` and `verify:attachment-fallback-live` commands are separate and never run in Vercel.
- **Repo is authoritative; the platform owns runtime.** Runtime env vars / secrets / domains live in Vercel / Trigger.dev / Supabase — never baked into CI shell commands, images, or committed `.env*` (except `.env.example`).
- **Schema changes only through the approved migration path** (`pnpm db:migrate` for generated `0NNN_*.sql`; Supabase MCP `apply_migration` for hand-written `sql/*.sql`). Never ad-hoc production schema edits as the normal path.
- **Traceability:** every production change is auditable from repo commit history + Vercel / Trigger.dev / Supabase deployment history.
- **Drift check is advisory.** The Drizzle migration-drift check needs prod DB creds and runs only in `pr-check.yml`, not in the Vercel build (the build has no prod DB access, by design). Migrations are applied manually via `pnpm db:migrate` anyway, so drift is a bookkeeping signal, not a runtime-breakage gate. Everything else (build + verify guards) is hard-gated in the Vercel build per the bullet above.

