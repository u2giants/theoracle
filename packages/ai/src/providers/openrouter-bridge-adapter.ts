/**
 * R6 — OpenRouter bridge adapter.
 *
 * Transitional adapter that lets the R6 claim-extraction worker call
 * `OracleAIClient.runObject(...)` without yet requiring the real
 * `@anthropic-ai/sdk`, `@google/genai`, or `openai` packages to be wired.
 * Under the hood it dispatches through the existing OpenRouter + Vercel AI
 * SDK stack — the same provider the worker already uses — but the call
 * shape and the context-pack/observability metadata go through the
 * provider-native pipeline.
 *
 * **This adapter is not part of the target architecture.** R7 wires the
 * VertexGeminiAdapter to real `@google/genai`; once that lands, the
 * claim-extraction worker drops the bridge and uses Vertex directly. R8/R9
 * do the same for the chat route and synthesis worker.
 *
 * Conventions:
 * - The adapter wears whichever `provider` tag the caller asked for
 *   (`anthropic`, `vertex`, or `openai`) so `OracleAIClient` dispatches
 *   to it via the curated route IDs. The real underlying provider on the
 *   wire is always OpenRouter for now.
 * - `route.modelId` is the curated production model name (e.g.
 *   `claude-haiku-4-5`); the bridge maps it to OpenRouter's namespace
 *   (e.g. `anthropic/claude-haiku-4-5`) at the call site.
 * - Usage data is normalized into OracleUsage just like a real adapter
 *   would do. Cache token counts are absent because OpenRouter doesn't
 *   surface provider-native cache metadata in a uniform way.
 */

import { generateObject, generateText } from 'ai';
import type { LanguageModel } from 'ai';
import { getOpenRouter } from '../openrouter';
import type {
  OracleObjectResult,
  OraclePromptPlan,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type { OracleModelRoute, OracleProvider } from '../routes';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';

export interface OpenRouterBridgeAdapterOptions {
  /** Which provider tag this adapter should report. Lets one adapter wear the hat of any of the 3 producers. */
  provider: OracleProvider;
  /** Optional override of the system message. Defaults to extracting from the plan blocks. */
  systemOverride?: string;
}

export class OpenRouterBridgeAdapter implements OracleProviderAdapter {
  readonly provider: OracleProvider;
  private readonly systemOverride?: string;

  constructor(opts: OpenRouterBridgeAdapterOptions) {
    this.provider = opts.provider;
    this.systemOverride = opts.systemOverride;
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route } = args;
    const model = this.resolveModel(route);
    const { systemPrompt, userMessage } = this.flattenPlan(plan);
    const callStartedAt = Date.now();
    const result = await generateText({
      model,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
    });
    const latencyMs = Date.now() - callStartedAt;
    return {
      text: result.text,
      usage: this.normalizeUsage(result.usage, latencyMs),
      rawResponse: { providerResponse: result.response, finishReason: result.finishReason },
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
      usage: this.normalizeUsage(result.usage, latencyMs),
      rawResponse: { providerResponse: result.response, finishReason: result.finishReason },
    };
  }

  /**
   * Map a curated `OracleModelRoute` to an OpenRouter model handle.
   *
   * The route's `modelId` is the production canonical name (e.g.
   * `claude-haiku-4-5`). OpenRouter namespaces these as `vendor/model`,
   * so we prepend the vendor prefix derived from `route.provider`.
   *
   * Note: a few curated route IDs include the OpenRouter-namespace
   * vendor prefix already (`google/...`, `anthropic/...`, `openai/...`).
   * The adapter handles both shapes.
   */
  private resolveModel(route: OracleModelRoute): LanguageModel {
    const openrouter = getOpenRouter();
    const handle = route.modelId.includes('/')
      ? route.modelId
      : `${this.openRouterVendorPrefix(route)}/${route.modelId}`;
    return openrouter(handle);
  }

  private openRouterVendorPrefix(route: OracleModelRoute): string {
    switch (route.provider) {
      case 'anthropic':
        return 'anthropic';
      case 'vertex':
        return 'google';
      case 'openai':
        return 'openai';
    }
  }

  /**
   * Flatten the OraclePromptPlan into a (systemPrompt, userMessage) pair
   * suitable for the Vercel AI SDK's `system` + single-user-message shape.
   *
   * Stable blocks (stable_system, stable_tool_definition, stable_schema,
   * output_contract) become the system prompt — preserving cacheable-prefix
   * ordering. Semi-stable, retrieved, and dynamic blocks concatenate into
   * the user message in order.
   */
  private flattenPlan(plan: OraclePromptPlan): { systemPrompt: string; userMessage: string } {
    if (this.systemOverride) {
      const userMessage = plan.blocks.map((b) => b.content).join('\n\n');
      return { systemPrompt: this.systemOverride, userMessage };
    }

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
   * Normalize Vercel-AI-SDK usage into OracleUsage. Cache token counts
   * are unavailable through the SDK abstraction — they're filled when
   * real provider adapters land in R7+.
   */
  private normalizeUsage(usage: unknown, latencyMs: number): OracleUsage {
    const u = (usage ?? {}) as {
      inputTokens?: number;
      outputTokens?: number;
      totalTokens?: number;
    };
    return {
      inputTokens: u.inputTokens,
      outputTokens: u.outputTokens,
      latencyMs,
      rawUsageJson: usage,
    };
  }
}
