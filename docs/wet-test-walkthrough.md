# How to wet-test the extraction pipeline against a new transcript

The original wet-test passed end-to-end on 2026-05-26 (commit `51a33ff`) and proved every layer of the candidate-before-claim pipeline against the live Supabase DB. This guide is for **repeating** the test against a new sample — when you want to:

- Validate a prompt change in `EXTRACTION_SYSTEM_PROMPT`.
- Smoke-test extraction against a real (or representative) message before deploying a worker change.
- Confirm an Anthropic / Vertex / OpenAI key works after rotation.
- Watch one extraction land in the admin dashboard with full observability rows.

The original first-time walkthrough (apply migrations, set up env vars, etc.) has been removed because that work is done. The current `.env.local` + the already-applied migrations + the `runClaimExtractionOnce` runner make this a 3-step operation.

---

## 0. Prerequisites

- `.env.local` populated with `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `OPENAI_API_KEY`. See `docs/configuration.md`.
- Vertex ADC valid: `gcloud auth application-default print-access-token > /dev/null && echo OK`.

If any of those fail, fix them first.

---

## 1. Insert a test message

Via Supabase SQL editor or the MCP, with content meaningful enough that extraction will produce at least one claim. Replace the synthetic example below with whatever you want to test.

```sql
INSERT INTO messages (channel_id, employee_id, role, content, extraction_status, created_at)
VALUES (
  (SELECT id FROM channels WHERE name = 'oracle-smoke-test' LIMIT 1),
  (SELECT id FROM employees WHERE email = 'u2giants@gmail.com' LIMIT 1),
  'user',
  '<your test content here — operational, with a quotable rule>',
  'pending',
  now()
)
RETURNING id;
```

Copy the returned `id`. The extraction worker only processes messages where `extraction_status='pending' AND role='user'`.

---

## 2. Fire one pass of the extraction worker

From the repo root:

```bash
pnpm --filter @oracle/workers tsx src/wet-test/run-claim-extraction-once.ts wet-test-<short-label>
```

This calls `runClaimExtractionOnce(triggerRunId)` — the exported core of the production Trigger.dev task. It does not go through Trigger.dev cloud; it runs once locally against the live DB. Typical elapsed time: 5–10 seconds for one message.

The script prints a JSON summary at the end:

```json
{
  "ok": true,
  "batchesProcessed": 1,
  "candidatesStaged": <N>,
  "claimsPromoted": <N>,
  "duplicatesAppended": 0,
  "rejections": 0,
  "circuitBreakerTrips": 0,
  "messagesProcessed": 1,
  "errors": 0
}
```

A successful run has `errors=0` and `claimsPromoted >= 1`. If `claimsPromoted=0` but `candidatesStaged>0`, look at `extraction_validation_results` — something failed the deterministic checks (quote, taxonomy, sensitivity, or hash). If `candidatesStaged=0`, look at `extraction_batches.error` — the model didn't produce parseable output.

---

## 3. Inspect what landed

Run these queries via Supabase MCP or SQL editor. Substitute `<MESSAGE_ID>` with the message id from step 1.

**The batch:**
```sql
SELECT id, status, validation_attempt_count, error, started_at, finished_at
FROM extraction_batches
WHERE source_message_ids @> to_jsonb(ARRAY['<MESSAGE_ID>']::uuid[])
ORDER BY created_at DESC LIMIT 1;
```

**Candidates from that batch:**
```sql
SELECT id, status, claim_type, summary, impact_score, confidence_score,
       domains, promoted_to_claim_id, promoted_at
FROM extraction_candidates
WHERE extraction_batch_id = (
  SELECT id FROM extraction_batches
  WHERE source_message_ids @> to_jsonb(ARRAY['<MESSAGE_ID>']::uuid[])
  ORDER BY created_at DESC LIMIT 1
);
```

**Validation results for those candidates:**
```sql
SELECT check_name, status, detail
FROM extraction_validation_results
WHERE candidate_id IN (
  SELECT id FROM extraction_candidates
  WHERE extraction_batch_id = (
    SELECT id FROM extraction_batches
    WHERE source_message_ids @> to_jsonb(ARRAY['<MESSAGE_ID>']::uuid[])
    ORDER BY created_at DESC LIMIT 1
  )
);
```

**Promoted claims + their evidence + their top-domains:**
```sql
SELECT c.id, c.summary, c.status, c.candidate_hash, c.created_at
FROM claims c
WHERE c.candidate_hash IN (
  SELECT ec.id FROM extraction_candidates ec
  WHERE ec.promoted_to_claim_id = c.id
);
```

Or via the admin UI: open `/admin/ai/runs`, find the most recent `claim-extraction` row, click in to see the full prompt-plan + observability rows.

---

## 4. Common failure shapes

| Symptom | Likely cause | Fix |
|---|---|---|
| Script throws on launch with "ANTHROPIC_API_KEY missing" etc. | `.env.local` not loaded or key removed | Check the four required vars; see `docs/configuration.md` § ".env.local override quirk" |
| Batch ends in `status='failed'` with `error="No object generated: could not parse the response."` | Model didn't return valid JSON matching `ExtractionOutputSchema` | If using a non-default route, check whether that model supports native JSON-schema output. Vertex Gemini Flash via direct `@google/genai` does; verify the route id. |
| Candidates staged but all `status='validation_failed'` | Quote validator rejected — model paraphrased instead of returning verbatim | Inspect `extraction_validation_results.detail` for `check_name='quote_exact_match'` failures |
| Candidates staged but `status='quarantined_sensitive'` and no `claims` row | Sensitivity gate fired (HR / PII content) | Expected behavior. Check via `/admin/ai/candidates` → "Sensitive" tab |
| Vertex call returns 401 | ADC expired or wrong project | `gcloud auth application-default login` and `gcloud config configurations activate oracle` |

---

## 5. Cleanup (optional)

If you want to remove the test rows after inspection:

```sql
-- Drop in reverse FK order
DELETE FROM claim_evidence WHERE claim_id IN (
  SELECT promoted_to_claim_id FROM extraction_candidates
  WHERE extraction_batch_id IN (
    SELECT id FROM extraction_batches
    WHERE source_message_ids @> to_jsonb(ARRAY['<MESSAGE_ID>']::uuid[])
  )
);
DELETE FROM claim_top_domains WHERE claim_id IN (...);  -- same subquery
DELETE FROM claims WHERE id IN (...);
DELETE FROM extraction_validation_results WHERE candidate_id IN (...);
DELETE FROM extraction_candidate_evidence WHERE candidate_id IN (...);
DELETE FROM extraction_candidates WHERE extraction_batch_id IN (...);
DELETE FROM extraction_batches WHERE source_message_ids @> to_jsonb(ARRAY['<MESSAGE_ID>']::uuid[]);
DELETE FROM messages WHERE id = '<MESSAGE_ID>';
```

The original wet-test rows (commit `51a33ff`, 2026-05-26) are intentionally preserved as the historical proof of the pipeline working — don't delete those.
