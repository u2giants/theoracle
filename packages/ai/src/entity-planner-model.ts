import { modelCapabilities, type OracleDb } from '@oracle/db';
import { eq } from 'drizzle-orm';
import { z } from 'zod';
import type { OracleAIClient } from './client/oracle-ai-client';
import { makeBlock } from './context/prompt-blocks';
import type { RegistryEntityCandidate, EntityPlannerSelection } from './retrieval-plan';
import { resolveRouteCandidates } from './routes/candidates';

const EntityPlannerOutputSchema = z.object({
  requiredEntities: z.array(z.object({
    entityType: z.string(),
    canonicalValue: z.string(),
  })).max(12),
});

export type EntityPlannerModelAttempt = {
  event: 'entity_aware_retrieval_model_call';
  latencyMs: number;
  totalCostUsd: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  provider: string;
  modelId: string;
  candidateCount: number;
  attemptedRouteCount: 1;
  validationOk: boolean;
  error?: string;
};

export type EntityPlannerModelOptions = {
  onAttempt?: (attempt: EntityPlannerModelAttempt) => void;
  logAttempt?: (attempt: EntityPlannerModelAttempt) => void;
};

export function calculateCatalogTokenCost(
  inputTokens: number | null,
  outputTokens: number | null,
  reasoningTokens: number | null,
  promptPer1mUsd: number | null,
  completionPer1mUsd: number | null,
): number | null {
  if (
    inputTokens == null || outputTokens == null ||
    promptPer1mUsd == null || completionPer1mUsd == null ||
    ![inputTokens, outputTokens, promptPer1mUsd, completionPer1mUsd]
      .every((value) => Number.isFinite(value) && value >= 0)
  ) return null;
  // Qwen Chat Completions reports completion_tokens as the total output count;
  // completion_tokens_details.reasoning_tokens is a classification within it.
  // It is therefore telemetry only here and must not be added a second time.
  void reasoningTokens;
  return (inputTokens * promptPer1mUsd + outputTokens * completionPer1mUsd) / 1_000_000;
}

export async function selectEntitiesWithConfiguredModel(
  db: OracleDb,
  client: OracleAIClient,
  query: string,
  candidates: RegistryEntityCandidate[],
  options: EntityPlannerModelOptions = {},
): Promise<EntityPlannerSelection[]> {
  const resolved = await resolveRouteCandidates(db, 'general');
  const routeCandidates = resolved.candidates.slice(0, 1);
  if (routeCandidates.length === 0) {
    throw new Error('general route resolved no entity-planner candidate');
  }
  const routeCandidate = routeCandidates[0]!;
  // Qwen JSON mode does not consume a JSON schema and pre-validates inside its
  // adapter. Dispatch z.unknown() there so the completed response and usage are
  // retained for the shared validation below. Schema-native providers receive
  // the real schema and keep their provider-side structured-output contract.
  const dispatchSchema = routeCandidate.route.provider === 'qwen'
    ? z.unknown()
    : EntityPlannerOutputSchema;
  const result = await client.runObject({
    taskType: 'admin_explanation',
    routeId: routeCandidate.route.routeId,
    routeCandidates,
    promptVersion: 'entity-retrieval-planner-1.0.0',
    schemaVersion: 'entity-retrieval-planner-1.0.0',
    schema: dispatchSchema,
    blocks: [
      makeBlock({
        id: 'entity-planner-rules',
        label: 'Entity planner rules',
        kind: 'stable_system',
        content:
          'Return JSON only in this exact shape: {"requiredEntities":[{"entityType":"...","canonicalValue":"..."}]}. ' +
          'Select only candidate entities explicitly named by the query. Copy entityType and canonicalValue exactly. ' +
          'Never invent an entity.',
        cacheEligible: true,
        reasonIncluded: 'Strict registry-only entity planning',
      }),
      makeBlock({
        id: 'entity-planner-query',
        label: 'Query and registry candidates',
        kind: 'dynamic_input',
        content: JSON.stringify({ query, candidates }),
        cacheEligible: false,
        reasonIncluded: 'Current query and bounded canonical candidates',
      }),
    ],
  });

  const priceIds = Array.from(new Set([
    routeCandidate.approvedModelId,
    `${result.provider}/${result.modelId}`,
    `${routeCandidate.route.provider}/${routeCandidate.route.modelId}`,
  ].filter((value): value is string => Boolean(value))));
  let pricing: { promptPer1mUsd: string | null; completionPer1mUsd: string | null } | undefined;
  for (const priceId of priceIds) {
    [pricing] = await db.select({
      promptPer1mUsd: modelCapabilities.promptPer1mUsd,
      completionPer1mUsd: modelCapabilities.completionPer1mUsd,
    }).from(modelCapabilities).where(eq(modelCapabilities.id, priceId)).limit(1);
    if (pricing) break;
  }
  const inputTokens = result.usage.inputTokens ?? null;
  const outputTokens = result.usage.outputTokens ?? null;
  const reasoningTokens = result.usage.reasoningTokens ?? null;
  const promptPrice = pricing?.promptPer1mUsd != null ? Number(pricing.promptPer1mUsd) : null;
  const completionPrice = pricing?.completionPer1mUsd != null ? Number(pricing.completionPer1mUsd) : null;
  const totalCostUsd = calculateCatalogTokenCost(
    inputTokens,
    outputTokens,
    reasoningTokens,
    promptPrice,
    completionPrice,
  );

  let parsed: z.infer<typeof EntityPlannerOutputSchema> | null = null;
  let validationError: string | undefined;
  try {
    parsed = EntityPlannerOutputSchema.parse(result.object);
  } catch (error) {
    validationError = error instanceof Error ? error.message : String(error);
  }
  const attempt: EntityPlannerModelAttempt = {
    event: 'entity_aware_retrieval_model_call',
    latencyMs: result.usage.latencyMs,
    totalCostUsd,
    inputTokens,
    outputTokens,
    provider: result.provider ?? routeCandidate.route.provider,
    modelId: result.modelId ?? routeCandidate.route.modelId,
    candidateCount: candidates.length,
    attemptedRouteCount: 1,
    validationOk: parsed != null,
    ...(validationError ? { error: validationError } : {}),
  };
  (options.logAttempt ?? ((value) => console.info(JSON.stringify(value))))(attempt);
  options.onAttempt?.(attempt);
  if (!parsed) throw new Error(`entity planner output failed validation: ${validationError}`);
  return parsed.requiredEntities;
}
