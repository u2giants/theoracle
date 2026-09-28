/**
 * OpenAI-compatible direct adapters for Meta Muse, Z.ai GLM and StepFun.
 *
 * Same pattern as DeepSeekAdapter: the official `openai` SDK pointed at each
 * vendor's own OpenAI-compatible Chat Completions endpoint. No OpenRouter and
 * no Vercel AI SDK in this path.
 *
 * Structured output: all three accept `response_format: { type: 'json_object' }`
 * (syntactic JSON, not provider-enforced JSON Schema), so generateObject uses
 * json_object + prompt guidance + Zod validation, like DeepSeek.
 *
 * Caching: all three report cache hits in the OpenAI shape
 * `usage.prompt_tokens_details.cached_tokens` (automatic, no client action).
 *
 * Reasoning: these models reason internally; reasoningEffort is logged and
 * otherwise ignored, as for DeepSeek.
 */

import OpenAI from 'openai';
import type {
  ChatCompletion,
  ChatCompletionCreateParamsNonStreaming,
  ChatCompletionMessageParam,
} from 'openai/resources/chat/completions';
import type { OracleObjectResult, OracleTextResult, OracleUsage } from '../client/types';
import type { GenerateObjectArgs, GenerateTextArgs, OracleProviderAdapter } from './types';
import type { OracleProvider } from '../routes';
import { normalizeMessageContentArray, toOpenAIContent } from './cache-utils';
import { flattenPlan, parseJsonOrRaw, tryZodParse } from './vertex-gemini-adapter';

export const META_MUSE_BASE_URL = 'https://api.meta.ai/v1';
export const ZAI_BASE_URL = 'https://api.z.ai/api/paas/v4';
export const STEPFUN_BASE_URL = 'https://api.stepfun.ai/v1';

export interface OpenAICompatibleAdapterOptions {
  apiKey?: string;
  baseURL?: string;
}

interface OpenAICompatibleUsageRaw {
  prompt_tokens?: number;
  completion_tokens?: number;
  prompt_tokens_details?: { cached_tokens?: number };
  completion_tokens_details?: { reasoning_tokens?: number };
  total_tokens?: number;
}

interface VendorConfig {
  provider: OracleProvider;
  label: string;
  apiKeyEnv: string;
  baseUrlEnv: string;
  defaultBaseURL: string;
}

abstract class OpenAICompatibleAdapter implements OracleProviderAdapter {
  abstract readonly provider: OracleProvider;
  private readonly client: OpenAI;
  private readonly label: string;

  protected constructor(cfg: VendorConfig, opts: OpenAICompatibleAdapterOptions) {
    this.label = cfg.label;
    const apiKey = opts.apiKey ?? process.env[cfg.apiKeyEnv];
    if (!apiKey) {
      throw new Error(
        `${cfg.label}: ${cfg.apiKeyEnv} is not set. Set it in .env.local or pass {apiKey} explicitly.`,
      );
    }
    this.client = new OpenAI({
      apiKey,
      baseURL: opts.baseURL ?? process.env[cfg.baseUrlEnv] ?? cfg.defaultBaseURL,
    });
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    const { plan, route, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    if (route.reasoningEffort && route.reasoningEffort !== 'off') {
      // eslint-disable-next-line no-console
      console.info(
        `[${this.label}] reasoningEffort=${route.reasoningEffort} requested for ${route.modelId} — model controls reasoning internally; param ignored.`,
      );
    }
    const startedAt = Date.now();
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages: this.buildMessages(systemPrompt, userMessage, providerOptions),
      temperature:
        typeof providerOptions?.temperature === 'number' ? providerOptions.temperature : undefined,
      ...(typeof providerOptions?.maxOutputTokens === 'number'
        ? { max_tokens: providerOptions.maxOutputTokens }
        : {}),
    });
    return {
      text: completion.choices[0]?.message?.content ?? '',
      usage: this.normalizeUsage(completion, Date.now() - startedAt),
      rawResponse: completion,
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    const { plan, route, schema, providerOptions } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const startedAt = Date.now();
    const request: ChatCompletionCreateParamsNonStreaming = {
      model: route.modelId,
      messages: ensureJsonInstruction(this.buildMessages(systemPrompt, userMessage, providerOptions)),
      temperature:
        typeof providerOptions?.temperature === 'number' ? providerOptions.temperature : 0.1,
      response_format: { type: 'json_object' },
      ...(typeof providerOptions?.maxOutputTokens === 'number'
        ? { max_tokens: providerOptions.maxOutputTokens }
        : {}),
    };
    // json_object mode is not strict on these vendors: an occasional reply is
    // unparsable or off-schema. Retry once; an unparsable second reply fails with
    // a snippet of what came back, an off-schema one flows to the caller's
    // validation as before.
    let completion = await this.client.chat.completions.create(request);
    let raw = completion.choices[0]?.message?.content;
    let parsed = raw ? parseLenientJson(raw) : undefined;
    if (typeof parsed !== 'object' || parsed === null
        || !matchesSchema(schema, parsed)) {
      completion = await this.client.chat.completions.create(request);
      raw = completion.choices[0]?.message?.content;
      parsed = raw ? parseLenientJson(raw) : undefined;
    }
    const choice = completion.choices[0];
    if (!raw) {
      throw new Error(
        `${this.label}.generateObject: empty response. finish_reason=${choice?.finish_reason}`,
      );
    }
    if (typeof parsed !== 'object' || parsed === null) {
      throw new Error(
        `${this.label}.generateObject: reply was not JSON after one retry: ${JSON.stringify(raw.slice(0, 200))}`,
      );
    }
    const validated = tryZodParse<TOutput>(schema, parsed);
    return {
      object: (validated ?? parsed) as TOutput,
      usage: this.normalizeUsage(completion, Date.now() - startedAt),
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
        content: toOpenAIContent(
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

  private normalizeUsage(completion: ChatCompletion, latencyMs: number): OracleUsage {
    const u = completion.usage as unknown as OpenAICompatibleUsageRaw | undefined;
    return {
      inputTokens: u?.prompt_tokens,
      outputTokens: u?.completion_tokens,
      cachedInputTokens: u?.prompt_tokens_details?.cached_tokens,
      reasoningTokens: u?.completion_tokens_details?.reasoning_tokens,
      latencyMs,
      providerRequestId: completion.id,
      rawUsageJson: u,
    };
  }
}

function ensureJsonInstruction(messages: ChatCompletionMessageParam[]): ChatCompletionMessageParam[] {
  const combined = messages
    .map((m) => stringifyContent((m as { content?: unknown }).content))
    .join('\n')
    .toLowerCase();
  if (combined.includes('json')) return messages;
  const next = messages.map((m) => ({ ...m }));
  const target = [...next].reverse().find((m) => m.role === 'user') as
    | (ChatCompletionMessageParam & { content?: unknown })
    | undefined;
  if (target) {
    target.content = `${stringifyContent(target.content)}\n\nReturn a valid JSON object.`;
    return next;
  }
  return [{ role: 'user', content: 'Return a valid JSON object.' }, ...next];
}

function stringifyContent(content: unknown): string {
  if (typeof content === 'string') return content;
  return normalizeMessageContentArray(content)
    .map((part) => String(part.text ?? ''))
    .filter(Boolean)
    .join('\n');
}

/** Meta Muse (Muse Spark) via api.meta.ai. Env: META_MUSE_API_KEY, optional META_MUSE_BASE_URL. */
export class MetaMuseAdapter extends OpenAICompatibleAdapter {
  readonly provider = 'meta_muse' as const;
  constructor(opts: OpenAICompatibleAdapterOptions = {}) {
    super(
      { provider: 'meta_muse', label: 'MetaMuseAdapter', apiKeyEnv: 'META_MUSE_API_KEY', baseUrlEnv: 'META_MUSE_BASE_URL', defaultBaseURL: META_MUSE_BASE_URL },
      opts,
    );
  }
}

/** Z.ai GLM via api.z.ai general API. Env: ZAI_API_KEY, optional ZAI_BASE_URL. */
export class ZaiGlmAdapter extends OpenAICompatibleAdapter {
  readonly provider = 'zai' as const;
  constructor(opts: OpenAICompatibleAdapterOptions = {}) {
    super(
      { provider: 'zai', label: 'ZaiGlmAdapter', apiKeyEnv: 'ZAI_API_KEY', baseUrlEnv: 'ZAI_BASE_URL', defaultBaseURL: ZAI_BASE_URL },
      opts,
    );
  }
}

/** StepFun via api.stepfun.ai. Env: STEPFUN_API_KEY, optional STEPFUN_BASE_URL. */
export class StepFunAdapter extends OpenAICompatibleAdapter {
  readonly provider = 'stepfun' as const;
  constructor(opts: OpenAICompatibleAdapterOptions = {}) {
    super(
      { provider: 'stepfun', label: 'StepFunAdapter', apiKeyEnv: 'STEPFUN_API_KEY', baseUrlEnv: 'STEPFUN_BASE_URL', defaultBaseURL: STEPFUN_BASE_URL },
      opts,
    );
  }
}

/**
 * json_object mode on these vendors is not strict: replies are sometimes wrapped
 * in ```json fences, double-encoded as a JSON string, or preceded by prose.
 * Unwrap those shapes before Zod validation; anything else is returned as-is.
 */
export function parseLenientJson(text: string): unknown {
  let value: unknown = parseJsonOrRaw(text.trim());
  if (typeof value === 'string') {
    const fenced = value.match(/```(?:json)?\s*([\s\S]*?)```/i);
    const body = fenced ? fenced[1]!.trim() : value;
    value = parseJsonOrRaw(body);
    if (typeof value === 'string') {
      const start = body.indexOf('{');
      const end = body.lastIndexOf('}');
      if (start !== -1 && end > start) value = parseJsonOrRaw(body.slice(start, end + 1));
    }
  }
  return value;
}

function matchesSchema(schema: unknown, value: unknown): boolean {
  const s = schema as { safeParse?: (v: unknown) => { success: boolean } };
  return typeof s?.safeParse === 'function' ? s.safeParse(value).success : true;
}

