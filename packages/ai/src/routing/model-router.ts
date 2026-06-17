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
  OracleTaskType,
  OracleTextResult,
} from '../client/types';
import {
  getOracleRoute,
  resolveModelRoute,
  type OracleModelRole,
  type OracleModelRoute,
  type OracleProvider,
} from '../routes';
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
      `No OracleModelRoute found for routeId "${routeId}". Use a catalog routeId or a supported provider/model id.`,
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

  /**
   * Resolve a route + adapter pair, or throw with a descriptive error.
   *
   * Static catalog routes are preferred. If the routeId is an admin-selected
   * provider/model id such as "qwen/qwen3.7-plus", synthesize the same dynamic
   * route shape produced by resolveRouteFromSettings().
   */
  resolve(routeId: string, taskType?: OracleTaskType): { route: OracleModelRoute; adapter: OracleProviderAdapter } {
    const route = getOracleRoute(routeId) ?? this.resolveDynamicRoute(routeId, taskType);
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
    providerOptions?: Record<string, unknown>,
  ): Promise<OracleObjectResult<TOutput>> {
    return this.dispatch(plan, (adapter, route) =>
      adapter.generateObject<TSchema, TOutput>({ plan, route, schema, providerOptions }),
    );
  }

  private async dispatch<T>(
    plan: OraclePromptPlan,
    call: (adapter: OracleProviderAdapter, route: OracleModelRoute) => Promise<T>,
  ): Promise<T> {
    const { route, adapter } = this.resolve(plan.routeId, plan.taskType);
    try {
      return this.withRouteMetadata(await call(adapter, route), route);
    } catch (err) {
      if (!this.fallbackOnError) throw err;
      if (!route.fallbackRouteId) throw err;
      if (!this.shouldFallback(err)) throw err;
      // Dispatch to fallback. Rebuild the plan with the fallback routeId so
      // observability records reflect which route actually ran.
      const fallbackPlan = { ...plan, routeId: route.fallbackRouteId };
      const { route: fbRoute, adapter: fbAdapter } = this.resolve(
        fallbackPlan.routeId,
        fallbackPlan.taskType,
      );
      return this.withRouteMetadata(await call(fbAdapter, fbRoute), fbRoute, route.routeId, err);
    }
  }

  private resolveDynamicRoute(
    routeId: string,
    taskType?: OracleTaskType,
  ): OracleModelRoute | null {
    if (!routeId.includes('/')) return null;
    const role = this.roleForTaskType(taskType);
    return role ? resolveModelRoute(routeId, role) : null;
  }

  private roleForTaskType(taskType?: OracleTaskType): OracleModelRole | null {
    switch (taskType) {
      case 'interview_chat':
      case 'gap_generation':
        return 'interview';
      case 'message_claim_extraction':
      case 'document_claim_extraction':
      case 'contradiction_detection':
      case 'validation_repair':
        return 'extraction';
      case 'brain_synthesis':
        return 'synthesis';
      case 'admin_explanation':
      case 'model_capability_discovery':
      default:
        return null;
    }
  }

  private withRouteMetadata<T>(
    result: T,
    route: OracleModelRoute,
    fellBackFromRouteId?: string,
    fallbackError?: unknown,
  ): T {
    if (!result || typeof result !== 'object') return result;
    return {
      ...(result as Record<string, unknown>),
      routeId: route.routeId,
      provider: route.provider,
      modelId: route.modelId,
      fellBackFromRouteId,
      fallbackReason: fallbackError ? this.fallbackReason(fallbackError) : undefined,
    } as T;
  }

  private fallbackReason(err: unknown): string {
    if (err instanceof Error) {
      const msg = err.message || err.name;
      return msg.length > 100 ? `${msg.slice(0, 97)}...` : msg;
    }
    const msg = String(err);
    return msg.length > 100 ? `${msg.slice(0, 97)}...` : msg;
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
    // Prefer typed HTTP status when the error object carries one (e.g. provider
    // SDK errors expose numeric `status` / `statusCode`). 429 or any 5xx is a
    // transient/server condition worth falling back on. Substring checks below
    // remain as a fallback for errors without a structured status.
    if (err && typeof err === 'object') {
      const status =
        'status' in err && typeof (err as { status: unknown }).status === 'number'
          ? (err as { status: number }).status
          : 'statusCode' in err && typeof (err as { statusCode: unknown }).statusCode === 'number'
            ? (err as { statusCode: number }).statusCode
            : undefined;
      if (status !== undefined && (status === 429 || status >= 500)) return true;
    }
    if (err instanceof Error) {
      const msg = err.message.toLowerCase();
      if (msg.includes('429') || msg.includes('rate limit')) return true;
      if (msg.includes('timeout') || msg.includes('econnreset') || msg.includes('socket hang up')) return true;
      if (err.name === 'FetchError' || err.name === 'AbortError') return true;
    }
    return false;
  }
}
