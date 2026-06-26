/**
 * ModelRouter dispatches compiled prompt plans to provider adapters.
 *
 * It does not read settings or choose models from the database. Production
 * callers pass an ordered candidate list that has already been approved and
 * capability-checked by the DB-aware resolver.
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
  type RouteCandidate,
} from '../routes';
import type { OracleProviderAdapter } from '../providers/types';
import { AllCandidatesFailedError, type CandidateFailure } from '../routes/errors';

export type ProviderAdapterMap = Partial<Record<OracleProvider, OracleProviderAdapter>>;

export interface ModelRouterOptions {
  adapters: ProviderAdapterMap;
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

export interface DispatchAttemptMetadata {
  routeId: string;
  provider: string;
  modelId: string;
  success: boolean;
  error?: string;
}

export class ModelRouter {
  private readonly adapters: ProviderAdapterMap;

  constructor(opts: ModelRouterOptions) {
    this.adapters = opts.adapters;
  }

  resolve(routeId: string, taskType?: OracleTaskType): { route: OracleModelRoute; adapter: OracleProviderAdapter } {
    const route = this.resolveRoute(routeId, taskType);
    const adapter = this.adapters[route.provider];
    if (!adapter) throw new NoAdapterRegisteredError(route.provider);
    return { route, adapter };
  }

  async generateText(
    plan: OraclePromptPlan,
    providerOptions?: Record<string, unknown>,
    candidates?: RouteCandidate[],
  ): Promise<OracleTextResult> {
    return this.dispatch(plan, candidates, (candidatePlan, adapter, route) =>
      adapter.generateText({ plan: candidatePlan, route, providerOptions }),
    );
  }

  async generateObject<TSchema, TOutput>(
    plan: OraclePromptPlan,
    schema: TSchema,
    providerOptions?: Record<string, unknown>,
    candidates?: RouteCandidate[],
  ): Promise<OracleObjectResult<TOutput>> {
    return this.dispatch(plan, candidates, (candidatePlan, adapter, route) =>
      adapter.generateObject<TSchema, TOutput>({
        plan: candidatePlan,
        route,
        schema,
        providerOptions,
      }),
    );
  }

  private async dispatch<T>(
    plan: OraclePromptPlan,
    candidates: RouteCandidate[] | undefined,
    call: (
      candidatePlan: OraclePromptPlan,
      adapter: OracleProviderAdapter,
      route: OracleModelRoute,
    ) => Promise<T>,
  ): Promise<T> {
    const routeCandidates: RouteCandidate[] = candidates?.length
      ? candidates
      : [{ route: this.resolveRoute(plan.routeId, plan.taskType), slot: this.roleForTaskType(plan.taskType) ?? 'general', isPrimary: true, approvedModelId: plan.routeId }];

    const attempts: DispatchAttemptMetadata[] = [];
    const failures: CandidateFailure[] = [];

    for (const candidate of routeCandidates) {
      const route = candidate.route;
      const candidatePlan = { ...plan, routeId: route.routeId };
      const adapter = this.adapters[route.provider];
      const attemptBase = {
        routeId: route.routeId,
        provider: route.provider,
        modelId: route.modelId,
      };

      try {
        if (!adapter) throw new NoAdapterRegisteredError(route.provider);
        const result = await call(candidatePlan, adapter, route);
        attempts.push({ ...attemptBase, success: true });
        return this.withRouteMetadata(result, route, attempts, !candidate.isPrimary);
      } catch (err) {
        const error = this.errorMessage(err);
        attempts.push({ ...attemptBase, success: false, error });
        failures.push({ ...attemptBase, error });
        console.error(
          `[model-router] candidate failed route=${route.routeId} provider=${route.provider} ` +
            `model=${route.modelId} primary=${candidate.isPrimary}: ${error}`,
        );
      }
    }

    throw new AllCandidatesFailedError(routeCandidates[0]?.slot ?? 'general', failures);
  }

  private resolveRoute(routeId: string, taskType?: OracleTaskType): OracleModelRoute {
    const route = getOracleRoute(routeId) ?? this.resolveDynamicRoute(routeId, taskType);
    if (!route) throw new UnknownRouteError(routeId);
    return route;
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
      case 'claim_translation':
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
    attemptedRoutes: DispatchAttemptMetadata[],
    usedNonPrimary: boolean,
  ): T {
    if (!result || typeof result !== 'object') return result;
    return {
      ...(result as Record<string, unknown>),
      routeId: route.routeId,
      actualRouteId: route.routeId,
      provider: route.provider,
      modelId: route.modelId,
      attemptedRoutes,
      usedNonPrimary,
    } as T;
  }

  private errorMessage(err: unknown): string {
    if (err instanceof Error) {
      return err.message || err.name;
    }
    return String(err);
  }
}
