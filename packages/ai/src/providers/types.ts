/**
 * Provider adapter interface.
 *
 * Every provider-native adapter (Anthropic, Vertex Gemini, OpenAI) must
 * implement this interface. The OracleAIClient dispatches through it; no
 * route handler or worker may call the provider SDKs directly.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md "Core interfaces".
 */

import type {
  OraclePromptPlan,
  OracleTextResult,
  OracleObjectResult,
  OracleUsage,
} from '../client/types';
import type { OracleModelRoute, OracleProvider } from '../routes';

export interface GenerateObjectArgs<TSchema> {
  plan: OraclePromptPlan;
  route: OracleModelRoute;
  /** Zod schema (or compatible) that the output must satisfy. */
  schema: TSchema;
}

export interface GenerateTextArgs {
  plan: OraclePromptPlan;
  route: OracleModelRoute;
  /**
   * Optional generic escape hatch for adapter-specific parameters that
   * don't fit into the OraclePromptPlan. The chat route uses this for:
   *   - `tools` (Vercel AI SDK ToolSet)
   *   - `stopWhen` (stepCountIs(N) for multi-turn tool calls)
   *   - `temperature`
   *   - `messages` — multi-turn conversation history that overrides the
   *     single (system, user-message) shape flattened from the plan
   *
   * Adapters that don't support a given option ignore it silently. The
   * shape is unconstrained on purpose to avoid leaking provider-specific
   * types into the OracleAIClient surface.
   */
  providerOptions?: Record<string, unknown>;
}

export interface OracleProviderAdapter {
  readonly provider: OracleProvider;

  generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>>;

  generateText(args: GenerateTextArgs): Promise<OracleTextResult>;

  /** Optional — only adapters that natively support streaming implement this. */
  streamText?(args: GenerateTextArgs): AsyncIterable<{ delta: string; usage?: OracleUsage }>;
}

/**
 * Sentinel error thrown by stub adapters when their real implementation has
 * not yet been built. OracleAIClient may catch this and route to a fallback
 * adapter or to the mock adapter under test mode.
 */
export class ProviderAdapterNotImplementedError extends Error {
  constructor(public readonly provider: OracleProvider) {
    super(
      `Provider adapter for "${provider}" is not yet implemented. R2 ships the interface and stubs only; real SDK integration lands in R3+. Use OracleAIClient in test mode to exercise the call shape.`,
    );
    this.name = 'ProviderAdapterNotImplementedError';
  }
}
