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

import OpenAI, { toFile } from 'openai';
import type { ChatCompletion, ChatCompletionMessageParam } from 'openai/resources/chat/completions';
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
import { pickOpenAICacheRetention, toOpenAIContent } from './cache-utils';
import { flattenPlan, parseJsonOrRaw, tryZodParse, zodToJsonSchema } from './vertex-gemini-adapter';

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
    const reasoningEffort = openaiEffort(route.reasoningEffort);
    const promptCacheRetention = pickOpenAICacheRetention(plan.taskType, providerOptions);
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages,
      prompt_cache_retention: promptCacheRetention,
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : undefined,
      // Modern OpenAI models use max_completion_tokens (o-series rejects max_tokens).
      ...(typeof providerOptions?.maxOutputTokens === 'number'
        ? { max_completion_tokens: providerOptions.maxOutputTokens }
        : {}),
      ...(reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
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
    // OpenAI strict mode requires every property to be required +
    // additionalProperties: false. The Zod JSON-schema converter produces
    // this shape for closed objects; we layer one safety net on top.
    const jsonSchema = stripIncompatibleFields(
      zodToJsonSchema(schema) as Record<string, unknown>,
    );
    const callStartedAt = Date.now();
    const reasoningEffort = openaiEffort(route.reasoningEffort);
    const promptCacheRetention = pickOpenAICacheRetention(plan.taskType, providerOptions);
    const completion = await this.client.chat.completions.create({
      model: route.modelId,
      messages: this.buildMessages(systemPrompt, userMessage, providerOptions),
      prompt_cache_retention: promptCacheRetention,
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : 0.1,
      response_format: {
        type: 'json_schema',
        json_schema: {
          name: 'oracle_structured_output',
          strict: true,
          schema: jsonSchema,
        },
      },
      ...(reasoningEffort ? { reasoning_effort: reasoningEffort } : {}),
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
    const parsed = parseJsonOrRaw(raw);
    const validated = tryZodParse<TOutput>(schema, parsed);
    return {
      object: (validated ?? parsed) as TOutput,
      usage: this.normalizeUsage(completion, latencyMs),
      rawResponse: completion,
    };
  }

  /**
   * Submit a batch of requests to OpenAI's Batch API. Builds a JSONL file
   * (one request per line, each with a caller-supplied `custom_id`),
   * uploads it via `client.files.create`, then opens the batch via
   * `client.batches.create` against `/v1/chat/completions`. 50% off sync
   * pricing with a 24-hour SLA.
   *
   * Returns the batch ID + the input file ID (so retrieveBatch can clean it
   * up after results are pulled, if desired).
   */
  async submitBatch(args: SubmitBatchArgs): Promise<SubmitBatchResult> {
    const { route, requests, jsonSchema } = args;
    const reasoningEffort = openaiEffort(route.reasoningEffort);
    const sharedResponseFormat = jsonSchema
      ? {
          type: 'json_schema' as const,
          json_schema: {
            name: 'oracle_structured_output',
            strict: true,
            schema: stripIncompatibleFields(jsonSchema as Record<string, unknown>),
          },
        }
      : undefined;

    const lines: string[] = [];
    for (const req of requests) {
      const { systemPrompt, userMessage } = flattenPlan(req.plan);
      const body: Record<string, unknown> = {
        model: route.modelId,
        messages: this.buildMessages(systemPrompt, userMessage),
        temperature: jsonSchema ? 0.1 : undefined,
      };
      if (sharedResponseFormat) body.response_format = sharedResponseFormat;
      if (reasoningEffort) body.reasoning_effort = reasoningEffort;
      // Strip undefined to keep the JSONL clean.
      for (const k of Object.keys(body)) if (body[k] === undefined) delete body[k];

      lines.push(JSON.stringify({
        custom_id: req.customId,
        method: 'POST',
        url: '/v1/chat/completions',
        body,
      }));
    }
    const jsonl = lines.join('\n') + '\n';

    const uploaded = await this.client.files.create({
      file: await toFile(Buffer.from(jsonl, 'utf-8'), 'oracle-batch-input.jsonl'),
      purpose: 'batch',
    });

    const batch = await this.client.batches.create({
      input_file_id: uploaded.id,
      endpoint: '/v1/chat/completions',
      completion_window: '24h',
    });

    return {
      providerBatchId: batch.id,
      providerMetadata: { inputFileId: uploaded.id },
    };
  }

  /**
   * Poll status and, when complete, download and parse the output JSONL.
   * Each output line carries the caller's `custom_id` so results map back
   * to the originating BatchRequest.
   */
  async retrieveBatch(args: RetrieveBatchArgs): Promise<RetrieveBatchResult> {
    const { providerBatchId } = args;
    const batch = await this.client.batches.retrieve(providerBatchId);
    const status = mapOpenAIBatchStatus(batch.status);
    const counts = batch.request_counts;

    if (status === 'in_progress' || status === 'submitted') {
      return {
        status,
        requestCount: counts?.total,
        completedCount: counts?.completed,
        failedCount: counts?.failed,
      };
    }

    if (status !== 'completed') {
      // failed / expired / canceled — surface the first error if available
      const errMsg = batch.errors?.data?.[0]?.message;
      return {
        status,
        error: errMsg,
        requestCount: counts?.total,
        completedCount: counts?.completed,
        failedCount: counts?.failed,
      };
    }

    if (!batch.output_file_id) {
      return {
        status: 'failed',
        error: 'completed batch has no output_file_id',
      };
    }

    const fileResponse = await this.client.files.content(batch.output_file_id);
    const outputText = await fileResponse.text();
    const results: BatchResultItem[] = [];

    for (const rawLine of outputText.split('\n')) {
      if (!rawLine.trim()) continue;
      let parsed: {
        custom_id: string;
        response: { status_code: number; body: ChatCompletion } | null;
        error: { code?: string; message?: string } | null;
      };
      try {
        parsed = JSON.parse(rawLine);
      } catch {
        // Malformed line — the customId is unrecoverable. Downstream marks the
        // missing request failed, but don't drop it silently: log the bad line
        // (truncated) so a corrupted batch output is visible, not invisible.
        console.error(
          `[OpenAIAdapter] unparseable batch result line (request result LOST): ${rawLine.slice(0, 200)}`,
        );
        continue;
      }

      if (parsed.error || !parsed.response) {
        results.push({
          customId: parsed.custom_id,
          success: false,
          error: parsed.error?.message ?? `status ${parsed.response?.status_code ?? 'unknown'}`,
        });
        continue;
      }

      const completion = parsed.response.body;
      const choice = completion.choices?.[0];
      const refusal = choice?.message?.refusal;
      if (refusal) {
        results.push({
          customId: parsed.custom_id,
          success: false,
          error: `model refused: ${refusal}`,
          usage: this.normalizeUsage(completion, 0),
        });
        continue;
      }

      const rawContent = choice?.message?.content ?? '';
      // Try JSON parse first (structured output); fall back to plain text.
      let output: unknown;
      let text: string | undefined;
      try {
        output = JSON.parse(rawContent);
      } catch {
        text = rawContent;
      }

      results.push({
        customId: parsed.custom_id,
        success: true,
        output,
        text,
        usage: this.normalizeUsage(completion, 0),
      });
    }

    return {
      status: 'completed',
      results,
      requestCount: counts?.total,
      completedCount: counts?.completed,
      failedCount: counts?.failed,
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
      // Translate provider-neutral image parts → OpenAI `image_url` at dispatch.
      const translated = override.map(
        (m) => ({ ...m, content: toOpenAIContent(m.content) }) as ChatCompletionMessageParam,
      );
      if (systemPrompt && !translated.some((m) => m.role === 'system')) {
        return [{ role: 'system', content: systemPrompt }, ...translated];
      }
      return translated;
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
 * OpenAI's strict JSON-schema mode is pickier than the JSON Schema that Zod's
 * converter emits. `walk` reconciles three gaps:
 *   1. It rejects keywords the OpenAPI subset doesn't support — most commonly
 *      `$schema` and `default` on optional properties — so we strip those.
 *   2. It requires EVERY key in an object's `properties` to also appear in
 *      `required`. Zod omits `.optional()` props from `required`, which makes
 *      strict mode 400 ("Invalid schema ... Missing 'sensitivityReason'") and
 *      hard-breaks every OpenAI extraction call.
 *   3. Forcing a genuinely-optional field into `required` without making it
 *      nullable would force the model to always emit a value, which is
 *      semantically wrong for fields that are meant to be absent. The canonical
 *      OpenAI-strict pattern is: every property is `required`, AND any
 *      formerly-optional property becomes nullable (its type is unioned with
 *      `null`). So for each property NOT already in the object's original
 *      `required` set, we union its type with `null`, then recompute `required`
 *      to cover all keys. The downstream Zod schema uses `.nullish()` for those
 *      fields, so the `null` the model emits parses cleanly (no coercion, no
 *      swallowed validation error).
 *
 * This transform is OpenAI-only. Gemini/Vertex keep the original schema —
 * they do not require all-keys-required and reject some OpenAI-isms.
 */
function stripIncompatibleFields(
  schema: Record<string, unknown>,
): Record<string, unknown> {
  const cloned = JSON.parse(JSON.stringify(schema)) as Record<string, unknown>;
  walk(cloned);
  return cloned;
}

/**
 * Union a single property schema node's type with `null` so OpenAI strict mode
 * accepts an absent-meaning value while the key stays in `required`. Handles the
 * shapes Zod's converter emits: `type` as a string, `type` as an array,
 * `anyOf`/`oneOf` unions, `$ref`, and `enum`. Idempotent — never doubles `null`.
 */
function makeNullable(prop: Record<string, unknown>): void {
  // anyOf / oneOf union → add a {type:'null'} branch if absent.
  for (const unionKey of ['anyOf', 'oneOf'] as const) {
    const union = prop[unionKey];
    if (Array.isArray(union)) {
      const hasNull = union.some(
        (b) => b && typeof b === 'object' && (b as Record<string, unknown>).type === 'null',
      );
      if (!hasNull) union.push({ type: 'null' });
      return;
    }
  }
  const t = prop.type;
  if (typeof t === 'string') {
    if (t !== 'null') prop.type = [t, 'null'];
    return;
  }
  if (Array.isArray(t)) {
    if (!t.includes('null')) t.push('null');
    return;
  }
  // No own `type` (e.g. a bare `$ref` or `enum`): wrap in anyOf with null so the
  // value may be the referenced shape or null.
  const { description, ...rest } = prop;
  for (const k of Object.keys(prop)) delete prop[k];
  prop.anyOf = [rest, { type: 'null' }];
  if (description !== undefined) prop.description = description;
}

/**
 * Translate unified ReasoningEffort to OpenAI's `reasoning_effort` enum.
 * Only meaningful for the o-series (o1/o3/o4) and GPT-5 reasoning models —
 * non-reasoning models silently accept and ignore the param.
 *
 * 'off' returns undefined so the caller can omit the param entirely.
 */
function openaiEffort(effort: ReasoningEffort | undefined): 'low' | 'medium' | 'high' | undefined {
  if (!effort || effort === 'off') return undefined;
  return effort; // 'low' | 'medium' | 'high' pass through unchanged
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
  // Strict mode requires `required` to cover every property AND that any
  // formerly-optional property be nullable. Zod only lists non-optional keys in
  // `required`; the difference is exactly the optional set. Make each optional
  // property nullable, THEN promote `required` to all keys.
  const props = obj.properties;
  if (props !== null && typeof props === 'object' && !Array.isArray(props)) {
    const properties = props as Record<string, unknown>;
    const allKeys = Object.keys(properties);
    const originalRequired = new Set(
      Array.isArray(obj.required) ? (obj.required as unknown[]).filter((k): k is string => typeof k === 'string') : [],
    );
    for (const key of allKeys) {
      if (originalRequired.has(key)) continue;
      const prop = properties[key];
      if (prop !== null && typeof prop === 'object' && !Array.isArray(prop)) {
        makeNullable(prop as Record<string, unknown>);
      }
    }
    obj.required = allKeys;
  }
  for (const value of Object.values(obj)) walk(value);
}

/**
 * Map OpenAI's batch.status enum onto our provider-agnostic BatchStatus.
 *
 *   validating | in_progress | finalizing → 'in_progress'
 *   completed                              → 'completed'
 *   failed                                 → 'failed'
 *   expired                                → 'expired'
 *   cancelling | cancelled                 → 'canceled'
 */
function mapOpenAIBatchStatus(s: string): BatchStatus {
  switch (s) {
    case 'completed': return 'completed';
    case 'failed': return 'failed';
    case 'expired': return 'expired';
    case 'cancelling':
    case 'cancelled':
      return 'canceled';
    case 'validating':
    case 'in_progress':
    case 'finalizing':
      return 'in_progress';
    default:
      // Unknown → treat as still-running so the drain task polls again
      return 'in_progress';
  }
}
