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
import type { Message } from '@anthropic-ai/sdk/resources/messages';
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

export interface AnthropicAdapterOptions {
  /** API key. Defaults to env ANTHROPIC_API_KEY. */
  apiKey?: string;
  /** Mark the stable system prompt as cache_control: ephemeral. Default true. */
  enableSystemPromptCache?: boolean;
  /** Max output tokens for both generateText and generateObject. */
  defaultMaxTokens?: number;
}

const DEFAULT_MAX_TOKENS = 4096;

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

    const messages = this.buildMessages(userMessage, providerOptions);
    const response = await this.client.messages.create({
      model: route.modelId,
      max_tokens: this.defaultMaxTokens,
      temperature:
        typeof providerOptions?.temperature === 'number'
          ? providerOptions.temperature
          : undefined,
      system: this.buildSystem(systemPrompt),
      messages,
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
    const { plan, route, schema } = args;
    const { systemPrompt, userMessage } = flattenPlan(plan);
    const jsonSchema = zodToJsonSchema(schema) as Record<string, unknown>;
    const callStartedAt = Date.now();

    // Force a single tool call. The tool's input_schema is the structured
    // output contract; Anthropic enforces it on the model.
    const TOOL_NAME = 'output_structured';
    const response = await this.client.messages.create({
      model: route.modelId,
      max_tokens: this.defaultMaxTokens,
      temperature: 0.1,
      system: this.buildSystem(systemPrompt),
      messages: [{ role: 'user', content: userMessage }],
      tools: [
        {
          name: TOOL_NAME,
          description:
            'Return the structured output. You MUST use this tool exactly once and never reply in plain text.',
          input_schema: jsonSchema as Anthropic.Tool.InputSchema,
        },
      ],
      tool_choice: { type: 'tool', name: TOOL_NAME },
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
   * Build the system field. When caching is enabled and the system prompt is
   * non-empty, use the array-of-blocks form so we can attach
   * cache_control: { type: 'ephemeral' }. Otherwise pass the plain string.
   */
  private buildSystem(
    systemPrompt: string,
  ): string | Anthropic.TextBlockParam[] {
    if (!this.enableSystemPromptCache || systemPrompt.length === 0) {
      return systemPrompt;
    }
    return [
      {
        type: 'text',
        text: systemPrompt,
        cache_control: { type: 'ephemeral' },
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
    userMessage: string,
    providerOptions?: Record<string, unknown>,
  ): Anthropic.MessageParam[] {
    const override = providerOptions?.messages as
      | Anthropic.MessageParam[]
      | undefined;
    if (Array.isArray(override) && override.length > 0) {
      return override.filter((m) => m.role === 'user' || m.role === 'assistant');
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
