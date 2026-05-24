# Model Roles and Model Routes

Status: mandatory AI implementation guidance.

This document defines the three primary model roles for The Oracle and the cost-aware route choices for each role.

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

## Critical cost correction

Do not default to frontier models for routine runtime workloads.

Frontier models are allowed only as escalation/manual-review routes. The default production routes must be cost-aware because The Oracle may run extraction workers on many messages and documents.

The target optimization is not best raw model quality.

The target optimization is:

```text
lowest cost per useful, validated, evidence-backed result
```

Track and optimize:

- cost per valid claim;
- cost per approved claim;
- cost per useful gap;
- cost per accepted Brain update;
- validation failure rate;
- retry rate;
- cache hit rate;
- human review rejection rate.

A cheap model that produces invalid candidates is expensive. A frontier model that runs on every background job is also expensive. The architecture must use cheaper models first, then escalate selectively.

## Important distinction: model role vs internal subroute

The three model roles are the user-facing/admin-facing defaults.

Internally, the `ModelRouter` may introduce subroutes such as:

- contradiction prefilter;
- hard contradiction review;
- validation repair;
- admin explanation;
- retrieval query rewriting;
- document OCR/image interpretation;
- Brain synthesis critique;
- high-risk escalation.

Do not expose every internal subroute to Albert at first. Keep the admin model configuration understandable.

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

type RouteCostTier = 'cheap_default' | 'balanced_default' | 'expensive_escalation' | 'manual_only_frontier';

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
  costTier: RouteCostTier;
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

The admin settings table should store selected `routeId` values. Route definitions may live in versioned TypeScript config first. Move them into Postgres only when live editing is needed.

## Model budget policy

The runtime route policy must be conservative:

```ts
export const ORACLE_MODEL_BUDGET_POLICY = {
  defaultToCheapOrBalanced: true,
  allowFrontierOnlyForEscalation: true,
  requireHumanOrValidatorTriggerForFrontier: true,
  requireCostLoggingForEveryCall: true,
  requireRouteEvalsBeforePromotion: true,
};
```

Do not allow routine cron workers to call frontier models across large batches.

Do not allow synthesis to call a frontier model by default until real eval data proves the cheaper route fails often enough to justify it.

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

Cost-aware top 3 interview routes:

### 1. Anthropic Claude Haiku direct

Default low-cost interview route.

Why:

- much cheaper than Sonnet while still generally good at conversational tone;
- suitable for routine direct mentions and short interviews;
- supports Anthropic prompt caching patterns;
- keeps employee-facing chat from becoming an uncontrolled cost center.

Caching strategy:

- use `anthropic_auto_plus_explicit` when available;
- cache stable Oracle system prompt and tool definitions;
- keep employee/channel context, recent messages, retrieved claims/gaps, and current user turn after stable cacheable content.

Use when:

- normal Oracle DMs;
- routine direct mentions;
- short follow-up questions;
- admin test chat that does not require deep synthesis.

### 2. Google Gemini Flash direct through Vertex AI

Second interview route and strong cost/performance fallback.

Why:

- strong cost/performance;
- useful for low-cost chat and long-context situations;
- direct Vertex usage can benefit from implicit caching;
- good fallback if Anthropic latency/quota/cost is problematic.

Caching strategy:

- use `vertex_implicit` for normal chat;
- use explicit Vertex context caching only if a large stable context is reused repeatedly;
- log cached token counts from provider metadata.

Use when:

- Anthropic is unavailable;
- chat needs larger retrieved context;
- Gemini wins interview evals on cost per useful conversation.

### 3. OpenAI mini model direct

Third interview route and structured/tool fallback.

Why:

- reliable tool/structured-output behavior;
- useful as a fallback if Anthropic/Gemini are unavailable;
- direct OpenAI prompt caching can be helped with stable prefix design and route-specific cache keys.

Caching strategy:

- use `openai_automatic_with_cache_key` where supported;
- keep stable prompt and tool schemas first;
- log cached tokens from provider-native usage fields.

Use when:

- Anthropic and Gemini fail;
- admin-facing response needs stricter formatting;
- OpenAI route wins interview evals.

Interview escalation routes:
- anthropic_claude_sonnet_interview_escalation (For reasoning/quality)
- anthropic_claude_haiku_45_interview_warmth_escalation (For emotional sensitivity)

Use Sonnet only when:
- Haiku/Gemini output lacks sufficient reasoning for a complex workflow;
- Albert/admin manually selects higher quality.

Use Haiku Warmth Escalation when:
- employeeSentiment in ['frustrated', 'defensive', 'confused', 'worried'];
- topicSensitivity in ['personnel_conflict', 'blame', 'error_source', 'customer_issue'].
The Oracle is an internal tool. If it sounds like a cold HR monitor, employees will lose trust. Route sensitive emotional states to a dedicated prompt/model variant tuned for empathy.

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

Cost-aware top 3 extraction routes:

### 1. Google Gemini Flash-Lite direct through Vertex AI
Default high-volume text extraction route.

Why:
- cheapest practical first pass for routine message extraction;
- can use direct Vertex implicit caching for repeated stable prefixes.

WARNING (The "Fast Path" Trap):
While Flash-Lite is extremely cheap, it struggles with strict JSON schema compliance compared to Flash 1.5/2.0 or GPT-4o-mini. If you use Flash-Lite for fast-path extraction, you MUST pair it with a rigid `StructuredOutputValidator`. If the validation failure rate exceeds 15%, the cost of retrying the prompt will wipe out the savings. Escalate to Gemini Flash or OpenAI Mini if schema repair is needed.

### 2. Google Gemini Flash direct through Vertex AI

Default document and multimodal extraction route.

Why:

- better than Flash-Lite for document-heavy and multimodal extraction;
- still far cheaper than frontier models;
- strong fit for PDFs, SOPs, tech packs, images, OCR-like document workflows;
- supports implicit caching and explicit context caching through Vertex.

Caching strategy:

- use `vertex_implicit_or_explicit_by_context_size`;
- use explicit context caching for large reusable PDFs/SOPs/style guides/transcript batches;
- store cached-content resource name, TTL, source hash, and expiration in Postgres;
- do not delete explicit caches immediately if retries/follow-up passes are likely.

Use when:

- extracting from document chunks;
- processing PDFs/images/technical documents;
- running multi-pass extraction over the same document;
- Flash-Lite fails validation too often.

### 3. OpenAI mini structured-output model direct

Structured-output fallback and validation-repair route.

Why:

- strong native structured output / JSON schema behavior;
- useful when Gemini produces schema-invalid candidates;
- good fallback for validation repair;
- still much cheaper than frontier models.

Caching strategy:

- use `openai_automatic_with_cache_key` for repeated stable extraction prompts and schemas;
- stable task/schema prompt first, dynamic messages/chunks last;
- log cached tokens and validation results.

Use when:

- Gemini route fails schema validation;
- exact output shape is more important than multimodal context;
- validation repair is needed.

Extraction escalation route:

- Anthropic Claude Haiku or Sonnet direct depending on severity.

Use Anthropic escalation only when:

- group-chat nuance is high;
- the candidate affects customers/licensors/compliance;
- cheaper model repeatedly fails quote/schema validation;
- the claim is high-impact and ambiguous.

Do not run Claude Sonnet across all routine extraction batches.

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
2. Ability to produce structured diffs.
3. Ability to avoid unsupported statements.
4. Clear writing.
5. Good handling of contradictions and exceptions.
6. Low enough cost to run regularly.

Cost-aware top 3 synthesis routes:

### 1. Google Gemini Flash direct through Vertex AI

Default routine synthesis draft route.

Why:

- strong cost/performance;
- good for routine Brain draft updates that will be backend-validated and admin-reviewed;
- direct Vertex caching can help if repeated synthesis uses the same approved claim/context bundle;
- keeps routine synthesis economical.

Caching strategy:

- use `vertex_implicit` for ordinary small/medium synthesis;
- use explicit Vertex context caching when approved claim corpus, source document, or section context is large and reused across multiple passes;
- validate output just as strictly as Anthropic output.

Use when:

- routine Brain section draft updates;
- low/medium risk sections;
- scheduled synthesis over approved claims;
- synthesis output is always validated before it updates current Brain version.

### 2. Anthropic Claude Haiku direct

Balanced writing/reasoning synthesis route.

Why:

- better conversational/writing style than many cheap models;
- much cheaper than Sonnet/Opus;
- useful for admin-facing summaries and routine Brain explanations;
- can use Anthropic cache breakpoints on stable synthesis prompt/schema.

Caching strategy:

- use `anthropic_explicit_breakpoints`;
- cache stable synthesis rules, traceability rules, output schema, validation rules, and tool definitions;
- keep section, approved claims, current version, and job input after the breakpoint.

Use when:

- Gemini output is too dry or fails writing-quality evals;
- admin-facing explanation matters;
- routine synthesis needs better wording but not Sonnet-level cost.

### 3. Anthropic Claude Sonnet direct

High-quality escalation route.

Why:

- stronger synthesis and contradiction reasoning;
- appropriate for high-impact sections or repeated validation failures;
- still cheaper than Opus-class manual-only frontier routes;
- good at preserving nuance, caveats, exceptions, and uncertainty.

Caching strategy:

- same as Haiku: explicit breakpoint after stable synthesis prompt/schema;
- use only when validation/escalation criteria are met.

Use when:

- high-impact Brain section update;
- hard contradiction resolution;
- Gemini/Haiku synthesis fails validation;
- Albert/admin manually requests higher-quality synthesis.

Synthesis manual-only frontier route:

- Anthropic Claude Opus direct or current frontier equivalent.
- Google Gemini Pro / OpenAI frontier equivalent only if evals show they outperform Sonnet on this task.

Use frontier synthesis only when:

- a human explicitly requests it;
- the section is strategically important;
- cheaper routes failed validation or produced low usefulness;
- cost is logged and visible.

Do not make Opus or Gemini Pro the default synthesis route.

## First Production Pass: 1 Primary + 1 Fallback

To prevent architecture bloat during the first production pass, the `ModelRouter` exposes exactly 3 roles. Each role has exactly 1 Primary Route and 1 Fallback Route.

### 1. Interview Role
- **Primary:** `anthropic_claude_3_5_sonnet_interview_primary`
- **Fallback:** `openai_gpt4o_interview_fallback`
*Fallback Condition:* Triggered if Anthropic experiences an outage or rate limit during a live session.

### 2. Extraction Role
- **Primary:** `vertex_gemini_2_5_flash_extraction_primary` (Uses Google Explicit/Implicit caching).
- **Fallback:** `openai_gpt4o_mini_extraction_fallback`
*Fallback Condition:* Triggered if Vertex API fails or if Gemini repeatedly fails Zod schema validation during extraction.

### 3. Synthesis Role
- **Primary:** `anthropic_claude_3_5_sonnet_synthesis_primary`
- **Fallback:** `vertex_gemini_2_5_flash_synthesis_fallback`
*Fallback Condition:* Triggered if the primary model fails to generate valid Markdown diffs mapping to approved claim IDs.

---

### Internal Escalation & Manual Subroutes
These routes live behind the scenes in the `OracleAIClient` and are not exposed to the admin as primary routing knobs:
- `vertex_gemini_2_5_flash_lite_message_triage` (Cheap pre-filter scout).
- `anthropic_claude_haiku_warmth_escalation` (Triggered if employee sentiment is frustrated/confused).
- `openai_gpt4o_mini_schema_repair` (One-shot fix for malformed JSON candidates).

## Admin settings behavior

The Admin Settings UI should display the three roles clearly:

- Interview model: controls real-time Oracle conversation.
- Extraction model: controls background claim candidate extraction from messages/documents.
- Synthesis model: controls Brain section synthesis and high-level operational reasoning.

Each selected route should show:

- provider;
- model display name;
- expected strengths;
- cost tier;
- cache strategy;
- structured-output strategy;
- whether it supports vision;
- whether it supports tools;
- fallback route;
- last 7-day cost;
- last 7-day validation success rate;
- last 7-day cache hit rate where available.

Do not show a giant public catalog of models. This app should expose a curated list of approved routes only.

## Model routing rules

Default routing should be cheap-first:

1. Run the lowest-cost approved route for the task.
2. Validate deterministically.
3. If schema validation fails, try one repair pass or structured fallback.
4. If quote validation fails, store failure; do not blindly retry frontier models.
5. If the task is high-impact or repeatedly fails, escalate.
6. If synthesis fails backend support validation, escalate once to the next route.
7. Frontier/manual-only routes require explicit trigger or configured admin approval.

## Evaluation rule

A model route is not approved because it is fashionable, cheap, or frontier.

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
