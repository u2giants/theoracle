# Widen model_capabilities provider CHECK — exact dispatch for review (revision 2)

Status: awaiting review. Tracking issue: #49 (catalog refresh scope). Nothing
runs before a `VERDICT APPROVE` naming the reviewed commit of this file; the
approval record goes on #49, not into this file.

Owner context (Albert, Claude chat, 2026-09-28): asked for the Muse and StepFun
models to appear in the admin model pool; "Refresh catalog" now fails with ~150
lines of errors. Revision 1 was refused (qwen); revision 2 fixes every finding.

## Evidence (read-only, 2026-09-28)

- Production constraint: `model_capabilities_provider_check CHECK (provider =
  ANY (ARRAY['anthropic','openai','google','deepseek','qwen']))`.
- `refreshModelCatalog` upserts all rows in one statement; PR #48 produces
  `meta_muse` and `stepfun` rows, so the whole refresh fails on the constraint.
- `pnpm db:check-drift` against production: "OK — 12 on-disk migrations and 12
  journal rows match exactly" (no pending generated migration).

## Change (PR #54)

- `packages/db/migrations/sql/56_model_capabilities_more_providers.sql`, which
  already drops and re-adds this CHECK on every `db:migrate`, now allows
  `'anthropic','openai','google','deepseek','qwen','meta_muse','zai','stepfun'`.
  Strictly wider; every existing row still passes; no data change.
- Edited in place on purpose: a new later file cannot widen it, because 56's
  narrow `ADD CONSTRAINT` would then fail on every rerun once a new-provider row
  exists. `packages/db/migrations/sql/README.md` records this exception.
- Guard: `verify:adapter-request-shapes` now asserts 56's list covers every
  `ModelProvider` in `packages/ai/src/model-capabilities/types.ts`.

## Execution (canonical runner only)

1. PR #54 merged; CI green on the merge commit; operator in a clean worktree at
   that commit with no `.env`/`.env.local`.
2. `ai-task-gates start --class shared-db --base origin/main`, then
   `ai-task-gates check --before production`; stop on anything but pass. (The
   repo maps `packages/db/migrations/**` to class `shared-db`, whose rulebooks
   are `canonical-oracle-migration-runner`, `migration-before-dependent-release`,
   `drizzle-journal-drift-proof`.)
3. Target proof: `DIRECT_URL`/`DATABASE_URL` = 1Password item
   `qcuyabwseaptvuzvtjejffi2ou` field `oracle_session_pooler` (Oracle's own
   Supabase project `eqccjfbyrywsqkxxpjvg`, not the shared database), per
   `docs/deployment.md`. Read-only: `select current_database()`, the constraint
   text equals Evidence, and `corepack pnpm --filter @oracle/db check-drift`
   reports OK. Stop otherwise.
4. Apply with the canonical runner: `corepack pnpm --filter @oracle/db migrate`
   (Supabase MCP `apply_migration` is unavailable in this session; the runner is
   the documented path and, with drift OK, only replays the idempotent `sql/`
   files; `99_vector_indexes.sql` stays skipped because
   `ORACLE_RUN_VECTOR_INDEXES` is unset). The CHECK DDL briefly takes an
   `ACCESS EXCLUSIVE` lock on the small `model_capabilities` table; any runner
   error is a stop, not a retry.
5. Verify (read-only): new constraint text lists all eight providers;
   `select provider, count(*) from model_capabilities group by 1` unchanged.
6. Acceptance: ask Albert to click **Refresh catalog**; then the same read-only
   group-by must show `meta_muse` and `stepfun` rows. Record both on #49.

## Rollback

Revert PR #54 (restores the five-provider file), then — only if new-provider
rows exist — export them (`copy (select * from model_capabilities where
provider in ('meta_muse','zai','stepfun')) to stdout csv`), record the count on
#49, run `delete from model_capabilities where provider in
('meta_muse','zai','stepfun')` in one transaction and confirm the deleted count
equals the exported count, then rerun `corepack pnpm --filter @oracle/db migrate`.
Each rollback step is a new production action needing its own review approval.
