# Provider-Native AI Architecture

Status: **production architecture** as of the R-providers + R11 retrofit (commits `bfc0821` + `51a33ff` + `b01e514`, 2026-05-26). OpenRouter has been removed entirely from the codebase. The Vercel AI SDK is forbidden inside `packages/ai/src/providers/` per `DECISIONS.md` D6 + D9.

This document supersedes the old OpenRouter-centered AI implementation for all production AI work.

## The OracleAIClient

The system relies exclusively on direct-provider APIs to guarantee access to native prompt caching and strict structured outputs.

**Flow:**
`Next.js/Trigger.dev -> OracleAIClient -> ContextCompiler -> ModelRouter -> Provider-Native Adapter`

- **VertexGeminiAdapter:** Manages Google Explicit Caching and temporary Storage bridging.
- **AnthropicAdapter:** Manages implicit cache breakpoints (`cache_control: "ephemeral"`).
- **OpenAIAdapter:** Manages strict JSON schema injection and invisible prefix caching.
- *OpenRouter is strictly deprecated for production operations and must not be used.*

---

## Executive decision

The Oracle must use a provider-neutral internal architecture with provider-native adapters underneath.

The production providers are limited to the Big 3 direct APIs:

- Anthropic direct;
- Google Vertex AI / Gemini direct;
- OpenAI direct.

The target architecture is not a single generic wrapper (e.g. OpenRouter) — that hides the caching, structured-output, and usage details The Oracle needs to optimize.

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

OpenRouter has been removed from the codebase entirely (commit `b01e514`, R11.0). The transitional bridge adapter, the `openrouter.ts` helper, the `@openrouter/ai-sdk-provider` dependency, and the `apps/web/app/api/admin/models/route.ts` proxy are all deleted. The `OPENROUTER_API_KEY` env var is no longer read by any production code path.

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

All model calls, regardless of provider, go through `OracleAIClient`.

No route handler or worker may call Anthropic, Google, OpenAI, Vercel AI SDK, or OpenRouter directly. The retrofit is complete — there is no longer a transitional bridge.

The Vercel AI SDK (`ai` package + `@ai-sdk/*` providers) is specifically forbidden inside `packages/ai/src/providers/`. The three production adapters (`AnthropicAdapter`, `VertexGeminiAdapter`, `OpenAIAdapter`) use the providers' official raw SDKs directly: `@anthropic-ai/sdk`, `@google/genai`, and `openai`. See `DECISIONS.md` D6 and D9 for the rationale.

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

Every claim, document, document chunk, message-derived candidate, Brain section, gap, and contradiction should be tagged or linkable by multiple dimensions:

1. Top-level domain: licensing approvals, product development, creative design, production lifecycle, supply chain, customer operations, vendor management, logistics/shipping, import compliance, IT systems, finance/pricing, people/org. These are governed by `knowledge_top_domains` and boundary rules in `07-knowledge-segmentation.md`; do not use a freeform `general` bucket except as a temporary unresolved/proposal state.
2. Source type: message, document chunk, external system, manual admin, Brain section.
3. Document class: SOP, vendor manual, customer routing guide, tech pack, style guide, ERP export, email, invoice, shipping document, chat transcript, unknown.
4. Process stage: concept, design, licensor approval, customer approval, costing, sourcing, sample request, sample review, production, quality control, packaging, routing, shipping, invoicing, ERP update, archive.
5. Department: design, licensing, sourcing, production, logistics, sales, admin, China team, finance, other.
6. Entity type and entity ID: customer, licensor, factory, freight_provider, testing_lab, packaging_supplier, service_provider, vendor (residual), brand, SKU, product line, employee, system, document. Licensors such as Disney, Marvel, Star Wars, NBCUniversal, and Warner Bros are first-class `licensor` entities, never `vendor`. Operating vendors should resolve to a specific type (`factory`, `freight_provider`, `testing_lab`, `packaging_supplier`, `service_provider`); the generic `vendor` type is a residual bucket only.
7. System: Coldlion, ResourceSpace, Supabase, Google Drive, Adobe Illustrator, Photoshop, email, WhatsApp, WeChat, other.
8. Geography/team: US, China, Brazil, Colombia, customer-specific, factory-specific.
9. Confidence/review state: candidate, validated, pending review, approved, rejected, superseded, challenged.
10. Time validity: observed at, effective from, superseded at, archived at.

### Filing rules during ingestion

When ingesting information, the extractor must produce candidate metadata as part of the structured output.

For each extracted claim candidate, the model should propose:

- top-level domain IDs;
- process stage;
- source type;
- document class if applicable;
- systems mentioned;
- departments involved;
- entities mentioned;
- whether the claim is a general rule, exception, workaround, bottleneck, requirement, timing rule, ownership rule, or ambiguity.

The deterministic validator does not need to prove all metadata is correct, but the system must store it separately from the evidence quote and make it reviewable.

If the extractor cannot fit a candidate into any active top-level domain, it must stage a taxonomy proposal instead of forcing the candidate into `general`.

### RetrievalPlanner rules

All answer generation, chat retrieval, contradiction review, and synthesis must go through `RetrievalPlanner` before vector search.

`RetrievalPlanner` must classify the user/task intent into a retrieval plan containing:

- allowed top-level domains;
- excluded top-level domains;
- allowed source types;
- excluded source types;
- document classes to include/exclude;
- process stages;
- systems;
- entities;
- excluded entity types where useful, such as excluding `vendor` for a pure licensor approval question;
- review-state requirements;
- max results per source bucket;
- fallback broadening policy.

Example for an ERP image-upload question:

```ts
{
  query: 'when does an image get uploaded to Coldlion',
  allowedTopDomains: ['it_systems', 'creative_design', 'production_lifecycle'],
  excludedDocumentClasses: ['vendor_manual'],
  excludedEntityTypes: ['vendor'],
  preferredSourceTypes: ['approved_claim', 'brain_section', 'message'],
  requiredEntities: [{ entityType: 'system', canonicalValue: 'Coldlion' }],
  processStages: ['design', 'erp_update', 'production'],
  reviewStates: ['approved'],
  fallbackBroadening: 'ask_permission_or_log_broadening'
}
```

Example for a licensor approval question:

```ts
{
  query: 'when do Disney approvals need to happen before production',
  allowedTopDomains: ['licensing_approvals', 'product_development', 'production_lifecycle'],
  excludedTopDomains: ['vendor_management'],
  excludedDocumentClasses: ['vendor_manual'],
  preferredSourceTypes: ['approved_claim', 'document_chunk', 'brain_section'],
  requiredEntities: [{ entityType: 'licensor', canonicalValue: 'Disney' }],
  processStages: ['licensor_approval', 'sample_review', 'production'],
  reviewStates: ['approved'],
  fallbackBroadening: 'ask_permission_or_log_broadening'
}
```

### Retrieval execution order (Hybrid Search Required)
Do not rely solely on vector search. Vector search is terrible at exact keyword matching (e.g., finding factory code "FCT-882" or SKU "BR-9901").

1. Classify the question/task into a retrieval plan.
2. Apply hard filters first: review status, source type, domain, document class.
3. Use **Hybrid Search (RRF - Reciprocal Rank Fusion)**: Query `pgvector` for semantic meaning AND query PostgreSQL Full-Text Search (`tsvector`) for exact SKUs/Entities.
4. Merge and rerank results with diversity.
5. Log the retrieval plan and actual searched buckets in the context pack.

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
- use explicit context caching ONLY when the math justifies the hourly storage cost.

Explicit Cache Heuristic:
Explicit caching charges by token volume and wall-clock retention, so a cache can be a cost leak if it is created for one-off work or kept longer than the reuse window. Do not create explicit caches for small, one-off chunks. Use this heuristic to determine if explicit caching is profitable:
`useExplicitGeminiCache = (sourceTokenEstimate >= 25_000 && expectedReuseCount >= 3) || (sourceTokenEstimate >= 100_000 && expectedReuseCount >= 2)`

Explicit Cache Lifecycle Rule:
Because explicit caches bill while they exist, workers must attach every cache to a short-lived reuse policy before creating it. The policy must record the expected reuse count, the latest planned reuse step, the hard expiration, and the cleanup owner in `provider_cached_content`.

Delete the cache immediately when the planned reuse window is finished. If a 100,000-token extraction batch completes in 2 minutes and no retry, validation-repair, synthesis, or follow-up pass will reuse the cache, delete it in a `finally` block instead of waiting for TTL expiration.

Do not delete the cache immediately when the job has known follow-up passes that will reuse it. In that case, keep the cache only until the last planned pass completes or the short TTL expires, whichever happens first. Every path must update `provider_cached_content.status` to `deleted`, `expired`, or `failed` so cache leaks are visible.

Use explicit context caching when:

- the same large PDF/SOP/style guide/tech pack will be queried repeatedly;
- the same large transcript batch will be processed in multiple passes;
- a document is large enough that first-write/cache-storage overhead is justified;
- multiple retries or validation-repair passes are likely;
- a large source context will be reused by both extraction and synthesis.

Do not use explicit context caching when:

- the input is a small one-off chunk;
- the context will be used once;
- cache storage cost/complexity exceeds likely savings;
- the worker cannot guarantee cleanup and status tracking.

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

## Existing repo retrofit map (status as of R11.4)

All items below are done unless explicitly marked open.

- ✅ `packages/ai/src/openrouter.ts` — deleted (R11.0, commit `b01e514`).
- ✅ `packages/ai/` has `OracleAIClient`, `ModelRouter`, provider adapters, context compiler, usage normalization, validation helpers (R2 + R-providers).
- ✅ `apps/web/app/api/chat/route.ts` calls `OracleAIClient.runText` via `AnthropicAdapter` (R8 + R-providers).
- ✅ `apps/workers/src/trigger/claim-extraction.ts` calls `OracleAIClient` and stages candidates before promotion (R6 + R-providers).
- ✅ `apps/workers/src/trigger/document-ingestion.ts` calls `OracleAIClient` via direct adapters; uses Vertex for extraction (R7 + R-providers).
- ✅ `apps/workers/src/trigger/brain-synthesis.ts` calls `OracleAIClient` via direct adapters; strict synthesis-diff validation enforced (R9 + R-providers).
- ✅ `apps/workers/src/trigger/contradiction-watcher.ts` calls `OracleAIClient` via direct adapters (R11.0); live-interjection path landed in R11.3.
- ✅ `apps/workers/src/trigger/lull-interjection.ts` — new in R11.2; calls `OracleAIClient` on the interview route for question drafting.
- ⏳ **Admin model picker** (`apps/web/app/admin/settings/`) — the OpenRouter `/models` proxy that backed the live capability icons was deleted in `b01e514`. A curated `OracleModelRoute.routeId` picker sourced from `packages/ai/src/routes/catalog.ts` is the planned replacement. Open follow-up.
- ⏳ **Retrieval helpers** (`packages/ai/src/retrieval.ts`) — still use `searchApprovedClaims` directly without going through a `RetrievalPlan`. Hybrid pgvector + tsvector RRF with metadata pre-filter is documented above but not yet wired in. Open follow-up.

## Environment variables

Do not commit secrets.

The production adapters read these variables (all required):

```text
ANTHROPIC_API_KEY=          # AnthropicAdapter — interview chat (Haiku 4.5)
OPENAI_API_KEY=             # OpenAIAdapter + text-embedding-3-small
GOOGLE_CLOUD_PROJECT=       # VertexGeminiAdapter — extraction + synthesis
GOOGLE_CLOUD_LOCATION=      # default us-central1
```

Vertex authentication uses Application Default Credentials. Locally: `gcloud auth application-default login`. Cloud workers need a service-account JSON via `GOOGLE_APPLICATION_CREDENTIALS` (the file path) or the equivalent secret-mounting pattern on the deploy platform.

`OPENROUTER_API_KEY` is no longer read by any code path and was removed from `.env.local` in commit `b01e514`. `ORACLE_ENABLE_OPENROUTER_FALLBACK` was never wired and was removed.

The full env-var table with sources lives in `docs/configuration.md`.

## Acceptance criteria for provider layer retrofit — status

| Criterion | Status |
|---|---|
| No production code calls `getOpenRouter()` | ✅ — file deleted in `b01e514` |
| `OracleAIClient` is the only production model-call gateway | ✅ — verified by recursive grep |
| Anthropic, Vertex/Gemini, and OpenAI adapters exist | ✅ — R-providers commit `bfc0821` |
| Adapters use raw SDKs (no Vercel AI SDK) | ✅ — D6 + D9 |
| Model routes selected by curated route ID | ✅ — R1 catalog |
| Model runs log provider-native usage details | ✅ — R3 + R-providers |
| Cache read/write tokens captured where available | ✅ — Anthropic + Vertex + OpenAI native fields normalized into `OracleUsage` |
| Context packs created for model calls | ✅ — `oracle_context_packs` |
| Worker extraction outputs candidates, not direct claims | ✅ — R4–R7 |
| Wet-test against live DB | ✅ — 2026-05-26, commit `51a33ff` |
| `pnpm typecheck` and Next production build pass | ✅ — every commit since R-providers |
| Retrieval is filtered by plan, not global vector search | ⏳ — open follow-up; legacy `searchApprovedClaims` still in use |
| Real Vertex explicit cache creation | ⏳ — round 2 of R-providers; implicit caching is wired today |
