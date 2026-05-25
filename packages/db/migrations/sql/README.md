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

## Numeric prefix convention

| Prefix range | Purpose |
|---|---|
| `01_*` | Extensions. Runs first, before Drizzle's table DDL. The runner pulls this out and runs it explicitly in step 1. |
| `10_*` | CHECK constraints and other table-level guards that depend on tables existing. |
| `15_*` | Auxiliary tables that downstream RLS helpers need to join through (e.g. `employee_identities`). |
| `20_*` | RLS helper functions (`current_employee_id`, `current_employee_is_admin`). Must come AFTER all tables they query exist. |
| `21_*` | RLS policies. Must come AFTER the helpers. |
| `30_*` | Admin / convenience views. May reference helpers. |
| `40_*` | One-shot data migrations and merges that transform existing rows. Idempotent. |
| `41_*` | More one-shot data migrations applied after the 40 group — typically narrow, project-specific reconciliations. |
| `99_*` | Opt-in / expensive. Currently just `99_vector_indexes.sql`. The runner skips this unless `ORACLE_RUN_VECTOR_INDEXES=1`. |

When adding a new file, pick a prefix that places it in the right phase. Within a phase, use any free number — order within a phase doesn't usually matter, but try not to skip too many numbers (current files: 01, 10, 15, 20, 21, 30, 40, 41, 99).

## Idempotency rules

Files run on every boot — they must not error or duplicate work:

- `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`.
- `DROP POLICY IF EXISTS …` followed by `CREATE POLICY …` for RLS policies (Postgres has no CREATE POLICY IF NOT EXISTS).
- Data migrations gated by existence checks: `IF EXISTS (SELECT 1 FROM ...)`, `ON CONFLICT DO NOTHING`, `WHERE col IS NOT NULL`.
- Wrap multi-statement data migrations in `BEGIN; ... COMMIT;` so partial application doesn't leave the DB in a half-state.

If a file is genuinely one-shot and can't be made idempotent (rare), the convention is to short-circuit it with an `IF NOT EXISTS` check on the post-condition.

## Current files

| File | What it does |
|---|---|
| `01_extensions.sql` | `CREATE EXTENSION IF NOT EXISTS` for pgvector, pgcrypto, uuid-ossp. |
| `10_check_constraints.sql` | `claim_evidence_source_check` — enforces that `source_type` matches its non-null FK column (spec 6.8). |
| `11_observability_constraints.sql` | R3 — value-whitelist CHECKs on `provider_cached_content` (provider, cache_kind, status, deleted_at consistency), non-negative token CHECKs on `model_run_usage_details`, and an `updated_at` trigger on `provider_cached_content`. |
| `12_taxonomy_constraints.sql` | R3.5 — value-whitelist CHECKs across the taxonomy tables: `knowledge_sub_topics.review_status`, `*_top_domains.assignment_reason` + confidence-range, `entities.entity_type` whitelist (with `licensor` distinct from `vendor` and operating-vendor subtypes enumerated), `taxonomy_proposals.proposal_type`/`status` + reviewed-consistency, `entity_proposals.status`/source-type + merge-consistency. |
| `13_extraction_constraints.sql` | R4 — value-whitelist + consistency CHECKs across the candidate-before-claim staging tables: `extraction_batches` status/batch_type + non-negative counters, `extraction_candidates` status/stance/impact/confidence + promoted/duplicate/sensitive consistency rules, `extraction_candidate_evidence` source-type/pointer consistency (mirrors spec 6.8) + validation_status + validated-fields-required-on-pass rule + offset ordering, `extraction_validation_results` check_name/status + target-present rule. |
| `14_claims_candidate_hash_unique.sql` | R7 — partial UNIQUE index on `claims.candidate_hash WHERE candidate_hash IS NOT NULL`. Enforces "no two distinct claims share the same canonicalized hash" across cron runs, while leaving historic pre-R7 rows (where the hash is NULL) untouched. |
| `15_employee_identities.sql` | DDL for the `employee_identities` table (multi-identity support — DECISIONS.md D2). |
| `16_knowledge_top_domains_seed.sql` | R3.5 — idempotent seed of the 12 top-level domains with boundary rules (belongs-here / does-not-belong-here / common entities / default exclusions / neighboring domains). ON CONFLICT DO NOTHING so admin edits aren't clobbered. |
| `17_entities_seed.sql` | R3.5 — idempotent seed of the canonical entity registry: 5 customers, 5 licensors, 10 systems, 8 departments, 4 geographies, 14 process stages, 10 document classes. |
| `20_rls_helpers.sql` | `current_employee_id()`, `current_employee_is_admin()` — both join through `employee_identities`. |
| `21_rls_policies.sql` | All RLS policies — employees, channels, messages, documents, intelligence tables, settings, employee_identities. |
| `30_admin_views.sql` | The seven admin views from spec Part 8 (`claims_with_primary_evidence`, etc.). |
| `31_observability_views.sql` | R3 — `model_runs_with_usage` view joining `model_runs`, `model_run_usage_details`, and `oracle_context_packs` with a derived `cache_hit_ratio`. |
| `40_employee_identities_data.sql` | One-shot, idempotent: copy any legacy `employees.auth_*` values into `employee_identities`, run the Albert merge, NULL the deprecated columns. |
| `41_albert_post_merge_fix.sql` | Idempotent reconciliation for Albert's specific case (Google + M365 identities folded onto one employee row). Uses real auth_user_ids. |
| `42_claim_top_domains_backfill.sql` | R3.5 — idempotent backfill from legacy `claim_domains` (Postgres enum) to new `claim_top_domains` (text FK). Includes the mechanical mapping (e.g., `licensing` → `licensing_approvals`, `coldlion` → `it_systems`, `general` → `customer_ops` residual). Legacy `claim_domains` is intentionally preserved per R3.5 acceptance gate. |
| `48_taxonomy_vector_indexes.sql` | R3.5 — HNSW index on `knowledge_sub_topics.centroid`. Always-on (not opt-in like 99) because the table is empty on install per the activation-threshold rule. |
| `99_vector_indexes.sql` | HNSW indexes on `claims.embedding` and `document_chunks.embedding`. Opt-in via `ORACLE_RUN_VECTOR_INDEXES=1`. |

## Anti-patterns

- **Don't edit a prior migration file.** Add a new file with the next free prefix. Old files have already run against production.
- **Don't depend on a specific machine's data inside a 40+ file** unless the file is guarded by an existence check on that data (see `41_albert_post_merge_fix.sql`, which only fires if Albert's specific Supabase auth ids exist).
- **Don't `DROP TABLE` here.** If a table must be removed, add a defensive `DROP TABLE IF EXISTS` and update `packages/db/src/schema.ts` in the same commit, and confirm no application code still references it.
