/**
 * OracleAIClient — the single production gateway for all Oracle model calls.
 *
 * After R2 is in place, NO route handler, worker, or admin component may
 * call a provider SDK directly. Everything goes through this client:
 *
 *     OracleAIClient
 *       -> ContextCompiler   (assemble the OraclePromptPlan)
 *       -> ModelRouter       (pick adapter, dispatch with fallback)
 *       -> ProviderAdapter   (Anthropic / Vertex / OpenAI / Mock)
 *
 * R2 ships the wiring. R3+ replaces the stub adapters with real SDK calls
 * and adds usage logging into `model_runs`.
 *
 * Test mode (`mode: 'test'`) registers MockProviderAdapter for every
 * provider, so the entire pipeline can be exercised without API keys.
 */

import type { ZodType } from 'zod';
import { getContextCompiler, type CompileArgs } from '../context/context-compiler';
import { ModelRouter, type ProviderAdapterMap } from '../routing/model-router';
import { AnthropicAdapter } from '../providers/anthropic-adapter';
import { VertexGeminiAdapter } from '../providers/vertex-gemini-adapter';
import { GoogleGeminiAdapter } from '../providers/google-gemini-adapter';
import { OpenAIAdapter } from '../providers/openai-adapter';
import { MockProviderAdapter } from '../providers/mock-adapter';
import {
  getStructuredOutputValidator,
  type ValidationResult,
} from '../validation/structured-output-validator';
import type {
  OracleObjectResult,
  OraclePromptPlan,
  OracleTextResult,
} from './types';
import type { RouteCandidate } from '../routes';

export type OracleAIClientMode = 'production' | 'test';

export interface OracleAIClientOptions {
  mode?: OracleAIClientMode;
  /**
   * Override the adapter map. When mode is 'test' and no override is given,
   * mock adapters are registered for every provider.
   */
  adapters?: ProviderAdapterMap;
}

export interface RunTextArgs extends CompileArgs {
  /**
   * Optional generic escape hatch passed through to the provider adapter.
   * The chat route (R8+) uses this for tool calling, multi-turn message
   * arrays, stopWhen step caps, and temperature. Adapters that don't
   * support a given option ignore it silently.
   */
  providerOptions?: Record<string, unknown>;
  routeCandidates?: RouteCandidate[];
}

export interface RunObjectArgs<TSchema> extends CompileArgs {
  schema: ZodType<TSchema>;
  /**
   * Optional generic escape hatch passed through to the provider adapter.
   * Used for cache-control hints, multi-turn context overrides, and other
   * provider-specific knobs that don't belong on OraclePromptPlan itself.
   */
  providerOptions?: Record<string, unknown>;
  routeCandidates?: RouteCandidate[];
}

export interface RunObjectResult<TSchema> extends OracleObjectResult<TSchema> {
  /** Result of validating the raw model output against the supplied Zod schema. */
  validation: ValidationResult<TSchema>;
}

export class OracleAIClient {
  private readonly compiler = getContextCompiler();
  private readonly router: ModelRouter;
  private readonly validator = getStructuredOutputValidator();
  readonly mode: OracleAIClientMode;

  constructor(opts: OracleAIClientOptions = {}) {
    this.mode = opts.mode ?? 'production';
    const adapters: ProviderAdapterMap =
      opts.adapters ??
      (this.mode === 'test'
        ? {
            anthropic: new MockProviderAdapter({ provider: 'anthropic' }),
            vertex: new MockProviderAdapter({ provider: 'vertex' }),
            google: new MockProviderAdapter({ provider: 'google' }),
            openai: new MockProviderAdapter({ provider: 'openai' }),
          }
        : {
            anthropic: new AnthropicAdapter(),
            vertex: new VertexGeminiAdapter(),
            google: new GoogleGeminiAdapter(),
            openai: new OpenAIAdapter(),
          });
    this.router = new ModelRouter({ adapters });
  }

  /** Compile a plan without running it. Useful for tests and for previewing the request. */
  compile(args: CompileArgs): OraclePromptPlan {
    return this.compiler.compile(args);
  }

  /** Compile + dispatch a freeform text call (e.g. interview chat). */
  async runText(args: RunTextArgs): Promise<OracleTextResult> {
    const plan = this.compile(args);
    return this.router.generateText(plan, args.providerOptions, args.routeCandidates);
  }

  /** Compile + dispatch a structured-output call. Output is validated against the supplied Zod schema. */
  async runObject<TSchema>(args: RunObjectArgs<TSchema>): Promise<RunObjectResult<TSchema>> {
    const plan = this.compile(args);
    const result = await this.router.generateObject<ZodType<TSchema>, TSchema>(
      plan,
      args.schema,
      args.providerOptions,
      args.routeCandidates,
    );
    const validation = this.validator.validate(args.schema, result.object);
    return { ...result, validation };
  }
}

/** Singleton convenience for production code. Construct your own for tests. */
let cached: OracleAIClient | null = null;
export function getOracleAIClient(): OracleAIClient {
  if (!cached) cached = new OracleAIClient();
  return cached;
}

/** Reset the cached singleton. Test-only. */
export function __resetOracleAIClientForTests(): void {
  cached = null;
}
