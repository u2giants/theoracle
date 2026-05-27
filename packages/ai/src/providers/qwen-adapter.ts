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
 * - The OpenAI-compatible endpoint does NOT expose client-controlled prompt
 *   caching. Qwen's native context caching requires the DashScope-native API
 *   (different SDK surface). For now we treat cache as zero — same usage shape
 *   as OpenAI but with all cached_tokens fields effectively null.
 * - If/when we need explicit caching, swap to the native DashScope SDK and
 *   implement `cacheStrategy: 'qwen_explicit_context_cache'` end-to-end.
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
  OracleObjectResult,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';
import { flattenPlan, tryZodParse } from './vertex-gemini-adapter';

const DASHSCOPE_BASE_URL = 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1';

export interface QwenAdapterOptions {
  /** API key. Defaults to env DASHSCOPE_API_KEY. */
  apiKey?: string;
  /** Override base URL — e.g. swap to the China-region endpoint
   *  `https://dashscope.aliyuncs.com/compatible-mode/v1`. */
  baseURL?: string;
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
      baseURL: opts.baseURL ?? DASHSCOPE_BASE_URL,
    });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const messages = this.buildMessages(systemPrompt, userMessage, providerOptions);
    const callStartedAt = Date.now();
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages,
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : undefined,
    });
    const latencyMs = Date.now() - callStartedAt;
    const choice = completion.choices[0];
    return {
      text: choice?.message?.content ?? '',
      usage: this.normalizeUsage(completion, latencyMs),
      rawResponse: completion,
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const callStartedAt = Date.now();
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages: this.buildMessages(systemPrompt, userMessage),
      temperature: 0.1,
      response_format: { type: 'json_object' },
    });
    const latencyMs = Date.now() - callStartedAt;
    const choice = completion.choices[0];
    const raw = choice?.message?.content;
    if (!raw) {
      throw new Error(
        `QwenAdapter.generateObject: empty response. finish_reason=${choice?.finish_reason}`,
      );
    }
    const parsed = JSON.parse(raw);
    const validated = tryZodParse<TOutput>(schema, parsed);
    return {
      object: (validated ?? parsed) as TOutput,
      usage: this.normalizeUsage(completion, latencyMs),
      rawResponse: completion,
    };
  }

  private buildMessages(
    systemPrompt: string,
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): ChatCompletionMessageParam[] {
    const override = providerOptions?.messages as
      | ChatCompletionMessageParam[]
      | undefined;
    if (Array.isArray(override) && override.length > 0) {
      if (systemPrompt && !override.some((m) => m.role === 'system')) {
        return [{ role: 'system', content: systemPrompt }, ...override];
      }
      return override;
    }
    const msgs: ChatCompletionMessageParam[] = [];
    if (systemPrompt) msgs.push({ role: 'system', content: systemPrompt });
    msgs.push({ role: 'user', content: userMessage });
    return msgs;
  }

  private normalizeUsage(
    completion: ChatCompletion,
    latencyMs: number,
  ): OracleUsage {
    const u = completion.usage;
    return {
      inputTokens: u?.prompt_tokens,
      outputTokens: u?.completion_tokens,
      cachedInputTokens: u?.prompt_tokens_details?.cached_tokens,
      latencyMs,
      providerRequestId: completion.id,
      rawUsageJson: u,
    };
  }
}
