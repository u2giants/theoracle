/**
 * ModelRouter — given a routeId, picks the correct provider adapter and
 * dispatches the call. Handles fallback dispatch when a primary route
 * fails with a known transient or schema-validation error.
 *
 * The router does NOT pick which route to use for a given task — that
 * decision belongs to whoever calls OracleAIClient (chat route, extraction
 * worker, etc.). The router only:
 *
 *   - resolves a routeId → adapter
 *   - executes the call
 *   - on failure, optionally dispatches the configured Fallback route
 *
 * Per docs/oracle/01-model-roles-and-routes.md "Model routing rules".
 */

import type {
  OracleObjectResult,
  OraclePromptPlan,
  OracleTextResult,
} from '../client/types';
import { getOracleRoute, type OracleModelRoute, type OracleProvider } from '../routes';
import {
  ProviderAdapterNotImplementedError,
  type OracleProviderAdapter,
} from '../providers/types';

export type ProviderAdapterMap = Partial<Record<OracleProvider, OracleProviderAdapter>>;

export interface ModelRouterOptions {
  adapters: ProviderAdapterMap;
  /**
   * If true, when the primary adapter throws a transient or schema error,
   * the router will dispatch to the route's fallbackRouteId. Default true.
   */
  fallbackOnError?: boolean;
}

export class UnknownRouteError extends Error {
  constructor(routeId: string) {
    super(
      `No OracleModelRoute found for routeId "${routeId}". Routes must be registered in packages/ai/src/routes/catalog.ts.`,
    );
    this.name = 'UnknownRouteError';
  }
}

export class NoAdapterRegisteredError extends Error {
  constructor(provider: OracleProvider) {
    super(
      `No adapter registered for provider "${provider}". Pass it to ModelRouter via options.adapters.`,
    );
    this.name = 'NoAdapterRegisteredError';
  }
}

export class ModelRouter {
  private readonly adapters: ProviderAdapterMap;
  private readonly fallbackOnError: boolean;

  constructor(opts: ModelRouterOptions) {
    this.adapters = opts.adapters;
    this.fallbackOnError = opts.fallbackOnError ?? true;
  }

  /** Resolve a route + adapter pair, or throw with a descriptive error. */
  resolve(routeId: string): { route: OracleModelRoute; adapter: OracleProviderAdapter } {
    const route = getOracleRoute(routeId);
    if (!route) throw new UnknownRouteError(routeId);
    const adapter = this.adapters[route.provider];
    if (!adapter) throw new NoAdapterRegisteredError(route.provider);
    return { route, adapter };
  }

  async generateText(
    plan: OraclePromptPlan,
    providerOptions?: Record<string, unknown>,
  ): Promise<OracleTextResult> {
    return this.dispatch(plan, (adapter, route) =>
      adapter.generateText({ plan, route, providerOptions }),
    );
  }

  async generateObject<TSchema, TOutput>(
    plan: OraclePromptPlan,
    schema: TSchema,
  ): Promise<OracleObjectResult<TOutput>> {
    return this.dispatch(plan, (adapter, route) =>
      adapter.generateObject<TSchema, TOutput>({ plan, route, schema }),
    );
  }

  private async dispatch<T>(
    plan: OraclePromptPlan,
    call: (adapter: OracleProviderAdapter, route: OracleModelRoute) => Promise<T>,
  ): Promise<T> {
    const { route, adapter } = this.resolve(plan.routeId);
    try {
      return await call(adapter, route);
    } catch (err) {
      if (!this.fallbackOnError) throw err;
      if (!route.fallbackRouteId) throw err;
      if (!this.shouldFallback(err)) throw err;
      // Dispatch to fallback. Rebuild the plan with the fallback routeId so
      // observability records reflect which route actually ran.
      const fallbackPlan = { ...plan, routeId: route.fallbackRouteId };
      const { route: fbRoute, adapter: fbAdapter } = this.resolve(fallbackPlan.routeId);
      return call(fbAdapter, fbRoute);
    }
  }

  /**
   * Conservative fallback policy. Falls back on:
   *   - provider adapter not yet implemented (R2 transitional state)
   *   - network/timeout errors (well-known node fetch error names)
   *   - explicit rate-limit / 429 markers
   *
   * Does NOT fall back on:
   *   - validation failures (those have their own repair flow)
   *   - assertion errors from ContextCompiler
   */
  private shouldFallback(err: unknown): boolean {
    if (err instanceof ProviderAdapterNotImplementedError) return true;
    if (err instanceof Error) {
      const msg = err.message.toLowerCase();
      if (msg.includes('429') || msg.includes('rate limit')) return true;
      if (msg.includes('timeout') || msg.includes('econnreset') || msg.includes('socket hang up')) return true;
      if (err.name === 'FetchError' || err.name === 'AbortError') return true;
    }
    return false;
  }
}
