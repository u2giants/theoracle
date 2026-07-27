import { and, desc, eq, inArray, sql } from 'drizzle-orm';
import {
  OracleAIClient,
  RESPONSIBILITY_MERGE_PROMPT_VERSION,
  RESPONSIBILITY_MERGE_SYSTEM_PROMPT,
  ResponsibilityMergeOutputSchema,
  buildStandardAdapters,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type OraclePromptPlan,
  type ResponsibilityMergeOutput,
} from '@oracle/ai';
import {
  businessElements,
  businessModelChanges,
  businessObjectTopDomains,
  businessObjects,
  businessObjectVersions,
  businessResponsibilityDetails,
  claims,
  departments,
  documentTopDomains,
  entities,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  settings,
  sourceWorkflowMaps,
  type OracleDb,
} from '@oracle/db';
import {
  enforceResponsibilityCreateGuard,
  normalizedResponsibilitySlug,
  responsibilityProposalInputHash,
  responsibilitySemanticKey,
  resolveResponsibilityCandidateEntities,
  stageEntityProposal,
  validateResponsibilityVerdict,
  type RegistryEntity,
  type ResponsibilityCandidate,
  type ResponsibilityMergeVerdict,
} from '@oracle/engines';

const ACTIVE_PROPOSAL_STATUSES = ['pending_review', 'approved', 'applying', 'needs_rebase'] as const;
const MIN_EVIDENCED_COVERAGE = 0.9;

export function responsibilityEvidenceCoverage(total: number, evidenced: number): number {
  if (
    !Number.isInteger(total) ||
    !Number.isInteger(evidenced) ||
    total < 1 ||
    evidenced < 0 ||
    evidenced > total
  ) {
    throw new Error(`Invalid responsibility coverage counts: ${evidenced}/${total}`);
  }
  return evidenced / total;
}

export function responsibilityShadowLockKey(args: {
  sourceMapId: string;
}): string {
  return `responsibility-shadow:${args.sourceMapId}`;
}

export function assertResponsibilityVersionTarget(args: {
  verdict: ResponsibilityMergeVerdict['verdict'];
  objectId: string | null;
  baseObjectVersionId: string | null;
}): void {
  if (
    (args.verdict === 'confirm' || args.verdict === 'refine_object') &&
    (!args.objectId || !args.baseObjectVersionId)
  ) {
    throw new Error(`${args.verdict} requires a shortlisted object with a current base version.`);
  }
}

export type ResponsibilityMergeModelRunner = (input: {
  plan: OraclePromptPlan;
  routeCandidates: Awaited<ReturnType<typeof resolveRouteCandidates>>['candidates'];
}) => Promise<{
  output: ResponsibilityMergeOutput;
  routeId: string;
  provider: string;
  modelId: string;
  usage: {
    inputTokens?: number | null;
    cachedInputTokens?: number | null;
    cacheWriteTokens?: number | null;
    outputTokens?: number | null;
    reasoningTokens?: number | null;
    providerRequestId?: string | null;
    rawUsageJson?: unknown;
  };
  attemptsMetadata?: unknown;
}>;

export async function invokeResponsibilityMergeModel(args: {
  plan: OraclePromptPlan;
  routeCandidates: Awaited<ReturnType<typeof resolveRouteCandidates>>['candidates'];
  runner: ResponsibilityMergeModelRunner;
  onSuccess: (result: Awaited<ReturnType<ResponsibilityMergeModelRunner>>) => Promise<void>;
  onFailure: (error: unknown) => Promise<void>;
}): Promise<Awaited<ReturnType<ResponsibilityMergeModelRunner>>> {
  try {
    const result = await args.runner({
      plan: args.plan,
      routeCandidates: args.routeCandidates,
    });
    await args.onSuccess(result);
    return result;
  } catch (error) {
    await args.onFailure(error);
    throw error;
  }
}

function buildContextPackInsert(plan: OraclePromptPlan) {
  return {
    taskType: plan.taskType,
    routeId: plan.routeId,
    promptVersion: plan.promptVersion,
    schemaVersion: plan.schemaVersion ?? null,
    stablePrefixHash: plan.metadata.stablePrefixHash,
    semiStableContextHash: plan.metadata.semiStableContextHash ?? null,
    retrievedContextHash: plan.metadata.retrievedContextHash ?? null,
    dynamicInputHash: plan.metadata.dynamicInputHash,
    toolSchemaHash: plan.metadata.toolSchemaHash ?? null,
    outputSchemaHash: plan.metadata.outputSchemaHash ?? null,
    blocksJson: plan.blocks.map((block) => ({
      id: block.id,
      label: block.label,
      kind: block.kind,
      hash: block.hash,
      tokenEstimate: block.tokenEstimate ?? null,
      cacheEligible: block.cacheEligible,
      reasonIncluded: block.reasonIncluded,
    })),
    includedClaimIds: plan.metadata.includedClaimIds ?? null,
    includedDocumentChunkIds: plan.metadata.includedDocumentChunkIds ?? null,
  };
}

async function requiredBooleanSetting(db: OracleDb, key: string): Promise<boolean> {
  const [row] = await db.select({ value: settings.value }).from(settings).where(eq(settings.key, key));
  if (!row) throw new Error(`Required fail-safe setting is missing: ${key}`);
  if (row.value === true || row.value === 'true') return true;
  if (row.value === false || row.value === 'false') return false;
  throw new Error(`Required fail-safe setting is invalid: ${key}`);
}

async function defaultModelRunner(args: {
  client: OracleAIClient;
  plan: OraclePromptPlan;
  routeCandidates: Awaited<ReturnType<typeof resolveRouteCandidates>>['candidates'];
}): ReturnType<ResponsibilityMergeModelRunner> {
  const result = await args.client.runObject<ResponsibilityMergeOutput>({
    taskType: 'business_model_merge',
    routeId: args.plan.routeId,
    promptVersion: RESPONSIBILITY_MERGE_PROMPT_VERSION,
    blocks: args.plan.blocks,
    schema: ResponsibilityMergeOutputSchema,
    routeCandidates: args.routeCandidates,
    providerOptions: { maxOutputTokens: 24_000 },
    observability: {
      includedClaimIds: args.plan.metadata.includedClaimIds,
      includedDocumentChunkIds: args.plan.metadata.includedDocumentChunkIds,
    },
  });
  if (!result.validation.ok) {
    throw new Error(`Responsibility merge schema failed: ${result.validation.error.message}`);
  }
  const route = args.routeCandidates.find((candidate) => candidate.route.routeId === args.plan.routeId)!
    .route;
  return {
    output: result.object,
    routeId: result.routeId ?? route.routeId,
    provider: result.provider ?? route.provider,
    modelId: result.modelId ?? route.modelId,
    usage: result.usage,
    attemptsMetadata: result,
  };
}

export async function createResponsibilityShadowProposal(args: {
  db: OracleDb;
  sourceMapId: string;
  client?: OracleAIClient;
  /** Tests only. Production tasks never accept or forward model output. */
  testOnlyModelRunner?: ResponsibilityMergeModelRunner;
}): Promise<{
  status: 'idempotent' | 'created';
  proposalId: string;
  coverage: number;
  omittedMapRefs: string[];
}> {
  if (!(await requiredBooleanSetting(args.db, 'business_model_merge_enabled'))) {
    throw new Error('Responsibility shadow merge was dispatched while business_model_merge_enabled=false.');
  }
  if (await requiredBooleanSetting(args.db, 'business_model_apply_enabled')) {
    throw new Error('R2 shadow merge refuses to run while business_model_apply_enabled=true.');
  }

  const [map] = await args.db
    .select({
      id: sourceWorkflowMaps.id,
      documentId: sourceWorkflowMaps.documentId,
      elements: sourceWorkflowMaps.elementsJson,
      status: sourceWorkflowMaps.status,
    })
    .from(sourceWorkflowMaps)
    .where(eq(sourceWorkflowMaps.id, args.sourceMapId))
    .limit(1);
  if (!map?.documentId || !['validated', 'degraded'].includes(map.status)) {
    throw new Error('R2 merge requires a validated/degraded document source map.');
  }
  const elements = (map.elements as Array<Record<string, unknown>>).filter(
    (item) => item.shape === 'responsibilities' && item.elementKind === 'responsibility',
  );
  if (elements.length === 0) throw new Error('R2 merge found no responsibility elements.');
  const refs = elements.map((item) => `${map.id}:element:${String(item.elementId)}`);
  const claimRows = await args.db
    .select({ id: claims.id, mapElementRef: claims.mapElementRef, status: claims.status })
    .from(claims)
    .where(inArray(claims.mapElementRef, refs));
  const currentClaims = claimRows.filter(
    (row) => row.status === 'pending_review' || row.status === 'approved',
  );
  const claimByRef = new Map(currentClaims.map((row) => [row.mapElementRef, row.id]));
  const omittedMapRefs = refs.filter((ref) => !claimByRef.has(ref));
  const coverage = responsibilityEvidenceCoverage(refs.length, refs.length - omittedMapRefs.length);
  if (coverage < MIN_EVIDENCED_COVERAGE) {
    throw new Error(
      `Responsibility evidence coverage ${coverage.toFixed(3)} is below ${MIN_EVIDENCED_COVERAGE}.`,
    );
  }
  const candidates: ResponsibilityCandidate[] = elements.flatMap((item) => {
    const ref = `${map.id}:element:${String(item.elementId)}`;
    const claimId = claimByRef.get(ref);
    if (!claimId) return [];
    return [
      {
        mapElementRef: ref,
        claimId,
        label: String(item.label),
        role: String(item.role),
        action: String(item.action),
        object: String(item.object),
        trigger: typeof item.trigger === 'string' ? item.trigger : null,
        requiredSystem: typeof item.system === 'string' ? item.system : null,
        ownerName: typeof item.ownerName === 'string' ? item.ownerName : null,
        department: typeof item.department === 'string' ? item.department : null,
        evidenceQuote: String(item.evidenceQuote),
        chunkId: String(item.chunkId),
      },
    ];
  });

  const [entityRows, departmentRows, sourceDomainRows, objectRows] = await Promise.all([
    args.db
      .select({
        id: entities.id,
        entityType: entities.entityType,
        canonicalValue: entities.canonicalValue,
        aliases: entities.aliases,
      })
      .from(entities),
    args.db.select({ id: departments.id, displayLabel: departments.displayLabel }).from(departments),
    args.db
      .select({ topDomainId: documentTopDomains.topDomainId })
      .from(documentTopDomains)
      .where(eq(documentTopDomains.documentId, map.documentId)),
    args.db
      .select({
        id: businessObjects.id,
        name: businessObjects.name,
        slug: businessObjects.slug,
        currentVersionId: businessObjects.currentVersionId,
        summary: businessObjects.summary,
      })
      .from(businessObjects)
      .where(eq(businessObjects.objectKind, 'responsibility_model')),
  ]);
  const resolutions = candidates.map((candidate) => ({
    sourceElementRef: candidate.mapElementRef,
    ...resolveResponsibilityCandidateEntities({
      mapId: map.id,
      candidate,
      entityRegistry: entityRows as RegistryEntity[],
      departmentRegistry: departmentRows,
    }),
  }));
  const objectIds = objectRows.map((row) => row.id);
  const [domainRows, durableRows] =
    objectIds.length === 0
      ? [[], []]
      : await Promise.all([
          args.db
            .select({
              objectId: businessObjectTopDomains.objectId,
              topDomainId: businessObjectTopDomains.topDomainId,
            })
            .from(businessObjectTopDomains)
            .where(inArray(businessObjectTopDomains.objectId, objectIds)),
          args.db
            .select({
              objectId: businessObjectVersions.objectId,
              versionId: businessObjectVersions.id,
              elementKey: businessElements.elementKey,
              ownerRaw: businessElements.ownerRaw,
              ownerDepartmentId: businessElements.ownerDepartmentId,
              ownerEntityId: businessElements.ownerEntityId,
              role: businessResponsibilityDetails.role,
              action: businessResponsibilityDetails.action,
              object: businessResponsibilityDetails.object,
              trigger: businessResponsibilityDetails.trigger,
              requiredSystem: businessResponsibilityDetails.requiredSystem,
            })
            .from(businessObjectVersions)
            .innerJoin(businessObjects, eq(businessObjects.currentVersionId, businessObjectVersions.id))
            .innerJoin(businessElements, eq(businessElements.versionId, businessObjectVersions.id))
            .innerJoin(
              businessResponsibilityDetails,
              eq(businessResponsibilityDetails.elementId, businessElements.id),
            )
            .where(inArray(businessObjectVersions.objectId, objectIds)),
        ]);
  const sourceDomains = new Set(sourceDomainRows.map((row) => row.topDomainId));
  const sourceSemanticKeys = new Set(candidates.map(responsibilitySemanticKey));
  const sourceOwners = new Set(
    candidates
      .map((item) => (item.ownerName ?? item.department ?? item.role).trim().toLowerCase())
      .filter(Boolean),
  );
  const sourceDepartmentIds = new Set(
    resolutions
      .map((resolution) => resolution.ownerDepartmentId)
      .filter((value): value is NonNullable<typeof value> => Boolean(value)),
  );
  const sourceOwnerEntityIds = new Set(
    resolutions
      .map((resolution) => resolution.ownerEntityId)
      .filter((value): value is string => Boolean(value)),
  );
  const plausibleObjectIds = objectRows
    .filter((objectRow) => {
      const exactSemantic = durableRows.some(
        (row) =>
          row.objectId === objectRow.id &&
          sourceSemanticKeys.has(
            responsibilitySemanticKey({
              role: row.role,
              action: row.action,
              object: row.object,
              trigger: row.trigger,
              requiredSystem: row.requiredSystem,
            }),
          ),
      );
      const sharedDomain = domainRows.some(
        (row) => row.objectId === objectRow.id && sourceDomains.has(row.topDomainId),
      );
      const sharedOwner = durableRows.some(
        (row) =>
          row.objectId === objectRow.id &&
          ((row.ownerRaw && sourceOwners.has(row.ownerRaw.trim().toLowerCase())) ||
            (row.ownerDepartmentId && sourceDepartmentIds.has(row.ownerDepartmentId)) ||
            (row.ownerEntityId && sourceOwnerEntityIds.has(row.ownerEntityId))),
      );
      return exactSemantic || (sharedDomain && sharedOwner);
    })
    .map((row) => row.id);

  const shortlist = objectRows
    .filter((row) => plausibleObjectIds.includes(row.id))
    .map((row) => ({
      ...row,
      topDomainIds: domainRows
        .filter((domain) => domain.objectId === row.id)
        .map((domain) => domain.topDomainId),
      elements: durableRows.filter((element) => element.objectId === row.id),
    }));
  const resolved = await resolveRouteCandidates(args.db, 'model_merge');
  for (const skipped of resolved.skipped) {
    console.error('[business-model-merge] skipped configured model_merge candidate', skipped);
  }
  const route = resolved.candidates[0]!.route;
  const blocks = [
    makeBlock({
      id: 'responsibility-merge-system',
      label: 'Responsibility merge system',
      kind: 'stable_system',
      content: RESPONSIBILITY_MERGE_SYSTEM_PROMPT,
      reasonIncluded: RESPONSIBILITY_MERGE_PROMPT_VERSION,
    }),
    makeBlock({
      id: 'responsibility-source-pack',
      label: 'Validated responsibility source pack',
      kind: 'retrieved_context',
      content: JSON.stringify({
        sourceMapId: map.id,
        coverage,
        candidates,
        omittedUnevidencedMapRefs: omittedMapRefs,
        entityResolutions: resolutions,
        sourceTopDomainIds: [...sourceDomains],
      }),
      reasonIncluded: 'validated evidence-backed responsibility records only',
    }),
    makeBlock({
      id: 'responsibility-existing-shortlist',
      label: 'Plausible durable responsibility models',
      kind: 'retrieved_context',
      content: JSON.stringify(shortlist),
      reasonIncluded: 'deterministic owner/domain/semantic shortlist; similarity is not identity',
    }),
    makeBlock({
      id: 'responsibility-merge-request',
      label: 'Responsibility merge request',
      kind: 'dynamic_input',
      content:
        'Return the safest create, confirm, refine, contradict, or needs-review verdict. Dispose every evidenced source ref through one operation or an explicit omission.',
      reasonIncluded: 'current immutable source-map merge',
    }),
  ];
  const client = args.client ?? new OracleAIClient({ adapters: buildStandardAdapters() });
  const plan = client.compile({
    taskType: 'business_model_merge',
    routeId: route.routeId,
    promptVersion: RESPONSIBILITY_MERGE_PROMPT_VERSION,
    blocks,
    observability: {
      includedClaimIds: candidates.map((candidate) => candidate.claimId),
      includedDocumentChunkIds: candidates.map((candidate) => candidate.chunkId),
    },
  });
  const [contextPack] = await args.db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('Failed to persist responsibility merge context pack.');
  const started = Date.now();
  const model = await invokeResponsibilityMergeModel({
    plan,
    routeCandidates: resolved.candidates,
    runner:
      args.testOnlyModelRunner ??
      ((input) => defaultModelRunner({ client, ...input })),
    onSuccess: async () => undefined,
    onFailure: async (error) => {
      await logAllCandidatesFailedAttempts({
        db: args.db,
        error,
        taskType: 'business-model-merge',
        slot: 'model_merge',
        contextPackId: contextPack.id,
      }).catch((logError) =>
        console.error('[business-model-merge] failed to record candidate attempts', logError),
      );
    },
  });
  const [modelRun] = await args.db
    .insert(modelRuns)
    .values({
      taskType: 'business-model-merge',
      model: model.modelId,
      provider: model.provider,
      promptVersion: RESPONSIBILITY_MERGE_PROMPT_VERSION,
      inputHash: plan.metadata.dynamicInputHash,
      inputTokens: model.usage.inputTokens ?? null,
      outputTokens: model.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: true,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('Failed to persist responsibility merge model run.');
  await args.db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    routeId: model.routeId,
    inputTokens: model.usage.inputTokens ?? null,
    cachedInputTokens: model.usage.cachedInputTokens ?? null,
    cacheWriteTokens: model.usage.cacheWriteTokens ?? null,
    outputTokens: model.usage.outputTokens ?? null,
    reasoningTokens: model.usage.reasoningTokens ?? null,
    providerRequestId: model.usage.providerRequestId ?? null,
    rawUsageJson: model.usage.rawUsageJson ?? null,
  });
  if (model.attemptsMetadata) {
    await logModelRunAttempts({
      db: args.db,
      metadata: model.attemptsMetadata as never,
      taskType: 'business-model-merge',
      slot: 'model_merge',
      contextPackId: contextPack.id,
      modelRunId: modelRun.id,
    });
  }
  await args.db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));
  for (const proposal of resolutions.flatMap((resolution) => resolution.entityProposalsToStage)) {
    await stageEntityProposal(args.db, {
      ...proposal,
      proposedByModelRunId: modelRun.id,
    });
  }

  const rawVerdict = model.output as ResponsibilityMergeVerdict;
  const requestedObject = rawVerdict.targetObjectId
    ? objectRows.find((row) => row.id === rawVerdict.targetObjectId)
    : null;
  if (rawVerdict.targetObjectId && !plausibleObjectIds.includes(rawVerdict.targetObjectId)) {
    throw new Error('Merge verdict targets an object outside the deterministic shortlist.');
  }
  const proposedSlug = normalizedResponsibilitySlug(rawVerdict.proposedName);
  const exactObject = objectRows.find((row) => row.slug === proposedSlug);
  const guarded = enforceResponsibilityCreateGuard({
    verdict: { ...rawVerdict, proposedSlug },
    exactNamespaceObjectId: exactObject?.id,
    plausibleObjectIds,
  });
  const targetObject = requestedObject ?? exactObject ?? null;
  const baseObjectVersionId = targetObject?.currentVersionId ?? null;
  assertResponsibilityVersionTarget({
    verdict: guarded.verdict,
    objectId: targetObject?.id ?? null,
    baseObjectVersionId,
  });
  const durableElementKeys = new Set(
    durableRows
      .filter((row) => row.objectId === targetObject?.id)
      .map((row) => row.elementKey),
  );
  const errors = validateResponsibilityVerdict({
    verdict: guarded,
    candidates,
    durableElementKeys,
  });
  if (errors.length > 0) throw new Error(`R2 merge verdict rejected: ${errors.join('; ')}`);
  const inputHash = responsibilityProposalInputHash({
    sourceMapId: map.id,
    baseVersionId: baseObjectVersionId,
    promptVersion: RESPONSIBILITY_MERGE_PROMPT_VERSION,
    modelVersion: `${model.provider}/${model.modelId}`,
    candidates,
  });

  return args.db.transaction(async (tx) => {
    const lockKey = responsibilityShadowLockKey({
      sourceMapId: map.id,
    });
    await tx.execute(sql`SELECT pg_advisory_xact_lock(hashtext(${lockKey}))`);
    const [existing] = await tx
      .select({ id: businessModelChanges.id })
      .from(businessModelChanges)
      .where(
        and(
          eq(businessModelChanges.sourceWorkflowMapId, map.id),
          inArray(businessModelChanges.status, [...ACTIVE_PROPOSAL_STATUSES]),
        ),
      )
      .limit(1);
    if (existing) {
      return { status: 'idempotent' as const, proposalId: existing.id, coverage, omittedMapRefs };
    }
    const [created] = await tx
      .insert(businessModelChanges)
      .values({
        objectId: targetObject?.id ?? null,
        objectKind: 'responsibility_model',
        proposedSlug,
        baseObjectVersionId,
        changeType: guarded.verdict,
        status: 'pending_review',
        sourceWorkflowMapId: map.id,
        operationsJson: {
          shadow: true,
          applyEligible: false,
          inputHash,
          promptVersion: RESPONSIBILITY_MERGE_PROMPT_VERSION,
          modelVersion: `${model.provider}/${model.modelId}`,
          coverage,
          omittedUnevidencedMapRefs: omittedMapRefs,
          explicitModelOmissions: guarded.omittedSourceElementRefs,
          evidence: candidates.map((candidate) => ({
            sourceElementRef: candidate.mapElementRef,
            claimId: candidate.claimId,
            quote: candidate.evidenceQuote,
            chunkId: candidate.chunkId,
          })),
          entityResolutions: resolutions,
          operations: guarded.operations,
          candidateObjectIds: guarded.candidateObjectIds ?? plausibleObjectIds,
        },
        summary: guarded.summary,
        modelRunId: modelRun.id,
      })
      .returning({ id: businessModelChanges.id });
    if (!created) throw new Error('R2 merge failed to persist shadow proposal.');
    return { status: 'created' as const, proposalId: created.id, coverage, omittedMapRefs };
  });
}
