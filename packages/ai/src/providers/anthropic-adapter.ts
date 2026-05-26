/**
 * AnthropicAdapter — direct Anthropic API integration via `@ai-sdk/anthropic`.
 *
 * Architecture:
 * - Calls Anthropic's REST API directly (NOT through OpenRouter).
 * - Authenticates via `ANTHROPIC_API_KEY` env var (the SDK auto-reads it).
 *
 * Caching strategy (round 1 — automatic prefix caching):
 * - Anthropic's prompt cache is opt-in per-block via the `cache_control:
 *   { type: 'ephemeral' }` marker. Round 1 wires automatic prefix caching:
 *   we mark the assembled stable system prompt as cacheable so repeated
 *   calls with the same stable prefix get cache reads.
 * - Cache write tokens land in `usage.cache_creation_input_tokens`;
 *   cache read tokens land in `usage.cache_read_input_tokens`.
 * - Explicit-cache-breakpoint strategies (multiple cache markers across
 *   semi-stable + tool definitions) are a round-2 follow-up.
 *
 * Structured output:
 * - Uses tool-call structured output mode via `generateObject` in the
 *   Vercel AI SDK. The SDK auto-selects tool-call mode for Anthropic.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "Anthropic direct".
 */

import { createAnthropic } from '@ai-sdk/anthropic';
import type { AnthropicProvider } from '@ai-sdk/anthropic';
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

export interface AnthropicAdapterOptions {
  /** API key. Defaults to env ANTHROPIC_API_KEY. */
  apiKey?: string;
  /** Whether to mark the stable system prompt as cache-control: ephemeral. Default true. */
  enableSystemPromptCache?: boolean;
}

export class AnthropicAdapter implements OracleProviderAdapter {
  readonly provider = 'anthropic' as const;
  private readonly client: AnthropicProvider;
  private readonly enableSystemPromptCache: boolean;

  constructor(opts: AnthropicAdapterOptions = {}) {
    const apiKey = opts.apiKey ?? process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      throw new Error(
        'AnthropicAdapter: ANTHROPIC_API_KEY is not set. ' +
          'Set it in .env.local or pass {apiKey} explicitly.',
      );
    }
    this.client = createAnthropic({ apiKey });
    this.enableSystemPromptCache = opts.enableSystemPromptCache ?? true;
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
      system: this.buildSystemWithCache(systemPrompt),
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
      system: this.buildSystemWithCache(systemPrompt),
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
   * Build the system prompt with an ephemeral cache marker if caching is
   * enabled. The Vercel AI SDK accepts either a plain string OR an array of
   * content blocks; we use the array form to attach providerOptions.
   *
   * `cache_control: { type: 'ephemeral' }` tells Anthropic to cache the
   * stable prefix for ~5 minutes. Subsequent calls with the same prefix
   * within the window get cache reads (cheap, fast).
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private buildSystemWithCache(systemPrompt: string): any {
    if (!this.enableSystemPromptCache || systemPrompt.length === 0) {
      return systemPrompt;
    }
    return [
      {
        type: 'text',
        text: systemPrompt,
        providerOptions: {
          anthropic: { cacheControl: { type: 'ephemeral' } },
        },
      },
    ];
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
   * Normalize Anthropic usage into OracleUsage. The Anthropic-specific
   * cache token fields land in `providerMetadata.anthropic.usage`.
   */
  private normalizeUsage(result: unknown, latencyMs: number): OracleUsage {
    const r = (result ?? {}) as {
      usage?: { inputTokens?: number; outputTokens?: number };
      providerMetadata?: {
        anthropic?: {
          usage?: {
            cache_read_input_tokens?: number;
            cache_creation_input_tokens?: number;
          };
        };
      };
      response?: { id?: string };
    };
    const anthropicUsage = r.providerMetadata?.anthropic?.usage ?? {};
    return {
      inputTokens: r.usage?.inputTokens,
      outputTokens: r.usage?.outputTokens,
      cachedInputTokens: anthropicUsage.cache_read_input_tokens,
      cacheWriteTokens: anthropicUsage.cache_creation_input_tokens,
      latencyMs,
      providerRequestId: r.response?.id,
      rawUsageJson: {
        usage: r.usage,
        providerMetadata: r.providerMetadata,
      },
    };
  }
}
