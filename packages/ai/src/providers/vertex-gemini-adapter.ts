/**
 * VertexGeminiAdapter — direct Google Vertex AI integration via
 * `@ai-sdk/google-vertex`. This is the real adapter that replaces the
 * transitional OpenRouterBridgeAdapter for `provider: 'vertex'` routes.
 *
 * Architecture:
 * - Calls Vertex AI's REST API directly (NOT through OpenRouter).
 * - Authenticates via Application Default Credentials. Set up locally
 *   with `gcloud auth application-default login` and ensure the active
 *   gcloud configuration points at the target project. In Vercel / cloud
 *   runtime, mount a service account JSON via env vars (the SDK auto-
 *   detects).
 * - Reads `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from env.
 *
 * Caching strategy (round 1 — implicit only):
 * - Implicit caching is automatic on Gemini's side; no client action
 *   required. Cache hits show up as a populated
 *   `usageMetadata.cachedContentTokenCount` in the response and are
 *   normalized into `OracleUsage.cachedInputTokens`.
 * - Explicit `cachedContent` lifecycle (with `provider_cached_content`
 *   row tracking + TTL cleanup) is a round-2 follow-up. Will require
 *   either upgrading to the raw `@google/genai` SDK or using the lower-
 *   level Vertex AI REST endpoints.
 *
 * Structured output:
 * - Uses Gemini's native JSON-schema mode via `generateObject` from the
 *   Vercel AI SDK. This is the property that fixes the wet-test
 *   blocker — OpenRouter → Gemini doesn't reliably enforce schema,
 *   direct Vertex does.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "Google Vertex AI
 * / Gemini direct".
 */

import { createVertex } from '@ai-sdk/google-vertex';
import type { GoogleVertexProvider } from '@ai-sdk/google-vertex';
import { generateObject, generateText } from 'ai';
import type { LanguageModel } from 'ai';
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
  /** Vertex region. Defaults to env GOOGLE_CLOUD_LOCATION or `us-central1`. */
  location?: string;
}

export class VertexGeminiAdapter implements OracleProviderAdapter {
  readonly provider = 'vertex' as const;
  private readonly client: GoogleVertexProvider;

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
    this.client = createVertex({ project, location });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const model = this.resolveModel(route);
    const { systemPrompt, userMessage } = this.flattenPlan(plan);
    const callStartedAt = Date.now();

    // The chat route (R8+) passes a pre-built multi-turn `messages` array
    // through providerOptions; if present it overrides the flattened
    // single-message form. tools / stopWhen / temperature pass straight
    // through.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const messagesOverride = (providerOptions?.messages as any) ?? [
      { role: 'user', content: userMessage },
    ];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = await (generateText as any)({
      model,
      system: systemPrompt,
      messages: messagesOverride,
      tools: providerOptions?.tools,
      stopWhen: providerOptions?.stopWhen,
      temperature: providerOptions?.temperature,
    });
    const latencyMs = Date.now() - callStartedAt;
    return {
      text: result.text,
      usage: this.normalizeUsage(result, latencyMs),
      rawResponse: {
        providerResponse: result.response,
        finishReason: result.finishReason,
      },
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema } = args;
    const model = this.resolveModel(route);
    const { systemPrompt, userMessage } = this.flattenPlan(plan);
    const callStartedAt = Date.now();
    // The Vercel AI SDK exposes generateObject as a discriminated union of
    // overloads; passing a Zod schema through a generic adapter requires a
    // duck-typed cast. OracleAIClient re-validates the output with the
    // caller-supplied Zod schema after dispatch, so the cast is safe.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = await (generateObject as any)({
      model,
      schema,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
      temperature: 0.1,
    });
    const latencyMs = Date.now() - callStartedAt;
    return {
      object: result.object as TOutput,
      usage: this.normalizeUsage(result, latencyMs),
      rawResponse: {
        providerResponse: result.response,
        finishReason: result.finishReason,
      },
    };
  }

  /** Map the curated route to a Vercel AI SDK Vertex model handle. */
  private resolveModel(route: OracleModelRoute): LanguageModel {
    return this.client(route.modelId);
  }

  /**
   * Flatten the OraclePromptPlan into a (systemPrompt, userMessage) pair.
   * Stable blocks (stable_system, stable_tool_definition, stable_schema,
   * output_contract) become the system prompt — preserving cacheable-prefix
   * ordering. Semi-stable, retrieved, and dynamic blocks concatenate into
   * the user message in order.
   */
  private flattenPlan(plan: OraclePromptPlan): {
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
   * Normalize Vertex AI SDK usage into OracleUsage.
   *
   * `@ai-sdk/google-vertex` exposes Gemini's `usageMetadata` under
   * `result.providerMetadata.google.usageMetadata`. The field names match
   * Gemini's REST schema:
   *   - promptTokenCount          -> inputTokens (top-level fallback)
   *   - candidatesTokenCount      -> outputTokens (top-level fallback)
   *   - cachedContentTokenCount   -> cachedInputTokens
   *   - thoughtsTokenCount        -> reasoningTokens (Gemini 2.5+ thinking)
   *
   * We prefer the top-level Vercel `usage` (provider-neutral) for input/output
   * counts when available and pull the Gemini-native fields only for cache
   * and reasoning counts.
   */
  private normalizeUsage(result: unknown, latencyMs: number): OracleUsage {
    const r = (result ?? {}) as {
      usage?: { inputTokens?: number; outputTokens?: number };
      providerMetadata?: {
        google?: {
          usageMetadata?: {
            promptTokenCount?: number;
            candidatesTokenCount?: number;
            cachedContentTokenCount?: number;
            thoughtsTokenCount?: number;
          };
        };
      };
      response?: { id?: string };
    };
    const googleUsage = r.providerMetadata?.google?.usageMetadata ?? {};
    return {
      inputTokens: r.usage?.inputTokens ?? googleUsage.promptTokenCount,
      outputTokens: r.usage?.outputTokens ?? googleUsage.candidatesTokenCount,
      cachedInputTokens: googleUsage.cachedContentTokenCount,
      reasoningTokens: googleUsage.thoughtsTokenCount,
      latencyMs,
      providerRequestId: r.response?.id,
      rawUsageJson: {
        usage: r.usage,
        providerMetadata: r.providerMetadata,
      },
    };
  }
}
