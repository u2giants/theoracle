<!-- Moved verbatim from AGENTS.md (issue #22). AGENTS.md is the router. -->

## 14. Critical incidents

### 2026-05-26 Provider-layer regression through a generic SDK abstraction

What happened:
A provider-adapter implementation briefly used generic AI SDK wrappers instead of raw provider SDKs.

Impact:
Provider-native cache and structured-output behavior would have been obscured.

Root cause:
The implementation ignored the documented provider-native boundary.

Recovery:
The adapters were rewritten to use raw provider SDKs directly.

Rule added to prevent recurrence:
Do not introduce generic inference wrappers into `packages/ai/src/providers/`.

### 2026-05-27 Missing migration caused auth callback failures

What happened:
Code referencing `employees.departments` reached production before the corresponding live DB column existed.

Impact:
OAuth callback queries failed and users hit 500s during sign-in.

Root cause:
A schema-affecting change was shipped without first applying the migration to the live DB.

Recovery:
A catch-up migration added and backfilled the missing column.

Rule added to prevent recurrence:
Apply migrations before pushing code that requires them, and stage git changes explicitly instead of sweeping unrelated files with `git add -A`.

### 2026-05-28 Drizzle migration journal drifted from production

What happened:
`pnpm db:migrate` failed at Step 2 with `relation "model_capabilities" already exists`. Migration `0006_magical_revanche` had been applied to production at some earlier point — all four objects it creates (tables `model_capabilities` + `typing_indicators`, columns `employees.departments` + `entity_proposals.proposal_count`) existed in the live DB — but its sha256 was never written to `drizzle.__drizzle_migrations`. The runner therefore tried to replay it on every invocation.

Impact:
Database migrations could not ship through the canonical runner. Hand-written `migrations/sql/*.sql` files were unreachable because Step 2 failed before Step 3 ran them.

Root cause:
At least one Drizzle-generated migration was applied through a side channel that does not write to `drizzle.__drizzle_migrations` — most likely Supabase MCP `apply_migration` (which writes to `supabase_migrations.schema_migrations` instead), the Supabase dashboard SQL editor, or `drizzle-kit push`.

Recovery:
Inserted the correct sha256 (`d273fe37e62858c4e0e0b7e76fb6baa794889e2ed6efbf5f265f83c70d6941db`) into `drizzle.__drizzle_migrations` for `0006_magical_revanche`. `pnpm db:migrate` then completed cleanly. Commit `b108821`.

Rules added to prevent recurrence:
1. Generated `packages/db/migrations/0NNN_*.sql` files ship ONLY through `pnpm db:migrate`. Hand-written `packages/db/migrations/sql/*.sql` files (idempotent views/constraints) MAY ship via Supabase MCP `apply_migration` — those aren't journaled. Documented in CLAUDE.md → "Drizzle journal hygiene".
2. Added `pnpm db:check-drift` (`packages/db/src/check-migration-drift.ts`) that compares on-disk migration hashes against the journal. Wired into `.github/workflows/pr-check.yml` so every PR / push to main fails the build on drift. Requires repo secret `PROD_DIRECT_URL`. Commit `35439b2`.

### 2026-06-26 Drizzle drift: generated migration 0007 hash mismatch

What happened:
GitHub Actions failed `pnpm db:check-drift` for
`0007_tricky_charles_xavier.sql`. Production already had the generated schema
objects from that migration (`claim_translations`, `claims.source_lang`,
`employees.locale`), but the journal row hash did not match the checkout hash
used by CI.

Recovery:
Verified the schema objects existed in current prod, then reconciled the journal
row to CI's reported LF checkout hash
`af12b253571b59ea7c214c978f11c21ef216bcca8e0dbe885ce61a011594cb5f`.
Rerunning GitHub Actions for commit `8e0a45c` then passed.

Future sessions should:
If generated-migration drift recurs, verify live schema objects first and only
then reconcile the journal. Do not replay generated migrations blindly, and be
aware that Windows CRLF vs CI LF can change the file hash the drift checker
computes.

### 2026-05-28 Batch-submit rollback left staging orphans

What happened:
The initial 2026-05-28 retry-safety fix in `claim-extraction-batch-submit.ts` (commit `830713c`) reverted messages from `processing` back to `pending` on submit failure but left the `extraction_batches` + `oracle_context_packs` rows it had already inserted in place. An inline comment falsely claimed the drain task would reap them later.

Impact:
There is no reaper in `claim-extraction-batch-drain.ts` for `extraction_batches WHERE provider_batch_job_id IS NULL`. Every failed submit accumulated dead `pending_model` staging rows + orphan context packs that admin observability would surface indefinitely as never-drained batches.

Root cause:
The fix's inline comment described an invariant that didn't exist in the codebase; the comment was never cross-checked against the drain task it referenced.

Recovery / fix:
Made the rollback symmetric and timing-aware. The submit task now tracks `stagedBatchIds`, `stagedContextPackIds`, `providerAccepted` (flipped the instant `adapter.submitBatch` returns), and `providerBatchJobInserted` (flipped after the durable `provider_batch_jobs` row exists). On failure:
- `providerAccepted === false` (no live provider state): revert messages + DELETE both staging tables, scoped to ids this run created. Drain finds nothing because nothing existed.
- `providerAccepted === true` but `providerBatchJobInserted === false`: the provider accepted work, but Oracle has no durable job row for the drain task to poll. Abandon that upstream batch, reset local messages/staging for a clean tracked retry, and log the provider batch id for operator awareness.
- `providerBatchJobInserted === true`: leave messages/staging in place. The provider batch is durably tracked, and the drain task can recover by polling `provider_batch_jobs`.

Rule added to prevent recurrence:
Any "this gets cleaned up downstream" comment must point at the specific code path doing the cleanup. If no such code exists, do the cleanup inline.

### 2026-06-04 Webhook dispatched to the wrong Trigger.dev environment (near-miss)

What happened:
The Teams transcript webhook called `tasks.trigger('teams-transcript-ingestion')`, but the run landed in the **dev** Trigger.dev environment and **expired** (TTL 10m, never executed) — while the workers are deployed to **prod**. The first real call was silently lost.

Impact:
Transcript ingestion appeared to work (subscription fired, webhook received + decrypted the notification correctly — confirmed by the decrypted payload on the expired dev run) but produced no messages. Unlike document-ingestion (saved by its 4h sweep cron), transcripts have no sweep, so the call was unrecoverable.

Root cause:
Vercel's `TRIGGER_SECRET_KEY` was a **dev** environment key. The Trigger.dev SDK routes a trigger to whatever environment the key belongs to. Dev tasks only run when a local `trigger.dev dev` session is connected — none was — so the run sat for its TTL and expired.

Recovery:
Set Vercel Production `TRIGGER_SECRET_KEY` to the **prod** secret key + redeployed `apps/web`; re-triggered the same transcript in prod via the Trigger MCP → resolved 2/2.

Rule added to prevent recurrence:
Vercel's `TRIGGER_SECRET_KEY` MUST be the prod-environment secret key. Any `tasks.trigger()` from the web app dispatches to the key's environment; a dev key silently drops production work.

### 2026-06-09 Entra secret rotation broke Supabase Microsoft login

What happened:
While wiring the Teams-native Azure Bot, `az ad app credential reset` was run without `--append` against the shared Entra app `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`. That removed existing client secrets, including the Supabase Azure provider secret and the Graph backend secret. Microsoft sign-in then redirected to `/auth/callback?error=server_error&error_code=unexpected_failure...`; Oracle showed `/denied?reason=no_code`.

Impact:
Microsoft SSO was temporarily broken. Graph-backed directory/transcript paths also needed fresh secrets in Vercel and Trigger.dev before they could safely run.

Root cause:
The same Entra app carries three separate client-secret consumers: Supabase Auth Azure provider, app-only Microsoft Graph backend, and Bot Framework authentication. Rotating one without `--append` invalidated the others.

Recovery:
Created fresh appended Entra secrets. Updated Supabase Auth's Azure provider client secret manually in the Supabase dashboard, updated Vercel `AZURE_GRAPH_CLIENT_SECRET` / `MICROSOFT_BOT_*`, updated Trigger.dev prod `AZURE_GRAPH_CLIENT_SECRET` via `POST https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod/import`, and redeployed Vercel production. Supabase Azure provider URL was corrected to `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971` (no `/v2.0`; Supabase appends `/oauth2/v2.0/authorize`).

Rule added to prevent recurrence:
When creating or rotating a client secret on the shared Entra app, use `az ad app credential reset --append --display-name <purpose> ...` unless intentionally replacing every consumer. Keep separate display names for `supabase-prod-*`, `oracle-graph-*`, and `oracle-teams-bot-*`. Never put `/v2.0` in the Supabase Azure provider URL.

