# Widen model_capabilities provider CHECK — exact dispatch for review

Status: awaiting review. Tracking issue: #49 (reopened scope: catalog refresh).
Nothing runs before a `VERDICT APPROVE` naming the reviewed commit of this file.

Owner context (Albert, Claude chat, 2026-09-28): asked for Muse and StepFun
models to appear in the admin model pool; "Refresh catalog" now fails.

## Evidence

- Production constraint (read-only query, 2026-09-28):
  `model_capabilities_provider_check CHECK (provider = ANY
  (ARRAY['anthropic','openai','google','deepseek','qwen']))`.
- PR #48 adapters produce rows with provider `meta_muse` and `stepfun` (Z.ai on
  hold, but reserved here to avoid another change). `refreshModelCatalog` upserts
  all rows in one statement, so the whole refresh fails with a constraint error.

## Change

Hand-written idempotent migration `packages/db/migrations/sql/56_model_capabilities_more_providers.sql`
(already run on every `db:migrate`), updated to:

```sql
ALTER TABLE model_capabilities DROP CONSTRAINT IF EXISTS model_capabilities_provider_check;
ALTER TABLE model_capabilities
  ADD CONSTRAINT model_capabilities_provider_check
  CHECK (provider IN ('anthropic','openai','google','deepseek','qwen','meta_muse','zai','stepfun'));
```

Strictly wider: every existing row still satisfies it. No data changes.

## Execution

1. PR with the file change merged to main (CI green).
2. `ai-task-gates start --class database` / `check --before database`.
3. Target proof: connect to Oracle's own Supabase project `eqccjfbyrywsqkxxpjvg`
   (1Password "Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle,
   eqccjfbyrywsqkxxpjvg)", shared IPv4 pooler, user
   `postgres.eqccjfbyrywsqkxxpjvg`); `select current_database()` and confirm the
   constraint text equals the Evidence text; else stop.
4. Apply exactly the two statements above in one transaction (repo rule:
   hand-written idempotent SQL may be applied directly; generated `0NNN_*.sql`
   may not, and none is touched). Not `db:migrate`, to avoid replaying anything
   else against production.
5. Verify the new constraint text and `select count(*) from model_capabilities`
   unchanged. Record on #49.

## Rollback

Re-apply the previous five-provider CHECK (valid only while no new-provider rows
exist; otherwise delete those rows first).
