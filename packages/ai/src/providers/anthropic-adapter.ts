/**
 * AnthropicAdapter — direct Anthropic API integration via `@anthropic-ai/sdk`.
 *
 * Architecture (DECISIONS.md D6, docs/oracle/02 §"Shared architecture"):
 * - Calls Anthropic's REST API directly using Anthropic's official SDK.
 * - NO Vercel AI SDK and NO OpenRouter in this path.
 * - Authenticates via `ANTHROPIC_API_KEY` env var (the SDK auto-reads it).
 *
 * Caching strategy (round 1 — automatic prefix caching):
 * - Anthropic's prompt cache is opt-in per-block via `cache_control: { type:
 *   'ephemeral' }`. Round 1 marks the assembled stable system prompt as
 *   cacheable so repeated calls hit a read.
 * - Cache writes land in `usage.cache_creation_input_tokens`; cache reads in
 *   `usage.cache_read_input_tokens`. Both normalize into OracleUsage.
 * - Explicit-cache-breakpoint strategies (multiple markers across tools,
 *   schema, and semi-stable context) are a round-2 follow-up.
 *
 * Structured output:
 * - Uses Anthropic's native tool-calling mode with a forced single tool
 *   choice. The tool's `input_schema` is the standard JSON Schema produced
 *   from the caller's Zod schema. Anthropic enforces the schema on the
 *   model's tool call.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "Anthropic direct".
 */

import Anthropic from '@anthropic-ai/sdk';
import type { Message, MessageCreateParamsNonStreaming } from '@anthropic-ai/sdk/resources/messages';
import type { MessageBatchIndividualResponse } from '@anthropic-ai/sdk/resources/messages/batches';
import type {
  OracleObjectResult,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type { OracleModelRoute, ReasoningEffort } from '../routes';
import type {
  BatchResultItem,
  BatchStatus,
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
  RetrieveBatchArgs,
  RetrieveBatchResult,
  SubmitBatchArgs,
  SubmitBatchResult,
} from './types';
import {
  estimatePlanStableTokens,
  getCacheHints,
  markLastTextPartCacheable,
  normalizeMessageContentArray,
  pickAnthropicCacheTtl,
  shouldDisableCache,
} from './cache-utils';
import { flattenPlan, tryZodParse, zodToJsonSchema } from './vertex-gemini-adapter';

export interface AnthropicAdapterOptions {
  /** API key. Defaults to env ANTHROPIC_API_KEY. */
  apiKey?: string;
  /** Mark the stable system prompt as cache_control: ephemeral. Default true. */
  enableSystemPromptCache?: boolean;
  /** Max output tokens for both generateText and generateObject. */
  defaultMaxTokens?: number;
}

const DEFAULT_MAX_TOKENS = 4096;
const ANTHROPIC_SONNET_CACHE_MIN_TOKENS = 1024;
const ANTHROPIC_HAIKU_CACHE_MIN_TOKENS = 2048;

export class AnthropicAdapter implements OracleProviderAdapter {
  readonly provider = 'anthropic' as const;
  private readonly client: Anthropic;
  private readonly enableSystemPromptCache: boolean;
  private readonly defaultMaxTokens: number;

  constructor(opts: AnthropicAdapterOptions = {}) {
    const apiKey = opts.apiKey ?? process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      throw new Error(
        'AnthropicAdapter: ANTHROPIC_API_KEY is not set. ' +
          'Set it in .env.local or pass {apiKey} explicitly.',
      );
    }
    this.client = new Anthropic({ apiKey });
    this.enableSystemPromptCache = opts.enableSystemPromptCache ?? true;
    this.defaultMaxTokens = opts.defaultMaxTokens ?? DEFAULT_MAX_TOKENS;
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const callStartedAt = Date.now();

    const ttl = pickAnthropicCacheTtl(plan.taskType, providerOptions);
    const messages = this.buildMessages(plan, userMessage, providerOptions, ttl);
    const thinking = thinkingParam(route.reasoningEffort, this.defaultMaxTokens);
    const response = await this.client.messages.create({
      model: route.modelId,
      max_tokens: this.defaultMaxTokens,
      // Anthropic requires temperature=1 when thinking is enabled.
      temperature: thinking
        ? 1
        : (typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : undefined),
      system: this.buildSystem(plan, systemPrompt, providerOptions, ttl),
      messages,
      ...(thinking ? { thinking } : {}),
    });
    const latencyMs = Date.now() - callStartedAt;
    return {
      text: this.extractText(response),
      usage: this.normalizeUsage(response, latencyMs),
      rawResponse: response,
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const jsonSchema = zodToJsonSchema(schema) as Record<string, unknown>;
    const callStartedAt = Date.now();
    const ttl = pickAnthropicCacheTtl(plan.taskType, providerOptions);

    // Force a single tool call. The tool's input_schema is the structured
    // output contract; Anthropic enforces it on the model.
    const TOOL_NAME = 'output_structured';
    const thinking = thinkingParam(route.reasoningEffort, this.defaultMaxTokens);
    const response = await this.client.messages.create({
      model: route.modelId,
      max_tokens: this.defaultMaxTokens,
      // Anthropic forbids temperature != 1 when thinking is enabled.
      temperature: thinking ? 1 : 0.1,
      system: this.buildSystem(plan, systemPrompt, providerOptions, ttl),
      messages: this.buildMessages(plan, userMessage, providerOptions, ttl),
      tools: [
        {
          name: TOOL_NAME,
          description:
            'Return the structured output. You MUST use this tool exactly once and never reply in plain text.',
          input_schema: jsonSchema as Anthropic.Tool.InputSchema,
        },
      ],
      tool_choice: { type: 'tool', name: TOOL_NAME },
      ...(thinking ? { thinking } : {}),
    });
    const latencyMs = Date.now() - callStartedAt;
    const toolUse = response.content.find((b) => b.type === 'tool_use');
    if (!toolUse || toolUse.type !== 'tool_use') {
      throw new Error(
        `AnthropicAdapter.generateObject: response contained no tool_use block. ` +
          `stop_reason=${response.stop_reason}`,
      );
    }
    const validated = tryZodParse<TOutput>(schema, toolUse.input);
    return {
      object: (validated ?? toolUse.input) as TOutput,
      usage: this.normalizeUsage(response, latencyMs),
      rawResponse: response,
    };
  }

  /**
   * Submit a batch of requests to Anthropic's Message Batches API. Each
   * request reuses the same per-call shape as generateText / generateObject
   * but is bundled into a single `messages.batches.create` call. 50% off
   * sync pricing with a 24-hour SLA.
   *
   * When `jsonSchema` is provided, the batch is treated as generateObject:
   * each request gets a forced single tool call whose `input_schema` is the
   * structured-output contract (mirrors generateObject above).
   *
   * The batch ID alone is sufficient to retrieve results later, so
   * providerMetadata is an empty object (see types.ts SubmitBatchResult).
   */
  async submitBatch(args: SubmitBatchArgs): Promise<SubmitBatchResult> {
    const { route, requests, jsonSchema } = args;
    const thinking = thinkingParam(route.reasoningEffort, this.defaultMaxTokens);
    const TOOL_NAME = 'output_structured';
    const structuredTool = jsonSchema
      ? {
          name: TOOL_NAME,
          description:
            'Return the structured output. You MUST use this tool exactly once and never reply in plain text.',
          input_schema: jsonSchema as Anthropic.Tool.InputSchema,
        }
      : undefined;

    const sdkRequests = requests.map((req) => {
      const { systemPrompt, userMessage } = flattenPlan(req.plan);
      const providerOptions = req.providerOptions;
      const params: MessageCreateParamsNonStreaming = {
        model: route.modelId,
        max_tokens: this.defaultMaxTokens,
        temperature: thinking
          ? 1
          : structuredTool
            ? 0.1
            : (typeof providerOptions?.temperature === 'number'
              ? providerOptions.temperature
              : undefined) as number | undefined,
        system: systemPrompt,
        messages: [{ role: 'user', content: userMessage }],
        ...(structuredTool
          ? {
              tools: [structuredTool],
              tool_choice: { type: 'tool', name: TOOL_NAME } as const,
            }
          : {}),
        ...(thinking ? { thinking } : {}),
      };
      return { custom_id: req.customId, params };
    });

    const batch = await this.client.messages.batches.create({ requests: sdkRequests });
    return {
      providerBatchId: batch.id,
      providerMetadata: {},
    };
  }

  /**
   * Poll status and, when terminal, stream the per-request results JSONL.
   * Each line carries the caller's `custom_id` so results map back to the
   * originating BatchRequest.
   *
   * Anthropic processing_status:
   *   in_progress | canceling → still running ('in_progress')
   *   ended                   → terminal; iterate results to build items
   *
   * Per-item `result.type`:
   *   succeeded → success; pull text or tool_use block
   *   errored   → failure with error.message
   *   canceled  → failure 'request canceled'
   *   expired   → failure 'request expired'
   */
  async retrieveBatch(args: RetrieveBatchArgs): Promise<RetrieveBatchResult> {
    const { providerBatchId } = args;
    const batch = await this.client.messages.batches.retrieve(providerBatchId);
    const counts = batch.request_counts;
    const requestCount =
      counts.processing + counts.succeeded + counts.errored + counts.canceled + counts.expired;
    const completedCount = counts.succeeded;
    const failedCount = counts.errored + counts.canceled + counts.expired;

    if (batch.processing_status !== 'ended') {
      return {
        status: 'in_progress' as BatchStatus,
        requestCount,
        completedCount,
        failedCount,
      };
    }

    const results: BatchResultItem[] = [];
    const stream = await this.client.messages.batches.results(providerBatchId);
    for await (const entry of stream as AsyncIterable<MessageBatchIndividualResponse>) {
      results.push(this.normalizeBatchResultItem(entry));
    }

    return {
      status: 'completed',
      results,
      requestCount,
      completedCount,
      failedCount,
    };
  }

  private normalizeBatchResultItem(entry: MessageBatchIndividualResponse): BatchResultItem {
    const customId = entry.custom_id;
    const result = entry.result;
    if (result.type === 'errored') {
      return {
        customId,
        success: false,
        error: result.error?.error?.message ?? 'errored',
      };
    }
    if (result.type === 'canceled') {
      return { customId, success: false, error: 'request canceled' };
    }
    if (result.type === 'expired') {
      return { customId, success: false, error: 'request expired' };
    }
    // succeeded
    const message = result.message;
    const usage = this.normalizeUsage(message, 0);
    const toolUse = message.content.find((b) => b.type === 'tool_use');
    if (toolUse && toolUse.type === 'tool_use') {
      return { customId, success: true, output: toolUse.input, usage };
    }
    return { customId, success: true, text: this.extractText(message), usage };
  }

  /**
   * Build the system field. When caching is enabled and the system prompt is
   * non-empty, use the array-of-blocks form so we can attach
   * cache_control: { type: 'ephemeral' }. Otherwise pass the plain string.
   */
  private buildSystem(
    plan: GenerateTextArgs['plan'],
    systemPrompt: string,
    providerOptions?: Record<string, unknown>,
    ttl?: '5m' | '1h',
  ): string | Anthropic.TextBlockParam[] {
    if (!this.enableSystemPromptCache || systemPrompt.length === 0 || shouldDisableCache(providerOptions)) {
      return systemPrompt;
    }
    const minTokens = anthropicCacheMinTokens(plan.routeId);
    const stableTokens = estimatePlanStableTokens(plan);
    if (stableTokens < minTokens) return systemPrompt;
    return [
      {
        type: 'text',
        text: systemPrompt,
        cache_control: ttl ? { type: 'ephemeral', ttl } : { type: 'ephemeral' },
      },
    ];
  }

  /**
   * Build the messages array. If the caller passed a multi-turn `messages`
   * override via providerOptions (chat route does this for R8 multi-turn),
   * pass it through; otherwise wrap the flattened user message in a single
   * user turn.
   */
  private buildMessages(
    plan: GenerateTextArgs['plan'],
    userMessage: string,
    providerOptions?: Record<string, unknown>,
    ttl?: '5m' | '1h',
  ): Anthropic.MessageParam[] {
    const override = providerOptions?.messages as
      | Array<{ role: string; content: unknown }>
      | undefined;
    if (Array.isArray(override) && override.length > 0) {
      const filtered = override
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({
          role: m.role as 'user' | 'assistant',
          content: normalizeMessageContentArray(m.content) as unknown as Anthropic.MessageParam['content'],
        }));
      if (shouldDisableCache(providerOptions)) return filtered;

      const hint = getCacheHints(providerOptions);
      const minTokens = anthropicCacheMinTokens(plan.routeId);
      const prefixText = filtered
        .slice(0, -1)
        .map((m) =>
          Array.isArray(m.content)
            ? m.content
                .map((part) => ('text' in part ? String(part.text ?? '') : ''))
                .join('\n')
            : '',
        )
        .join('\n');
      if (
        filtered.length > 1 &&
        (estimateText(prefixText) >= minTokens || hint?.preferExplicitCache)
      ) {
        const target = filtered[filtered.length - 2]!;
        target.content = markLastTextPartCacheable(
          target.content as unknown as Array<Record<string, unknown>>,
          ttl,
        ) as unknown as Anthropic.MessageParam['content'];
      }
      return filtered;
    }
    return [{ role: 'user', content: userMessage }];
  }

  /** Extract concatenated text from response content blocks (ignores tool_use). */
  private extractText(response: Message): string {
    const parts: string[] = [];
    for (const block of response.content) {
      if (block.type === 'text') parts.push(block.text);
    }
    return parts.join('');
  }

  /**
   * Normalize Anthropic usage into OracleUsage.
   *   - input_tokens                 -> inputTokens
   *   - output_tokens                -> outputTokens
   *   - cache_read_input_tokens      -> cachedInputTokens
   *   - cache_creation_input_tokens  -> cacheWriteTokens
   */
  private normalizeUsage(response: Message, latencyMs: number): OracleUsage {
    const u = response.usage;
    return {
      inputTokens: u.input_tokens,
      outputTokens: u.output_tokens,
      cachedInputTokens: u.cache_read_input_tokens ?? undefined,
      cacheWriteTokens: u.cache_creation_input_tokens ?? undefined,
      latencyMs,
      providerRequestId: response.id,
      rawUsageJson: u,
    };
  }
}

function anthropicCacheMinTokens(routeId: string): number {
  return routeId.includes('haiku')
    ? ANTHROPIC_HAIKU_CACHE_MIN_TOKENS
    : ANTHROPIC_SONNET_CACHE_MIN_TOKENS;
}

function estimateText(text: string): number {
  return Math.ceil(text.length / 4);
}

/**
 * Build Anthropic's `thinking` request parameter from a unified effort enum.
 * Returns undefined when no thinking should be requested (off, undefined, or
 * when budget would exceed the model's max_tokens). The budget MUST be less
 * than max_tokens — Anthropic rejects the request otherwise.
 */
function thinkingParam(
  effort: ReasoningEffort | undefined,
  maxTokens: number,
): { type: 'enabled'; budget_tokens: number } | undefined {
  if (!effort || effort === 'off') return undefined;
  const targetBudget = effort === 'low' ? 2048 : effort === 'medium' ? 8192 : 24000;
  // Clamp so budget < max_tokens. Reserve at least 512 tokens for the answer.
  const budget = Math.max(1024, Math.min(targetBudget, maxTokens - 512));
  if (budget < 1024) return undefined;   // model can't fit even a low budget
  return { type: 'enabled', budget_tokens: budget };
}
