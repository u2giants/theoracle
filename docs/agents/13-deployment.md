---
summary: "AGENTS.md section 13: real deploy path (Vercel web, Coolify brain image, Supabase), rollback, and the binding release, branch and migration policy."
kind: living
status: current
read-when: before any commit, push, branch or pull-request decision, deploy or migration
---

<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob b5e39e1305331da62607e6aae51de8c2ffdfe884 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 13. Deployment

Oracle 2 and the old Trigger.dev workers were removed in #398 (2026-11-04); there is no worker deploy any more.

Current deployment path:

- GitHub repo: `u2giants/theoracle`
- CI workflows: `pr-check.yml` (web build + guards + migration drift), `task-gates.yml`, `brain-ci.yml` and `brain-image.yml` (brain service tests and GHCR image), `ai-review.yml` and `review-fixer.yml` (advisory)
- Web deploy target: Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`
- Brain service: Coolify service `oracle-brain`, image `ghcr.io/u2giants/theoracle-brain`
- Database/auth/storage target: Supabase project configured through env

How deployment works today:

1. Merge to `main` through a pull request.
2. `pr-check.yml` installs dependencies, runs `verify:vercel-contract`, builds `@oracle/web`, runs the remaining DB guards, then runs `pnpm db:check-drift` against production (requires `PROD_DIRECT_URL`; skips gracefully if absent).
3. Vercel auto-deploys the web app from GitHub using `vercel.json` (`pnpm run build:vercel`).
4. The brain image is built and published by `brain-image.yml`; Coolify runs it.
5. The brain applies its own `cmap` schema (`apps/brain/brain/sql/*.sql`, idempotent) at every start-up (`brain/__main__.py`); a failure stops the new container. The web app's database migrations are applied manually with `pnpm db:migrate` before shipping code that depends on them. Hand-written `migrations/sql/*.sql` files MAY be applied via Supabase MCP `apply_migration`; generated `0NNN_*.sql` files MUST go through `pnpm db:migrate` (otherwise the journal drifts — see incident 2026-05-28).

Rollback:

- Web: promote a previous Vercel deployment.
- Brain: redeploy the previous image tag in Coolify.
- DB: ship a compensating SQL migration; there is no automatic rollback layer.

Runtime env vars live in Vercel project settings, the Coolify service environment, and local `.env.local`. SSH is not part of the normal deployment path.

### Release & CI/CD policy

- **`main` is the only long-lived branch.** Every source change uses a short-lived branch and pull request; never push directly to protected `main`.
- **One release path, repo-driven:** merge to `main` → Vercel builds the web app; the brain ships as a GHCR image run by Coolify; DB via `pnpm db:migrate`.
- **Repo is authoritative; the platform owns runtime.** Env vars, secrets and domains live in Vercel / Coolify / Supabase — never in CI shell commands, images, or committed `.env*` (except `.env.example`).
- **Schema changes only through the approved migration path** (`pnpm db:migrate` for generated `0NNN_*.sql`; Supabase MCP `apply_migration` for hand-written `sql/*.sql`).
- **Drift check is advisory** and runs only in `pr-check.yml`.
