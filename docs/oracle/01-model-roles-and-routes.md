# Model Roles and Model Routes

Status: mandatory AI implementation guidance.

This document defines the three primary model roles for The Oracle and the top model choices for each role.

## Executive decision

Yes: the three-role split is correct.

The Oracle should expose three primary model roles in Admin settings:

1. Interview model.
2. Extraction model.
3. Synthesis model.

These roles match the product architecture better than a single global model setting. The Oracle performs three very different kinds of work:

- talking to employees tactfully;
- extracting evidence-backed claim candidates cheaply and repeatedly;
- synthesizing operational truth into a versioned Brain with high reasoning quality.

Trying to optimize all three with one model will either waste money or reduce quality.

## Important distinction: model role vs internal subroute

The three model roles are the user-facing/admin-facing defaults.

Internally, the `ModelRouter` may later introduce subroutes such as:

- contradiction prefilter;
- hard contradiction review;
- validation repair;
- admin explanation;
- retrieval query rewriting;
- document OCR/image interpretation;
- Brain synthesis critique.

Do not expose those internal subroutes to Albert at first unless there is a clear operational reason. Keep the admin model configuration understandable.

## Big 3 provider boundary

The production provider set is:

- Google Vertex AI / Gemini direct;
- Anthropic direct;
- OpenAI direct.

Do not use OpenRouter for production background extraction, document ingestion, synthesis, or other cache-sensitive AI jobs.

OpenRouter may remain as a temporary legacy path while the repo is being refactored, or as a model scouting tool, but it is not the target architecture.

## Model route object

Do not store only a raw model string such as `anthropic/claude-sonnet-4.6`.

A route must include provider, model, cache strategy, structured-output strategy, fallback behavior, and task fit.

Minimum route shape:

```ts
type OracleModelRole = 'interview' | 'extraction' | 'synthesis';

type OracleProvider = 'anthropic' | 'vertex' | 'openai';

type CacheStrategy =
  | 'anthropic_automatic'
  | 'anthropic_explicit_breakpoints'
  | 'anthropic_auto_plus_explicit'
  | 'vertex_implicit'
  | 'vertex_explicit_context_cache'
  | 'vertex_implicit_or_explicit_by_context_size'
  | 'openai_automatic_prefix'
  | 'openai_automatic_with_cache_key'
  | 'openai_automatic_with_retention'
  | 'none';

type StructuredOutputStrategy =
  | 'native_json_schema'
  | 'tool_call'
  | 'schema_prompt_plus_validator';

type OracleModelRoute = {
  routeId: string;
  role: OracleModelRole;
  provider: OracleProvider;
  modelId: string;
  displayName: string;
  recommendedUse: string;
  cacheStrategy: CacheStrategy;
  structuredOutputStrategy: StructuredOutputStrategy;
  supportsVision: boolean;
  supportsStreaming: boolean;
  supportsToolCalling: boolean;
  supportsStructuredOutput: boolean;
  supportsReasoningControls: boolean;
  maxInputTokens?: number;
  maxOutputTokens?: number;
  fallbackRouteIds: string[];
  enabled: boolean;
};
```

The admin settings table may store the selected `routeId`. The route definitions themselves may live in versioned TypeScript config first. Move them into Postgres only when live editing is needed.

## Role 1: Interview model

Purpose:

- employee-facing Oracle conversation;
- direct mentions in 1:1 and group chat;
- interview-style questioning;
- tactful clarification;
- psychologically safe follow-up questions;
- weaving in open gaps when relevant.

Most important qualities:

1. Tone and tact.
2. Ability to ask one precise question.
3. Resistance to sounding like HR, a cop, or a project manager.
4. Tool use for searching approved claims and open gaps.
5. Low latency.
6. Reasonable cost.

Top 3 interview model choices:

### 1. Anthropic Claude Sonnet 4.6 direct

Default recommendation for the interview role.

Why:

- best balance of tone, tact, instruction-following, and cost;
- strong at psychologically safe workplace phrasing;
- strong at conversation and follow-up questions;
- supports Anthropic prompt caching patterns for repeated system prompt and long conversations;
- likely better than a pure extraction model at not sounding robotic.

Caching strategy:

- use `anthropic_auto_plus_explicit` when possible;
- explicit cache breakpoint after stable Oracle system prompt and stable tool definitions;
- use automatic/top-level caching for longer conversation history when the provider supports it;
- dynamic current turn, retrieved claims, and retrieved gaps must remain after stable cacheable content.

Use when:

- default live Oracle chat;
- direct employee interviews;
- admin test chat;
- delicate group-chat clarifications.

### 2. Google Gemini Pro direct through Vertex AI

Second choice for the interview role when long context or Google ecosystem behavior is more valuable.

Why:

- strong long-context handling;
- direct Vertex usage can benefit from implicit caching for stable prefixes;
- useful if the interview route increasingly includes long documents or long histories;
- good fallback if Anthropic latency, quota, or cost becomes problematic.

Caching strategy:

- use `vertex_implicit` for normal chat;
- use explicit Vertex context caching only if a large stable interview context is reused repeatedly;
- track cached token counts from provider metadata.

Use when:

- interview conversations need unusually large context;
- the Oracle needs to reason over a large document in live chat;
- Anthropic is unavailable.

### 3. OpenAI GPT direct

Third choice for interview and admin-facing chat fallback.

Why:

- reliable general-purpose fallback;
- good structured/tool behavior;
- useful if Anthropic or Gemini route fails;
- direct OpenAI prompt caching can be helped with stable prefix design and route-specific cache keys.

Caching strategy:

- use `openai_automatic_with_cache_key` where supported;
- keep stable prompt, stable tool schemas, and stable output rules first;
- log cached tokens from provider-native usage fields.

Use when:

- Anthropic and Gemini are unavailable;
- admin-facing explanation needs reliable structured formatting;
- a direct OpenAI model wins interview evals.

## Role 2: Extraction model

Purpose:

- claim candidate extraction from chat messages;
- document chunk claim extraction;
- group-chat semantic extraction;
- domain tagging;
- low-risk gap suggestions;
- candidate evidence extraction.

Most important qualities:

1. Low cost at high volume.
2. Structured output reliability.
3. Verbatim quote discipline.
4. Strong enough reasoning to separate claim stated, challenged, refined, and exception introduced.
5. Good caching with repeated prompts/schemas/documents.

Top 3 extraction model choices:

### 1. Google Gemini 2.5 Flash direct through Vertex AI

Default recommendation for extraction.

Why:

- best fit for high-volume extraction and document-heavy processing;
- strong cost/performance for large batches;
- direct Vertex AI supports implicit caching for repeated stable prefixes;
- explicit context caching can be used for large reusable PDFs, SOPs, tech packs, style guides, and transcript batches;
- good multimodal/document capabilities.

Caching strategy:

- use `vertex_implicit` for normal message extraction;
- use `vertex_implicit_or_explicit_by_context_size` for document ingestion;
- create explicit cached content only when the same large document/context will be queried multiple times;
- store provider cached-content resource names, TTLs, source hashes, and expiration in Postgres;
- do not delete explicit caches immediately if retries/follow-up passes are likely.

Use when:

- extracting from batches of chat messages;
- extracting from document chunks;
- processing PDFs/images/technical documents;
- running high-volume nightly or four-hour cron extraction.

### 2. OpenAI small/mini structured-output model direct

Second choice for extraction when strict structured output is the priority.

Why:

- strong native structured outputs / JSON schema support;
- good fallback when Gemini produces schema-invalid candidates;
- useful for validation-repair passes;
- direct OpenAI automatic prompt caching can reduce repeated schema/prompt costs.

Caching strategy:

- use `openai_automatic_with_cache_key` for repeated stable extraction prompts and schemas;
- use stable task/schema prompt first, dynamic messages or chunks last;
- log cached token counts and validation results.

Use when:

- Gemini extraction fails schema validation too often;
- exact output shape is more important than multimodal context;
- validation repair is needed.

### 3. Anthropic Claude Sonnet direct

Third choice for extraction when nuance matters more than raw cost.

Why:

- strong at understanding human disagreement and subtle process exceptions;
- useful for group chats where employees challenge or refine each other;
- useful as an escalation route for high-impact or ambiguous claims.

Caching strategy:

- use explicit breakpoints after stable extraction rules/schema;
- dynamic transcript or document chunk comes after the cache breakpoint;
- avoid using Sonnet for all bulk extraction unless evals show the higher cost is justified.

Use when:

- candidate affects customer/licensor risk;
- conversation contains disagreement, sarcasm, correction, or exception handling;
- cheaper model output fails validation or is too shallow.

## Role 3: Synthesis model

Purpose:

- Brain section synthesis;
- versioned operational narrative;
- material changes based on approved claims;
- contradiction reasoning;
- gap creation and resolution;
- admin-facing explanation of why the Oracle believes something.

Most important qualities:

1. Evidence fidelity.
2. Strong reasoning.
3. Ability to produce structured diffs.
4. Ability to avoid unsupported statements.
5. Clear writing.
6. Good handling of contradictions and exceptions.

Top 3 synthesis model choices:

### 1. Anthropic Claude Opus 4.7 direct

Highest-quality synthesis route.

Why:

- best choice for hard synthesis, architecture-level reasoning, and nuanced operational truth;
- preferred for complex Brain section rewrites and cross-department logic;
- likely strongest at preserving caveats, exceptions, and uncertainty;
- best route when a failed synthesis would waste human review time.

Caching strategy:

- use `anthropic_explicit_breakpoints`;
- cache stable synthesis rules, traceability rules, output schema, validation rules, and tool definitions;
- keep selected section, approved claims, current version, and dynamic job input after the breakpoint;
- use longer TTL only when repeated synthesis attempts or review passes are expected.

Use when:

- synthesizing important Brain sections;
- resolving complex contradictions;
- creating admin-facing executive explanations;
- quality matters more than cost.

### 2. Anthropic Claude Sonnet 4.6 direct

Default day-to-day synthesis route.

Why:

- strong synthesis quality at lower cost/latency than Opus;
- good enough for most Brain sections once the validation layer is strict;
- same provider caching mechanics as Opus;
- useful as the normal synthesis default, with Opus as escalation.

Caching strategy:

- same as Opus: explicit breakpoint after stable synthesis prompt/schema;
- route to Opus if validation fails repeatedly or the section is high-impact.

Use when:

- ordinary Brain section updates;
- scheduled maintenance synthesis;
- approved claim batches that are not high-risk.

### 3. Google Gemini Pro direct through Vertex AI

Third choice for synthesis when context size is the binding constraint.

Why:

- strong long-context option;
- useful for unusually large sets of approved claims or large source documents;
- Vertex explicit context caching may make repeated analysis over large context economical.

Caching strategy:

- use `vertex_implicit` for ordinary synthesis;
- use explicit Vertex context caching when the approved claim corpus, source document, or section context is very large and reused across multiple passes;
- validate output just as strictly as Anthropic output.

Use when:

- context is too large or too document-heavy for the default Anthropic route;
- repeated synthesis/review passes over the same large context are expected;
- Anthropic is unavailable.

## Recommended defaults

Initial default role selections:

```ts
export const DEFAULT_ORACLE_MODEL_ROUTES = {
  interview: 'anthropic_claude_sonnet_interview_primary',
  extraction: 'vertex_gemini_flash_extraction_primary',
  synthesis: 'anthropic_claude_sonnet_synthesis_primary',
};
```

Escalation defaults:

```ts
export const ORACLE_ESCALATION_ROUTES = {
  interviewQualityEscalation: 'anthropic_claude_opus_interview_escalation',
  extractionStructuredFallback: 'openai_structured_extraction_fallback',
  extractionNuanceEscalation: 'anthropic_claude_sonnet_extraction_escalation',
  synthesisQualityEscalation: 'anthropic_claude_opus_synthesis_escalation',
  synthesisLongContextFallback: 'vertex_gemini_pro_synthesis_long_context',
};
```

## Admin settings behavior

The Admin Settings UI should display the three roles clearly:

- Interview model: controls real-time Oracle conversation.
- Extraction model: controls background claim candidate extraction from messages/documents.
- Synthesis model: controls Brain section synthesis and high-level operational reasoning.

Each selected route should show:

- provider;
- model display name;
- expected strengths;
- cache strategy;
- structured-output strategy;
- whether it supports vision;
- whether it supports tools;
- fallback route;
- last 7-day cost;
- last 7-day validation success rate;
- last 7-day cache hit rate where available.

Do not show a giant public catalog of models. This app should expose a curated list of approved routes only.

## Evaluation rule

A model route is not approved because it is fashionable or cheap.

A model route is approved only if it performs well on Oracle-specific evals:

- interview usefulness and tone;
- claim extraction precision/recall;
- evidence quote validity;
- wrong-domain rate;
- duplicate-claim rate;
- false contradiction rate;
- Brain section usefulness;
- cost per valid claim;
- cost per accepted Brain update;
- cache hit rate;
- retry/fallback rate.

## Current repo retrofit warning

The current repo uses OpenRouter model IDs in settings and an OpenRouter model picker. That is legacy implementation debt.

The model picker should be refactored to select `OracleModelRoute.routeId`, not arbitrary OpenRouter model IDs.

OpenRouter-specific capability detection should not drive production provider selection after the Big 3 adapter retrofit.
