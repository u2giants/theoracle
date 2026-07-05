import type { ZodType } from 'zod';
import {
  getOracleRoute,
  makeBlock,
  type OracleAIClient,
  type RunObjectResult,
  type OracleTaskType,
  type RouteCandidate,
} from '@oracle/ai';

const SCHEMA_REPAIR_ROUTE_ID = 'openai_gpt4o_mini_schema_repair';
const SCHEMA_REPAIR_PROMPT_VERSION = 'schema-repair-v1';

export async function repairStructuredOutput<TSchema>(args: {
  client: OracleAIClient;
  taskType: OracleTaskType;
  originalPromptVersion: string;
  schema: ZodType<TSchema>;
  invalidObject: unknown;
  validationError: string;
  expectedShape: string;
  maxOutputTokens?: number;
}): Promise<RunObjectResult<TSchema> | null> {
  const route = getOracleRoute(SCHEMA_REPAIR_ROUTE_ID);
  if (!route) throw new Error(`[schema-repair] missing route ${SCHEMA_REPAIR_ROUTE_ID}`);

  const routeCandidates: RouteCandidate[] = [
    {
      route,
      slot: 'general',
      isPrimary: true,
      approvedModelId: route.routeId,
    },
  ];
  const result = await args.client.runObject<TSchema>({
    taskType: args.taskType,
    routeId: route.routeId,
    promptVersion: `${args.originalPromptVersion}:${SCHEMA_REPAIR_PROMPT_VERSION}`,
    blocks: [
      makeBlock({
        id: 'schema-repair-system',
        label: 'Schema repair system prompt',
        kind: 'stable_system',
        content:
          'You repair malformed structured JSON. Preserve the factual content and IDs from the input. Do not add new facts. Return only JSON matching the requested schema.',
        reasonIncluded: 'one-shot schema repair for malformed structured output',
      }),
      makeBlock({
        id: 'schema-repair-target-shape',
        label: 'Expected output shape',
        kind: 'stable_schema',
        content: args.expectedShape,
        reasonIncluded: 'repair must target this high-level schema shape',
      }),
      makeBlock({
        id: 'schema-repair-validation-error',
        label: 'Validation error',
        kind: 'retrieved_context',
        content: args.validationError,
        reasonIncluded: 'Zod validation error from the original model output',
      }),
      makeBlock({
        id: 'schema-repair-invalid-object',
        label: 'Malformed object',
        kind: 'retrieved_context',
        content: JSON.stringify(args.invalidObject).slice(0, 40_000),
        reasonIncluded: 'raw object returned by the original model candidate',
      }),
      makeBlock({
        id: 'schema-repair-request',
        label: 'Schema repair request',
        kind: 'dynamic_input',
        content:
          'Rewrite the malformed object into valid JSON for the requested schema. Keep only supportable entries from the input. If an array is missing, return an empty array rather than inventing records.',
        reasonIncluded: 'request repaired structured output',
      }),
    ],
    schema: args.schema,
    providerOptions: { maxOutputTokens: args.maxOutputTokens ?? 8_000 },
    routeCandidates,
  });

  return result.validation.ok ? result : null;
}
