/**
 * Mock adapter — returns canned output for test mode.
 *
 * OracleAIClient uses this adapter when run with `{ mode: 'test' }`. It lets
 * the entire pipeline (compiler → router → adapter → usage normalizer →
 * validator) be exercised without any provider SDK or API key.
 *
 * This adapter is NOT a fallback for production. If a real adapter throws
 * ProviderAdapterNotImplementedError in production mode, OracleAIClient
 * surfaces that error — it does not silently swap in mock output.
 */

import type {
  OracleObjectResult,
  OracleTextResult,
  OracleUsage,
} from '../client/types';
import type { OracleProvider } from '../routes';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';

export interface MockAdapterOptions {
  /** What provider this mock should impersonate. Useful for testing dispatch. */
  provider: OracleProvider;
  /** Canned text output for generateText. */
  cannedText?: string;
  /** Canned object output for generateObject. */
  cannedObject?: unknown;
  /** Fixed latency to report. Defaults to 1ms. */
  latencyMs?: number;
}

export class MockProviderAdapter implements OracleProviderAdapter {
  readonly provider: OracleProvider;
  private readonly cannedText: string;
  private readonly cannedObject: unknown;
  private readonly latencyMs: number;

  constructor(opts: MockAdapterOptions) {
    this.provider = opts.provider;
    this.cannedText = opts.cannedText ?? `[mock ${opts.provider}] OK`;
    this.cannedObject = opts.cannedObject ?? { ok: true, provider: opts.provider };
    this.latencyMs = opts.latencyMs ?? 1;
  }

  async generateText(args: GenerateTextArgs): Promise<OracleTextResult> {
    return {
      text: this.cannedText,
      usage: this.makeUsage(args.plan.blocks.map((b) => b.tokenEstimate ?? 0).reduce((a, b) => a + b, 0)),
      rawResponse: {
        mock: true,
        provider: this.provider,
        routeId: args.route.routeId,
        taskType: args.plan.taskType,
      },
    };
  }

  async generateObject<TSchema, TOutput>(
    args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    return {
      object: this.cannedObject as TOutput,
      usage: this.makeUsage(args.plan.blocks.map((b) => b.tokenEstimate ?? 0).reduce((a, b) => a + b, 0)),
      rawResponse: {
        mock: true,
        provider: this.provider,
        routeId: args.route.routeId,
        taskType: args.plan.taskType,
      },
    };
  }

  private makeUsage(inputTokens: number): OracleUsage {
    return {
      inputTokens,
      cachedInputTokens: 0,
      outputTokens: 16,
      latencyMs: this.latencyMs,
      providerRequestId: `mock-${this.provider}-${Date.now()}`,
      rawUsageJson: { mock: true, provider: this.provider },
    };
  }
}
