# Candidate-Before-Claim Validation Pipeline

Status: mandatory implementation target.

This document defines the hardened extraction pipeline for The Oracle.

## Core rule

No AI output becomes official operational truth directly.

The AI may propose claim candidates. It may not create permanent claims.

All extraction output must pass through:

1. staging;
2. deterministic validation;
3. duplicate/overlap checks;
4. review triage;
5. transactional promotion.

Only after those steps may the system write to permanent `claims`, `claim_domains`, and `claim_evidence`.

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
  // message_segment | document_chunk | document_page | transcript_segment

  status: varchar('status', { length: 50 }).default('pending_model').notNull(),
  // pending_model | model_complete | validation_complete | promoted | failed | skipped

  sourceMessageIds: jsonb('source_message_ids'),
  sourceDocumentChunkIds: jsonb('source_document_chunk_ids'),
  sourceHash: varchar('source_hash', { length: 255 }).notNull(),

  rawModelOutput: jsonb('raw_model_output'),
  validationSummary: jsonb('validation_summary'),
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
  // pending_validation | validation_failed | validated | duplicate | promoted | rejected

  claimType: varchar('claim_type', { length: 100 }).notNull(),
  summary: text('summary').notNull(),
  impactScore: integer('impact_score').notNull(),
  confidenceScore: integer('confidence_score'),

  domains: jsonb('domains').notNull(),
  stance: varchar('stance', { length: 50 }),
  // stated | confirmed | challenged | refined | exception_introduced | ambiguity_revealed

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
  // pending | exact_match | normalized_match | failed | ambiguous

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
  // not_duplicate | domain_valid | score_range_valid | promotion_transaction

  status: varchar('status', { length: 50 }).notNull(),
  // pass | fail | warning | skipped

  detail: text('detail'),
  metadataJson: jsonb('metadata_json'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

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

## Candidate promotion transaction

Promotion must happen inside a database transaction.

For each validated candidate:

1. Re-read candidate and evidence rows with row locks where practical.
2. Confirm candidate status is `validated` and not already promoted.
3. Check duplicate claim/candidate constraints.
4. Insert `claims` row.
5. Insert `claim_domains` rows.
6. Insert one or more `claim_evidence` rows using validated evidence data.
7. Insert suggested `gaps` only after claim insert succeeds.
8. Update candidate `promotedToClaimId`, `status = promoted`, `promotedAt`.
9. Update batch summary.
10. Commit.

If any step fails, rollback. The database must never contain a permanent claim without evidence.

## Idempotency

Every worker must be safe to retry.

Use stable hashes and unique constraints where possible:

- `sourceHash` for extraction batch source content;
- candidate hash from claim summary + domains + source evidence IDs + validated quote;
- evidence hash from source pointer + validated quote + offsets;
- synthesis job hash from section ID + approved claim IDs + current version ID.

If the same worker runs twice, it must not create duplicate permanent claims.

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

## Worker retrofit acceptance criteria

The extraction worker retrofit is complete only when:

- LLM output is stored in staging tables before any permanent claim insert;
- permanent claims are created only by the promotion transaction;
- exact quote validation records offsets and validation method;
- invalid candidates are preserved for debugging/review;
- duplicate worker retries do not create duplicate claims;
- `model_runs`, `job_runs`, and `oracle_context_packs` are linked;
- claim extraction evals can compute validation failure rate by model route;
- existing admin claims dashboard still works for promoted claims.
