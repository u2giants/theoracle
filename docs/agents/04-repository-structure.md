<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 4. Repository structure

This is a `pnpm` + `turbo` TypeScript monorepo.

Code we own:

- `apps/web/` — Next.js 16 App Router app, API routes, `/admin/employees`, Company Map UI
- `packages/auth/` — Supabase auth helpers and employee identity linker
- `packages/db/` — Drizzle schema, client, migrate scripts
- `packages/shared/` — shared types/constants
- `apps/brain/` — Python FastAPI Company Map service (Coolify)
- Oracle 2 and the old workers were removed in #398 (2026-11-04).
- `docs/` — project documentation
- root markdown files — `README.md`, `AGENTS.md`, `CLAUDE.md`, `DECISIONS.md`,
  supporting design/history files, and `china_imp.md`

Generated code:

- `packages/db/migrations/0*.sql` — Drizzle-generated SQL
- `packages/db/migrations/meta/` — Drizzle metadata

Third-party / framework code:

- `node_modules/`
- `apps/web/components/ui/` — shadcn-generated primitives; treat as framework layer

Build artifacts and caches:

- `apps/web/.next/`
- `dist/`
- `.turbo/`
- `.vercel/`
- `.cache/`
- `coverage/`

Docs:

- `docs/architecture.md`
- `docs/development.md`
- `docs/configuration.md`
- `docs/deployment.md`
- `oracle_master_spec.md` — product/spec contract
- `china_imp.md` — design + resolved decisions for the China bilingual claim layer (Phase 1 implemented; the code is the source of truth, this doc captures rationale). Read only for China bilingual / translation / recertification work.
- `plan_repo_reliability_and_release_gaps.md` — canonical plan for known runtime verification,
  stale-script/comment, drift, production-proof, and release-automation gaps.
- `plan_deferred_product_and_infrastructure_gaps.md` — canonical plan for known product,
  optional-infrastructure, and owner-deferred security gaps.

Scripts:

- `packages/db/src/{migrate,verify-identities,inspect-auth-users}.ts`
- `scripts/test-teams-transcript-access.ps1` — no-dep PowerShell probe: does the tenant grant the app Teams transcript access?
- `scripts/diagnose-transcripts.ps1` — tries `getAllTranscripts` variants for an organizer (scheduled meetings only)
- `scripts/create-adhoc-subscription.ps1` — one-off `adhocCalls/getAllTranscripts` subscription creation (webhook must be live first)

Migrations:

- `packages/db/src/schema.ts` — source of truth
- `packages/db/migrations/0*.sql` — generated DDL
- `packages/db/migrations/sql/*.sql` — hand-written constraints, extensions, RLS helpers and policies, data migrations

Deployment files:

- `vercel.json` — repo-level Vercel build contract
- `.github/workflows/pr-check.yml` — production build and repository verification gate
- `.github/workflows/task-gates.yml` — task-classification policy gate; never deploys

