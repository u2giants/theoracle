# Wet-test walkthrough — R5/R5.5/R6/R7 candidate-before-claim pipeline

This guide walks you (Albert) through running the candidate-before-claim
pipeline end-to-end against the **real Supabase database** for the first
time. Until you complete this walkthrough, R11 (resume interjection) is
blocked per `HANDOFF.md`.

The goal is to:

1. Apply the retrofit migrations to Supabase Cloud.
2. Run one real extraction through the worker (a single small Slack message).
3. Open the admin observability dashboard at `/admin/ai`.
4. Confirm that the candidate → validation → promotion path produced exactly
   the rows we expect.
5. Confirm sensitive material was NOT promoted into `claims`.

Everything here is reversible up to step 4. Step 4 writes real claim rows;
delete them by hand if the wet-test reveals a bug.

---

## 0. Prerequisites

You should already have:

- A working `.env.local` in `apps/web/` pointing at the Supabase project,
  containing `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and a provider
  API key (Anthropic or OpenRouter — whichever your active route uses).
- `pnpm install` already run at the repo root.
- A Supabase project where you do NOT mind a handful of test rows in
  `messages`, `extraction_batches`, `extraction_candidates`, and possibly
  one row in `claims` if everything passes.

Don't proceed if you have production data you can't afford to dirty. The
wet-test is short but it writes.

---

## 1. Apply the retrofit migrations

The retrofit migrations live in `packages/db/migrations/sql/`. They are
hand-written, numerically ordered, and idempotent — re-running them is
safe.

Open a terminal at the repo root and run:

```bash
pnpm db:migrate
```

This will:

- Connect to the Supabase URL in your `.env.local`.
- Run every `.sql` file in `packages/db/migrations/sql/` in numeric order.
- Skip files whose statements are already applied (each file is wrapped in
  `IF NOT EXISTS` / `CREATE OR REPLACE` patterns).

Expected output: a series of `applied: NN_*.sql` lines and no errors.

If you get a failure on any specific migration, **stop**. Send me the
error output and the failing file number. Do not try to "fix forward"
by hand-editing the SQL — the migrations are append-only.

After it succeeds, double-check by running this query in Supabase SQL
editor:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'extraction_batches',
    'extraction_candidates',
    'extraction_candidate_evidence',
    'extraction_validation_results',
    'knowledge_top_domains',
    'knowledge_sub_topics',
    'entities',
    'oracle_context_packs',
    'model_run_usage_details',
    'provider_cached_content'
  )
ORDER BY table_name;
```

You should see **all ten** tables listed. If any are missing, the migration
didn't fully apply.

Also confirm the top-domain seed data loaded:

```sql
SELECT id, label FROM knowledge_top_domains ORDER BY id;
```

You should see 12 rows: `customer_ops`, `licensing_approvals`,
`product_development`, `creative_design`, `supply_chain`, `it_systems`,
`production_lifecycle`, `finance_pricing`, `people_org`, `vendor_management`,
`logistics_shipping`, `import_compliance`.

---

## 2. Pick a small test message

Open the Supabase SQL editor and find a recent, low-stakes message you don't
mind being extracted. Ideal candidates:

- An operational message about artwork, lead times, or factory rules.
- Short (under 500 chars).
- Does NOT mention anyone by full name + an HR action in the same sentence
  (we don't want to trip the sensitivity gate by accident on the first run).

Note the `id`, the `channel_id`, and the `created_at` timestamp. We'll use
the `id` as the `messageId` input.

If you don't have a real message handy, run this to insert a synthetic one:

```sql
INSERT INTO messages (id, channel_id, employee_id, role, content, created_at)
VALUES (
  gen_random_uuid(),
  (SELECT id FROM channels LIMIT 1),
  (SELECT id FROM employees LIMIT 1),
  'user',
  'For the Mickey 100th anniversary mug line, all artwork files must be delivered to the factory at 300 DPI minimum. Anything below 300 will be rejected at sampling.',
  now()
)
RETURNING id;
```

Copy the returned `id`.

---

## 3. Trigger the claim-extraction worker

The R6 worker is implemented in
`apps/workers/src/trigger/claim-extraction.ts`. It accepts a payload with
`{ messageIds: string[] }`.

The simplest way to invoke it locally is to run the workers dev server:

```bash
cd apps/workers
pnpm dev
```

Wait until you see `triggers ready` (Trigger.dev v3 dev mode). Then from
another terminal, invoke the task with your test message ID. Either:

**Option A — use the Trigger.dev dev dashboard** (easiest if you have it set up):

1. Open the Trigger.dev local dev dashboard (URL printed by `pnpm dev`).
2. Find the `claim-extraction` task.
3. Click "Test run".
4. Paste payload `{ "messageIds": ["<your-message-id>"] }` and run.

**Option B — call via SQL** (if you have the trigger wired through Postgres):
Skip if you're not using the Postgres wake mechanism.

Watch the worker logs. You're looking for:

- `provider call complete` (the LLM returned)
- `inserted N candidates`
- `validation complete` with a candidate count
- `promotion complete` with either `insert_new_claim` or `reject` per candidate

---

## 4. Verify the candidate row landed

In Supabase SQL editor:

```sql
SELECT
  c.id                         AS candidate_id,
  c.status                     AS candidate_status,
  c.summary,
  c.candidate_hash,
  c.created_at
FROM extraction_candidates c
WHERE c.source_message_id = '<your-message-id>'
ORDER BY c.created_at DESC;
```

Expected for the routine handoff sample message:

- `candidate_status` = `promoted`
- `summary` matches the model's output
- `candidate_hash` is a 32-char hex string

Also inspect the validation results:

```sql
SELECT check_name, status, detail
FROM extraction_validation_results
WHERE candidate_id = '<the candidate_id from above>'
ORDER BY created_at;
```

For a routine handoff you should see all `pass` rows for: `source_exists`,
`quote_exact_match`, `domain_valid`, `sensitivity_gate`, `promotion_transaction`.

---

## 5. Verify the claim row landed

```sql
SELECT id, summary, status, candidate_hash, created_at
FROM claims
WHERE candidate_hash = '<the candidate_hash from step 4>';
```

You should see exactly **one** row with `status = 'pending_review'`.

And the linked evidence:

```sql
SELECT id, claim_id, source_message_id, exact_quote, validated_char_start, validated_char_end
FROM claim_evidence
WHERE claim_id = '<the claim id from above>';
```

The `exact_quote` should be a verbatim substring of the original message
content. The offsets should land on that substring.

---

## 6. Open the admin observability dashboard

Start the web app:

```bash
cd apps/web
pnpm dev
```

Visit `http://localhost:3000/admin/ai`. You should see:

- A model-run row for the run you just triggered, with cost, latency, token
  counts.
- A context-pack row showing what was assembled.
- A taxonomy assignment row for the new claim.

Visit `http://localhost:3000/admin/taxonomy` to confirm the top-domain
assignment shows up in the governance dashboard.

---

## 7. Sensitive-content negative test (recommended)

Repeat steps 2-4 with a message that DOES contain sensitive HR content —
something like the transcript-03 fixture content. Use a *synthetic* message,
not a real disciplinary record.

What you SHOULD see:

- An `extraction_candidates` row with `status = 'quarantined_sensitive'` (or
  `rejected_sensitive`).
- **No** row in `claims` for that candidate's hash.
- A validation result with `check_name = 'sensitivity_gate'` and `status = 'fail'`.

If a claim row appears for sensitive content, **stop**. That's a P0 bug.
Delete the claim row by hand and let me know which check failed.

---

## 8. Cleanup (optional)

If you want to remove the wet-test rows entirely:

```sql
-- Delete in reverse FK order
DELETE FROM extraction_validation_results
WHERE candidate_id IN (
  SELECT id FROM extraction_candidates WHERE source_message_id = '<your-message-id>'
);
DELETE FROM extraction_candidate_evidence
WHERE candidate_id IN (
  SELECT id FROM extraction_candidates WHERE source_message_id = '<your-message-id>'
);
DELETE FROM claim_evidence
WHERE claim_id IN (
  SELECT id FROM claims WHERE candidate_hash IN (
    SELECT candidate_hash FROM extraction_candidates
    WHERE source_message_id = '<your-message-id>'
  )
);
DELETE FROM claims
WHERE candidate_hash IN (
  SELECT candidate_hash FROM extraction_candidates
  WHERE source_message_id = '<your-message-id>'
);
DELETE FROM extraction_candidates WHERE source_message_id = '<your-message-id>';
DELETE FROM extraction_batches
WHERE source_message_id = '<your-message-id>';
```

Don't delete the original `messages` row unless you inserted a synthetic one.

---

## 9. Sign off

When everything in steps 4–7 passes, update `HANDOFF.md`:

- Move R5–R10.5 to "validated against live DB" status.
- Unblock R11 — resume interjection engine.

Then ping me and we can start R11.

---

## Troubleshooting

**Migration fails on a numbered file**: send me the file number and the error
text. Do not edit the SQL by hand.

**Worker logs show "no active route"**: your `OracleAIClient` configuration
isn't seeing the route catalog. Check `packages/ai/src/routes/index.ts` and
the env var that selects the active extraction route.

**Quote validator rejects every candidate**: the model is returning paraphrases
instead of verbatim quotes. The extraction system prompt
(`packages/ai/src/prompts/extraction-system.ts`) has the verbatim-quote rule;
confirm the active model isn't trimming it.

**Sensitivity gate over-fires (everything quarantined)**: tune the keyword
list or extend the rule in `packages/oracle-engines/src/extraction/`. Send me
the false positives.

**Mock-mode eval already covers this case**: yes — see
`pnpm --filter @oracle/ai eval:extraction`. The wet-test confirms the *real*
DB + worker + provider path, which the mock-mode eval can't cover.
