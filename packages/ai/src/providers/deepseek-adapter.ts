/**
 * DeepSeekAdapter — direct DeepSeek API integration via the official `openai`
 * SDK pointed at api.deepseek.com.
 *
 * Architecture (DECISIONS.md D6, docs/oracle/02 §"Shared architecture"):
 * - Calls DeepSeek's REST API directly using the OpenAI-compatible surface.
 * - NO Vercel AI SDK and NO OpenRouter in this path.
 * - Authenticates via `DEEPSEEK_API_KEY` env var.
 *
 * Caching strategy (automatic prefix caching):
 * - DeepSeek auto-caches prompts on stable prefixes — no client action required.
 * - Cache hits surface in `usage.prompt_cache_hit_tokens` and misses in
 *   `usage.prompt_cache_miss_tokens` (DeepSeek-specific fields, NOT the OpenAI
 *   `prompt_tokens_details.cached_tokens` shape).
 *
 * Structured output:
 * - DeepSeek supports OpenAI-compatible `response_format: { type: 'json_object' }`
 *   for free-form JSON. Strict JSON-schema mode is NOT supported as of writing,
 *   so generateObject falls back to json_object + Zod validation.
 *
 * Reasoning models:
 * - `deepseek-reasoner` returns the chain-of-thought in `message.reasoning_content`
 *   (separate from `message.content`). We surface reasoning_content tokens in
 *   OracleUsage.reasoningTokens when present.
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
import { normalizeMessageContentArray, toOpenAIImageContent } from './cache-utils';
import { flattenPlan, parseJsonOrRaw, tryZodParse } from './vertex-gemini-adapter';

const DEEPSEEK_BASE_URL = 'https://api.deepseek.com';

export interface DeepSeekAdapterOptions {
  /** API key. Defaults to env DEEPSEEK_API_KEY. */
  apiKey?: string;
  /** Override base URL (e.g. for proxy or China-region endpoint). */
  baseURL?: string;
}

/** DeepSeek's usage object extends OpenAI's with cache hit/miss fields. */
interface DeepSeekUsageRaw {
  prompt_tokens?: number;
  completion_tokens?: number;
  prompt_cache_hit_tokens?: number;
  prompt_cache_miss_tokens?: number;
  completion_tokens_details?: { reasoning_tokens?: number };
  total_tokens?: number;
}

export class DeepSeekAdapter implements OracleProviderAdapter {
  readonly provider = 'deepseek' as const;
  private readonly client: OpenAI;

  constructor(opts: DeepSeekAdapterOptions = {}) {
    const apiKey = opts.apiKey ?? process.env.DEEPSEEK_API_KEY;
    if (!apiKey) {
      throw new Error(
        'DeepSeekAdapter: DEEPSEEK_API_KEY is not set. ' +
          'Set it in .env.local or pass {apiKey} explicitly.',
      );
    }
    this.client = new OpenAI({
      apiKey,
      baseURL: opts.baseURL ?? DEEPSEEK_BASE_URL,
    });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const messages = this.buildMessages(systemPrompt, userMessage, providerOptions);
    // DeepSeek-reasoner does reasoning internally with no client-side budget
    // control. Log when an effort was requested so observability can surface
    // it; the value is otherwise ignored at the API layer.
    if (route.reasoningEffort && route.reasoningEffort !== 'off') {
      // eslint-disable-next-line no-console
      console.info(
        `[DeepSeekAdapter] reasoningEffort=${route.reasoningEffort} requested for ${route.modelId} — model controls reasoning internally; param ignored.`,
      );
    }
    const callStartedAt = Date.now();
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages,
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : undefined,
      ...(typeof providerOptions?.maxOutputTokens === 'number'
        ? { max_tokens: providerOptions.maxOutputTokens }
        : {}),
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
    const { plan, route, schema, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    // DeepSeek supports json_object (free-form JSON), not strict json_schema.
    // We embed schema guidance in the system prompt and validate with Zod after.
    const callStartedAt = Date.now();
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages: this.buildMessages(systemPrompt, userMessage, providerOptions),
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : 0.1,
      response_format: { type: 'json_object' },
    });
    const latencyMs = Date.now() - callStartedAt;
    const choice = completion.choices[0];
    const raw = choice?.message?.content;
    if (!raw) {
      throw new Error(
        `DeepSeekAdapter.generateObject: empty response. finish_reason=${choice?.finish_reason}`,
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
    systemPrompt: string,
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): ChatCompletionMessageParam[] {
    const override = providerOptions?.messages as
      | Array<{ role: string; content: unknown }>
      | undefined;
    if (Array.isArray(override) && override.length > 0) {
      const normalized = override.map((m) => ({
        role: m.role,
        content: toOpenAIImageContent(
          Array.isArray(m.content) ? normalizeMessageContentArray(m.content) : m.content,
        ),
      })) as unknown as ChatCompletionMessageParam[];
      if (systemPrompt && !normalized.some((m) => m.role === 'system')) {
        return [{ role: 'system', content: systemPrompt }, ...normalized];
      }
      return normalized;
    }
    const msgs: ChatCompletionMessageParam[] = [];
    if (systemPrompt) msgs.push({ role: 'system', content: systemPrompt });
    msgs.push({ role: 'user', content: userMessage });
    return msgs;
  }

  /**
   * Normalize DeepSeek usage. Cache hits live in `prompt_cache_hit_tokens`
   * (NOT the OpenAI prompt_tokens_details shape). The OpenAI SDK exposes
   * the raw object on `usage` — we cast through unknown to read DeepSeek's
   * extra fields.
   */
  private normalizeUsage(
    completion: ChatCompletion,
    latencyMs: number,
  ): OracleUsage {
    const u = completion.usage as unknown as DeepSeekUsageRaw | undefined;
    return {
      inputTokens: u?.prompt_tokens,
      outputTokens: u?.completion_tokens,
      cachedInputTokens: u?.prompt_cache_hit_tokens,
      reasoningTokens: u?.completion_tokens_details?.reasoning_tokens,
      latencyMs,
      providerRequestId: completion.id,
      rawUsageJson: u,
    };
  }
}
