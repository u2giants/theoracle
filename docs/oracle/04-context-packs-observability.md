# Context Packs, Model Runs, Cache Metrics, and Observability

Status: mandatory implementation target.

The Oracle must be able to explain not only why it believes an operational claim, but also how the AI call that produced or synthesized the claim was assembled.

## Core rule

Every model call must produce a durable audit trail:

- what task was attempted;
- which route/provider/model was used;
- which prompt version and schema version were used;
- which messages, chunks, claims, gaps, and contradictions were included;
- which context was stable, retrieved, or dynamic;
- whether prompt/context caching worked;
- how many tokens and dollars were spent;
- whether structured validation passed;
- whether retry/fallback was used.

## Why context packs exist

If the Oracle hallucinates or misses an obvious fact, there are several possible causes:

- the model was weak;
- the prompt was bad;
- the output schema was ambiguous;
- retrieval found the wrong context;
- retrieval missed the right evidence;
- the context was too large or noisy;
- the cache strategy changed the prompt layout;
- the validator was too permissive;
- the fallback route changed behavior.

Without context packs, we are guessing.

With context packs, Albert can inspect exactly what the model saw.

## Required tables

### `oracle_context_packs`

One row per compiled model-call context.

Recommended fields:

```ts
export const oracleContextPacks = pgTable('oracle_context_packs', {
  id: uuid('id').primaryKey().defaultRandom(),

  taskType: varchar('task_type', { length: 100 }).notNull(),
  routeId: varchar('route_id', { length: 150 }).notNull(),
  promptVersion: varchar('prompt_version', { length: 100 }).notNull(),
  schemaVersion: varchar('schema_version', { length: 100 }),

  stablePrefixHash: varchar('stable_prefix_hash', { length: 255 }).notNull(),
  semiStableContextHash: varchar('semi_stable_context_hash', { length: 255 }),
  retrievedContextHash: varchar('retrieved_context_hash', { length: 255 }),
  dynamicInputHash: varchar('dynamic_input_hash', { length: 255 }).notNull(),
  toolSchemaHash: varchar('tool_schema_hash', { length: 255 }),
  outputSchemaHash: varchar('output_schema_hash', { length: 255 }),

  approximateTokenCount: integer('approximate_token_count'),
  stableTokenEstimate: integer('stable_token_estimate'),
  retrievedTokenEstimate: integer('retrieved_token_estimate'),
  dynamicTokenEstimate: integer('dynamic_token_estimate'),

  includedMessageIds: jsonb('included_message_ids'),
  includedDocumentChunkIds: jsonb('included_document_chunk_ids'),
  includedClaimIds: jsonb('included_claim_ids'),
  includedGapIds: jsonb('included_gap_ids'),
  includedContradictionIds: jsonb('included_contradiction_ids'),
  includedBrainSectionIds: jsonb('included_brain_section_ids'),

  retrievalPlanId: uuid('retrieval_plan_id'),
  selectedDomains: jsonb('selected_domains'),
  selectedSourceTypes: jsonb('selected_source_types'),
  selectedDocumentClasses: jsonb('selected_document_classes'),
  selectedProcessStages: jsonb('selected_process_stages'),
  selectedSystems: jsonb('selected_systems'),

  inclusionReasonJson: jsonb('inclusion_reason_json'),
  compiledBlocksJson: jsonb('compiled_blocks_json'),

  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

Store hashes and IDs by default, not full sensitive prompt text. Full prompt capture is handled by `model_run_payloads` below and must be short-lived, admin-only, and disabled where privacy risk is too high.

### `model_run_usage_details`

One row per model run with normalized usage and provider-native metadata.

Recommended fields:

```ts
export const modelRunUsageDetails = pgTable('model_run_usage_details', {
  id: uuid('id').primaryKey().defaultRandom(),
  modelRunId: uuid('model_run_id').references(() => modelRuns.id).notNull(),
  contextPackId: uuid('context_pack_id').references(() => oracleContextPacks.id),

  routeId: varchar('route_id', { length: 150 }).notNull(),
  routeReason: text('route_reason'),
  providerRequestId: varchar('provider_request_id', { length: 255 }),

  inputTokens: integer('input_tokens'),
  cachedInputTokens: integer('cached_input_tokens'),
  cacheWriteTokens: integer('cache_write_tokens'),
  outputTokens: integer('output_tokens'),
  reasoningTokens: integer('reasoning_tokens'),

  totalCostUsd: numeric('total_cost_usd', { precision: 12, scale: 6 }),
  latencyMs: integer('latency_ms'),

  validationStatus: varchar('validation_status', { length: 50 }),
  validationErrors: jsonb('validation_errors'),

  retryOfModelRunId: uuid('retry_of_model_run_id'),
  fallbackFromRouteId: varchar('fallback_from_route_id', { length: 150 }),
  fallbackReason: text('fallback_reason'),

  providerUsageJson: jsonb('provider_usage_json'),
  providerResponseMetadataJson: jsonb('provider_response_metadata_json'),

  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

### `provider_cached_content`

Used primarily for Vertex explicit context caching, but designed generically.

Recommended fields:

```ts
export const providerCachedContent = pgTable('provider_cached_content', {
  id: uuid('id').primaryKey().defaultRandom(),

  provider: varchar('provider', { length: 50 }).notNull(),
  routeId: varchar('route_id', { length: 150 }),
  providerResourceName: varchar('provider_resource_name', { length: 500 }).notNull(),

  sourceType: varchar('source_type', { length: 50 }).notNull(),
  // document | document_group | transcript_batch | prompt_prefix | other

  sourceDocumentId: uuid('source_document_id'),
  sourceHash: varchar('source_hash', { length: 255 }).notNull(),
  stablePrefixHash: varchar('stable_prefix_hash', { length: 255 }),

  tokenCount: integer('token_count'),
  ttlSeconds: integer('ttl_seconds'),
  expiresAt: timestamp('expires_at'),

  status: varchar('status', { length: 50 }).default('active').notNull(),
  // active | expired | deleted | failed

  metadataJson: jsonb('metadata_json'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
  deletedAt: timestamp('deleted_at'),
});
```

### `model_run_payloads`

Short-lived debugging table or Supabase Storage-backed payload log for exact prompts/responses.

Purpose:

- hashes are excellent for grouping and cache debugging;
- hashes are not enough when a model goes rogue and Albert needs to inspect the exact payload;
- therefore extraction and synthesis jobs may store exact serialized model payloads temporarily.

Recommended fields if using a table:

```ts
export const modelRunPayloads = pgTable('model_run_payloads', {
  id: uuid('id').primaryKey().defaultRandom(),
  modelRunId: uuid('model_run_id').references(() => modelRuns.id).notNull(),
  contextPackId: uuid('context_pack_id').references(() => oracleContextPacks.id),

  payloadKind: varchar('payload_kind', { length: 50 }).notNull(),
  // request | response | validation_error

  storageMode: varchar('storage_mode', { length: 50 }).notNull(),
  // db_json | supabase_storage

  payloadJson: jsonb('payload_json'),
  storageBucket: varchar('storage_bucket', { length: 100 }),
  storagePath: text('storage_path'),

  containsSensitiveData: boolean('contains_sensitive_data').default(false).notNull(),
  redactionApplied: boolean('redaction_applied').default(false).notNull(),
  expiresAt: timestamp('expires_at').notNull(),
  deletedAt: timestamp('deleted_at'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

Payload logging rules:

- default TTL is 7 days;
- payloads must be admin-only and service-role-only;
- payload logging is for extraction, synthesis, validation repair, and provider debugging;
- routine employee chat payload logging should be disabled by default or heavily redacted;
- sensitive HR/personal-conflict candidates must not be stored in general debug payload views;
- expired payloads must be deleted by scheduled cleanup;
- hashes in `oracle_context_packs` remain durable after payload deletion.

## Required `model_runs` enhancements

The existing `model_runs` table should remain as the main row. Add columns or companion rows so the following are trackable:

- provider;
- model;
- route ID;
- task type;
- prompt version;
- schema version;
- context pack ID;
- input tokens;
- cached input tokens;
- cache write tokens;
- output tokens;
- reasoning tokens;
- cost;
- latency;
- success;
- validation status;
- retry/fallback status;
- provider request ID;
- provider-native raw usage JSON.

Do not destroy old `model_runs` data. Add migrations.

## Cache metrics by provider

### Anthropic

Log native fields where exposed:

- input tokens;
- cache creation/write tokens;
- cache read tokens;
- output tokens;
- provider request ID;
- raw usage JSON.

Also log:

- cache strategy used;
- number and location of cache breakpoints;
- stable prefix hash;
- whether the call used automatic caching, explicit breakpoints, or both.

### Google Vertex AI / Gemini

Log native fields where exposed:

- prompt/input tokens;
- cached content token count;
- output tokens;
- provider request/resource metadata;
- cached content resource name if explicit caching is used;
- TTL and expiration.

Also log:

- whether caching was implicit or explicit;
- source hash of cached document/context;
- cache lookup hit/miss where inferable;
- explicit cache creation cost and later cache read savings when computable.

### OpenAI

Log native fields where exposed:

- input tokens;
- cached tokens;
- output tokens;
- reasoning tokens if available;
- prompt cache key/retention if used;
- provider request ID;
- raw usage JSON.

Also log:

- stable prefix hash;
- prompt cache key;
- cache retention mode;
- whether the prompt likely exceeded cache threshold.

## Cost metrics

The dashboards should report:

- cost per valid claim;
- cost per approved claim;
- cost per promoted claim;
- cost per useful gap;
- cost per accepted Brain section update;
- cost per failed validation;
- retry cost by model route;
- fallback cost by model route;
- cache savings estimate by provider/task;
- token spend by task type.

Do not optimize only for lowest raw token price.

A cheap model that creates invalid candidates is expensive.

An expensive model that succeeds in one pass may be cheaper per accepted result.

## Quality metrics

Track by route and task:

- structured output validity;
- exact quote validity;
- normalized quote match rate;
- failed quote validation rate;
- duplicate candidate rate;
- wrong-domain rate;
- false contradiction rate;
- admin rejection reason distribution;
- retry rate;
- fallback rate;
- Albert usefulness rating.

## Admin dashboards to add

The existing admin dashboards should be expanded with these views.

### AI runs dashboard

Show:

- task type;
- route;
- provider;
- model;
- success/failure;
- validation status;
- token counts;
- cached token counts;
- cost;
- latency;
- retry/fallback;
- link to context pack.

### Context pack viewer

Show:

- included message IDs;
- included document chunk IDs;
- included claim IDs;
- included gap/contradiction IDs;
- hashes;
- token estimates;
- reason each item was included;
- retrieval plan filters and broadening steps;
- short-lived payload link if still available and user has permission.

Do not show full sensitive source text by default. Provide admin-only drilldown. Sensitive HR/personal-conflict payloads require stricter access than normal admin views.

### Cache dashboard

Show by provider/route/task:

- cache read tokens;
- cache write tokens;
- cache hit ratio where available;
- cached content resources active/expired;
- estimated cache savings;
- top prompts with unstable prefixes.

### Extraction candidate dashboard

Show:

- candidates by status;
- validation failures;
- exact quote failures;
- duplicate warnings;
- model route;
- source highlight.

Sensitive rejected candidates must not appear in the standard queue.

### AI Cache Health Dashboard (Non-Technical UX)
Albert needs to know if caching is broken without reading JSON. Build a traffic-light dashboard:

| Metric | Good (Green) | Warning (Yellow) | Bad (Red) |
| :--- | :--- | :--- | :--- |
| Cached input % | 60–90%+ | 25–60% | <25% |
| Repeated-prefix hit rate | 70%+ | 40–70% | <40% |
| Prompt prefix stability | Stable hash reused | Many variants | Every call unique |
| Explicit Cache Reuse | 3+ uses/cache | 2 uses/cache | 1 use/cache |

Add a "Run Cache Test" button that runs the same extraction route twice with a dummy message and reports: "Success: Second call reused X cached tokens" or "Fail: 0 tokens reused. Prefix likely changed."

### The 7-Day Raw Payload Log
Hashes (`stablePrefixHash`) are great for grouping, but if an AI goes rogue at 3 AM, looking at a hash doesn't tell Albert what the prompt actually said.
- Introduce a `model_run_payloads` table (or Supabase Storage bucket) that stores the exact, raw text payload sent to the LLM for extraction and synthesis.
- Mandate a strict **7-day Time-To-Live (TTL)**. This gives you one week to debug a hallucination by looking at the exact text, after which it safely auto-deletes to save database costs.

## Stable prefix debugging

A low cache hit rate should trigger investigation.

The system should compare hashes:

- stablePrefixHash;
- toolSchemaHash;
- outputSchemaHash;
- semiStableContextHash;
- retrievedContextHash;
- dynamicInputHash.

If stablePrefixHash changes too often, likely causes are:

- timestamp accidentally added to system prompt;
- request ID inserted too early;
- retrieved context placed before stable instructions;
- tool definitions generated in nondeterministic order;
- schema property order changes;
- model route injecting volatile config into stable prefix.

## Acceptance criteria

Observability retrofit is complete only when:

- every model call has a `model_runs` row;
- every model call has an `oracle_context_packs` row;
- every model call has normalized usage details;
- cache metrics are captured where provider exposes them;
- explicit Vertex cached content is tracked in Postgres;
- short-lived payload logging exists for extraction/synthesis debugging with 7-day TTL;
- sensitive payloads are excluded from standard admin views;
- candidate validation failures are measurable by route;
- admin can inspect cost and validation outcomes;
- no production AI call is invisible.
