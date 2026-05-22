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

## Provider-specific caching

### Anthropic direct

Use Anthropic for:

- interview/chat default;
- synthesis default;
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
- model-router decisions.

Use conversational text for:

- employee-facing Oracle chat;
- admin explanations where no DB write happens.

Even when a provider guarantees JSON schema shape, business validation still runs separately.

Native structured output does not prove:

- the quote exists;
- the claim is true;
- the claim is non-duplicate;
- the evidence source ID is valid;
- the Brain paragraph is fully supported.

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
- do not auto-retry more than once unless the failure is caused by whitespace/normalization that the validator explicitly supports.

If synthesis validation fails:

- do not update `brain_sections.currentVersionId`;
- save failed candidate output;
- record validation errors;
- optionally escalate to a stronger synthesis route.

## Existing repo retrofit map

Current code to refactor:

- `packages/ai/src/openrouter.ts` becomes legacy/deprecated.
- `packages/ai` gains `OracleAIClient`, `ModelRouter`, provider adapters, context compiler, usage normalization, validation helpers.
- `apps/web/app/api/chat/route.ts` should call `OracleAIClient` instead of `getOpenRouter()`.
- `apps/workers/src/trigger/claim-extraction.ts` should call `OracleAIClient` and stage candidates before promotion.
- `apps/workers/src/trigger/document-ingestion.ts` should use `VertexGeminiAdapter` for document-heavy extraction and explicit context caching when justified.
- `apps/workers/src/trigger/brain-synthesis.ts` should use Anthropic adapter by default and strict synthesis validation.
- Admin model picker should select curated `OracleModelRoute.routeId`, not arbitrary OpenRouter model IDs.

## Environment variables

Do not commit secrets.

Expected new environment variables:

```text
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_VERTEX_PROJECT_ID=
GOOGLE_VERTEX_LOCATION=
GOOGLE_APPLICATION_CREDENTIALS_JSON= # or provider-supported workload identity config
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
- `pnpm typecheck` and the Next production build pass.
