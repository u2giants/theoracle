# Adapter quirks and structured-output capability split

Status: implementation started 2026-07-07. This file is the forward plan and
implementation record for making Oracle model routing capability-accurate
instead of model-family folklore.

## Why this exists

`workflow_read` and the macro/holistic layer need large, deeply nested,
schema-validated JSON. The old `structuredOutputs` flag was too broad: it mixed
"can return JSON somehow" with "can enforce this exact Oracle schema through the
current adapter request body."

Live failures proved the distinction matters:

- `anthropic/claude-sonnet-5` failed immediately because the Anthropic adapter
  sent a `temperature` parameter that this model rejects.
- `google/gemini-2.5-pro` and related Gemini schema-mode candidates rejected the
  workflow/macro schemas as too complex.
- Qwen and DeepSeek JSON modes are best-effort `json_object` plus validation,
  not strict provider-enforced schema conformance.
- The workflow/macro pools stayed healthy only because fallback reached OpenAI
  strict JSON-schema models.

The goal is still portability across provider families where it is real. The
non-goal is weakening schemas, quote validation, or provenance just so another
family can appear eligible.

## Capability model

Keep `structuredOutputs` as a broad UI/readability flag, but do not use it alone
for deep-schema routing.

Add these `model_capabilities` fields:

- `strict_json_schema`: the provider/adapter path enforces the supplied JSON
  Schema, not just "please output JSON."
- `deep_schema_accepted`: the exact model+adapter path has been proven against
  Oracle's real workflow/macro schemas.
- `adapter_params_safe`: the current adapter request body is accepted by this
  model, including temperature, reasoning, cache, tool, and response-format
  params.
- `adapter_param_notes`: JSON notes for known provider/model caveats.

Initial policy:

- OpenAI `gpt-4.1` and `gpt-4.1-mini` are `deep_schema_accepted=true`.
- Gemini can be `strict_json_schema=true` for simpler tasks but
  `deep_schema_accepted=false` until real probes pass.
- Anthropic can be `strict_json_schema=true` through forced tool use, but
  `deep_schema_accepted=false` until real probes pass.
- Qwen and DeepSeek are `strict_json_schema=false` because their current paths
  use loose JSON mode.

## Runtime routing changes

Use explicit capability gates instead of provider-name gates:

- `workflow_read`: requires `strictJsonSchema`, `deepSchemaAccepted`,
  `adapterParamsSafe`, and context > 100K.
- `macro`: requires `strictJsonSchema`, `deepSchemaAccepted`, and
  `adapterParamsSafe`.
- `model_merge`: requires `strictJsonSchema`.
- ordinary extraction can still use strict schema-capable Gemini/OpenAI models;
  it should not inherit the deep-schema requirement unless its schema grows into
  that risk class.

Fallback remains load-bearing. If all candidates are filtered or fail at call
time, keep `AllCandidatesFailedError` and attempt logging.

## Adapter fixes

Anthropic:

- Omit `temperature` for Claude 5-style models and other models known to require
  default sampling.
- Preserve `temperature=1` for Anthropic thinking requests when supported.
- Make `generateObject` honor `providerOptions.maxOutputTokens`; workflow-read
  needs the 32K cap.

Qwen:

- Force `enable_thinking=false` for structured-output calls because DashScope
  thinking mode is incompatible with JSON mode.
- Keep Qwen out of strict/deep schema pools until the provider exposes real
  schema enforcement.

OpenAI/Gemini:

- Keep strict OpenAI JSON Schema as the known-good deep-schema baseline.
- Keep Gemini eligible for simpler structured work, but require a live
  deep-schema probe before allowing it into workflow/macro runtime gates.

## Admin UI and APIs

Expose the new fields in:

- `packages/ai/src/model-capabilities/types.ts`
- `packages/db/src/schema.ts`
- `/api/admin/model-catalog`
- `/api/admin/models`
- Admin Settings model picker and model pool editor

The model pool editor should show separate Strict, Deep, and Safe badges so an
admin can see why a model is unsuitable instead of reading Trigger logs after a
run fails.

## Verification plan

Required local gates:

- `corepack pnpm --filter @oracle/ai run verify:adapter-request-shapes`
- `corepack pnpm --filter @oracle/ai run verify:auxiliary-defaults`
- `corepack pnpm --filter @oracle/ai run verify:workflow-read`
- `corepack pnpm --filter @oracle/ai typecheck`
- `corepack pnpm --filter @oracle/web typecheck` if UI/API types changed

Required live/prod-like probes before changing non-OpenAI deep-schema eligibility:

1. Configure a one-element `model_pool_workflow_read` for the candidate.
2. Run `source-workflow-read` on the Stage 2 gate document.
3. Confirm the provider accepts the schema, returns schema-valid output, and
   survives quote validation at the expected recall threshold.
4. Repeat for macro relationship and coverage schemas if the model will be used
   by `macro`.
5. Only then set `deep_schema_accepted=true` for that model and record the
   evidence in `evals/` or `AGENT_ERROR_LOG.md`.

## Files touched by implementation

- Migration: `packages/db/migrations/sql/87_model_capability_granularity.sql`
- DB mirror: `packages/db/src/schema.ts`
- Capability source of truth: `packages/ai/src/model-capabilities/*`
- Runtime gates: `packages/ai/src/routes/capability-requirements.ts`,
  `packages/ai/src/routes/candidates.ts`, `packages/ai/src/routes/auxiliary.ts`
- Adapters: `packages/ai/src/providers/anthropic-adapter.ts`,
  `packages/ai/src/providers/qwen-adapter.ts`
- Admin surfaces: `apps/web/app/api/admin/models/route.ts`,
  `apps/web/app/api/admin/model-catalog/route.ts`,
  `apps/web/lib/stage-requirements.ts`, Admin Settings picker/pool components
- Guard script: `packages/ai/src/__verify__/adapter-request-shapes.ts`

