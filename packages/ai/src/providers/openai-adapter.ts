/**
 * OpenAIAdapter — direct OpenAI API integration via `@ai-sdk/openai`.
 *
 * Architecture:
 * - Calls OpenAI's REST API directly (NOT through OpenRouter).
 * - Authenticates via `OPENAI_API_KEY` env var (the SDK auto-reads it).
 *
 * Caching strategy (round 1 — automatic prefix caching):
 * - OpenAI auto-caches prompts >= 1024 tokens on the same prefix. No
 *   client action required. Cache hits show up as a populated
 *   `prompt_tokens_details.cached_tokens` in usage, normalized into
 *   `OracleUsage.cachedInputTokens`.
 * - Explicit cache-retention extensions (`prompt_cache_retention`) are a
 *   round-2 follow-up if we need long-lived caches.
 *
 * Structured output:
 * - Uses `response_format: { type: 'json_schema', strict: true }` via the
 *   Vercel AI SDK's `generateObject`. OpenAI's strict JSON-schema mode
 *   is highly reliable.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "OpenAI direct".
 */

import { createOpenAI } from '@ai-sdk/openai';
import type { OpenAIProvider } from '@ai-sdk/openai';
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

export interface OpenAIAdapterOptions {
  /** API key. Defaults to env OPENAI_API_KEY. */
  apiKey?: string;
  /** OpenAI organization. Defaults to env OPENAI_ORG_ID. */
  organization?: string;
}

export class OpenAIAdapter implements OracleProviderAdapter {
  readonly provider = 'openai' as const;
  private readonly client: OpenAIProvider;

  constructor(opts: OpenAIAdapterOptions = {}) {
    const apiKey = opts.apiKey ?? process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error(
        'OpenAIAdapter: OPENAI_API_KEY is not set. ' +
          'Set it in .env.local or pass {apiKey} explicitly.',
      );
    }
    this.client = createOpenAI({
      apiKey,
      organization: opts.organization ?? process.env.OPENAI_ORG_ID,
    });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const model = this.resolveModel(route);
    const { systemPrompt, userMessage } = this.flattenPlan(plan);
    const callStartedAt = Date.now();

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

  private resolveModel(route: OracleModelRoute): LanguageModel {
    return this.client(route.modelId);
  }

  /**
   * Flatten the OraclePromptPlan into a (systemPrompt, userMessage) pair.
   * Stable blocks become the system prompt; semi-stable / retrieved /
   * dynamic blocks concatenate into the user message.
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
   * Normalize OpenAI usage into OracleUsage. OpenAI exposes auto-prefix-
   * cache reads under `providerMetadata.openai.cachedPromptTokens`.
   * Reasoning tokens (o-series models) under `providerMetadata.openai.reasoningTokens`.
   */
  private normalizeUsage(result: unknown, latencyMs: number): OracleUsage {
    const r = (result ?? {}) as {
      usage?: { inputTokens?: number; outputTokens?: number };
      providerMetadata?: {
        openai?: {
          cachedPromptTokens?: number;
          reasoningTokens?: number;
        };
      };
      response?: { id?: string };
    };
    const openaiMeta = r.providerMetadata?.openai ?? {};
    return {
      inputTokens: r.usage?.inputTokens,
      outputTokens: r.usage?.outputTokens,
      cachedInputTokens: openaiMeta.cachedPromptTokens,
      reasoningTokens: openaiMeta.reasoningTokens,
      latencyMs,
      providerRequestId: r.response?.id,
      rawUsageJson: {
        usage: r.usage,
        providerMetadata: r.providerMetadata,
      },
    };
  }
}
