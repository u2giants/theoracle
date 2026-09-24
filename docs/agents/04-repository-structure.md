<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 4. Repository structure

This is a `pnpm` + `turbo` TypeScript monorepo.

Code we own:

- `apps/web/` — Next.js 16 App Router app, API routes, admin UI, employee chat UI
- `apps/workers/` — Trigger.dev tasks and worker config
- `packages/ai/` — `OracleAIClient`, retrieval, prompts, provider adapters, model catalog
- `packages/auth/` — Supabase auth helpers and employee identity linker
- `packages/db/` — Drizzle schema, client, migrate/seed scripts
- `packages/oracle-engines/` — deterministic extraction and synthesis logic
- `packages/shared/` — shared types/constants
- `docs/` — project documentation
- root markdown files — `README.md`, `AGENTS.md`, `CLAUDE.md`, `DECISIONS.md`,
  `MACRO_FIRST_IMPLEMENTATION_PLAN.md`, supporting design/history files, and `china_imp.md`

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
- `packages/ai/evals/runs/`

Docs:

- `docs/architecture.md`
- `docs/development.md`
- `docs/configuration.md`
- `docs/deployment.md`
- `docs/wet-test-walkthrough.md`
- `docs/macro-understanding-implementation-plan.md` - macro-first source outlines, meaning-based source groups, budgeted document lens fan-out, cross-claim macro relationships, and coverage audits; the first end-to-end implementation is migrated and deployed
- `docs/oracle/` — deeper AI-retrofit reference material
- `oracle_master_spec.md` — product/spec contract
- `oracle_ai_architecture_prompt caching.md` — historical AI architecture/prompt-cache reference
- `china_imp.md` — design + resolved decisions for the China bilingual claim layer (Phase 1 implemented; the code is the source of truth, this doc captures rationale). Read only for China bilingual / translation / recertification work.
- `MACRO_FIRST_IMPLEMENTATION_PLAN.md` — canonical forward plan for the macro-first redesign;
  supporting macro/shape documents retain rationale, history, and completed gate evidence.
- `plan_repo_reliability_and_release_gaps.md` — canonical plan for known runtime verification,
  stale-script/comment, drift, production-proof, and release-automation gaps.
- `plan_deferred_product_and_infrastructure_gaps.md` — canonical plan for known product,
  optional-infrastructure, and owner-deferred security gaps.
- `plan_typesafe_jev_decision_layer.md` — staged plan for a separate TypeSafe Jev decision
  layer, shadow evaluations, privacy gates, and one-use-case-at-a-time rollout.

Scripts:

- `scripts/verify-catalog.ts` — provider/model catalog inspection
- `scripts/refresh-catalog.ts` — model catalog refresh against the real DB
- `packages/db/src/{migrate,seed,verify-identities,inspect-auth-users}.ts`
- `scripts/test-teams-transcript-access.ps1` — no-dep PowerShell probe: does the tenant grant the app Teams transcript access?
- `scripts/diagnose-transcripts.ps1` — tries `getAllTranscripts` variants for an organizer (scheduled meetings only)
- `scripts/create-adhoc-subscription.ps1` — one-off `adhocCalls/getAllTranscripts` subscription creation (webhook must be live first; the `teams-subscription-manager` worker is the production path)
- `scripts/reevaluate-document.mjs` — guarded single-document re-evaluation: deletes a document's prior claims/chunks/candidates/batches/tags and resets it to `pending_processing` (DRY-RUN by default; `APPLY=1` to act; aborts if any target claim is in the Brain/a contradiction/a gap/multi-source). Run with the prod session-pooler URL: `PROD_URL=<pooler> DOCUMENT_ID=<id> APPLY=1 node scripts/reevaluate-document.mjs`, then trigger `document-ingestion`.

Migrations:

- `packages/db/src/schema.ts` — source of truth
- `packages/db/migrations/0*.sql` — generated DDL
- `packages/db/migrations/sql/*.sql` — hand-written constraints, views, data migrations, seeds

Deployment files:

- `vercel.json` — repo-level Vercel build contract
- `.github/workflows/pr-check.yml` — production build and repository verification gate
- `.github/workflows/task-gates.yml` — task-classification policy gate; never deploys
- `apps/workers/trigger.config.ts` — Trigger.dev runtime config

