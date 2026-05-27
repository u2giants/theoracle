// OpenAI capability source — live list of model IDs + Gemini classification.
//
// OpenAI's /v1/models endpoint returns only { id, owned_by, created } per
// model — no capability metadata. To avoid hand-typed capability tables that
// drift, we send the filtered list of chat model IDs through Gemini 2.5
// Flash-Lite with a strict schema, instructing the model to use only
// publicly documented capabilities and to mark anything unknown as false.

import { z } from 'zod';
import type { ModelCapability } from '../types';
import { OracleAIClient } from '../../client/oracle-ai-client';
import { makeBlock } from '../../context/prompt-blocks';

// IDs matching these patterns are NOT chat models and are filtered out before
// we ask the classifier. The list intentionally has no per-model capability
// knowledge — it just removes non-chat product categories so we don't waste
// Gemini tokens classifying e.g. DALL-E.
const NON_CHAT_PREFIXES = [
  /^dall-e/, /^whisper/, /^tts/, /^text-embedding/, /^omni-moderation/,
  /^text-moderation/, /^babbage/, /^davinci/, /^ada/, /^curie/, /^codex/,
  /-(audio|realtime|image|search|transcribe|moderation|embedding)/,
];

type OpenAIModelRaw = { id: string; owned_by: string; created: number };

async function listOpenAIChatModels(apiKey: string): Promise<string[]> {
  const res = await fetch('https://api.openai.com/v1/models', {
    headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new Error(`OpenAI /v1/models: ${res.status} ${await res.text()}`);
  const body = (await res.json()) as { data: OpenAIModelRaw[] };
  return (body.data ?? [])
    .filter((m) => m.owned_by === 'openai' || m.owned_by === 'openai-internal')
    .filter((m) => !NON_CHAT_PREFIXES.some((rx) => rx.test(m.id)))
    .map((m) => m.id)
    .sort();
}

const ClassifiedSchema = z.object({
  models: z.array(z.object({
    id: z.string(),
    displayName: z.string(),
    contextLength: z.number().int().nullable(),
    maxOutputTokens: z.number().int().nullable(),
    vision: z.boolean(),
    pdf: z.boolean(),
    thinking: z.boolean(),
    structuredOutputs: z.boolean(),
    toolCalling: z.boolean(),
    promptCaching: z.boolean(),
  })),
});

const CLASSIFIER_PROMPT_VERSION = 'model-capability-classifier@1';

const CLASSIFIER_SYSTEM = `You are classifying capabilities of OpenAI chat-completion models for an admin dashboard. The dashboard powers a model picker; misclassifying a capability sends a real customer request to a model that cannot fulfil it.

Use ONLY capabilities that are explicitly documented in OpenAI's public API reference (https://platform.openai.com/docs/api-reference) or model documentation (https://platform.openai.com/docs/models). If a capability is not clearly documented for a given model, output false / null. Do not guess. Do not extrapolate from a sibling model.

Fields:
- contextLength: integer max input tokens, or null if undocumented
- maxOutputTokens: integer max output tokens per request, or null if undocumented
- vision: true iff the model accepts image_url content parts via the Chat Completions / Responses API
- pdf: true iff the model accepts file/document uploads (NOT screenshots; few models support this — most are false)
- thinking: true iff the model exposes a "reasoning" parameter (reasoning_effort, etc.) — currently only the o-series (o1, o1-mini, o3, o3-mini, o4-mini, GPT-5 reasoning models)
- structuredOutputs: true iff the model supports response_format with type "json_schema"
- toolCalling: true iff the model supports the "tools" parameter (function calling)
- promptCaching: true iff prompt caching is documented as supported (most modern GPT-4.x / GPT-5.x / o-series models — true for the gpt-4o family and newer)
- displayName: human-readable label, e.g. "GPT-4o (2024-11-20)"

Output exactly one entry per input model ID — same order, no extras, no drops.`;

/**
 * Discover OpenAI capabilities. Requires an OracleAIClient instance configured
 * with the Vertex Gemini adapter (the classifier route is
 * vertex_gemini_2_5_flash_lite_message_triage).
 */
export async function fetchOpenAICapabilities(
  client: OracleAIClient,
): Promise<ModelCapability[]> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY not set');

  const ids = await listOpenAIChatModels(apiKey);
  if (ids.length === 0) return [];

  const userPayload = JSON.stringify({ models: ids });

  const plan = client.compile({
    taskType: 'model_capability_discovery',
    routeId: 'vertex_gemini_2_5_flash_lite_message_triage',
    promptVersion: CLASSIFIER_PROMPT_VERSION,
    blocks: [
      makeBlock({
        id: 'system',
        label: 'Classifier system prompt',
        kind: 'stable_system',
        content: CLASSIFIER_SYSTEM,
        reasonIncluded: 'Static classifier rules',
      }),
      makeBlock({
        id: 'input',
        label: 'OpenAI model id list',
        kind: 'dynamic_input',
        content: `Classify each model id in this JSON:\n${userPayload}`,
        reasonIncluded: 'Live OpenAI /v1/models id list',
      }),
    ],
  });

  const result = await client.runObject({
    taskType: 'model_capability_discovery',
    routeId: 'vertex_gemini_2_5_flash_lite_message_triage',
    promptVersion: CLASSIFIER_PROMPT_VERSION,
    blocks: plan.blocks,
    schema: ClassifiedSchema,
  });

  if (!result.validation.ok) {
    throw new Error(
      `OpenAI capability classification failed schema validation: ${result.validation.error.message.slice(0, 500)}`,
    );
  }

  const now = new Date().toISOString();
  return result.validation.value.models.map((c): ModelCapability => ({
    id: `openai/${c.id}`,
    provider: 'openai',
    displayName: c.displayName || c.id,
    contextLength: c.contextLength,
    maxOutputTokens: c.maxOutputTokens,
    vision: c.vision,
    pdf: c.pdf,
    thinking: c.thinking,
    structuredOutputs: c.structuredOutputs,
    toolCalling: c.toolCalling,
    promptCaching: c.promptCaching,
    source: 'openai_classified',
    fetchedAt: now,
  }));
}
