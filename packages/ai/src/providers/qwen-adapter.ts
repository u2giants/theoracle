/**
 * QwenAdapter — direct Alibaba Qwen integration via Alibaba DashScope's
 * OpenAI-compatible endpoint.
 *
 * Architecture (DECISIONS.md D6, docs/oracle/02 §"Shared architecture"):
 * - Calls DashScope's OpenAI-compatible REST API using the official `openai` SDK.
 * - NO Vercel AI SDK and NO OpenRouter in this path.
 * - Authenticates via `DASHSCOPE_API_KEY` env var.
 *
 * Caching strategy:
 * - DashScope's OpenAI-compatible Chat Completions endpoint supports explicit
 *   prompt caching via per-content-block `cache_control` markers.
 * - This adapter marks the reusable prefix explicitly:
 *   - for multi-turn chat, the prefix ends at the penultimate message so the
 *     latest user turn stays dynamic
 *   - for one-shot calls, the stable system prompt is marked cacheable
 * - For text calls, the adapter can switch to the Responses API session-cache
 *   path when the caller supplies a stable `sessionCacheKey`. The chat route
 *   persists `previous_response_id` in Postgres so the cache survives across
 *   requests and processes.
 *
 * Structured output:
 * - Qwen supports OpenAI-compatible `response_format: { type: 'json_object' }`.
 *   Strict json_schema mode is not universally supported, so generateObject
 *   falls back to json_object + Zod validation (same pattern as DeepSeek).
 *
 * Reasoning models:
 * - QwQ / Qwen-3 thinking models stream reasoning tokens but don't yet expose
 *   a separate reasoning_content field on the OpenAI-compat endpoint. We
 *   capture only standard input/output tokens.
 */

import OpenAI from 'openai';
import type { ChatCompletion, ChatCompletionMessageParam } from 'openai/resources/chat/completions';
import type {
  EasyInputMessage,
  Response as OpenAIResponse,
  ResponseUsage,
} from 'openai/resources/responses/responses';
import type {
  OracleObjectResult,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type { ReasoningEffort } from '../routes';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';
import {
  getCacheHints,
  markLastTextPartCacheable,
  normalizeMessageContentArray,
  pickAnthropicCacheTtl,
  pickOpenAICacheRetention,
  shouldDisableCache,
  toOpenAIContent,
} from './cache-utils';
import { flattenPlan, parseJsonOrRaw, tryZodParse } from './vertex-gemini-adapter';

const DASHSCOPE_BASE_URL = 'https://dashscope-us.aliyuncs.com/compatible-mode/v1';

export interface QwenAdapterOptions {
  /** API key. Defaults to env DASHSCOPE_API_KEY. */
  apiKey?: string;
  /** Override base URL — e.g. swap to the China-region endpoint
   *  `https://dashscope.aliyuncs.com/compatible-mode/v1`. */
  baseURL?: string;
}

interface QwenUsageRaw {
  prompt_tokens?: number;
  completion_tokens?: number;
  prompt_tokens_details?: {
    cached_tokens?: number;
    cache_creation_input_tokens?: number;
  };
  completion_tokens_details?: {
    reasoning_tokens?: number;
  };
}

export class QwenAdapter implements OracleProviderAdapter {
  readonly provider = 'qwen' as const;
  private readonly client: OpenAI;

  constructor(opts: QwenAdapterOptions = {}) {
    const apiKey = opts.apiKey ?? process.env.DASHSCOPE_API_KEY;
    if (!apiKey) {
      throw new Error(
        'QwenAdapter: DASHSCOPE_API_KEY is not set. ' +
          'Set it in .env.local or pass {apiKey} explicitly.',
      );
    }
    this.client = new OpenAI({
      apiKey,
      // Region-configurable: some models (e.g. qwen3-vl-*) are only served on the
      // intl endpoint. Override with DASHSCOPE_BASE_URL (e.g.
      // https://dashscope-intl.aliyuncs.com/compatible-mode/v1).
      baseURL: opts.baseURL ?? process.env.DASHSCOPE_BASE_URL ?? DASHSCOPE_BASE_URL,
    });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const hints = getCacheHints(providerOptions);
    if (hints?.sessionCacheKey || hints?.previousResponseId) {
      return this.generateTextViaResponsesApi(
        plan.taskType,
        route,
        systemPrompt,
        userMessage,
        providerOptions,
      );
    }
    const messages = this.buildMessages(plan.taskType, route.modelId, systemPrompt, userMessage, providerOptions);
    const callStartedAt = Date.now();
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages,
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : undefined,
      // Output-token budget (vision transcription of dense diagrams + the
      // thinking trace need a high cap or DashScope truncates mid-reasoning).
      ...(typeof providerOptions?.maxOutputTokens === 'number'
        ? { max_tokens: providerOptions.maxOutputTokens }
        : {}),
      // For qwen-vl, DashScope downscales images to a default pixel budget,
      // which makes a dense diagram's small text unreadable (the model then
      // confabulates). `vl_high_resolution_images: true` keeps full resolution.
      ...(providerOptions?.highResolutionVision === true
        ? { vl_high_resolution_images: true }
        : {}),
      // Qwen-specific reasoning controls pass through via `extra_body`.
      // DashScope's OpenAI-compat layer forwards unknown root-level params.
      ...qwenThinkingExtras(route.reasoningEffort),
    });
    const latencyMs = Date.now() - callStartedAt;
    const choice = completion.choices[0];
    return {
      text: choice?.message?.content ?? '',
      usage: this.normalizeUsage(completion, latencyMs),
      rawResponse: completion,
    };
  }

  private async generateTextViaResponsesApi(
    taskType: GenerateTextArgs['plan']['taskType'],
    route: GenerateTextArgs['route'],
    systemPrompt: string,
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): Promise<OracleTextResult> {
    const hints = getCacheHints(providerOptions);
    const callStartedAt = Date.now();
    const response = await this.client.responses.create(
      {
        model: route.modelId,
        instructions: systemPrompt || undefined,
        input: this.buildResponseInput(userMessage, providerOptions),
        temperature:
          typeof providerOptions?.temperature === 'number'
            ? providerOptions.temperature
            : undefined,
        prompt_cache_key: hints?.sessionCacheKey,
        previous_response_id: hints?.previousResponseId,
        prompt_cache_retention: pickOpenAICacheRetention(taskType, providerOptions),
        ...qwenThinkingExtras(route.reasoningEffort),
      },
      {
        headers: {
          'x-dashscope-session-cache': 'enable',
        },
      },
    );
    const latencyMs = Date.now() - callStartedAt;
    return {
      text: response.output_text ?? '',
      usage: this.normalizeResponseUsage(response, latencyMs),
      rawResponse: response,
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const callStartedAt = Date.now();
    const messages = this.ensureJsonInstruction(
      this.buildMessages(plan.taskType, route.modelId, systemPrompt, userMessage, providerOptions),
    );
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages,
      temperature: 0.1,
      response_format: { type: 'json_object' },
      // DashScope structured output is JSON mode, and Qwen thinking mode is
      // explicitly incompatible with that mode. Force non-thinking here even
      // if the route carries a stage-level reasoning effort.
      ...({ enable_thinking: false } as Record<string, unknown>),
    });
    const latencyMs = Date.now() - callStartedAt;
    const choice = completion.choices[0];
    const raw = choice?.message?.content;
    if (!raw) {
      throw new Error(
        `QwenAdapter.generateObject: empty response. finish_reason=${choice?.finish_reason}`,
      );
    }
    const parsed = parseJsonOrRaw(raw);
    const validated = tryZodParse<TOutput>(schema, parsed);
    return {
      object: (validated ?? parsed) as TOutput,
      usage: this.normalizeUsage(completion, latencyMs),
      rawResponse: completion,
    };
  }

  private buildMessages(
    taskType: GenerateTextArgs['plan']['taskType'],
    modelId: string,
    systemPrompt: string,
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): ChatCompletionMessageParam[] {
    const systemRoleAllowed = this.supportsSystemRole(taskType, modelId);
    const override = providerOptions?.messages as
      | Array<{ role: string; content: unknown }>
      | undefined;
    if (Array.isArray(override) && override.length > 0) {
      let normalized = override.map((m) => ({
        role: m.role,
        // Translate provider-neutral image parts → OpenAI `image_url` at dispatch,
        // so a fallback into this adapter still sends a readable image.
        content: toOpenAIContent(m.content),
      })) as unknown as ChatCompletionMessageParam[];
      if (systemPrompt && systemRoleAllowed && !normalized.some((m) => m.role === 'system')) {
        normalized.unshift({ role: 'system', content: systemPrompt });
      }
      if (!systemRoleAllowed) {
        normalized = this.foldSystemMessagesIntoFirstUser(systemPrompt, normalized);
      }
      return this.applyExplicitCacheMarkers(taskType, normalized, providerOptions);
    }
    const msgs: ChatCompletionMessageParam[] = [];
    if (systemPrompt && systemRoleAllowed) msgs.push({ role: 'system', content: systemPrompt });
    msgs.push({
      role: 'user',
      content: systemPrompt && !systemRoleAllowed
        ? `${systemPrompt}\n\n${userMessage}`
        : userMessage,
    });
    return this.applyExplicitCacheMarkers(taskType, msgs, providerOptions);
  }

  /**
   * Qwen MT models reject OpenAI's `system` role with
   * "Role must be in [user, assistant]". Keep the same instructions, but fold
   * them into the first user turn for translation calls.
   */
  private supportsSystemRole(
    taskType: GenerateTextArgs['plan']['taskType'],
    modelId: string,
  ): boolean {
    const lower = modelId.toLowerCase();
    return !(taskType === 'claim_translation' || lower.includes('qwen-mt'));
  }

  private foldSystemMessagesIntoFirstUser(
    systemPrompt: string,
    messages: ChatCompletionMessageParam[],
  ): ChatCompletionMessageParam[] {
    const systemParts: string[] = [];
    const nonSystem: ChatCompletionMessageParam[] = [];
    for (const message of messages) {
      if (message.role === 'system') {
        systemParts.push(this.stringifyResponseContent(
          (message as ChatCompletionMessageParam & { content?: unknown }).content,
        ));
      } else {
        nonSystem.push(message);
      }
    }
    if (systemPrompt) systemParts.unshift(systemPrompt);
    const instructions = systemParts.filter(Boolean).join('\n\n');
    if (!instructions) return nonSystem;

    const firstUser = nonSystem.find(
      (message) => message.role === 'user',
    ) as (ChatCompletionMessageParam & { content?: unknown }) | undefined;
    if (firstUser) {
      firstUser.content = `${instructions}\n\n${this.stringifyResponseContent(firstUser.content)}`;
      return nonSystem;
    }
    return [{ role: 'user', content: instructions }, ...nonSystem];
  }

  private ensureJsonInstruction(
    messages: ChatCompletionMessageParam[],
  ): ChatCompletionMessageParam[] {
    const combined = messages
      .map((message) =>
        this.stringifyResponseContent(
          (message as ChatCompletionMessageParam & { content?: unknown }).content,
        ),
      )
      .join('\n')
      .toLowerCase();
    if (combined.includes('json')) return messages;

    const next = messages.map((message) => ({ ...message }));
    const target = [...next]
      .reverse()
      .find((message) => message.role === 'user') as
      | (ChatCompletionMessageParam & { content?: unknown })
      | undefined;
    if (target) {
      target.content = `${this.stringifyResponseContent(target.content)}\n\nReturn a valid JSON object.`;
      return next;
    }
    return [{ role: 'user', content: 'Return a valid JSON object.' }, ...next];
  }

  private normalizeUsage(
    completion: ChatCompletion,
    latencyMs: number,
  ): OracleUsage {
    const u = completion.usage as QwenUsageRaw | undefined;
    return {
      inputTokens: u?.prompt_tokens,
      outputTokens: u?.completion_tokens,
      cachedInputTokens: u?.prompt_tokens_details?.cached_tokens,
      cacheWriteTokens: u?.prompt_tokens_details?.cache_creation_input_tokens,
      reasoningTokens: u?.completion_tokens_details?.reasoning_tokens,
      latencyMs,
      providerRequestId: completion.id,
      rawUsageJson: u,
    };
  }

  private normalizeResponseUsage(
    response: OpenAIResponse,
    latencyMs: number,
  ): OracleUsage {
    const u = response.usage as ResponseUsage | undefined;
    return {
      inputTokens: u?.input_tokens,
      outputTokens: u?.output_tokens,
      cachedInputTokens: u?.input_tokens_details?.cached_tokens,
      reasoningTokens: u?.output_tokens_details?.reasoning_tokens,
      latencyMs,
      providerRequestId: response.id,
      rawUsageJson: u,
    };
  }

  private applyExplicitCacheMarkers(
    taskType: GenerateTextArgs['plan']['taskType'],
    messages: ChatCompletionMessageParam[],
    providerOptions?: Record<string, unknown>,
  ): ChatCompletionMessageParam[] {
    if (shouldDisableCache(providerOptions)) return messages;
    const ttl = pickAnthropicCacheTtl(taskType, providerOptions);
    const next = messages.map((message) => ({ ...message }));

    if (next.length > 1) {
      const target = next[next.length - 2] as ChatCompletionMessageParam & { content?: unknown };
      target.content = markLastTextPartCacheable(
        normalizeMessageContentArray(target.content),
        ttl,
      ) as unknown as ChatCompletionMessageParam['content'];
      return next;
    }

    const system = next.find((message) => message.role === 'system') as
      | (ChatCompletionMessageParam & { content?: unknown })
      | undefined;
    if (system) {
      system.content = markLastTextPartCacheable(
        normalizeMessageContentArray(system.content),
        ttl,
      ) as unknown as ChatCompletionMessageParam['content'];
    }
    return next;
  }

  private buildResponseInput(
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): EasyInputMessage[] {
    const override = providerOptions?.messages as
      | Array<{ role: string; content: unknown }>
      | undefined;
    const messages = Array.isArray(override) && override.length > 0
      ? override
      : [{ role: 'user', content: userMessage }];

    return messages
      .filter((message) =>
        message.role === 'user' ||
        message.role === 'assistant' ||
        message.role === 'system',
      )
      .map((message) => ({
        role: message.role as EasyInputMessage['role'],
        content: this.stringifyResponseContent(message.content),
        type: 'message',
      }));
  }

  private stringifyResponseContent(content: unknown): string {
    if (typeof content === 'string') return content;
    return normalizeMessageContentArray(content)
      .map((part) => String(part.text ?? ''))
      .filter(Boolean)
      .join('\n');
  }
}

/**
 * Translate unified ReasoningEffort to Qwen / QwQ thinking parameters.
 *
 * Qwen3 thinking models accept `enable_thinking: true` (with optional
 * `thinking_budget` in tokens). DashScope's OpenAI-compat layer forwards
 * unknown top-level params verbatim, so we set them directly. Non-thinking
 * Qwen models silently ignore both fields.
 *
 *   off    → enable_thinking: false (forces fast path on QwQ / Qwen3-thinking)
 *   low    → enable_thinking: true, thinking_budget: 2048
 *   medium → enable_thinking: true, thinking_budget: 8192
 *   high   → enable_thinking: true, thinking_budget: 24576
 */
function qwenThinkingExtras(
  effort: ReasoningEffort | undefined,
): Record<string, unknown> {
  if (!effort) return {};
  if (effort === 'off') return { enable_thinking: false };
  const budget = effort === 'low' ? 2048 : effort === 'medium' ? 8192 : 24576;
  return { enable_thinking: true, thinking_budget: budget };
}
