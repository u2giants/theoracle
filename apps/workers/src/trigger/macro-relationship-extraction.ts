import { task } from '@trigger.dev/sdk/v3';
import { and, eq, inArray, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { z } from 'zod';
import {
  MACRO_RELATIONSHIP_PROMPT_VERSION,
  MACRO_RELATIONSHIP_SYSTEM_PROMPT,
  MacroRelationshipOutputSchema,
  OracleAIClient,
  buildStandardAdapters,
  embedText,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type MacroRelationshipOutput,
  type OraclePromptPlan,
} from '@oracle/ai';
import { getDirectDb } from '@oracle/db/client';
import { EMBEDDING_DIM } from '@oracle/shared';
import {
  claims,
  contradictions,
  entities,
  macroRelationshipClaims,
  macroRelationshipSources,
  macroRelationships,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  sourceOutlineSources,
  sourceOutlines,
} from '@oracle/db';
import { statusForGeneratedMacroRelationship, validateMacroRelationshipSummaryEntities } from '@oracle/engines';

const payloadSchema = z.object({
  documentId: z.string().uuid().optional(),
  sourceOutlineId: z.string().uuid().optional(),
  claimIds: z.array(z.string().uuid()).optional(),
  relationshipScope: z.enum(['single_source', 'cross_source']).default('single_source'),
});

const DEFAULT_MACRO_RELATIONSHIP_NEAR_DUPLICATE_DISTANCE = 0.08;

type SupportClaim = {
  id: string;
  summary: string;
  claimType: string;
  claimKind: string | null;
  claimKindConfidence: number | null;
  claimKindReviewStatus: string | null;
  status: string;
  impactScore: number;
  confidenceScore: number;
};

type MacroBudget = {
  maxSupportClaims: number;
  nearDuplicateDistance: number;
  entityValidationExtraStopwords: string[];
};

function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
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
    blocksJson: plan.blocks.map((b) => ({
      id: b.id,
      label: b.label,
      kind: b.kind,
      hash: b.hash,
      tokenEstimate: b.tokenEstimate ?? null,
      cacheEligible: b.cacheEligible,
      reasonIncluded: b.reasonIncluded,
    })),
    includedClaimIds: plan.metadata.includedClaimIds ?? null,
  };
}

function formatClaimsForPrompt(rows: SupportClaim[]): string {
  return rows
    .map(
      (claim, index) =>
        `${index + 1}. claimId=${claim.id}\n` +
        `status=${claim.status}; claimType=${claim.claimType}; claimKind=${claim.claimKind ?? 'uncertain'}; kindConfidence=${claim.claimKindConfidence ?? 'unknown'}; kindReviewStatus=${claim.claimKindReviewStatus ?? 'unreviewed'}\n` +
        `impact=${claim.impactScore}; confidence=${claim.confidenceScore}\n` +
        `summary=${claim.summary}`,
    )
    .join('\n\n');
}

async function loadSupportClaims(args: {
  documentId?: string;
  sourceOutlineId?: string;
  claimIds?: string[];
  relationshipScope?: 'single_source' | 'cross_source';
}): Promise<{ claims: SupportClaim[]; documentId: string | null; sourceOutlineId: string | null }> {
  const db = getDirectDb();
  let documentId = args.documentId ?? null;
  let sourceOutlineId = args.sourceOutlineId ?? null;

  if (sourceOutlineId && !documentId) {
    const [source] = await db
      .select({ documentId: sourceOutlineSources.documentId })
      .from(sourceOutlineSources)
      .where(
        and(
          eq(sourceOutlineSources.sourceOutlineId, sourceOutlineId),
          eq(sourceOutlineSources.sourceType, 'document'),
        ),
      )
      .limit(1);
    documentId = source?.documentId ?? null;
  }

  let rows: SupportClaim[] = [];
  if (args.claimIds?.length) {
    rows = await db
      .select({
        id: claims.id,
        summary: claims.summary,
        claimType: claims.claimType,
        claimKind: claims.claimKind,
        claimKindConfidence: claims.claimKindConfidence,
        claimKindReviewStatus: claims.claimKindReviewStatus,
        status: claims.status,
        impactScore: claims.impactScore,
        confidenceScore: claims.confidenceScore,
      })
      .from(claims)
      .where(inArray(claims.id, args.claimIds))
      .limit(40);
  } else if (documentId && args.relationshipScope === 'cross_source') {
    const result = await db.execute(sql`
      WITH seed_claims AS (
        SELECT DISTINCT c.id
        FROM claims c
        JOIN claim_evidence ce ON ce.claim_id = c.id
        JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
        WHERE dc.document_id = ${documentId}::uuid
          AND c.status IN ('pending_review', 'approved')
      ),
      seed_domains AS (
        SELECT DISTINCT ctd.top_domain_id
        FROM claim_top_domains ctd
        JOIN seed_claims sc ON sc.id = ctd.claim_id
      ),
      related_claims AS (
        SELECT DISTINCT c.id
        FROM claims c
        JOIN claim_top_domains ctd ON ctd.claim_id = c.id
        WHERE c.status IN ('pending_review', 'approved')
          AND ctd.top_domain_id IN (SELECT top_domain_id FROM seed_domains)
      )
      SELECT DISTINCT
        c.id,
        c.summary,
        c.claim_type AS "claimType",
        c.claim_kind AS "claimKind",
        c.claim_kind_confidence AS "claimKindConfidence",
        c.claim_kind_review_status AS "claimKindReviewStatus",
        c.status,
        c.impact_score AS "impactScore",
        c.confidence_score AS "confidenceScore"
      FROM claims c
      WHERE c.id IN (
        SELECT id FROM seed_claims
        UNION
        SELECT id FROM related_claims
      )
      ORDER BY
        CASE WHEN c.id IN (SELECT id FROM seed_claims) THEN 0 ELSE 1 END,
        c.impact_score DESC,
        c.confidence_score DESC,
        c.created_at DESC
      LIMIT 40
    `);
    rows = [...result] as SupportClaim[];
  } else if (documentId) {
    const result = await db.execute(sql`
      SELECT DISTINCT
        c.id,
        c.summary,
        c.claim_type AS "claimType",
        c.claim_kind AS "claimKind",
        c.claim_kind_confidence AS "claimKindConfidence",
        c.claim_kind_review_status AS "claimKindReviewStatus",
        c.status,
        c.impact_score AS "impactScore",
        c.confidence_score AS "confidenceScore"
      FROM claims c
      JOIN claim_evidence ce ON ce.claim_id = c.id
      JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
      WHERE dc.document_id = ${documentId}::uuid
        AND c.status IN ('pending_review', 'approved')
      ORDER BY c.impact_score DESC, c.confidence_score DESC, c.created_at DESC
      LIMIT 40
    `);
    rows = [...result] as SupportClaim[];
  }

  if (!sourceOutlineId && documentId) {
    const [outline] = await db
      .select({ id: sourceOutlines.id })
      .from(sourceOutlines)
      .innerJoin(
        sourceOutlineSources,
        eq(sourceOutlineSources.sourceOutlineId, sourceOutlines.id),
      )
      .where(
        and(
          eq(sourceOutlineSources.documentId, documentId),
          eq(sourceOutlineSources.sourceType, 'document'),
          eq(sourceOutlines.status, 'provisional'),
        ),
      )
      .limit(1);
    sourceOutlineId = outline?.id ?? null;
  }

  return { claims: rows, documentId, sourceOutlineId };
}

function settingToNumber(value: unknown, fallback: number, options: { min?: number; max?: number } = {}): number {
  const parsed = typeof value === 'number' ? value : Number(value ?? fallback);
  if (!Number.isFinite(parsed)) return fallback;
  const min = options.min ?? Number.NEGATIVE_INFINITY;
  const max = options.max ?? Number.POSITIVE_INFINITY;
  return Math.max(min, Math.min(max, parsed));
}

function settingToStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => String(entry).trim()).filter(Boolean);
}

async function loadMacroBudget(): Promise<MacroBudget> {
  const db = getDirectDb();
  const rows = await db.execute(sql`
    SELECT key, value FROM settings
    WHERE key IN (
      'macro_auto_max_support_claims',
      'macro_relationship_near_duplicate_distance',
      'macro_entity_validation_extra_stopwords'
    )
  `);
  const map = new Map(([...rows] as Array<{ key: string; value: unknown }>).map((row) => [row.key, row.value]));
  return {
    maxSupportClaims: Math.floor(
      settingToNumber(map.get('macro_auto_max_support_claims'), 40, { min: 2, max: 80 }),
    ),
    nearDuplicateDistance: settingToNumber(
      map.get('macro_relationship_near_duplicate_distance'),
      DEFAULT_MACRO_RELATIONSHIP_NEAR_DUPLICATE_DISTANCE,
      { min: 0.001, max: 1 },
    ),
    entityValidationExtraStopwords: settingToStringArray(
      map.get('macro_entity_validation_extra_stopwords'),
    ),
  };
}

async function runMacroRelationshipExtraction(rawPayload: unknown) {
  const payload = payloadSchema.parse(rawPayload);
  const db = getDirectDb();
  const support = await loadSupportClaims(payload);
  if (support.claims.length < 2) {
    return { status: 'skipped_too_few_claims', count: support.claims.length };
  }
  const budget = await loadMacroBudget();
  support.claims = support.claims.slice(0, budget.maxSupportClaims);

  const client = new OracleAIClient({ adapters: buildStandardAdapters() });
  const resolved = await resolveRouteCandidates(db, 'general');
  const routeCandidates = resolved.candidates;
  const route = routeCandidates[0]!.route;
  const claimIds = support.claims.map((claim) => claim.id);

  const [outline] = support.sourceOutlineId
    ? await db
        .select({ summary: sourceOutlines.summary, outlineJson: sourceOutlines.outlineJson })
        .from(sourceOutlines)
        .where(eq(sourceOutlines.id, support.sourceOutlineId))
        .limit(1)
    : [null];

  const blocks = [
    makeBlock({
      id: 'macro-relationship-system',
      label: 'Macro relationship system prompt',
      kind: 'stable_system',
      content: MACRO_RELATIONSHIP_SYSTEM_PROMPT,
      reasonIncluded: `macro relationship prompt v${MACRO_RELATIONSHIP_PROMPT_VERSION}`,
    }),
    ...(outline
      ? [
          makeBlock({
            id: 'source-outline-summary',
            label: 'Source outline summary',
            kind: 'semi_stable_domain_context' as const,
            content: JSON.stringify({
              summary: outline.summary,
              outline: outline.outlineJson,
            }),
            reasonIncluded: 'provisional source outline guides macro grouping only',
          }),
        ]
      : []),
    makeBlock({
      id: 'support-claims',
      label: 'Candidate support claims',
      kind: 'retrieved_context',
      content: formatClaimsForPrompt(support.claims),
      reasonIncluded: `${support.claims.length} bounded support candidate claims`,
    }),
    makeBlock({
      id: 'macro-relationship-request',
      label: 'Macro relationship request',
      kind: 'dynamic_input',
      content:
        'Propose high-value macro relationships supported only by the supplied claims. Use claim IDs exactly. Omit weak or duplicate relationships.',
      reasonIncluded: 'request macro relationship proposals',
    }),
  ];

  const plan = client.compile({
    taskType: 'macro_relationship',
    routeId: route.routeId,
    promptVersion: MACRO_RELATIONSHIP_PROMPT_VERSION,
    blocks,
    observability: { includedClaimIds: claimIds },
  });
  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[macro-relationship] failed to insert context pack');

  const started = Date.now();
  const result = await client
    .runObject<MacroRelationshipOutput>({
      taskType: 'macro_relationship',
      routeId: route.routeId,
      promptVersion: MACRO_RELATIONSHIP_PROMPT_VERSION,
      blocks,
      schema: MacroRelationshipOutputSchema,
      observability: { includedClaimIds: claimIds },
      providerOptions: { maxOutputTokens: 12_000 },
      routeCandidates,
    })
    .catch(async (err) => {
      await logAllCandidatesFailedAttempts({
        db,
        error: err,
        taskType: 'macro-relationship',
        slot: 'general',
        contextPackId: contextPack.id,
      });
      throw err;
    });

  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'macro-relationship',
      model: result.modelId ?? route.modelId,
      provider: result.provider ?? route.provider,
      promptVersion: MACRO_RELATIONSHIP_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[macro-relationship] failed to insert model run');

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
    taskType: 'macro-relationship',
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
      '[macro-relationship] model output failed Zod schema validation: ' +
        result.validation.error.message,
    );
  }

  const supportById = new Map(support.claims.map((claim) => [claim.id, claim]));
  const registryRows = await db.select({ canonicalValue: entities.canonicalValue }).from(entities);
  const registryEntityNames = registryRows.map((row) => row.canonicalValue);
  let inserted = 0;
  let rejectedUnsupportedEntities = 0;
  let rejectedNearDuplicates = 0;
  for (const relationship of result.object.relationships) {
    const supportLinks = relationship.supportingClaims.filter((link) => supportById.has(link.claimId));
    if (supportLinks.length < 2) continue;
    const entityValidation = validateMacroRelationshipSummaryEntities({
      summary: relationship.summary,
      supportClaimSummaries: supportLinks.map((link) => supportById.get(link.claimId)!.summary),
      registryEntityNames,
      extraStopwords: budget.entityValidationExtraStopwords,
    });
    if (!entityValidation.ok) {
      rejectedUnsupportedEntities += 1;
      console.warn('[macro-relationship] rejected unsupported summary entities', {
        unsupportedEntities: entityValidation.unsupportedEntities,
        summary: relationship.summary,
      });
      continue;
    }

    const duplicateHash = sha256(
      `${relationship.relationshipType}\n${relationship.summary.toLowerCase().replace(/\s+/g, ' ').trim()}\n${supportLinks.map((link) => link.claimId).sort().join(',')}`,
    );
    const [existing] = await db
      .select({ id: macroRelationships.id })
      .from(macroRelationships)
      .where(sql`metadata_json->>'dedupeHash' = ${duplicateHash}`)
      .limit(1);
    if (existing) continue;

    const { vector } = await embedText(relationship.summary);
    const vec = `[${vector.join(',')}]`;
    const [nearDuplicate] = await db.execute<{ id: string; status: string; distance: number }>(sql`
      SELECT id, status, embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))}) AS distance
      FROM macro_relationships
      WHERE relationship_type = ${relationship.relationshipType}
        AND status IN ('pending_review', 'blocked_pending_support', 'needs_review', 'approved', 'rejected')
        AND embedding IS NOT NULL
        AND embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))}) < ${budget.nearDuplicateDistance}
      ORDER BY embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))})
      LIMIT 1
    `);
    if (nearDuplicate) {
      if (nearDuplicate.status === 'rejected') rejectedNearDuplicates += 1;
      continue;
    }

    const supportStatuses = supportLinks.map((link) => supportById.get(link.claimId)?.status ?? 'missing');
    const [row] = await db
      .insert(macroRelationships)
      .values({
        relationshipType: relationship.relationshipType,
        summary: relationship.summary,
        status: statusForGeneratedMacroRelationship(supportStatuses),
        sourceOutlineId: support.sourceOutlineId,
        confidenceScore: relationship.confidenceScore,
        impactScore: relationship.impactScore,
        triageScore: String(relationship.impactScore * 10 + relationship.confidenceScore),
        embedding: vector,
        metadataJson: {
          whyThisIsMacro: relationship.whyThisIsMacro,
          reviewReason: relationship.reviewReason ?? null,
          riskFlags: relationship.riskFlags ?? [],
          sourceOutlineElementIds: relationship.sourceOutlineElementIds ?? [],
          dedupeHash: duplicateHash,
        },
        modelRunId: modelRun.id,
        contextPackId: contextPack.id,
      })
      .returning({ id: macroRelationships.id });
    if (!row) continue;

    await db.insert(macroRelationshipClaims).values(
      supportLinks.map((link, index) => {
        const supportClaim = supportById.get(link.claimId)!;
        return {
          macroRelationshipId: row.id,
          claimId: link.claimId,
          supportRole: link.supportRole,
          claimStatusAtLink: supportClaim.status,
          claimVersionHash: sha256(supportClaim.summary),
          sortOrder: index,
        };
      }),
    );

    if (support.documentId) {
      await db.insert(macroRelationshipSources).values({
        macroRelationshipId: row.id,
        sourceType: 'document',
        documentId: support.documentId,
      });
    }

    if (relationship.relationshipType === 'contradiction_or_tension' && supportLinks.length >= 2) {
      await db.insert(contradictions).values({
        claimAId: supportLinks[0]!.claimId,
        claimBId: supportLinks[1]!.claimId,
        description: relationship.summary,
        severity: relationship.impactScore >= 8 ? 'high' : 'medium',
        status: 'possible',
        detectionConfidence: relationship.confidenceScore * 10,
        retrievedClaimIds: supportLinks.map((link) => link.claimId),
        createdByModelRunId: modelRun.id,
      });
    }

    inserted += 1;
  }

  return { status: 'complete', inserted, rejectedUnsupportedEntities, rejectedNearDuplicates };
}

export const macroRelationshipExtractionTask = task({
  id: 'macro-relationship-extraction',
  maxDuration: 60 * 10,
  run: async (payload: unknown) => runMacroRelationshipExtraction(payload),
});
