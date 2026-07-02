import { task } from '@trigger.dev/sdk/v3';
import { and, eq, sql } from 'drizzle-orm';
import { z } from 'zod';
import {
  COVERAGE_AUDIT_PROMPT_VERSION,
  COVERAGE_AUDIT_SYSTEM_PROMPT,
  CoverageAuditOutputSchema,
  OracleAIClient,
  buildStandardAdapters,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type CoverageAuditOutput,
  type OraclePromptPlan,
} from '@oracle/ai';
import { getDirectDb } from '@oracle/db/client';
import {
  claims,
  macroRelationships,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  sourceCoverageFindings,
  sourceOutlineSources,
  sourceOutlines,
} from '@oracle/db';

const payloadSchema = z.object({
  sourceOutlineId: z.string().uuid(),
});

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
    blocksJson: plan.blocks.map((b) => ({
      id: b.id,
      label: b.label,
      kind: b.kind,
      hash: b.hash,
      tokenEstimate: b.tokenEstimate ?? null,
      cacheEligible: b.cacheEligible,
      reasonIncluded: b.reasonIncluded,
    })),
  };
}

async function runCoverageAudit(rawPayload: unknown) {
  const { sourceOutlineId } = payloadSchema.parse(rawPayload);
  const db = getDirectDb();

  const [outline] = await db
    .select({
      id: sourceOutlines.id,
      summary: sourceOutlines.summary,
      outlineJson: sourceOutlines.outlineJson,
      documentId: sourceOutlineSources.documentId,
    })
    .from(sourceOutlines)
    .leftJoin(
      sourceOutlineSources,
      eq(sourceOutlineSources.sourceOutlineId, sourceOutlines.id),
    )
    .where(eq(sourceOutlines.id, sourceOutlineId))
    .limit(1);
  if (!outline) return { status: 'skipped_not_found' };

  const claimRows = outline.documentId
    ? ([...(await db.execute(sql`
        SELECT DISTINCT c.id, c.summary, c.claim_type, c.claim_kind, c.status
        FROM claims c
        JOIN claim_evidence ce ON ce.claim_id = c.id
        JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
        WHERE dc.document_id = ${outline.documentId}::uuid
        ORDER BY c.created_at DESC
        LIMIT 80
      `))] as Array<{
        id: string;
        summary: string;
        claim_type: string;
        claim_kind: string | null;
        status: string;
      }>)
    : [];

  const relationshipRows = await db
    .select({
      id: macroRelationships.id,
      relationshipType: macroRelationships.relationshipType,
      summary: macroRelationships.summary,
      status: macroRelationships.status,
    })
    .from(macroRelationships)
    .where(eq(macroRelationships.sourceOutlineId, sourceOutlineId))
    .limit(50);

  const client = new OracleAIClient({ adapters: buildStandardAdapters() });
  const resolved = await resolveRouteCandidates(db, 'general');
  const routeCandidates = resolved.candidates;
  const route = routeCandidates[0]!.route;

  const blocks = [
    makeBlock({
      id: 'coverage-audit-system',
      label: 'Coverage audit system prompt',
      kind: 'stable_system',
      content: COVERAGE_AUDIT_SYSTEM_PROMPT,
      reasonIncluded: `coverage audit prompt v${COVERAGE_AUDIT_PROMPT_VERSION}`,
    }),
    makeBlock({
      id: 'source-outline',
      label: 'Source outline',
      kind: 'retrieved_context',
      content: JSON.stringify({ summary: outline.summary, outline: outline.outlineJson }),
      reasonIncluded: 'outline expectations to compare against extracted knowledge',
    }),
    makeBlock({
      id: 'extracted-knowledge',
      label: 'Extracted claims and macro relationships',
      kind: 'retrieved_context',
      content: JSON.stringify({
        claims: claimRows,
        macroRelationships: relationshipRows,
      }),
      reasonIncluded: 'current extracted representation of this source',
    }),
    makeBlock({
      id: 'coverage-request',
      label: 'Coverage audit request',
      kind: 'dynamic_input',
      content:
        'Find actionable coverage gaps. If the outline is rich but atomic claims are sparse, include a macro_only_source or low_claim_density finding. Do not assert new facts as true.',
      reasonIncluded: 'request coverage findings',
    }),
  ];

  const plan = client.compile({
    taskType: 'coverage_audit',
    routeId: route.routeId,
    promptVersion: COVERAGE_AUDIT_PROMPT_VERSION,
    blocks,
    observability: { includedClaimIds: claimRows.map((claim) => claim.id) },
  });
  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[coverage-audit] failed to insert context pack');

  const started = Date.now();
  const result = await client
    .runObject<CoverageAuditOutput>({
      taskType: 'coverage_audit',
      routeId: route.routeId,
      promptVersion: COVERAGE_AUDIT_PROMPT_VERSION,
      blocks,
      schema: CoverageAuditOutputSchema,
      observability: { includedClaimIds: claimRows.map((claim) => claim.id) },
      providerOptions: { maxOutputTokens: 8_000 },
      routeCandidates,
    })
    .catch(async (err) => {
      await logAllCandidatesFailedAttempts({
        db,
        error: err,
        taskType: 'source-coverage-audit',
        slot: 'general',
        contextPackId: contextPack.id,
      });
      throw err;
    });

  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'source-coverage-audit',
      model: result.modelId ?? route.modelId,
      provider: result.provider ?? route.provider,
      promptVersion: COVERAGE_AUDIT_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[coverage-audit] failed to insert model run');

  await db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    routeId: result.routeId ?? route.routeId,
    inputTokens: result.usage.inputTokens ?? null,
    cachedInputTokens: result.usage.cachedInputTokens ?? null,
    cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
    outputTokens: result.usage.outputTokens ?? null,
    reasoningTokens: result.usage.reasoningTokens ?? null,
    providerRequestId: result.usage.providerRequestId ?? null,
    rawUsageJson: result.usage.rawUsageJson ?? null,
  });
  await logModelRunAttempts({
    db,
    metadata: result,
    taskType: 'source-coverage-audit',
    slot: 'general',
    contextPackId: contextPack.id,
    modelRunId: modelRun.id,
  });
  await db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));

  if (!result.validation.ok) {
    throw new Error(
      '[coverage-audit] model output failed Zod schema validation: ' +
        result.validation.error.message,
    );
  }

  const validClaimIds = new Set(claimRows.map((claim) => claim.id));
  const findings = result.object.findings.filter(
    (finding) => finding.recommendedAction !== 'ignore',
  );
  if (findings.length > 0) {
    await db.insert(sourceCoverageFindings).values(
      findings.map((finding) => ({
        sourceOutlineId,
        findingType: finding.findingType,
        summary: finding.summary,
        suggestedQuestion: finding.suggestedQuestion ?? null,
        relatedClaimIds: finding.relatedClaimIds.filter((id) => validClaimIds.has(id)),
        relatedSourceRefs: finding.relatedSourceRefs,
        severity: finding.severity,
        triageScore: String(finding.severity * 10),
        status: 'open',
      })),
    );
  }

  if (claimRows.length < 2 && findings.every((finding) => finding.findingType !== 'macro_only_source')) {
    await db.insert(sourceCoverageFindings).values({
      sourceOutlineId,
      findingType: 'macro_only_source',
      summary:
        'This source has a substantive macro outline but too few quote-validated atomic claims to represent it as approved operational knowledge yet.',
      suggestedQuestion:
        'Should this source be used as orientation/context only, or should a reviewer identify specific quote-backed claims to extract?',
      relatedClaimIds: claimRows.map((claim) => claim.id),
      relatedSourceRefs: [],
      severity: 5,
      triageScore: '50',
      status: 'open',
    });
  }

  return { status: 'complete', findings: findings.length };
}

export const sourceCoverageAuditTask = task({
  id: 'source-coverage-audit',
  maxDuration: 60 * 10,
  run: async (payload: unknown) => runCoverageAudit(payload),
});
