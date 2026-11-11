---
summary: "Rules for hand-written SQL migrations: run after Drizzle output, lexical order, must be idempotent, what belongs here and numbering."
kind: ops
status: current
read-when: adding or editing a hand-written SQL migration
---

# Hand-written SQL migrations

These files run **after** Drizzle's auto-generated migrations on every `pnpm db:migrate` invocation. They are applied in **lex order by filename**, and they must be **idempotent** — every invocation of `pnpm db:migrate` runs every file in this directory (with two exceptions noted below). The runner is `packages/db/src/migrate.ts`.

## Why hand-written SQL at all

Drizzle generates table DDL only. It does not model:

- CHECK constraints
- Postgres functions and procedures
- RLS policies
- Views
- pg extensions (pgvector, pgcrypto, uuid-ossp)
- Data migrations (one-shot UPDATE / INSERT against existing rows)

Everything in those categories lives here.

## Scope: the live schema only

Oracle 2 is gone (issue #398). Its tables were dropped from production and its
raw SQL — constraints, seeds, views, settings rows, taxonomy/extraction/macro
DDL — was removed from this directory along with it (issue #431). What remains
covers exactly the tables the live system uses:

`public.employees`, `public.employee_identities`, `public.employee_departments`,
`public.departments`, `public.employee_directory_roles`.

The Company Map lives in the `cmap` schema and is owned by `apps/brain`; nothing
here touches it.

## Numeric prefix convention

| Prefix range | Purpose                                                                                                                 |
| ------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `01_*`       | Extensions. Runs first, before Drizzle's table DDL. The runner pulls this out and runs it explicitly in step 1.         |
| `10_*`       | CHECK constraints and other table-level guards that depend on tables existing.                                          |
| `15_*`       | Auxiliary tables that downstream RLS helpers need to join through (e.g. `employee_identities`).                         |
| `20_*`       | RLS helper functions (`current_employee_id`, `current_employee_is_admin`). Must come AFTER all tables they query exist. |
| `21_*`       | RLS policies. Must come AFTER the helpers.                                                                              |
| `30_*`       | Admin / convenience views. May reference helpers.                                                                       |
| `40_*`       | One-shot data migrations and merges that transform existing rows. Idempotent.                                           |
| `41_*`       | More one-shot data migrations applied after the 40 group — typically narrow, project-specific reconciliations.          |
| `99_*`       | Opt-in / expensive. Currently just `99_vector_indexes.sql`. The runner skips this unless `ORACLE_RUN_VECTOR_INDEXES=1`. |

When adding a new file, pick a prefix that places it in the right phase. Within a phase, use any free number — order within a phase doesn't usually matter, but try not to skip too many numbers.

## Idempotency rules

Files run on every boot — they must not error or duplicate work:

- `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`.
- `DROP POLICY IF EXISTS …` followed by `CREATE POLICY …` for RLS policies (Postgres has no CREATE POLICY IF NOT EXISTS).
- Data migrations gated by existence checks: `IF EXISTS (SELECT 1 FROM ...)`, `ON CONFLICT DO NOTHING`, `WHERE col IS NOT NULL`.
- Wrap multi-statement data migrations in `BEGIN; ... COMMIT;` so partial application doesn't leave the DB in a half-state.

If a file is genuinely one-shot and can't be made idempotent (rare), the convention is to short-circuit it with an `IF NOT EXISTS` check on the post-condition.

## Current files

| File                                                | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `01_extensions.sql`                                 | `CREATE EXTENSION IF NOT EXISTS` for pgvector, pgcrypto, uuid-ossp.                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `15_employee_identities.sql`                        | DDL for the `employee_identities` table (multi-identity support — DECISIONS.md D2).                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `15_employee_directory_roles.sql`                   | DDL for `employee_directory_roles` — DesignFlow role names per employee, written only by the brain `directory_sync` job (DECISIONS.md D-dflow-directory-source-of-truth).                                                                                                                                                                                                                                                                                                                                          |
| `20_rls_helpers.sql`                                | `current_employee_id()`, `current_employee_is_admin()` — both join through `employee_identities`.                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `21_rls_policies.sql`                               | RLS policies for `employees` and `employee_identities`.                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `21_employee_directory_roles_rls.sql`               | RLS for `employee_directory_roles` — admins manage, signed-in employees read.                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `40_employee_identities_data.sql`                   | One-shot, idempotent: copy any legacy `employees.auth_*` values into `employee_identities`, run the Albert merge, NULL the deprecated columns. The runner skips it once the legacy columns are gone.                                                                                                                                                                                                                                                                                                              |
| `41_albert_post_merge_fix.sql`                      | Idempotent reconciliation for Albert's specific case (Google + M365 identities folded onto one employee row). Uses real auth_user_ids.                                                                                                                                                                                                                                                                                                                                                                            |
| `49_security_hardening.sql`                         | Revokes EXECUTE on the SECURITY DEFINER helpers from anon/authenticated and re-grants to service_role, so they are never reachable via PostgREST RPC. Also locks down the optional `rls_auto_enable` helper when a project happens to have one.                                                                                                                                                                                                                                                                     |
| `56_employees_departments_array.sql`                | Data migration: copy legacy `employees.department` (varchar) into `employees.departments` (text[]). Re-runs safely — only fills still-empty rows.                                                                                                                                                                                                                                                                                                                                                                 |
| `57_employees_departments_array_catchup.sql`        | Catch-up for the same column on databases that never got the generated DDL: drops NOT NULL on `department`, adds `departments text[]` if missing, backfills.                                                                                                                                                                                                                                                                                                                                                      |
| `61_departments.sql`                                | Org-unit departments: `department` enum, `departments` metadata table, `employee_departments` join table, one seed row per enum value, best-effort backfill from `employees.departments`, and an `updated_at` touch trigger.                                                                                                                                                                                                                                                                                       |
| `98_drop_deprecated_employee_identity_columns.sql`  | GAP-10 rerun-safe final removal of the three legacy identity columns after the live zero-data/dependency audit and rollback authentication proof passed. Explicitly drops the local unique constraint/index, then uses `DROP COLUMN IF EXISTS`. Applied in production release `30eed14`; a second full migration run and protected post-drop authentication passed. |
| `99_vector_indexes.sql`                             | HNSW indexes on `claims.embedding` and `document_chunks.embedding`. **Oracle 2 leftovers, kept only because the GAP-10 identity-cleanup contract asserts this file sorts after `98`.** It is opt-in (`ORACLE_RUN_VECTOR_INDEXES=1`) and its target tables no longer exist, so it is never applied — do not turn the flag on. |

## Anti-patterns

- **Don't edit a prior migration file.** Add a new file with the next free prefix. Old files have already run against production. Exception: a whitelist CHECK that is dropped and re-added by a replayed file must be widened **in that same file** — a later file cannot widen it, because the earlier narrow `ADD CONSTRAINT` would fail on every rerun once a new value exists.
- **Don't depend on a specific machine's data inside a 40+ file** unless the file is guarded by an existence check on that data (see `41_albert_post_merge_fix.sql`, which only fires if Albert's specific Supabase auth ids exist).
- **Don't `DROP TABLE` here.** If a table must be removed, add a defensive `DROP TABLE IF EXISTS` and update `packages/db/src/schema.ts` in the same commit, and confirm no application code still references it.
- **Don't reference a table outside the live schema.** A raw file that names a dropped Oracle 2 table fails the whole run at `Step 3` — that is exactly what issue #431 had to repair.
