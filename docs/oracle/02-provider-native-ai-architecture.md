# Provider-Native AI Architecture

Status: mandatory architecture target for the AI retrofit.

This document supersedes the old OpenRouter-centered AI implementation for production AI work.

## Executive decision

The Oracle must use a provider-neutral internal architecture with provider-native adapters underneath.

The production providers are limited to the Big 3 direct APIs:

- Anthropic direct;
- Google Vertex AI / Gemini direct;
- OpenAI direct.

The target architecture is not `Vercel AI SDK -> OpenRouter -> everything`.

The target architecture is:

```text
Oracle application
  -> OracleAIClient
      -> ContextCompiler
      -> ModelRouter
      -> PromptTemplateRegistry
      -> RetrievalPlanner
      -> StructuredOutputValidator
      -> EvidenceValidator
      -> UsageLogger
      -> CostTracker
      -> EvalRunner
      -> Provider adapters
          -> AnthropicAdapter
          -> VertexGeminiAdapter
          -> OpenAIAdapter
```

OpenRouter may stay temporarily for existing runtime behavior while refactoring. It should be deprecated for production background workers and cache-sensitive workloads.

## Why provider-native adapters are required

The three providers do not expose caching, structured output, tools, usage accounting, or reasoning controls the same way.

A single generic wrapper hides exactly the details The Oracle needs to optimize:

- prompt cache read tokens;
- cache creation/write tokens;
- cached content IDs;
- provider-native request IDs;
- structured-output failure modes;
- retry/fallback behavior;
- long-context explicit cache lifecycle;
- task-specific cost per useful result.

The Oracle should normalize these details after the provider call, not erase them before the call.

## Shared architecture

All model calls, regardless of provider, must go through `OracleAIClient`.

No route handler or worker may call Anthropic, Google, OpenAI, Vercel AI SDK, or OpenRouter directly once the retrofit is complete.

Allowed exception during transition:

- existing OpenRouter code may remain until the corresponding task has a provider-native replacement;
- new code must not extend OpenRouter usage for production workloads.

## Core interfaces

The exact implementation may vary, but the architecture must preserve these boundaries.

```ts
type OracleTaskType =
  | 'interview_chat'
  | 'message_claim_extraction'
  | 'document_claim_extraction'
  | 'contradiction_detection'
  | 'brain_synthesis'
  | 'gap_generation'
  | 'admin_explanation'
  | 'validation_repair';

type PromptBlock = {
  id: string;
  label: string;
  kind:
    | 'stable_system'
    | 'stable_schema'
    | 'stable_tool_definition'
    | 'semi_stable_domain_context'
    | 'retrieved_context'
    | 'dynamic_input'
    | 'output_contract';
  content: string;
  hash: string;
  tokenEstimate?: number;
  cacheEligible: boolean;
  reasonIncluded: string;
};

type OraclePromptPlan = {
  taskType: OracleTaskType;
  routeId: string;
  promptVersion: string;
  schemaVersion?: string;
  blocks: PromptBlock[];
  outputContract?: {
    name: string;
    schemaHash: string;
    mode: 'native_json_schema' | 'tool_call' | 'schema_prompt_plus_validator';
  };
  metadata: {
    stablePrefixHash: string;
    semiStableContextHash?: string;
    retrievedContextHash?: string;
    dynamicInputHash: string;
    toolSchemaHash?: string;
    outputSchemaHash?: string;
    includedMessageIds?: string[];
    includedDocumentChunkIds?: string[];
    includedClaimIds?: string[];
    includedGapIds?: string[];
    includedContradictionIds?: string[];
    retrievalPlanId?: string;
    selectedDomains?: string[];
    selectedSourceTypes?: string[];
    selectedProcessStages?: string[];
    selectedEntityIds?: string[];
  };
};

type OracleUsage = {
  inputTokens?: number;
  cachedInputTokens?: number;
  cacheWriteTokens?: number;
  outputTokens?: number;
  reasoningTokens?: number;
  totalCostUsd?: string;
  latencyMs: number;
  providerRequestId?: string;
  rawUsageJson?: unknown;
};

interface OracleProviderAdapter {
  provider: 'anthropic' | 'vertex' | 'openai';
  generateObject<T>(args: {
    plan: OraclePromptPlan;
    route: OracleModelRoute;
    schema: unknown;
  }): Promise<{ object: T; usage: OracleUsage; rawResponse: unknown }>;
  generateText(args: {
    plan: OraclePromptPlan;
    route: OracleModelRoute;
  }): Promise<{ text: string; usage: OracleUsage; rawResponse: unknown }>;
  streamText?(args: {
    plan: OraclePromptPlan;
    route: OracleModelRoute;
  }): AsyncIterable<unknown>;
}
```

## ContextCompiler rules

Every AI request must be compiled in this order:

1. Stable system/task instructions.
2. Stable tool definitions.
3. Stable output schema or Zod/JSON schema description.
4. Semi-stable domain/taxonomy context.
5. Retrieved context.
6. Dynamic input.
7. Retry-specific or validation-error suffix.

Dynamic content must never be placed before the cacheable stable prefix.

Stable content examples:

- Oracle identity and role;
- psychological safety rules;
- extraction rules;
- group-chat interpretation rules;
- synthesis traceability rules;
- output schemas;
- tool definitions;
- domain enum definitions.

Dynamic content examples:

- current user message;
- current transcript segment;
- current document chunk;
- current validation failure;
- current selected claim list;
- current Brain section version;
- timestamps;
- request IDs.

## Knowledge filing and retrieval routing

Knowledge-domain labels alone are not enough.

The Oracle will eventually contain many unrelated kinds of knowledge: vendor manuals, customer routing guides, ERP workflow rules, artwork handoff rules, licensing approval rules, freight documents, costing assumptions, factory communication patterns, and employee interview claims.

The retrieval system must not search the whole knowledge base by default.

A question like:

```text
When does an image get uploaded to Coldlion?
```

should not search vendor manuals unless there is a strong reason. It should prefer ERP/Coldlion, artwork files, design handoff, production workflow, and approved operational claims.

### Required metadata dimensions

Every claim, document chunk, message-derived candidate, Brain section, gap, and contradiction should be tagged or linkable by multiple dimensions:

1. Knowledge domain: design, licensing, production, sourcing, logistics, sales, Coldlion, customers, retail compliance, sampling, costing, artwork files, factory communication, quality control, approvals, shipping documents, general.
2. Source type: message, document chunk, external system, manual admin, Brain section.
3. Document class: SOP, vendor manual, customer routing guide, tech pack, style guide, ERP export, email, invoice, shipping document, chat transcript, unknown.
4. Process stage: concept, design, licensor approval, customer approval, costing, sourcing, sample request, sample review, production, quality control, packaging, routing, shipping, invoicing, ERP update, archive.
5. Department: design, licensing, sourcing, production, logistics, sales, admin, China team, finance, other.
6. Entity type and entity ID: customer, vendor, factory, licensor, brand, SKU, product line, employee, system, document.
7. System: Coldlion, ResourceSpace, Supabase, Google Drive, Adobe Illustrator, Photoshop, email, WhatsApp, WeChat, other.
8. Geography/team: US, China, Brazil, Colombia, customer-specific, factory-specific.
9. Confidence/review state: candidate, validated, pending review, approved, rejected, superseded, challenged.
10. Time validity: observed at, effective from, superseded at, archived at.

### Filing rules during ingestion

When ingesting information, the extractor must produce candidate metadata as part of the structured output.

For each extracted claim candidate, the model should propose:

- knowledge domains;
- process stage;
- source type;
- document class if applicable;
- systems mentioned;
- departments involved;
- entities mentioned;
- whether the claim is a general rule, exception, workaround, bottleneck, requirement, timing rule, ownership rule, or ambiguity.

The deterministic validator does not need to prove all metadata is correct, but the system must store it separately from the evidence quote and make it reviewable.

Do not use a single `general` bucket unless classification genuinely fails.

### RetrievalPlanner rules

All answer generation, chat retrieval, contradiction review, and synthesis must go through `RetrievalPlanner` before vector search.

`RetrievalPlanner` must classify the user/task intent into a retrieval plan containing:

- allowed knowledge domains;
- excluded knowledge domains;
- allowed source types;
- excluded source types;
- document classes to include/exclude;
- process stages;
- systems;
- entities;
- review-state requirements;
- max results per source bucket;
- fallback broadening policy.

Example for an ERP image-upload question:

```ts
{
  query: 'when does an image get uploaded to Coldlion',
  allowedDomains: ['coldlion', 'artwork_files', 'design', 'production'],
  excludedDocumentClasses: ['vendor_manual'],
  preferredSourceTypes: ['approved_claim', 'brain_section', 'message'],
  systems: ['coldlion'],
  processStages: ['design', 'erp_update', 'production'],
  reviewStates: ['approved'],
  fallbackBroadening: 'ask_permission_or_log_broadening'
}
```

### Retrieval execution order

Do not start with one global vector search.

Use this order:

1. Classify the question/task into a retrieval plan.
2. Apply hard filters first: review status, source type, domain, document class, system, process stage.
3. Search approved claims and Brain sections before raw documents for normal business questions.
4. Search raw document chunks only when the query asks about a document/source, approved knowledge is missing, or the retrieval plan allows that document class.
5. Use vector search inside each allowed bucket.
6. Use keyword/entity search as a second signal for systems, customers, SKUs, licensors, vendors, and document names.
7. Merge and rerank results with diversity: do not return 10 chunks from the same manual unless the user asked for that manual.
8. Log the retrieval plan and actual searched buckets in the context pack.

### Retrieval broadening policy

If filtered retrieval returns weak results, do not silently search everything.

The system may broaden retrieval in stages:

1. same domains, more source types;
2. adjacent domains;
3. raw documents in allowed document classes;
4. broader global search only if logged and justified.

For employee-facing chat, broadening should usually be conservative. For admin/research mode, broadening can be more aggressive but must be shown in the context pack.

### Anti-contamination rules

- Vendor manuals should not answer ERP workflow questions unless the retrieval plan explicitly includes vendor documentation.
- Customer routing guides should not answer internal design handoff questions unless the question is customer-specific.
- Raw unapproved candidate claims should not answer employee-facing questions.
- Superseded claims should not answer current operational questions unless the user asks for history.
- Document chunks should not override approved claims without contradiction/gap creation.
- Low-confidence OCR text should not be used as final evidence without review.

### Retrieval observability

Every model call context pack must include:

- retrieval plan ID;
- selected domains;
- excluded domains;
- selected source types;
- selected document classes;
- selected systems/process stages;
- number of results considered per bucket;
- final included IDs;
- reason each included item was selected;
- whether broadening occurred.

This is essential for debugging bad answers.

## Provider-specific caching

### Anthropic direct

Use Anthropic for:

- interview/chat escalation;
- synthesis escalation;
- hard contradiction review;
- high-nuance extraction escalation.

Caching rules:

- use automatic caching for longer multi-turn interview/chat when useful;
- use explicit block-level cache breakpoints for stable-prefix/dynamic-suffix jobs;
- place cache breakpoints after stable reusable content, never after dynamic current input;
- cache stable system prompt, tool definitions, extraction rules, synthesis rules, and schemas;
- log provider-native cache read and cache creation/write token fields;
- keep raw provider usage JSON for audit/debug.

Anthropic prompt layout examples:

Interview/chat:

```text
[stable Oracle system prompt]
[stable tool definitions]
CACHE BREAKPOINT WHEN SUPPORTED
[employee/channel context]
[recent messages]
[retrieved gaps/claims]
[current user turn]
```

Synthesis:

```text
[stable synthesis role]
[stable traceability rules]
[stable output schema]
[stable validation rules]
CACHE BREAKPOINT
[selected brain section]
[current brain version]
[approved claim set]
[current synthesis request]
```

### Google Vertex AI / Gemini direct

Use Vertex/Gemini for:

- default extraction;
- document ingestion;
- default routine synthesis draft route;
- long-context fallback;
- multimodal source processing;
- large document loops.

Caching rules:

- use implicit caching by default for repeated stable-prefix Gemini 2.5+ calls;
- use explicit context caching for large reusable contexts;
- store explicit cached-content resource names, source hashes, TTLs, expiration timestamps, and provider metadata in Postgres;
- do not immediately delete explicit caches in `finally` if retries, follow-up extraction passes, or review/synthesis passes are likely;
- delete or expire explicit caches by policy;
- log cached token counts from provider response metadata.

Use explicit context caching when:

- the same large PDF/SOP/style guide/tech pack will be queried repeatedly;
- the same large transcript batch will be processed in multiple passes;
- a document is large enough that first-write/cache-storage overhead is justified;
- multiple retries or validation-repair passes are likely;
- a large source context will be reused by both extraction and synthesis.

Do not use explicit context caching when:

- the input is a small one-off chunk;
- the context will be used once;
- cache storage cost/complexity exceeds likely savings.

### Supabase-to-Vertex storage bridge

Supabase Storage remains the durable source of company documents.

Vertex explicit context caching may require a Google-native file handle, temporary file upload, or Google Cloud Storage URI depending on the selected SDK/API path. Therefore, the document ingestion worker must implement a secure server-side storage bridge:

1. Read the document from private Supabase Storage using service-role access inside Trigger.dev.
2. Stream or buffer the file server-side only.
3. Upload it to the Google/Vertex temporary file mechanism or Google Cloud Storage location selected during implementation.
4. Create explicit cached content from that Google-side file/resource only when reuse justifies it.
5. Store Google temporary file/resource metadata and cached-content metadata in Postgres.
6. Track TTL, expiration, source document hash, and cleanup status.
7. Clean up temporary Google resources according to policy.

Do not expose document bytes to the browser.

Do not write Google service-account credentials to disk inside Trigger.dev.

Preferred authentication options, in order:

1. workload identity or managed identity if available for the deployment setup;
2. service-account credentials supplied through secure environment variables and constructed in memory;
3. provider-supported ADC-style environment variables if confirmed by the selected SDK.

The implementation must verify the selected SDK's exact Vertex authentication behavior before assuming that variables such as `GOOGLE_CLIENT_EMAIL` and `GOOGLE_PRIVATE_KEY` are auto-discovered.

Expected environment variables, subject to SDK verification:

```text
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLIENT_EMAIL=
GOOGLE_PRIVATE_KEY=
```

If `GOOGLE_PRIVATE_KEY` is stored with escaped newlines, convert `\\n` to real newline characters in memory.

Vertex extraction layout examples:

Implicit caching:

```text
[stable extraction system prompt]
[stable schema]
[stable domain taxonomy]
[large repeated document/transcript context if reused]
[current page/chunk/message extraction instruction]
```

Explicit context caching:

```text
CachedContent resource:
  [stable extraction rules]
  [large PDF/SOP/transcript or reusable source context]

Generate request:
  cachedContent: resourceName
  dynamic instruction: extract claims from page/chunk/segment X
  output contract: strict candidate schema
```

### OpenAI direct

Use OpenAI for:

- structured-output fallback;
- validation repair;
- admin explanation;
- extraction fallback;
- possible interview/synthesis fallback if evals prove it wins.

Caching rules:

- rely on automatic prefix prompt caching;
- use a stable prefix and dynamic suffix;
- use task-specific prompt cache keys/retention when available and useful;
- log cached tokens from provider-native usage fields;
- do not try to create explicit cached-content resources;
- do not use Anthropic-style block breakpoints.

OpenAI prompt layout examples:

```text
[stable task prompt]
[stable schema]
[stable tools]
[semi-stable domain context]
[retrieved context]
[dynamic input]
```

## Structured output strategy

All background intelligence jobs must produce structured outputs and must be validated server-side.

Use structured output for:

- claim candidate extraction;
- document claim extraction;
- contradiction decisions;
- gap creation;
- synthesis diffs;
- validation repair;
- model-router decisions;
- retrieval-plan decisions.

Use conversational text for:

- employee-facing Oracle chat;
- admin explanations where no DB write happens.

Even when a provider guarantees JSON schema shape, business validation still runs separately.

Native structured output does not prove:

- the quote exists;
- the claim is true;
- the claim is non-duplicate;
- the evidence source ID is valid;
- the Brain paragraph is fully supported;
- the retrieval plan chose the correct source buckets.

## Retry policy

Do not blindly retry the same failed prompt.

If provider call fails transiently:

1. retry once with the same route if safe;
2. then fallback to the route’s configured fallback.

If structured validation fails:

1. store the invalid output;
2. retry once with a validation-repair prompt if appropriate;
3. fallback to stronger model if configured;
4. mark job failed or pending admin review if still invalid.

If exact quote validation fails:

- do not promote the candidate;
- store validation error;
- do not auto-retry more than once unless the failure is caused by whitespace/normalization that the validator explicitly supports;
- trip the validation-loop circuit breaker defined in `05-ai-retrofit-phase-packet.md` if the same batch repeatedly fails quote validation.

If synthesis validation fails:

- do not update `brain_sections.currentVersionId`;
- save failed candidate output;
- record validation errors;
- optionally escalate to a stronger synthesis route.

## Existing repo retrofit map

Current code to refactor:

- `packages/ai/src/openrouter.ts` becomes legacy/deprecated.
- `packages/ai` gains `OracleAIClient`, `ModelRouter`, `RetrievalPlanner`, provider adapters, context compiler, usage normalization, validation helpers.
- `apps/web/app/api/chat/route.ts` should call `OracleAIClient` instead of `getOpenRouter()`.
- `apps/workers/src/trigger/claim-extraction.ts` should call `OracleAIClient` and stage candidates before promotion.
- `apps/workers/src/trigger/document-ingestion.ts` should use `VertexGeminiAdapter` for document-heavy extraction and explicit context caching when justified.
- `apps/workers/src/trigger/brain-synthesis.ts` should use provider-native synthesis routes and strict synthesis validation.
- Admin model picker should select curated `OracleModelRoute.routeId`, not arbitrary OpenRouter model IDs.
- Retrieval helpers should be refactored so they do not perform global vector search without a retrieval plan.

## Environment variables

Do not commit secrets.

Expected new environment variables:

```text
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_CLIENT_EMAIL=
GOOGLE_PRIVATE_KEY=
ORACLE_ENABLE_OPENROUTER_FALLBACK=false
```

Actual variable names may be refined during implementation, but they must be documented in `.env.example` and `docs/configuration.md`.

## Acceptance criteria for provider layer retrofit

The provider layer retrofit is complete only when:

- no new production code calls `getOpenRouter()`;
- `OracleAIClient` is the only production model-call gateway;
- Anthropic, Vertex/Gemini, and OpenAI adapters exist;
- model routes are selected by route ID, not arbitrary model string;
- model runs log provider-native usage details;
- cache read/write tokens are captured where available;
- context packs are created for model calls;
- worker extraction outputs candidates, not direct permanent claims;
- retrieval is filtered by plan, not global vector search by default;
- `pnpm typecheck` and the Next production build pass.
