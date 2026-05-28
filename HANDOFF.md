# HANDOFF — Drizzle migration-journal drift

Created: 2026-05-28
Created by: Claude Code session that landed `830713c` (runtime-first stabilization fixes).

Delete this file once the issue described below is resolved.

## What was being worked on

This session implemented and deployed the four-phase runtime stabilization plan
(see commit `830713c`):

- Phase 1 — extraction retry safety + dispatch_mode on `model_runs_with_usage`
- Phase 2 — brain synthesis reads `claim_top_domains` instead of `claim_domains`
- Phase 3 — retrieval entity filter tuple-match + fallback parity
- Phase 4 — docs reconciliation for items overtaken by landed code

All four phases are fully implemented and shipped:

- `git push origin main` — done. Vercel auto-deploys the web app from `main`.
- Supabase view update — applied via Supabase MCP `apply_migration`
  (`add_dispatch_mode_to_model_runs_with_usage_appended`). The view now
  includes `dispatch_mode` as the last column.
- Trigger.dev worker deploy — done, version `20260528.1`, 13 tasks.

There is no unfinished feature work. **The one open item is operational, not
code:**

## The unfinished item: Drizzle journal is out of sync with production

### Symptom

`pnpm db:migrate` fails at Step 2 (Drizzle generated migrations) with:

```
PostgresError: relation "model_capabilities" already exists
code: 42P07
```

### What this means in plain terms

We use two layers of database changes:

1. **Drizzle-generated migrations** under `packages/db/migrations/0*.sql` —
   these create tables, columns, indexes. Drizzle tracks which ones already
   ran by writing rows into an internal `__drizzle_migrations` table on the
   production database.
2. **Hand-written SQL** under `packages/db/migrations/sql/*.sql` — views,
   constraints, RLS policies. These are designed to be idempotent and run
   on every boot.

The Drizzle journal (`__drizzle_migrations` table in prod) does NOT show
that the migration which created `model_capabilities` has run, even though
the table demonstrably exists. So when the runner replays the migration
list, it tries to `CREATE TABLE model_capabilities` and Postgres refuses
because the table is already there.

At least one — possibly several — Drizzle migrations have run in production
without their hash being inserted into `__drizzle_migrations`. This drift
predates this session; the session only surfaced it.

### Why this is blocking

Until the journal is reconciled:

- `pnpm db:migrate` cannot be used to ship future schema changes.
- Hand-written SQL files in `packages/db/migrations/sql/` cannot be reapplied
  through the official runner — Step 2 fails before Step 3 reaches them.
- Any change touching `packages/db/src/schema.ts` that requires a Drizzle
  migration is effectively un-shippable through normal flow until this is
  fixed.

### Workaround used in this session

For the `model_runs_with_usage` view change in this commit, I applied the
SQL directly via the Supabase MCP `apply_migration` tool. That worked, but it
is not a general substitute — it skips the Drizzle layer entirely. Anything
that requires a generated migration (new column, new table, dropped column)
still needs the journal reconciled first.

### Exact next action

1. Connect to the production database (Supabase MCP, the Supabase SQL editor,
   or `psql` with `DIRECT_URL`).
2. Inspect the current journal state:
   ```sql
   SELECT hash, created_at FROM __drizzle_migrations ORDER BY created_at;
   ```
3. Compare against `packages/db/migrations/meta/_journal.json` — list every
   migration tag that file declares.
4. For every on-disk migration whose tables/columns ALREADY exist in
   production but whose hash is NOT in `__drizzle_migrations`, insert its
   hash so the runner treats it as already applied. The hash format Drizzle
   uses is `sha256(migration_sql)`; the simplest way to get the right hash
   is to read it from `packages/db/migrations/meta/_journal.json` (it stores
   the hash there) OR let drizzle compute it by examining the migrator
   source.
5. Re-run `pnpm db:migrate` and confirm it now reaches Step 3.

### Risks / unknowns

- I did not enumerate the exact set of drifted migrations during this
  session — only confirmed `model_capabilities` is one of them. There may
  be others; treat the reconciliation as "find all" not "fix one".
- Inserting hashes into `__drizzle_migrations` is a one-way write. Do it on
  a maintenance window or staging-mirror, not under user traffic.
- Never DROP / TRUNCATE `__drizzle_migrations`; that would tell the runner
  every migration is unapplied and replays them all from scratch against a
  populated production DB. That is the failure mode this drift caused in the
  first place.

### Where to look in the code

- Runner: `packages/db/src/migrate.ts`
- Drizzle journal source: `packages/db/migrations/meta/_journal.json`
- Generated migrations: `packages/db/migrations/0*.sql`
- Hand-written migrations: `packages/db/migrations/sql/*.sql`
- Hand-written README explaining the two layers: `packages/db/migrations/sql/README.md`

### Decisions made this session

- The view column `dispatch_mode` was placed at the END of the SELECT list
  in `31_observability_views.sql`, not in the middle next to other `mr.*`
  columns. Reason: `CREATE OR REPLACE VIEW` rejects column insertions that
  shift positions of existing columns. The end-of-list position is the
  Postgres-friendly choice and keeps every existing ordinal-position-based
  consumer working.
- The Drizzle drift was NOT reconciled in this session. Reason: the
  reconciliation is a production-state operation that needs operator
  judgment about which migrations have actually run, and the workaround
  (Supabase MCP `apply_migration`) was sufficient for this commit's needs.

### Not started

- Reconciling `__drizzle_migrations`. See "Exact next action" above.
