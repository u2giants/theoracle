# ORACLE AI ARCHITECTURE IMPLEMENTATION PROMPT

Status: historical planning material. This file is useful background for prompt-cache hygiene, module boundaries, and traceability goals, but the current implementation plan lives in `docs/oracle/00-buildout-index.md` through `docs/oracle/07-knowledge-segmentation.md`.

If this file conflicts with the current `docs/oracle/` packet, keep the product boundaries and traceability requirements here, but follow `docs/oracle/` for provider selection, route IDs, candidate-before-claim validation, retrieval planning, cache lifecycle, and implementation order. In particular, the OpenRouter-centered production guidance below is superseded for the AI retrofit; OpenRouter remains a legacy fallback path, not the target production architecture.

**Project:** POP Creations / Spruce Line Enterprise Knowledge Graph  
**System Name:** The Oracle  
**Target Agent:** Claude Code / AI coding agent  
**Primary Stack:** TypeScript monorepo, Next.js App Router, Supabase Cloud PostgreSQL, Drizzle ORM, Vercel AI SDK, OpenRouter, Trigger.dev Cloud v3  
**Purpose of This Prompt:** Implement the AI architecture of The Oracle in the most token-efficient, cache-aware, traceable, production-ready way possible without sacrificing quality.

---

## 0. Read This First

You are implementing the AI architecture for **The Oracle**, an evidence-backed Enterprise Knowledge Graph for POP Creations / Spruce Line.

You are **not** building a generic chatbot.
You are **not** building a project-management system.
You are **not** building a ClickUp clone.
You are **not** building a task tracker.
You are **not** building an autonomous hidden-agent framework.

The Oracle is a living company brain. It observes conversations, ingests documents, extracts operational claims, links claims to evidence, identifies gaps and contradictions, synthesizes versioned brain sections, and lets Albert ask operational questions with traceable answers.

The core product requirement is:

> The Oracle must be able to answer: "Why does it believe this?"  
> And the system must answer with specific employees, messages, documents, chunks, quotes, claims, model runs, and brain section versions.

This prompt is an **AI architecture addendum** to the master development specification. The master specification remains authoritative. If this prompt appears to conflict with the master spec, follow the master spec and implement the safest minimal interpretation.

---

## 1. Non-Negotiable Product Boundaries

Follow these rules exactly.

### 1.1 Do Not Reinterpret the Product

The Oracle is:

- an AI-powered Business Intelligence System
- a claim/evidence/synthesis pipeline
- a living Enterprise Knowledge Graph
- an operational-reality discovery system
- a traceable company brain

The Oracle is not:

- a task manager
- a ticket system
- a due-date manager
- a workflow assignment tool
- a project-management application
- a private unstructured AI memory

If implementation work starts drifting toward assigning normal operational tasks, changing due dates, managing project execution, or building a ticket board, stop and reassess.

### 1.2 Technology Rules

Use:

- TypeScript
- Next.js App Router
- Tailwind CSS
- shadcn/ui
- lucide-react
- Supabase Cloud PostgreSQL
- Supabase Auth
- Supabase Storage
- Supabase Realtime
- pgvector
- Drizzle ORM
- Vercel AI SDK
- OpenRouter
- Trigger.dev Cloud v3

Do not introduce:

- Python
- LangChain
- LangGraph
- Celery
- Aegra
- Docker
- self-managed VPS services
- unapproved agent frameworks
- unstructured local long-term AI memory
- durable operational knowledge stored in flat Markdown files, Redis, JSON dumps, or local files

Durable knowledge belongs in PostgreSQL.

### 1.3 Source of Truth Rule

PostgreSQL is the source of truth.

Every durable operational object must be stored in Postgres, including:

- messages
- documents
- document chunks
- claims
- claim evidence
- gaps
- contradictions
- brain sections
- brain section versions
- model runs
- job runs
- AI context packs
- model usage details
- validation results

No operational claim may exist only inside an LLM response, a Markdown file, a Redis cache, a frontend state object, or an agent scratchpad.

---

## 2. The AI Architecture Goal

Build a centralized AI orchestration layer that minimizes cost and latency while preserving evidence quality, extraction accuracy, contradiction accuracy, synthesis usefulness, and auditability.

The optimization target is not:

- fewest tokens per request
- cheapest individual model call
- maximum prompt-cache usage at any cost
- largest possible context window

The optimization target is:

> **Lowest cost per validated, useful, evidence-backed result.**

For The Oracle, a successful AI call usually means one of these:

- a valid extracted claim with exact evidence
- a valid document claim linked to a document chunk
- a useful gap with a clear reason
- a possible contradiction with real supporting claim IDs
- a synthesized brain section version where every material statement maps to approved claim IDs
- a live chat answer that uses tools and does not hallucinate unsupported operational facts

Token efficiency must never weaken traceability.

---

## 3. Central Rule: No Direct Ad-Hoc LLM Calls

No route handler, Trigger.dev worker, service file, UI component, or utility should call OpenRouter directly.

All model calls must go through a centralized TypeScript AI orchestration layer.

Implement these modules:

```text
OracleAIClient
ContextCompiler
ModelRouter
ProviderCapabilityMatrix
PromptTemplateRegistry
StructuredOutputValidator
UsageLogger
CostTracker
EvalRunner
RetrievalPlanner
PromptCacheManager
```

The architecture must make every AI call:

- typed
- measurable
- retry-aware
- provider-aware
- schema-validated when appropriate
- prompt-cache-aware when appropriate
- traceable to database records
- debuggable from Admin Dashboard later

---

## 4. Required Module Responsibilities

### 4.1 OracleAIClient

`OracleAIClient` is the only approved gateway for model calls.

It must:

- accept a typed task request
- call the `ContextCompiler`
- call the `ModelRouter`
- choose the correct Vercel AI SDK primitive
- call OpenRouter through the configured provider adapter
- validate structured outputs
- record context packs
- record model runs
- record usage details
- calculate cost where possible
- handle retry/escalation policy
- return typed results to the caller

Approved high-level method shape:

```ts
oracleAI.generateObject<T>(request: OracleObjectTaskRequest<T>): Promise<OracleObjectTaskResult<T>>;
oracleAI.streamChat(request: OracleChatTaskRequest): Promise<OracleChatStreamResult>;
oracleAI.embed(request: OracleEmbeddingRequest): Promise<OracleEmbeddingResult>;
```

Do not expose raw provider responses to random application code. Normalize them.

### 4.2 ContextCompiler

The `ContextCompiler` deterministically assembles every AI request.

It must split context into these sections, in this order:

1. Stable Prefix
2. Semi-Stable Context
3. Retrieved Context
4. Dynamic Request
5. Output Contract

This ordering is critical for prompt caching and sanity.

#### Stable Prefix

Stable prefix may include:

- Oracle role and identity
- psychological safety rules
- traceability rules
- evidence rules
- durable output rules
- stable task instructions
- stable tool definitions
- stable Zod/JSON schema descriptions
- stable formatting rules
- stable business rules that rarely change

Stable prefix must not include:

- timestamps
- request IDs
- current user message
- current document chunk
- current channel transcript
- current error output
- current retrieval results
- selected file lists
- current employee-specific one-off details
- volatile model routing notes

Stable prefix should be byte-for-byte identical across many repeated calls of the same task type and prompt version.

#### Semi-Stable Context

Semi-stable context may include:

- knowledge domain enum
- claim type definitions
- extraction policy
- review policy
- contradiction policy
- brain section definitions
- reusable task taxonomy
- stable company workflow categories
- schema version notes

This content changes occasionally. Hash it separately.

#### Retrieved Context

Retrieved context may include:

- recent messages
- selected document chunks
- approved claims
- claim evidence quotes
- relevant gaps
- relevant contradictions
- current employee profile
- current channel metadata
- relevant brain section excerpts

Retrieved context must be small, relevant, and justified.

Every retrieved item should have a reason for inclusion.

#### Dynamic Request

Dynamic request includes the actual current thing being processed:

- current user chat message
- current document chunk
- current transcript segment
- current synthesis section
- current validation failure
- current error logs
- current tool result

Dynamic content belongs near the end, after the stable reusable prefix.

#### Output Contract

Output contract includes:

- Zod schema name/version
- JSON schema
- tool call contract
- validation requirements
- required IDs
- exact quote rules
- fallback behavior

Keep output schemas stable whenever possible.

### 4.3 Context Pack Logging

Every compiled context must produce a database record.

Create a table such as `ai_context_packs` if not already present.

Required fields:

```ts
taskType
promptVersion
schemaVersion
stablePrefixHash
semiStableContextHash
retrievedContextHash
dynamicInputHash
toolSchemaHash
outputSchemaHash
approximateTokenCount
includedMessageIds
includedClaimIds
includedDocumentChunkIds
includedGapIds
includedContradictionIds
inclusionReasonJson
createdAt
```

The purpose is to answer:

- What did the model see?
- Why was this context included?
- What changed between this call and the previous one?
- Did the stable prefix remain stable?
- Did prompt caching have a fair chance to work?

Do not store sensitive full prompt text unnecessarily if hashes and linked database IDs provide enough traceability. If storing full prompt text is useful for debugging, make it configurable and access-controlled.

### 4.4 ModelRouter

The `ModelRouter` chooses the cheapest model likely to produce a validated useful result.

It must route by:

- task type
- risk level
- required capability
- context size
- need for structured output
- need for streaming
- need for vision
- need for reasoning
- prior validation failure
- retry count
- current provider availability

Do not hard-code one model everywhere.

#### Cheap/Fast Model Tasks

Use cheaper/faster models for:

- message classification
- document chunk classification
- initial claim extraction
- domain tagging
- duplicate claim detection
- simple gap prioritization
- metadata extraction
- title generation
- low-risk summaries

#### Stronger Model Tasks

Use stronger models for:

- brain synthesis
- complicated contradiction analysis
- high-risk claim extraction
- cross-department workflow reasoning
- admin-facing explanations
- answers where evidence must be synthesized across many claims

#### Reasoning Model Tasks

Use reasoning-capable models only when justified:

- difficult contradictions
- synthesis that cheaper models fail
- multi-step operational reasoning
- architecture decisions
- high-impact disputed process logic

Do not use expensive reasoning models for routine extraction.

### 4.5 ProviderCapabilityMatrix

Create a configuration-driven provider/model capability matrix.

For every model, track:

```ts
provider
modelId
supportsToolCalling
supportsStructuredOutput
supportsStreaming
supportsVision
supportsReasoning
supportsVisibleReasoning
supportsReasoningSummaries
supportsPromptCaching
supportsExplicitCacheControl
supportsEmbeddings
maxContextTokens
costInputPerMillion
costOutputPerMillion
costCachedInputPerMillion
recommendedTaskTypes
fallbackModelIds
notes
```

Do not assume all OpenRouter models behave the same.
Do not assume reasoning behavior is consistent across providers.
Do not assume prompt caching worked unless usage data confirms it.
Do not assume structured output quality is equal across models.

Model capability data must live in config, not scattered through application logic.

### 4.6 PromptTemplateRegistry

Store prompt templates centrally.

Each prompt template must have:

```ts
taskType
promptVersion
stablePrefix
semiStableInstructions
schemaVersion
expectedOutputMode
lastUpdatedAt
```

Do not embed long prompts inside random worker files.
Do not duplicate prompts across route handlers.
Do not mutate prompt text ad hoc at runtime.

### 4.7 StructuredOutputValidator

All extraction, contradiction, gap, and synthesis jobs must use strict structured output.

Use Vercel AI SDK `generateObject` or equivalent schema-validated generation for:

- claim extraction
- document claim extraction
- contradiction decisions
- gap creation
- synthesis diffs
- model-router decisions where useful

Use `streamText` only for:

- live Oracle chat
- admin-facing conversational responses

Every structured output must be validated server-side before writing to Postgres.

### 4.8 UsageLogger and CostTracker

The Oracle must be able to inspect AI economics later.

Every model call must log:

```ts
taskType
provider
model
routeReason
promptVersion
schemaVersion
contextPackId
stablePrefixHash
toolSchemaHash
outputSchemaHash
retrievedContextHash
dynamicInputHash
inputTokens
cachedInputTokens
cacheWriteTokens
outputTokens
reasoningTokens
totalCostUsd
latencyMs
success
validationStatus
retryCount
error
providerRequestId
createdAt
```

Extend `model_runs` or create `model_run_usage_details`.

The existing `model_runs` table is not enough for serious prompt-cache and routing optimization. Add a related table if cleaner.

---

## 5. Recommended Database Additions

Add these tables unless an equivalent already exists.

### 5.1 AI Context Packs

```ts
export const aiContextPacks = pgTable(
  'ai_context_packs',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    taskType: varchar('task_type', { length: 100 }).notNull(),
    promptVersion: varchar('prompt_version', { length: 50 }),
    schemaVersion: varchar('schema_version', { length: 50 }),

    stablePrefixHash: varchar('stable_prefix_hash', { length: 255 }).notNull(),
    semiStableContextHash: varchar('semi_stable_context_hash', { length: 255 }),
    retrievedContextHash: varchar('retrieved_context_hash', { length: 255 }),
    dynamicInputHash: varchar('dynamic_input_hash', { length: 255 }),
    toolSchemaHash: varchar('tool_schema_hash', { length: 255 }),
    outputSchemaHash: varchar('output_schema_hash', { length: 255 }),

    approximateTokenCount: integer('approximate_token_count'),

    includedMessageIds: jsonb('included_message_ids'),
    includedClaimIds: jsonb('included_claim_ids'),
    includedDocumentChunkIds: jsonb('included_document_chunk_ids'),
    includedGapIds: jsonb('included_gap_ids'),
    includedContradictionIds: jsonb('included_contradiction_ids'),

    inclusionReasonJson: jsonb('inclusion_reason_json'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    taskCreatedIdx: index('ai_context_packs_task_created_idx').on(t.taskType, t.createdAt),
    stablePrefixIdx: index('ai_context_packs_stable_prefix_idx').on(t.stablePrefixHash),
  })
);
```

### 5.2 Model Run Usage Details

```ts
export const modelRunUsageDetails = pgTable(
  'model_run_usage_details',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    modelRunId: uuid('model_run_id').references(() => modelRuns.id).notNull(),
    contextPackId: uuid('context_pack_id').references(() => aiContextPacks.id),

    routeReason: text('route_reason'),
    providerRequestId: varchar('provider_request_id', { length: 255 }),

    cachedInputTokens: integer('cached_input_tokens'),
    cacheWriteTokens: integer('cache_write_tokens'),
    reasoningTokens: integer('reasoning_tokens'),

    validationStatus: varchar('validation_status', { length: 50 }),
    validationErrors: jsonb('validation_errors'),

    retryOfModelRunId: uuid('retry_of_model_run_id'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    modelRunIdx: index('model_run_usage_details_model_run_idx').on(t.modelRunId),
    contextPackIdx: index('model_run_usage_details_context_pack_idx').on(t.contextPackId),
  })
);
```

### 5.3 Optional: Prompt Template Versions

If useful, add:

```ts
export const promptTemplateVersions = pgTable(
  'prompt_template_versions',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    taskType: varchar('task_type', { length: 100 }).notNull(),
    promptVersion: varchar('prompt_version', { length: 50 }).notNull(),
    stablePrefixHash: varchar('stable_prefix_hash', { length: 255 }).notNull(),
    outputSchemaHash: varchar('output_schema_hash', { length: 255 }),
    notes: text('notes'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    taskVersionUnique: uniqueIndex('prompt_template_versions_task_version_unique').on(t.taskType, t.promptVersion),
  })
);
```

Use this only if it improves auditing and does not add unnecessary complexity.

---

## 6. Prompt Caching Rules

Prompt caching matters, but do not bloat prompts just to chase cache thresholds.

The Oracle should get most of its AI savings from:

1. sending less irrelevant context
2. batching extraction intelligently
3. using strict schemas to reduce retries
4. routing simple tasks to cheaper models
5. caching stable prompts/schemas/tool definitions
6. caching file summaries and repo indexes
7. measuring actual cost per validated result

### 6.1 General Prompt Caching Rules

- Put stable content first.
- Put dynamic content last.
- Keep stable task prompts byte-identical across repeated calls.
- Keep tool definitions stable.
- Keep output schemas stable.
- Do not include timestamps in stable prompt sections.
- Do not include request IDs in stable prompt sections.
- Do not include current messages or retrieval results before stable content.
- Do not reorder stable sections unless the prompt version changes.
- Track cached tokens where available.
- If cache hit rate drops, identify which hash changed.

### 6.2 OpenAI

- Use automatic prompt caching where supported.
- Keep reusable content at the beginning of the prompt.
- Track `cached_tokens` or equivalent usage details.
- Do not assume every OpenAI-compatible route behaves identically through OpenRouter.

### 6.3 Anthropic / Claude

- Support explicit `cache_control` breakpoints.
- Put the breakpoint at the end of the largest stable reusable prefix.
- Do not place the breakpoint after current messages, current document chunks, retrieved claims, or other volatile content.
- Respect the provider's limit on cache breakpoints.
- Make cache TTL configurable where supported.

### 6.4 Gemini / Google

- Support implicit caching where available.
- Also support explicit cache configuration through the selected route/provider where required or beneficial.
- Verify with usage metrics, not assumptions.

### 6.5 OpenRouter

- Treat OpenRouter as a routing layer with model/provider-specific behavior.
- Use the provider capability matrix.
- Track cache read/write metrics returned by OpenRouter where available.
- Do not rely on sticky routing alone without measuring usage.

### 6.6 Qwen / Alibaba / DeepSeek / Moonshot / Kimi / Other Providers

- Treat caching behavior as provider-specific.
- Implement through the capability matrix.
- Do not hard-code folklore or assumptions.
- If explicit cache control is required, encode it only in provider adapter logic.

---

## 7. Task-Specific AI Context Rules

The Oracle has multiple AI workflows. Do not use one universal context strategy.

### 7.1 Live Oracle Chat

Live chat should be lean.

Include:

- master Oracle personality/system prompt
- current employee context
- current channel context
- recent conversation context
- highest-priority relevant gaps
- small number of strictly relevant approved claims
- tool definitions for deeper retrieval

Do not include:

- full Brain
- giant brain sections
- entire claim database
- unrelated document chunks
- old transcripts unless retrieved for a reason

Live chat should use `streamText`.

The Oracle should answer direct mentions immediately, but proactive interjections must remain tactful and rare.

Live chat must follow the master prompt rules:

- ask one question at a time
- do not blame employees
- investigate systems, handoffs, missing context, unclear ownership, and system limitations
- do not interrupt human-to-human conversation unnecessarily
- if disagreement appears, treat it as process ambiguity

### 7.2 Claim Extraction Worker

Claim extraction is one of the main token-cost centers.

Use strict structured output.

Batch messages by:

- channel
- employee
- conversation segment
- time window
- reply structure when available

Include:

- extraction rules
- claim schema
- knowledge domain enum
- group-chat semantics
- exact quote validation rules
- current transcript segment
- minimal surrounding context

Do not include:

- full Brain
- unrelated prior conversations
- unrelated claims unless needed for duplicate detection or contradiction detection

The extraction model must distinguish:

- claim stated
- claim confirmed
- claim challenged
- claim refined
- exception introduced
- process ambiguity revealed

Example behavior:

If Employee A says, "We always send that to China after licensor approval," and Employee B says, "Not always. For Walmart seasonal, sourcing sees it earlier," the system should produce:

- general process claim
- exception claim
- possible contradiction or refinement
- gap asking when the exception applies

Do not flatten group conversations into isolated single-speaker facts.

### 7.3 Exact Quote Validation

No claim should be approved unless its evidence quote is valid.

Backend validation must confirm:

- exact quote exists in the source message or document chunk
- source ID exists
- charStart and charEnd are plausible when provided
- source type matches required foreign key
- evidence source constraint is satisfied

If quote validation fails:

- do not auto-approve
- mark failed or pending review
- store validation error details

### 7.4 Document Ingestion and Document Claim Extraction

Documents must never be processed as one monolithic text blob.

Process document chunks.

Each chunk should preserve:

- page number
- sheet name
- row start/end
- bounding boxes where available
- raw extracted text
- content hash
- token count
- metadata

Document claim extraction should include:

- current chunk
- limited neighboring chunk context only when needed
- document metadata
- chunk metadata
- extraction schema

Claims extracted from documents must link to `document_chunks` through `claim_evidence`.

Do not link evidence only to the whole document.

### 7.5 Contradiction Watcher

The contradiction watcher must be retrieval-first, model-second.

Workflow:

1. New user message arrives.
2. Cheap vector retrieval searches approved claims.
3. If there are plausible candidate conflicts, call a model.
4. Model receives only the new message plus retrieved candidate claims.
5. If possible misalignment exists, create a `contradictions` row with status `possible`.
6. Decide whether to silently queue, create a gap, request admin review, or live interject.
7. Most possible contradictions should not cause live interjections.

Never send the whole claim database to an LLM.

Live interjection only when confidence and operational impact are very high, and settings allow it.

### 7.6 Curiosity Engine / Gap Creation

A gap is a durable curiosity object.

Create gaps when conversations reveal:

- unknown workflow
- workaround
- dependency
- exception
- system limitation
- unclear handoff
- ambiguous ownership
- contradictory understanding

A useful gap must include:

- question to ask
- why it matters
- target employee or department if known
- related claims or contradictions if known
- priority
- status

Gap generation should be schema-validated.

Do not generate vague questions. Prefer one tightly scoped operational question.

### 7.7 Brain Synthesis Worker

Brain synthesis is allowed to use a stronger model.

It should synthesize one section at a time.

Include:

- selected brain section
- current brain section version if relevant
- approved claims relevant to that section
- claim evidence summaries
- sectionClaims
- related open contradictions
- related gaps if relevant
- synthesis output schema

Do not include:

- unrelated claims
- entire transcript history
- unapproved claims as factual support
- unsupported brain content as fact

The model must output a structured diff.

Every material paragraph or bullet must map to approved claim IDs.

Backend validator must reject synthesis when:

- section ID does not exist
- claim ID does not exist
- any supporting claim is not approved
- material text contains unsupported named people, systems, customers, stages, departments, or process rules
- new gaps lack `whyItMatters`
- contradictions point to missing claim IDs

If validation fails:

- do not update `brain_sections.currentVersionId`
- save job failure details
- optionally save failed candidate output for admin inspection

---

## 8. Structured Output Rules

Use structured output for production AI tasks.

### 8.1 Use Structured Output For

- claim extraction
- document claim extraction
- contradiction analysis
- gap creation
- brain synthesis
- model router decisions
- classification tasks
- duplicate-claim detection

### 8.2 Use Streaming Text For

- live Oracle chat
- admin conversational assistance
- human-readable explanation responses

### 8.3 Do Not Rely on Raw Markdown JSON

Do not rely on raw Markdown JSON blocks unless the selected model lacks structured output support and there is no better fallback.

Production workflows must validate model outputs.

### 8.4 Validation and Repair

If structured output validation fails:

1. retry once with the same model using the validation error as feedback
2. if it fails again, escalate to a stronger model
3. if the stronger model fails, save job failure and require admin review

Do not blindly retry the same failed prompt multiple times.

---

## 9. Reasoning Mode Rules

Reasoning can be useful, but do not build compliance around visible chain-of-thought.

The system may configure reasoning where supported:

```ts
reasoning.enabled
reasoning.effort
reasoning.max_tokens
reasoning.exclude
```

Rules:

- Do not assume every model supports reasoning controls.
- Do not assume every model exposes reasoning text.
- Do not require visible chain-of-thought for audit.
- Do not log private chain-of-thought as a required system feature.
- Store reasoning summaries only where supported and useful.
- Track reasoning token cost where exposed.

For audit, rely on:

- inputs
- linked context IDs
- outputs
- tool calls
- claim IDs
- evidence IDs
- validation results
- model metadata
- prompt/schema versions
- usage metrics
- optional reasoning summary if supported

---

## 10. Retrieval Rules

Retrieval quality is more important than raw context size.

### 10.1 RetrievalPlanner

Build a `RetrievalPlanner` that selects context by task type.

It should retrieve:

- recent messages for chat
- candidate claims for contradiction analysis
- approved claims for synthesis
- document chunks for document Q&A/extraction
- open gaps for interviews
- section-specific claims for brain updates

Every retrieved item must have a reason for inclusion.

### 10.2 General Retrieval Principles

- Prefer exact relevant snippets over whole files.
- Prefer approved claims over raw messages when answering operational questions.
- Prefer source evidence when validating or explaining claims.
- Include tests and validation errors when fixing implementation code.
- Include recent context for chat, not old unrelated transcripts.
- Include call sites or dependency relationships only when changing code.

### 10.3 Context Budget Reduction Order

If context is too large, reduce it in this order:

1. Remove duplicate content.
2. Remove irrelevant tools.
3. Replace full files with relevant snippets.
4. Replace low-priority snippets with summaries.
5. Ask a cheap model to rank context by relevance.
6. Keep schemas, interfaces, tests, and exact error output before general background.
7. Escalate to a larger-context model only when compression would hurt quality.

Do not cut evidence requirements to save tokens.

---

## 11. Tool Calling Rules

Live Oracle chat may use tools.

Approved tools include:

```text
search_company_knowledge
check_open_gaps
```

Future tools may be added, but keep tool definitions stable and minimal.

### 11.1 search_company_knowledge

Must search:

- approved claims
- claim domains
- relevant evidence
- brain sections where appropriate
- document chunks where appropriate

Must filter by:

- claim_domains
- brain_sections.knowledgeDomain
- brain_sections.relatedDomains
- semantic similarity
- current channel / employee context where relevant

The tool must return small, traceable results. It should not dump giant Brain sections into the chat context.

### 11.2 check_open_gaps

Returns open gaps relevant to:

- current employee
- current department
- current channel context
- recent topic

The Oracle may weave gap questions into conversation naturally, but must ask one tightly scoped question at a time.

---

## 12. AI Task Type Registry

Define explicit task types.

Suggested task types:

```ts
export const AI_TASK_TYPES = [
  'live_chat',
  'direct_mention_response',
  'claim_extraction',
  'document_claim_extraction',
  'document_chunk_classification',
  'contradiction_candidate_analysis',
  'gap_generation',
  'brain_synthesis',
  'duplicate_claim_detection',
  'domain_tagging',
  'admin_explanation',
  'eval_run',
] as const;
```

Each task type should have:

- default prompt version
- default schema version
- default model route
- fallback model route
- max retry count
- structured output requirement
- prompt caching strategy
- validation policy

---

## 13. Suggested File Structure

Adapt to the existing repo structure, but prefer something like:

```text
packages/
  ai/
    src/
      oracle-ai-client.ts
      context/
        context-compiler.ts
        context-pack-types.ts
        context-hashing.ts
      routing/
        model-router.ts
        provider-capability-matrix.ts
        model-config.ts
      prompts/
        prompt-template-registry.ts
        templates/
          live-chat.ts
          claim-extraction.ts
          document-claim-extraction.ts
          contradiction-analysis.ts
          gap-generation.ts
          brain-synthesis.ts
      validation/
        structured-output-validator.ts
        schemas/
          claim-extraction.schema.ts
          contradiction.schema.ts
          gap.schema.ts
          brain-synthesis.schema.ts
      retrieval/
        retrieval-planner.ts
        claim-retrieval.ts
        gap-retrieval.ts
        document-chunk-retrieval.ts
      usage/
        usage-logger.ts
        cost-tracker.ts
        provider-usage-normalizer.ts
      evals/
        eval-runner.ts
        eval-types.ts
```

If the monorepo already has a better pattern, follow it. Do not create unnecessary packages if a simpler structure fits the phase.

---

## 14. Vercel AI SDK Usage Rules

Use Vercel AI SDK because the master spec requires it.

Use streaming for live chat:

```ts
streamText({
  model,
  messages,
  tools,
});
```

Use object generation for structured workflows:

```ts
generateObject({
  model,
  schema,
  messages,
});
```

Do not hide prompts, schemas, or retrieval behind opaque custom frameworks.

LLM calls must remain explicit and understandable.

---

## 15. Worker-Specific Guidance

### 15.1 Claim Extraction Worker

Implementation requirements:

- query pending user messages
- group into conversation segments
- compile extraction context
- call `OracleAIClient.generateObject`
- validate output
- validate quotes
- create claims
- create claim_domains
- create claim_evidence
- set extraction status
- log model run
- log job run

Auto-approve only if:

- exact quote validates
- claim type is low-risk
- no contradiction found
- impact score <= configured threshold

Use pending review if:

- impact score is high
- contradiction detected
- claim affects future PM-system requirements
- claim names a person as a bottleneck
- claim implies customer/licensor risk
- OCR/document confidence is low

### 15.2 Document Ingestion Worker

Implementation requirements:

- parse documents into chunks
- preserve chunk metadata
- dedupe via content hash
- embed chunks
- extract claims from chunks
- link claims to chunk evidence
- mark document complete or failed
- log job and model runs

### 15.3 Contradiction Watcher

Implementation requirements:

- trigger on new user messages
- retrieve approved claim candidates cheaply
- call model only for plausible candidates
- create contradiction records
- create gaps where useful
- log interjection decisions
- avoid live interjections unless settings and confidence allow

### 15.4 Brain Synthesis Worker

Implementation requirements:

- select one section
- retrieve relevant approved claims
- compile synthesis context
- call strong enough model
- validate structured diff
- insert new brain_section_versions row
- update currentVersionId transactionally only after validation
- create/resolve gaps and contradictions
- log model run and job run

---

## 16. Model Routing Starting Defaults

Use configuration, but initial defaults may be:

```ts
const defaultModelRoutes = {
  live_chat: {
    primary: 'anthropic/claude-sonnet-4.6',
    fallback: 'openai/gpt-4.1',
  },
  claim_extraction: {
    primary: 'google/gemini-flash',
    fallback: 'anthropic/claude-sonnet-4.6',
  },
  document_claim_extraction: {
    primary: 'google/gemini-flash',
    fallback: 'anthropic/claude-sonnet-4.6',
  },
  contradiction_candidate_analysis: {
    primary: 'google/gemini-flash',
    fallback: 'anthropic/claude-sonnet-4.6',
  },
  gap_generation: {
    primary: 'google/gemini-flash',
    fallback: 'anthropic/claude-sonnet-4.6',
  },
  brain_synthesis: {
    primary: 'anthropic/claude-sonnet-4.6',
    fallback: 'openai/gpt-4.1',
  },
};
```

Do not treat these as permanent truth. The model router and evals should allow replacement.

If a model ID is unavailable, outdated, unsupported, or fails capability checks, choose a configured fallback.

---

## 17. Validation Philosophy

The LLM is not the authority.

The database plus validators are the authority.

The model may propose:

- claims
- evidence
- gaps
- contradictions
- synthesis changes

The backend decides what is valid.

### 17.1 Claim Validation

Validate:

- schema correctness
- allowed domain
- allowed status
- impact/confidence ranges
- exact quote existence
- source type foreign key correctness
- duplicate similarity where feasible

### 17.2 Synthesis Validation

Validate:

- section exists
- all supporting claim IDs exist
- all supporting claims are approved
- material statements map to claim IDs
- no unsupported named entities or process rules
- new gaps have whyItMatters
- contradictions reference existing claims

### 17.3 Chat Validation

For live chat:

- avoid unsupported operational claims
- prefer tool-backed answers
- keep tone concise
- ask one question at a time
- respect psychological safety

---

## 18. Evaluation System

Before broad rollout, implement gold-standard evals from 3-5 known transcripts.

The eval set should define:

- expected claims
- expected evidence quotes
- expected gaps
- expected contradictions
- expected brain-section updates

Track:

- claim extraction precision
- claim extraction recall
- evidence quote validity
- wrong-domain rate
- duplicate-claim rate
- false contradiction rate
- brain section usefulness
- Albert usefulness rating
- cost per validated claim
- cost per useful synthesis update
- latency per job

Initial targets:

- evidence quote validity: 98%+
- wrong-domain rate: under 10%
- duplicate claim rate: under 15%
- false contradiction rate: under 20% initially
- Albert usefulness rating for brain sections: 4/5 or better

Do not broaden rollout until the Oracle produces useful, evidence-backed output on known transcripts.

---

## 19. Admin Observability Requirements

Eventually, the Admin Dashboard should allow Albert to inspect:

- model runs
- job runs
- context packs
- model costs
- prompt cache hits/misses
- validation failures
- retry chains
- failed structured outputs
- extraction precision/recall from evals
- top cost centers by task type
- cost per approved claim
- cost per brain section update

The first implementation does not need the full dashboard, but the data model and logging must make it possible.

---

## 20. Implementation Phasing

Do not build everything in one pass.

Respect the master spec's phase-by-phase principle.

For this AI architecture work, implement in this order:

### Phase AI-1: Foundations

Deliver:

- `OracleAIClient` shell
- `ProviderCapabilityMatrix`
- `PromptTemplateRegistry`
- `ContextCompiler`
- hashing utilities
- AI task type registry
- database migrations for `ai_context_packs` and `model_run_usage_details`
- usage logging integrated with existing `model_runs`

Acceptance gate:

- one test model call creates model run, context pack, and usage details
- stable prefix hash remains identical across repeated calls with different dynamic input
- dynamic input hash changes when current message/chunk changes

### Phase AI-2: Structured Extraction Path

Deliver:

- claim extraction schema
- claim extraction prompt template
- claim extraction context compiler path
- quote validation helper
- model routing for extraction
- retry/escalation behavior

Acceptance gate:

- transcript segment produces structured claim candidates
- invalid quotes are rejected
- valid claims link to evidence
- model run and context pack are logged

### Phase AI-3: Document Extraction Path

Deliver:

- document chunk extraction schema
- chunk-specific context compiler path
- document claim evidence linking
- chunk metadata preservation

Acceptance gate:

- document chunk produces claims linked to `document_chunks`
- whole document is not sent unnecessarily
- context pack includes chunk IDs

### Phase AI-4: Contradiction and Gap Path

Deliver:

- retrieval-first contradiction watcher
- contradiction analysis schema
- gap generation schema
- interjection decision logging

Acceptance gate:

- new message retrieves candidate approved claims
- possible contradiction row is created when appropriate
- live interjection remains disabled unless settings allow it

### Phase AI-5: Brain Synthesis Path

Deliver:

- synthesis schema
- synthesis prompt template
- section-specific context compiler path
- validator for claim support
- transactional brain section version update

Acceptance gate:

- approved claims synthesize into a new brain section version
- unsupported material statements fail validation
- failed validation does not update currentVersionId

### Phase AI-6: Evals and Optimization

Deliver:

- eval runner
- gold transcript fixture support
- cost/quality reporting by task type
- prompt cache hit reporting
- model route comparison

Acceptance gate:

- eval run reports quality and cost metrics
- model routes can be compared by cost per validated result

---

## 21. Concrete Tests to Add

Add tests for:

### Context Compiler

- stable prefix hash unchanged when dynamic request changes
- dynamic input hash changes when dynamic request changes
- retrieved context hash changes when retrieved claims change
- timestamps are not included in stable prefix
- request IDs are not included in stable prefix
- output schema hash is stable across repeated calls

### Model Router

- routes simple extraction to cheap model
- routes synthesis to stronger model
- escalates after validation failure
- rejects models missing required structured output capability
- rejects models missing required vision capability for image tasks

### Structured Output Validator

- rejects missing evidence quote
- rejects invalid claim domain
- rejects synthesis with unapproved claim IDs
- rejects synthesis with unsupported material statements
- accepts valid claim extraction result

### Usage Logging

- model run is created for every AI call
- context pack is created for every AI call
- usage details link to model run
- retry model run links back to previous model run
- cached token fields are nullable but supported

### Prompt Caching Hygiene

- stable prefix remains byte-identical across equivalent calls
- dynamic retrieval does not pollute stable prefix
- tool schema hash changes only when tool definitions change

---

## 22. Security and RLS Reminders

Browser code must never receive:

- Supabase service role key
- direct Postgres connection string
- Trigger.dev secrets
- OpenRouter API key

Employee chat UI must receive intelligence only through server-side Oracle route handlers.

Admin-only intelligence tables include:

- claims
- claim_evidence
- brain_sections
- brain_section_versions
- section_claims
- gaps
- contradictions
- model_runs
- job_runs
- oracle_interventions
- ai_context_packs
- model_run_usage_details

Do not accidentally expose AI logs containing sensitive context to normal employees.

---

## 23. Coding Style Requirements

- TypeScript-first
- strongly typed
- use Zod or equivalent validation where appropriate
- keep schemas shared where useful
- avoid hidden magic
- avoid opaque abstractions
- use explicit provider adapters
- make prompts inspectable
- make context assembly deterministic
- make model routing explainable
- make validation strict

Do not write clever code that hides the core AI process.

This system must be understandable by Albert and future developers.

---

## 24. Final Implementation Principle

The Oracle succeeds only if it can say:

> "I believe this because these specific employees said these specific things, in these specific messages or documents, these became approved claims, and those claims were synthesized into this brain section version by this model run."

Therefore every AI architecture decision must support:

- traceability
- auditability
- evidence linking
- schema validation
- cost measurement
- prompt-cache hygiene
- model-routing transparency
- safe phased implementation

Do not optimize for token savings in a way that weakens the Oracle's trustworthiness.

Do not build the whole system in one pass.

Implement phase-by-phase and stop after each phase for verification.
