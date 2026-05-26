/**
 * OpenAIAdapter — direct OpenAI API integration via the official `openai` SDK.
 *
 * Architecture (DECISIONS.md D6, docs/oracle/02 §"Shared architecture"):
 * - Calls OpenAI's REST API directly using the official SDK.
 * - NO Vercel AI SDK and NO OpenRouter in this path.
 * - Authenticates via `OPENAI_API_KEY` env var.
 *
 * Caching strategy (round 1 — automatic prefix caching):
 * - OpenAI auto-caches prompts >= 1024 tokens on the same stable prefix; no
 *   client action required. Cache hits show up in
 *   `usage.prompt_tokens_details.cached_tokens` and are normalized into
 *   `OracleUsage.cachedInputTokens`.
 * - Explicit cache-retention extensions (`prompt_cache_key`,
 *   `prompt_cache_retention`) are a round-2 follow-up.
 *
 * Structured output:
 * - Uses `response_format: { type: 'json_schema', json_schema: { name,
 *   strict: true, schema } }`. Strict mode enforces the JSON Schema 100%
 *   on the model — refusals come back as a `refusal` field on the message.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "OpenAI direct".
 */

import OpenAI from 'openai';
import type { ChatCompletion, ChatCompletionMessageParam } from 'openai/resources/chat/completions';
import type {
  OracleObjectResult,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type { OracleModelRoute } from '../routes';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';
import { flattenPlan, tryZodParse, zodToJsonSchema } from './vertex-gemini-adapter';

export interface OpenAIAdapterOptions {
  /** API key. Defaults to env OPENAI_API_KEY. */
  apiKey?: string;
  /** OpenAI organization. Defaults to env OPENAI_ORG_ID. */
  organization?: string;
}

export class OpenAIAdapter implements OracleProviderAdapter {
  readonly provider = 'openai' as const;
  private readonly client: OpenAI;

  constructor(opts: OpenAIAdapterOptions = {}) {
    const apiKey = opts.apiKey ?? process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error(
        'OpenAIAdapter: OPENAI_API_KEY is not set. ' +
          'Set it in .env.local or pass {apiKey} explicitly.',
      );
    }
    this.client = new OpenAI({
      apiKey,
      organization: opts.organization ?? process.env.OPENAI_ORG_ID,
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
    // OpenAI strict mode requires every property to be required +
    // additionalProperties: false. The Zod JSON-schema converter produces
    // this shape for closed objects; we layer one safety net on top.
    const jsonSchema = stripIncompatibleFields(
      zodToJsonSchema(schema) as Record<string, unknown>,
    );
    const callStartedAt = Date.now();
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages: this.buildMessages(systemPrompt, userMessage),
      temperature: 0.1,
      response_format: {
        type: 'json_schema',
        json_schema: {
          name: 'oracle_structured_output',
          strict: true,
          schema: jsonSchema,
        },
      },
    });
    const latencyMs = Date.now() - callStartedAt;
    const choice = completion.choices[0];
    const refusal = choice?.message?.refusal;
    if (refusal) {
      throw new Error(`OpenAIAdapter.generateObject: model refused: ${refusal}`);
    }
    const raw = choice?.message?.content;
    if (!raw) {
      throw new Error(
        `OpenAIAdapter.generateObject: empty response. finish_reason=${choice?.finish_reason}`,
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

  /**
   * Normalize OpenAI usage. OpenAI exposes auto-prefix-cache reads under
   * `usage.prompt_tokens_details.cached_tokens`, and reasoning tokens (o-series)
   * under `usage.completion_tokens_details.reasoning_tokens`.
   */
  private normalizeUsage(
    completion: ChatCompletion,
    latencyMs: number,
  ): OracleUsage {
    const u = completion.usage;
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

/**
 * OpenAI's strict JSON-schema mode rejects certain keywords that Zod's
 * converter emits but the OpenAPI subset doesn't support — most commonly
 * `$schema`, `format` on unrecognised types, and `default` on optional
 * properties. Strip them defensively so the schema validates server-side.
 */
function stripIncompatibleFields(
  schema: Record<string, unknown>,
): Record<string, unknown> {
  const cloned = JSON.parse(JSON.stringify(schema)) as Record<string, unknown>;
  walk(cloned);
  return cloned;
}

function walk(node: unknown): void {
  if (node === null || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const item of node) walk(item);
    return;
  }
  const obj = node as Record<string, unknown>;
  delete obj.$schema;
  delete obj.default;
  for (const value of Object.values(obj)) walk(value);
}
