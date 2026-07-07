# Candidate-Before-Claim Validation Pipeline

Status: mandatory implementation target.

This document defines the hardened extraction pipeline for The Oracle.

## Core rule

No AI output becomes official operational truth directly.

The AI may propose claim candidates. It may not create permanent claims.

All extraction output must pass through:

1. staging;
2. privacy/sensitivity screening;
3. deterministic evidence validation;
4. duplicate/overlap checks;
5. review triage;
6. transactional promotion.

Only after those steps may the system write to permanent `claims`, `claim_top_domains`, and `claim_evidence`. During the migration window, legacy `claim_domains` is treated as pre-retrofit compatibility state only.

## Why this exists

LLMs naturally paraphrase. They also sometimes attribute a quote to the wrong message, merge multiple people into one claim, or turn a suggestion into a fact.

The Oracle is only valuable if Albert can ask:

> Why does the Oracle believe this?

And the system can answer:

> Because this exact employee or document said this exact thing, and the claim was validated and promoted from candidate to permanent claim.

## Current repo problem

The current `claim-extraction` worker validates quotes, but then inserts directly into permanent claim tables.

That is better than no validation, but it is not the target architecture.

The target pipeline must stage AI output first.

## Required tables

Add these tables through Drizzle schema and raw SQL migrations where needed.

### `extraction_batches`

One row per extraction job segment.

Purpose:

- identify which source messages/chunks were processed together;
- prevent duplicate concurrent processing;
- store batch-level status and hashes;
- connect candidates to job/model/context records.

Recommended fields:

```ts
export const extractionBatches = pgTable('extraction_batches', {
  id: uuid('id').primaryKey().defaultRandom(),
  jobRunId: uuid('job_run_id').references(() => jobRuns.id),
  modelRunId: uuid('model_run_id').references(() => modelRuns.id),
  contextPackId: uuid('context_pack_id').references(() => oracleContextPacks.id),

  batchType: varchar('batch_type', { length: 50 }).notNull(),
  // message_segment | document_chunk | document_page | document_lens_group | transcript_segment

  status: varchar('status', { length: 50 }).default('pending_model').notNull(),
  // pending_model | model_complete | validation_complete | promoted | failed |
  // skipped | failed_validation_loop

  sourceMessageIds: jsonb('source_message_ids'),
  sourceDocumentChunkIds: jsonb('source_document_chunk_ids'),
  sourceHash: varchar('source_hash', { length: 255 }).notNull(),

  rawModelOutput: jsonb('raw_model_output'),
  validationSummary: jsonb('validation_summary'),
  validationAttemptCount: integer('validation_attempt_count').default(0).notNull(),
  consecutiveQuoteFailureCount: integer('consecutive_quote_failure_count').default(0).notNull(),
  error: text('error'),

  startedAt: timestamp('started_at').defaultNow().notNull(),
  finishedAt: timestamp('finished_at'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

### `extraction_candidates`

One row per proposed operational claim.

Purpose:

- preserve untrusted AI output;
- track validation status;
- allow admin/debug review of failed extractions;
- prevent bad candidates from contaminating permanent truth.

Recommended fields:

```ts
export const extractionCandidates = pgTable('extraction_candidates', {
  id: uuid('id').primaryKey().defaultRandom(),
  extractionBatchId: uuid('extraction_batch_id')
    .references(() => extractionBatches.id)
    .notNull(),

  status: varchar('status', { length: 50 }).default('pending_validation').notNull(),
  // pending_validation | validation_failed | failed_validation_loop | validated |
  // duplicate | promoted | rejected | rejected_sensitive | quarantined_sensitive

  claimType: varchar('claim_type', { length: 100 }).notNull(),
  summary: text('summary').notNull(),
  impactScore: integer('impact_score').notNull(),
  confidenceScore: integer('confidence_score'),

  domains: jsonb('domains').notNull(),
  stance: varchar('stance', { length: 50 }),
  // stated | confirmed | challenged | refined | exception_introduced | ambiguity_revealed

  containsSensitivePersonalData: boolean('contains_sensitive_personal_data').default(false).notNull(),
  containsSensitiveHRData: boolean('contains_sensitive_hr_data').default(false).notNull(),
  isPersonalConflict: boolean('is_personal_conflict').default(false).notNull(),
  sensitivityReason: text('sensitivity_reason'),

  riskFlags: jsonb('risk_flags'),
  requiresReview: boolean('requires_review').default(true).notNull(),
  reviewReason: text('review_reason'),

  duplicateOfCandidateId: uuid('duplicate_of_candidate_id'),
  duplicateOfClaimId: uuid('duplicate_of_claim_id'),
  promotedToClaimId: uuid('promoted_to_claim_id'),

  rawCandidateJson: jsonb('raw_candidate_json').notNull(),
  validationError: text('validation_error'),

  createdAt: timestamp('created_at').defaultNow().notNull(),
  validatedAt: timestamp('validated_at'),
  promotedAt: timestamp('promoted_at'),
});
```

The extraction output schema must include these fields:

```ts
containsSensitivePersonalData: boolean;
containsSensitiveHRData: boolean;
isPersonalConflict: boolean;
sensitivityReason?: string;
```

### `extraction_candidate_evidence`

One row per proposed evidence quote.

Purpose:

- store the AI's proposed quote;
- validate exact source match;
- support multiple evidence rows per candidate;
- cleanly promote valid evidence to `claim_evidence`.

Recommended fields:

```ts
export const extractionCandidateEvidence = pgTable('extraction_candidate_evidence', {
  id: uuid('id').primaryKey().defaultRandom(),
  candidateId: uuid('candidate_id')
    .references(() => extractionCandidates.id)
    .notNull(),

  sourceType: evidenceSourceTypeEnum('source_type').notNull(),
  sourceMessageId: uuid('source_message_id').references(() => messages.id),
  sourceDocumentChunkId: uuid('source_document_chunk_id').references(() => documentChunks.id),
  sourceExternalRecordId: varchar('source_external_record_id', { length: 255 }),

  assertedByEmployeeId: uuid('asserted_by_employee_id').references(() => employees.id),
  uploadedByEmployeeId: uuid('uploaded_by_employee_id').references(() => employees.id),
  createdByEmployeeId: uuid('created_by_employee_id').references(() => employees.id),

  exactQuoteProvided: text('exact_quote_provided').notNull(),
  normalizedQuote: text('normalized_quote'),
  charStartProvided: integer('char_start_provided'),
  charEndProvided: integer('char_end_provided'),

  validatedExactQuote: text('validated_exact_quote'),
  validatedCharStart: integer('validated_char_start'),
  validatedCharEnd: integer('validated_char_end'),
  pageNumber: integer('page_number'),

  validationStatus: varchar('validation_status', { length: 50 }).default('pending').notNull(),
  // pending | exact_match | normalized_match | failed | ambiguous | failed_validation_loop

  validationMethod: varchar('validation_method', { length: 100 }),
  validationError: text('validation_error'),
  confidence: integer('confidence'),

  createdAt: timestamp('created_at').defaultNow().notNull(),
  validatedAt: timestamp('validated_at'),
});
```

### `extraction_validation_results`

One row per validation check or per candidate validation summary.

Purpose:

- make failed validation debuggable;
- track exact reason candidates were rejected;
- evaluate models by validation failure type.

Recommended fields:

```ts
export const extractionValidationResults = pgTable('extraction_validation_results', {
  id: uuid('id').primaryKey().defaultRandom(),
  candidateId: uuid('candidate_id').references(() => extractionCandidates.id),
  candidateEvidenceId: uuid('candidate_evidence_id').references(() => extractionCandidateEvidence.id),

  checkName: varchar('check_name', { length: 100 }).notNull(),
  // source_exists | quote_exact_match | quote_offsets_match | source_type_valid |
  // not_duplicate | domain_valid | score_range_valid | sensitivity_gate |
  // promotion_transaction | duplicate_promotion_lock | validation_loop_circuit_breaker

  status: varchar('status', { length: 50 }).notNull(),
  // pass | fail | warning | skipped | circuit_breaker

  detail: text('detail'),
  metadataJson: jsonb('metadata_json'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

## Privacy and sensitivity gate

The Oracle observes workplace conversations. Some messages may contain employee-sensitive, personal, HR, interpersonal, compensation, health, or disciplinary material.

The extraction model must flag sensitive candidates, but the deterministic validator must enforce the policy.

If any of these are true:

- `containsSensitivePersonalData = true`;
- `containsSensitiveHRData = true`;
- `isPersonalConflict = true`;
- deterministic keyword/policy screening flags the candidate as sensitive;

then the candidate must not become normal operational truth.

Required behavior:

1. Mark the candidate `rejected_sensitive` or `quarantined_sensitive`.
2. Do not promote it to `claims`.
3. Do not show it in the standard admin claim-review queue.
4. Do not include it in employee-facing retrieval.
5. Preserve only the minimum metadata needed for audit/debug, under stricter access control.
6. Write an `extraction_validation_results` row with `checkName = 'sensitivity_gate'`.

Sensitive material may be reviewed only in a restricted owner/super-admin view if such a view is intentionally built. It must not be visible to general admins by default.

Do not allow the Oracle Brain to become a repository of employee-sensitive or personal-conflict information.

## Validation checks

The validator must be deterministic TypeScript code.

It must not ask an LLM whether the quote is valid.

### Required evidence validation

For every evidence row:

1. Source exists.
2. Source type matches a required source pointer.
3. Source content is loaded from the database.
4. `exactQuoteProvided` appears verbatim in source text, or matches an explicitly allowed normalization rule.
5. If `charStartProvided` / `charEndProvided` are present, they match the quote exactly.
6. If no offsets are provided, compute offsets with deterministic search.
7. Store validated offsets.
8. Reject ambiguous quotes that appear multiple times unless the model provided correct offsets.
9. Reject quotes spanning multiple messages unless the schema explicitly supports multi-message evidence.
10. Reject quotes from edited/deleted messages unless policy allows historical extraction.

### 11. The PII and Sensitivity Gate
The Oracle observes live employee chats and will inevitably ingest sensitive topics (medical leave, salaries, HR conflicts).
- The Zod schema for extraction must include `containsSensitiveHRData: boolean` or `isPersonalConflict: boolean`.
- If the model flags either as `true`, the deterministic validator MUST instantly route the candidate to a `rejected_sensitive` status.
- Sensitive candidates must NEVER be auto-approved and must be hidden from the standard admin review queue to protect employee privacy.

### `.includes()` is not enough

`sourceText.includes(quote)` is a useful first check, but production validation must also handle:

- exact index location;
- repeated quote ambiguity;
- source ID correctness;
- source type correctness;
- edited/deleted source records;
- document chunk page/sheet/row metadata;
- normalized whitespace policy;
- Unicode quote/apostrophe normalization policy;
- multiline quote boundaries.

### Normalization policy

Default rule: exact verbatim match only.

Allowed optional normalizations:

- CRLF vs LF line endings;
- repeated whitespace collapsed only if source is OCR or PDF text extraction;
- smart quotes vs straight quotes only if stored as normalized alternative;
- leading/trailing whitespace trim.

When normalized matching is used, store:

- `exactQuoteProvided` from the model;
- `normalizedQuote`;
- `validatedExactQuote` as the actual source substring;
- validation method.

Do not silently rewrite evidence quotes.

## Candidate promotion transaction (Concurrency Locked)
Trigger.dev workers are asynchronous. If two workers process two different channels that mention the exact same new rule simultaneously, they will create duplicate permanent claims. Promotion must be strictly locked.

For each validated candidate:
1. Begin Database Transaction.
2. Acquire an advisory lock or `SELECT ... FOR UPDATE` on a hashed representation of the claim candidate to block concurrent promotions.
3. Confirm candidate status is `validated` and not already promoted.
4. Check duplicate claim/candidate constraints. (If a duplicate is detected *during* the transaction due to another worker beating it, mark the current candidate as `duplicate` and append its evidence to the winning claim instead of inserting a new row).
5. Insert `claims`, `claim_top_domains`, and `claim_evidence` rows.
6. Commit.

## Idempotency

Every worker must be safe to retry.

Use stable hashes and unique constraints where possible:

- `sourceHash` for extraction batch source content;
- candidate hash from claim summary + domains + source evidence IDs + validated quote;
- evidence hash from source pointer + validated quote + offsets;
- synthesis job hash from section ID + approved claim IDs + current version ID.

If the same worker runs twice, it must not create duplicate permanent claims.

## Circuit breakers and infinite-loop prevention

Workers must not retry invalid quote extraction forever.

For each extraction batch, track validation attempts and consecutive exact-quote failures.

If a batch produces candidates but deterministic quote validation fails more than 3 times in a row for the same source batch, the worker must:

1. stop retrying that batch;
2. mark the batch status `failed_validation_loop`;
3. mark affected candidates/evidence `failed_validation_loop`;
4. insert an `extraction_validation_results` row with `checkName = 'validation_loop_circuit_breaker'` and `status = 'circuit_breaker'`;
5. store enough metadata to debug the loop: route ID, model run IDs, source hash, failed quote strings, source IDs, and retry count;
6. mark the source messages/chunks as failed or needs-admin-review according to worker policy;
7. move on to the next batch.

Do not escalate automatically to a frontier model after repeated quote failures. Exact quote failure usually means the model is paraphrasing or the source chunk is wrong, not that the model needs more intelligence.

Allowed exception: one structured repair attempt may be made with a cheap/balanced route if the failure is clearly schema formatting rather than quote hallucination. After that, trip the circuit breaker.

## Group-chat semantics

The extraction schema must distinguish group-chat stance:

- `stated`: employee states an operational rule/fact;
- `confirmed`: another employee confirms or agrees;
- `challenged`: another employee says the statement is wrong or incomplete;
- `refined`: another employee narrows or modifies the statement;
- `exception_introduced`: another employee describes a case where the rule differs;
- `ambiguity_revealed`: the exchange shows process uncertainty but no clear new rule.

Do not flatten a group conversation into isolated single-speaker facts.

Example:

```text
Employee A: We always send that to China after licensor approval.
Employee B: Not always. For Walmart seasonal, sourcing sees it earlier.
```

Correct extraction:

- candidate general process claim from Employee A;
- candidate exception claim from Employee B;
- possible contradiction/refinement relationship;
- gap asking when the Walmart seasonal exception applies.

## Triage rules

Auto-approval should be conservative.

A candidate may be auto-approved only if all are true:

- privacy/sensitivity gate passes;
- exact quote validation passes;
- source is reliable;
- claim type is low risk;
- impact score is below the configured threshold;
- no contradiction is detected;
- no person is named as a bottleneck;
- no customer/licensor/legal/compliance risk is implied;
- not a duplicate;
- model route is approved for auto-approval.

Otherwise mark `pending_review` after promotion, or hold as `validated` candidate pending admin review depending on UI design.

## Admin review behavior

The admin review UI should show:

- candidate summary;
- proposed claim type;
- domains;
- stance;
- source message/document chunk;
- exact quote as validated;
- source text with highlighted quote;
- validation status;
- model route;
- model cost;
- risk flags;
- duplicate warnings;
- approve/promote/reject controls.

Admin rejection reasons should be structured:

- not operational;
- sensitive/personal material;
- bad quote;
- wrong source;
- duplicate;
- wrong domain;
- too vague;
- unsupported;
- person-blaming;
- customer/licensor risk;
- other.

These labels feed evals.

Sensitive rejected/quarantined candidates must not appear in this standard queue.

## Provenance vs. Corroboration

Validation in The Oracle is a two-step axis.

**1. Provenance Validation (Binary / Deterministic)**
The deterministic `.includes()` check. It proves the `exactQuote` physically exists in the source text. If this fails, the candidate is destroyed.

**2. Corroboration Tiers (Strength of Trust)**
If provenance passes, the claim is assigned a Corroboration Tier. Corroboration measures operational truth, not just quoting accuracy. A single claim might have 10 evidence rows (1 person repeating it 10 times) but still have low corroboration.

- `single_source_observed`: One employee mentioned it. Treated as anecdotal.
- `multi_source_corroborated`: Mentioned by 2+ independent employees in different contexts.
- `system_verified`: Supported by a direct Coldlion ERP data export or API read.
- `admin_certified`: Albert manually reviewed and locked the claim as ground truth.

**Impact:** Low corroboration claims (`single_source_observed`) should trigger the Interview model to ask follow-up questions to other departments. High impact claims require `multi_source_corroborated` or `admin_certified` status before the Synthesis role is allowed to update the official Brain section.

---

## Worker retrofit acceptance criteria

The extraction worker retrofit is complete only when:

- LLM output is stored in staging tables before any permanent claim insert;
- sensitive/personal candidates are blocked from normal promotion and normal admin queues;
- permanent claims are created only by the promotion transaction;
- promotion uses locking or an equivalent transaction-safe duplicate guard;
- exact quote validation records offsets and validation method;
- invalid candidates are preserved for debugging/review;
- duplicate worker retries do not create duplicate claims;
- validation loops trip a circuit breaker instead of retrying forever;
- `model_runs`, `job_runs`, and `oracle_context_packs` are linked;
- claim extraction evals can compute validation failure rate by model route;
- existing admin claims dashboard still works for promoted claims.
