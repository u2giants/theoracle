// Vertex Gemini capability source — Gemini Flash-Lite enumerates + classifies.
//
// Vertex's publishers/google/models REST endpoint returns the entire Model
// Garden (TFVision, MedLM, open-source forks, etc.) without a clean capability
// schema for Gemini specifically. Filtering by "gemini-" prefix would leave us
// with IDs and no caps, so we'd still need a classifier.
//
// Cleaner: ask Gemini Flash-Lite both to list the current Gemini production
// models available on Vertex and to classify each one against the same schema
// used for OpenAI. Gemini knows its own family and the prompt instructs it to
// use only Google's official Vertex AI docs.

import { z } from 'zod';
import type { ModelCapability } from '../types';
import { OracleAIClient } from '../../client/oracle-ai-client';
import { makeBlock } from '../../context/prompt-blocks';

const VertexClassifiedSchema = z.object({
  models: z.array(z.object({
    id: z.string(),                  // bare model id, e.g. "gemini-2.5-flash"
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

const CLASSIFIER_PROMPT_VERSION = 'vertex-gemini-discovery@1';

const VERTEX_SYSTEM = `You are enumerating and classifying Gemini foundation models currently available as PUBLISHER MODELS in Vertex AI (us-central1 region) for an admin dashboard. The dashboard powers a model picker; misclassifying a capability sends real customer requests to a model that cannot fulfil them.

Output the current production-grade Gemini models suitable for general chat / extraction / synthesis workloads. Include the live Gemini families documented by Google for Vertex AI use (e.g. Gemini 2.5 Pro / Flash / Flash-Lite, Gemini 2.0 Flash, Gemini 1.5 Pro / Flash). Exclude experimental "-exp" variants, model garden third-party models, embeddings, image generation models, and any model marked deprecated. Include stable, non-preview entries only.

Per-model fields, using ONLY capabilities documented in the Vertex AI / Google AI public docs for that exact model id. If unknown, output false / null. Do not guess.

- id: bare Vertex model id (e.g. "gemini-2.5-flash" — no provider prefix, no project path)
- displayName: official name (e.g. "Gemini 2.5 Flash")
- contextLength: documented max input tokens (integer)
- maxOutputTokens: documented max output tokens per request (integer)
- vision: true iff the model accepts image / video inputs
- pdf: true iff the model accepts PDF/document file inputs (Gemini supports this broadly for 1.5+)
- thinking: true iff the model supports the thinkingConfig / "thinking mode" parameter (Gemini 2.5 family and 2.0 Flash; older 1.5 family does NOT)
- structuredOutputs: true iff the model supports responseSchema / responseMimeType=application/json with a schema
- toolCalling: true iff the model supports the tools / function_declarations parameter
- promptCaching: true iff Vertex prompt caching (implicit or explicit) is supported`;

/**
 * Discover Vertex Gemini capabilities. Requires an OracleAIClient instance
 * configured with the Vertex Gemini adapter.
 */
export async function fetchVertexCapabilities(
  client: OracleAIClient,
): Promise<ModelCapability[]> {
  const plan = client.compile({
    taskType: 'model_capability_discovery',
    routeId: 'vertex_gemini_2_5_flash_lite_message_triage',
    promptVersion: CLASSIFIER_PROMPT_VERSION,
    blocks: [
      makeBlock({
        id: 'system',
        label: 'Vertex Gemini discovery prompt',
        kind: 'stable_system',
        content: VERTEX_SYSTEM,
        reasonIncluded: 'Static enumeration + classification rules',
      }),
      makeBlock({
        id: 'input',
        label: 'Vertex Gemini list request',
        kind: 'dynamic_input',
        content: 'Enumerate and classify the current Vertex AI Gemini publisher models.',
        reasonIncluded: 'Trigger for the discovery turn',
      }),
    ],
  });

  const result = await client.runObject({
    taskType: 'model_capability_discovery',
    routeId: 'vertex_gemini_2_5_flash_lite_message_triage',
    promptVersion: CLASSIFIER_PROMPT_VERSION,
    blocks: plan.blocks,
    schema: VertexClassifiedSchema,
  });

  if (!result.validation.ok) {
    throw new Error(
      `Vertex capability discovery failed schema validation: ${result.validation.error.message.slice(0, 500)}`,
    );
  }

  const now = new Date().toISOString();
  return result.validation.value.models.map((c): ModelCapability => ({
    id: `google/${c.id}`,
    provider: 'google',
    displayName: c.displayName || c.id,
    contextLength: c.contextLength,
    maxOutputTokens: c.maxOutputTokens,
    vision: c.vision,
    pdf: c.pdf,
    thinking: c.thinking,
    structuredOutputs: c.structuredOutputs,
    toolCalling: c.toolCalling,
    promptCaching: c.promptCaching,
    source: 'vertex_classified',
    fetchedAt: now,
  }));
}
