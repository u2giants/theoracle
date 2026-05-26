/**
 * VertexGeminiAdapter — direct Google Vertex AI integration via `@google/genai`.
 *
 * Architecture (DECISIONS.md D6, docs/oracle/02 §"Shared architecture"):
 * - Calls Vertex AI's REST API directly using Google's official GenAI SDK.
 * - NO Vercel AI SDK and NO OpenRouter in this path.
 * - Authenticates via Application Default Credentials. Set up locally with
 *   `gcloud auth application-default login`. In cloud runtime, mount a
 *   service-account JSON or use workload identity — the SDK auto-detects.
 * - Reads `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from env.
 *
 * Caching strategy (round 1 — implicit only):
 * - Implicit caching is automatic on Gemini's side; no client action needed.
 *   Cache hits show up as `usageMetadata.cachedContentTokenCount` and are
 *   normalized into `OracleUsage.cachedInputTokens`.
 * - Explicit `cachedContent` lifecycle (with `provider_cached_content` row
 *   tracking + TTL cleanup per R7) is a follow-up. The SDK supports
 *   `ai.caches.create(...)` and `ai.caches.delete(...)` for that path.
 *
 * Structured output:
 * - Uses `responseMimeType: 'application/json'` + `responseJsonSchema:
 *   <jsonSchema>` (added in @google/genai 2.6). The JSON-schema mode is
 *   strict — Gemini enforces the schema on output. This is the direct
 *   capability that the OpenRouter -> Gemini bridge couldn't reach.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "Google Vertex AI
 * / Gemini direct".
 */

import { GoogleGenAI } from '@google/genai';
import type { Content, GenerateContentResponse } from '@google/genai';
import { z, type ZodTypeAny } from 'zod';
import type {
  OracleObjectResult,
  OraclePromptPlan,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type { OracleModelRoute } from '../routes';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';

export interface VertexGeminiAdapterOptions {
  /** GCP project ID. Defaults to env GOOGLE_CLOUD_PROJECT. */
  project?: string;
  /** Vertex region. Defaults to env GOOGLE_CLOUD_LOCATION or 'us-central1'. */
  location?: string;
}

export class VertexGeminiAdapter implements OracleProviderAdapter {
  readonly provider = 'vertex' as const;
  private readonly client: GoogleGenAI;

  constructor(opts: VertexGeminiAdapterOptions = {}) {
    const project = opts.project ?? process.env.GOOGLE_CLOUD_PROJECT;
    const location =
      opts.location ?? process.env.GOOGLE_CLOUD_LOCATION ?? 'us-central1';
    if (!project) {
      throw new Error(
        'VertexGeminiAdapter: GOOGLE_CLOUD_PROJECT is not set. ' +
          'Set it in .env.local or pass {project} explicitly.',
      );
    }
    this.client = new GoogleGenAI({ vertexai: true, project, location });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const contents = this.buildContents(userMessage, providerOptions);
    const callStartedAt = Date.now();

    const response = await this.client.models.generateContent({
      model: route.modelId,
      contents,
      config: {
        systemInstruction: systemPrompt || undefined,
        temperature:
          typeof providerOptions?.temperature === 'number'
            ? providerOptions.temperature
            : undefined,
      },
    });
    const latencyMs = Date.now() - callStartedAt;
    return {
      text: response.text ?? '',
      usage: this.normalizeUsage(response, latencyMs),
      rawResponse: response,
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const jsonSchema = zodToJsonSchema(schema);
    const callStartedAt = Date.now();

    const response = await this.client.models.generateContent({
      model: route.modelId,
      contents: [{ role: 'user', parts: [{ text: userMessage }] }],
      config: {
        systemInstruction: systemPrompt || undefined,
        temperature: 0.1,
        responseMimeType: 'application/json',
        // responseJsonSchema accepts standard JSON Schema as of @google/genai 2.6.
        responseJsonSchema: jsonSchema as unknown,
      },
    });
    const latencyMs = Date.now() - callStartedAt;
    const text = response.text ?? '';
    const parsed = JSON.parse(text);
    // Best-effort runtime validation if a Zod schema was supplied — gives the
    // caller a typed error rather than silently passing through malformed output.
    const validated = tryZodParse<TOutput>(schema, parsed);
    return {
      object: (validated ?? parsed) as TOutput,
      usage: this.normalizeUsage(response, latencyMs),
      rawResponse: response,
    };
  }

  /**
   * Translate `providerOptions.messages` (a multi-turn array shaped for the
   * Vercel AI SDK / OpenAI chat format) into Vertex's `contents` shape, or
   * fall back to a single user turn when no override is present.
   */
  private buildContents(
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): Content[] {
    const messages = providerOptions?.messages as
      | Array<{ role: 'user' | 'assistant' | 'system'; content: string }>
      | undefined;
    if (Array.isArray(messages) && messages.length > 0) {
      // Vertex uses 'model' instead of 'assistant'; system goes in
      // systemInstruction not contents.
      return messages
        .filter((m) => m.role !== 'system')
        .map((m) => ({
          role: m.role === 'assistant' ? 'model' : 'user',
          parts: [{ text: m.content }],
        }));
    }
    return [{ role: 'user', parts: [{ text: userMessage }] }];
  }

  /**
   * Normalize Gemini usage into OracleUsage.
   *   - promptTokenCount        -> inputTokens
   *   - candidatesTokenCount    -> outputTokens
   *   - cachedContentTokenCount -> cachedInputTokens
   *   - thoughtsTokenCount      -> reasoningTokens (Gemini 2.5+ thinking)
   */
  private normalizeUsage(
    response: GenerateContentResponse,
    latencyMs: number,
  ): OracleUsage {
    const u = response.usageMetadata ?? {};
    return {
      inputTokens: u.promptTokenCount,
      outputTokens: u.candidatesTokenCount,
      cachedInputTokens: u.cachedContentTokenCount,
      reasoningTokens: u.thoughtsTokenCount,
      latencyMs,
      providerRequestId: response.responseId,
      rawUsageJson: u,
    };
  }
}

// ─── Shared helpers (also used by anthropic + openai adapters) ──────────────

/**
 * Flatten the OraclePromptPlan into a (systemPrompt, userMessage) pair.
 * Stable blocks become the system prompt; semi-stable / retrieved / dynamic
 * blocks concatenate into the user message in order. Preserves cacheable-
 * prefix ordering so provider-native cache machinery actually hits.
 */
export function flattenPlan(plan: OraclePromptPlan): {
  systemPrompt: string;
  userMessage: string;
} {
  const stable: string[] = [];
  const dynamic: string[] = [];
  for (const block of plan.blocks) {
    const isStable =
      block.kind === 'stable_system' ||
      block.kind === 'stable_tool_definition' ||
      block.kind === 'stable_schema' ||
      block.kind === 'output_contract';
    if (isStable) stable.push(block.content);
    else dynamic.push(block.content);
  }
  return {
    systemPrompt: stable.join('\n\n'),
    userMessage: dynamic.join('\n\n'),
  };
}

/**
 * Convert a Zod schema (or any unknown — we duck-type) to standard JSON
 * Schema 2020-12. Falls back to assuming the input is already JSON Schema if
 * it doesn't look like a Zod object.
 */
export function zodToJsonSchema(schema: unknown): unknown {
  const s = schema as { _def?: unknown };
  if (s && typeof s === 'object' && '_def' in s) {
    return z.toJSONSchema(schema as ZodTypeAny);
  }
  return schema;
}

/**
 * Best-effort Zod runtime validation. Returns the validated value on success,
 * or null if the input doesn't look like a Zod schema (so the caller can fall
 * back to the raw parsed JSON). Throws on Zod validation failure — the caller
 * decides what to do.
 */
export function tryZodParse<T>(schema: unknown, value: unknown): T | null {
  const s = schema as { safeParse?: (v: unknown) => { success: boolean; data: T; error: unknown } };
  if (s && typeof s === 'object' && typeof s.safeParse === 'function') {
    const result = s.safeParse(value);
    if (!result.success) {
      throw new Error(
        `VertexGeminiAdapter.generateObject: model output failed Zod validation: ${String(result.error)}`,
      );
    }
    return result.data;
  }
  return null;
}
