import { task } from '@trigger.dev/sdk/v3';
import { and, eq, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { z } from 'zod';
import {
  OracleAIClient,
  buildStandardAdapters,
  embedText,
  EXTRACTION_LENSES,
  EXTRACTION_PROMPT_VERSION,
  EXTRACTION_SYSTEM_PROMPT,
  ExtractionOutputSchema,
  loadClaimCorrectionLessonPack,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type ExtractionOutput,
  type OraclePromptPlan,
  type RouteCandidate,
} from '@oracle/ai';
import { getDirectDb } from '@oracle/db/client';
import {
  documentChunks,
  documentChunkTopDomains,
  documentTopDomains,
  documents,
  entities,
  extractionBatches,
  extractionCandidateEvidence,
  extractionCandidates,
  extractionValidationResults,
  jobRuns,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  sourceGroupItems,
  sourceGroups,
  sourceOutlines,
  type OracleDb,
} from '@oracle/db';
import {
  AdvisoryLockBusyError,
  computeCandidateHash,
  executePromotion,
  mapLegacyDomainsToTopDomains,
  MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
  stageEntityProposal,
  validateQuote,
  validateSourcePointer,
  validateTaxonomy,
  type RegistryEntity,
} from '@oracle/engines';
import {
  EMBEDDING_DIM,
  type EntityType,
  type KnowledgeDomain,
  type TopLevelDomainId,
} from '@oracle/shared';
import { documentHasCompletedLensBatch, type ExtractionLens } from '../lib/document-lens-budget';
import { autoApproveDocumentClaimIfEligible } from '../lib/document-claim-auto-approval';
import { maybeTriggerMacroFollowupsAfterLensCompletion } from '../lib/macro-followups';

const payloadSchema = z.object({
  documentId: z.string().uuid(),
  sourceOutlineId: z.string().uuid(),
  sourceGroupId: z.string().uuid(),
  lens: z.enum(EXTRACTION_LENSES),
});

const EXTRACTION_MAX_OUTPUT_TOKENS = 32_000;
const DEFAULT_LENS_DEDUP_DISTANCE = 0.08;
const DEFAULT_LENS_DEDUP_DENSITY_THRESHOLD_PER_10K = 10;

type InsertedDocumentChunk = {
  id: string;
  text: string;
};

type ExtractedClaim = ExtractionOutput['claims'][number];
type LensValidationTuning = {
  dedupDistance: number;
  dedupDensityThresholdPer10k: number;
};

function sha256(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex');
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
    includedDocumentChunkIds: plan.metadata.includedDocumentChunkIds ?? null,
  };
}

function formatDocumentChunksForExtraction(chunks: InsertedDocumentChunk[]): string {
  return chunks
    .map(
      (chunk) => `DOCUMENT CHUNK\nDocument Chunk ID: ${chunk.id}\nContent:\n${chunk.text}\n---\n`,
    )
    .join('\n');
}

function lensInstruction(lens: ExtractionLens): string {
  switch (lens) {
    case 'handoffs':
      return 'Focus on handoffs: who/which role/system passes work, approvals, files, tasks, or decisions to whom, and what must be true at the handoff.';
    case 'exceptions_and_workarounds':
      return 'Focus on exceptions, branches, blocked paths, manual overrides, unofficial workarounds, and fallback behavior.';
    case 'ownership_and_roles':
      return 'Focus on ownership, accountable roles/departments, review authority, and required participation.';
    case 'dependencies_and_sequence':
      return 'Focus on prerequisite order, sequencing, inputs, outputs, blockers, and before/after dependencies.';
    case 'systems_and_data_entry':
      return 'Focus on systems of record, data entry, field mapping, file locations, and system-to-system transfer rules.';
    case 'definitions_and_acronyms':
      return 'Focus on terms, acronyms, aliases, meanings, and disambiguation that affect operations.';
    case 'customer_or_licensor_risk':
      return 'Focus on customer, licensor, compliance, deadline, quality, or financial risk that changes the operational path.';
    case 'contradictions_and_tensions':
      return 'Focus on policy-vs-practice tension, conflicting instructions, ambiguity, and places where the source implies inconsistent behavior.';
  }
}

function pickEvidenceChunk(
  exactQuote: string,
  chunks: InsertedDocumentChunk[],
  sourceIdFallback?: InsertedDocumentChunk,
): InsertedDocumentChunk {
  const fallback = sourceIdFallback ?? chunks[0]!;
  if (!exactQuote) return fallback;
  return chunks.find((chunk) => chunk.text.includes(exactQuote)) ?? fallback;
}

function hasSensitivityFlags(claim: ExtractedClaim): boolean {
  return (
    claim.sensitivityFlags?.containsSensitiveHRData === true ||
    claim.sensitivityFlags?.containsSensitivePersonalData === true ||
    claim.sensitivityFlags?.isPersonalConflict === true
  );
}

async function loadActiveTopDomainIds(db: OracleDb): Promise<string[]> {
  const rows = await db.execute<{ id: string }>(
    sql`SELECT id FROM knowledge_top_domains WHERE is_active = true`,
  );
  return [...rows].map((r) => r.id);
}

async function loadEntityRegistry(db: OracleDb): Promise<RegistryEntity[]> {
  const rows = await db
    .select({
      id: entities.id,
      entityType: entities.entityType,
      canonicalValue: entities.canonicalValue,
      aliases: entities.aliases,
    })
    .from(entities);
  return rows.map((r) => ({
    id: r.id,
    entityType: r.entityType as EntityType,
    canonicalValue: r.canonicalValue,
    aliases: (r.aliases as string[] | null) ?? null,
  }));
}

async function resolveExtractionCandidates(db: OracleDb): Promise<RouteCandidate[]> {
  const resolved = await resolveRouteCandidates(db, 'extraction');
  for (const skipped of resolved.skipped) {
    console.error(
      `[document-lens-extraction] skipped configured extraction candidate ${skipped.modelIdOrRouteId}: ${skipped.reason}`,
    );
  }
  return resolved.candidates;
}

function settingToNumber(value: unknown, fallback: number, options: { min?: number; max?: number } = {}): number {
  const parsed = typeof value === 'number' ? value : Number(value ?? fallback);
  if (!Number.isFinite(parsed)) return fallback;
  const min = options.min ?? Number.NEGATIVE_INFINITY;
  const max = options.max ?? Number.POSITIVE_INFINITY;
  return Math.max(min, Math.min(max, parsed));
}

async function loadLensValidationTuning(db: OracleDb): Promise<LensValidationTuning> {
  const rows = await db.execute<{ key: string; value: unknown }>(sql`
    SELECT key, value FROM settings
    WHERE key IN (
      'macro_lens_dedup_distance',
      'macro_lens_dedup_density_threshold_per_10k'
    )
  `);
  const values = new Map([...rows].map((row) => [row.key, row.value]));
  return {
    dedupDistance: settingToNumber(
      values.get('macro_lens_dedup_distance'),
      DEFAULT_LENS_DEDUP_DISTANCE,
      { min: 0.001, max: 1 },
    ),
    dedupDensityThresholdPer10k: settingToNumber(
      values.get('macro_lens_dedup_density_threshold_per_10k'),
      DEFAULT_LENS_DEDUP_DENSITY_THRESHOLD_PER_10K,
      { min: 0, max: 1000 },
    ),
  };
}

async function shouldRunSemanticDedup(args: {
  db: OracleDb;
  documentId: string;
  chunkChars: number;
  thresholdPer10k: number;
}): Promise<boolean> {
  const rows = await args.db.execute<{ claim_count: number }>(sql`
    SELECT COUNT(DISTINCT c.id)::int AS claim_count
    FROM claims c
    JOIN claim_evidence ce ON ce.claim_id = c.id
    WHERE ce.source_document_chunk_id IN (
      SELECT id FROM document_chunks WHERE document_id = ${args.documentId}
    )
  `);
  const count = Number([...rows][0]?.claim_count ?? 0);
  const density = count / Math.max(1, args.chunkChars / 10_000);
  return density >= args.thresholdPer10k;
}

async function findNearDuplicateClaim(args: {
  db: OracleDb;
  summary: string;
  topDomainIds: string[];
  distance: number;
}): Promise<{ id: string; distance: number } | null> {
  const { vector } = await embedText(args.summary);
  const vec = `[${vector.join(',')}]`;
  const domainList = sql.join(
    args.topDomainIds.map((id) => sql`${id}`),
    sql`, `,
  );
  const rows = await args.db.execute<{ id: string; distance: number }>(sql`
    SELECT c.id, c.embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))}) AS distance
    FROM claims c
    WHERE c.embedding IS NOT NULL
      AND c.status IN ('approved', 'pending_review')
      AND c.embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))}) < ${args.distance}
      AND EXISTS (
        SELECT 1 FROM claim_top_domains ctd
        WHERE ctd.claim_id = c.id
          AND ctd.top_domain_id IN (${domainList})
      )
    ORDER BY c.embedding <=> ${vec}::vector(${sql.raw(String(EMBEDDING_DIM))})
    LIMIT 1
  `);
  return [...rows][0] ?? null;
}

async function runDocumentLensExtraction(rawPayload: unknown, triggerRunId: string) {
  const payload = payloadSchema.parse(rawPayload);
  const db = getDirectDb();

  const [doc] = await db
    .select({
      id: documents.id,
      fileName: documents.fileName,
      fileType: documents.fileType,
      uploaderId: documents.uploaderId,
      context: documents.context,
      domainHints: documents.domainHints,
    })
    .from(documents)
    .where(eq(documents.id, payload.documentId))
    .limit(1);
  if (!doc) return { status: 'skipped_document_not_found' as const, ...payload };

  const [group] = await db
    .select({
      id: sourceGroups.id,
      title: sourceGroups.title,
      groupType: sourceGroups.groupType,
      description: sourceGroups.description,
      metadataJson: sourceGroups.metadataJson,
    })
    .from(sourceGroups)
    .where(
      and(
        eq(sourceGroups.id, payload.sourceGroupId),
        eq(sourceGroups.sourceOutlineId, payload.sourceOutlineId),
      ),
    )
    .limit(1);
  if (!group) return { status: 'skipped_group_not_found' as const, ...payload };

  const [outline] = await db
    .select({
      id: sourceOutlines.id,
      summary: sourceOutlines.summary,
      outlineJson: sourceOutlines.outlineJson,
    })
    .from(sourceOutlines)
    .where(eq(sourceOutlines.id, payload.sourceOutlineId))
    .limit(1);
  if (!outline) return { status: 'skipped_outline_not_found' as const, ...payload };

  const chunkRows = await db
    .select({
      id: documentChunks.id,
      text: documentChunks.rawText,
      chunkIndex: documentChunks.chunkIndex,
    })
    .from(sourceGroupItems)
    .innerJoin(documentChunks, eq(documentChunks.id, sourceGroupItems.documentChunkId))
    .where(eq(sourceGroupItems.sourceGroupId, payload.sourceGroupId))
    .orderBy(sourceGroupItems.sortOrder, documentChunks.chunkIndex);
  if (chunkRows.length === 0) return { status: 'skipped_no_group_chunks' as const, ...payload };

  const chunks = chunkRows.map((row) => ({ id: row.id, text: row.text }));
  const documentCorpus = formatDocumentChunksForExtraction(chunks);
  const sourceHash = sha256(
    JSON.stringify({
      documentId: payload.documentId,
      sourceOutlineId: payload.sourceOutlineId,
      sourceGroupId: payload.sourceGroupId,
      lens: payload.lens,
      chunkIds: chunks.map((chunk) => chunk.id),
      chunkHash: sha256(documentCorpus),
    }),
  );
  const [jobRun] = await db
    .insert(jobRuns)
    .values({
      triggerRunId,
      jobType: 'document-lens-extraction',
      status: 'running',
      startedAt: new Date(),
      inputJson: payload,
    })
    .returning({ id: jobRuns.id });
  if (!jobRun) throw new Error('[document-lens-extraction] failed to insert job_runs row');

  if (await documentHasCompletedLensBatch({ db, sourceHash })) {
    const output = {
      status: 'skipped_existing_batch' as const,
      ...payload,
    };
    await db
      .update(jobRuns)
      .set({ status: 'complete', finishedAt: new Date(), outputJson: output })
      .where(eq(jobRuns.id, jobRun.id));
    const macroFollowups = await maybeTriggerMacroFollowupsAfterLensCompletion({
      db,
      documentId: payload.documentId,
      outlineId: payload.sourceOutlineId,
    }).catch((err) => {
      console.warn('[document-lens-extraction] macro followup check failed', err);
      return { triggered: false, reason: 'macro_followup_check_failed' };
    });
    await db
      .update(jobRuns)
      .set({ outputJson: { ...output, macroFollowups } })
      .where(eq(jobRuns.id, jobRun.id));
    return { ...output, macroFollowups };
  }

  let modelRunId: string | null = null;
  const outcome = {
    candidatesStaged: 0,
    claimsPromoted: 0,
    claimsAutoApproved: 0,
    duplicatesFlagged: 0,
    duplicatesAppended: 0,
    rejections: 0,
  };

  try {
    const routeCandidates = await resolveExtractionCandidates(db);
    const route = routeCandidates[0]!.route;
    const activeTopDomainIds = await loadActiveTopDomainIds(db);
    const entityRegistry = await loadEntityRegistry(db);
    const correctionLessons = await loadClaimCorrectionLessonPack(db);
    const validationTuning = await loadLensValidationTuning(db);
    const semanticDedupEnabled = await shouldRunSemanticDedup({
      db,
      documentId: payload.documentId,
      chunkChars: chunks.reduce((sum, chunk) => sum + chunk.text.length, 0),
      thresholdPer10k: validationTuning.dedupDensityThresholdPer10k,
    }).catch((err) => {
      console.warn('[document-lens-extraction] semantic dedup density check failed', err);
      return false;
    });

    const [batch] = await db
      .insert(extractionBatches)
      .values({
        jobRunId: jobRun.id,
        batchType: 'document_lens_group',
        status: 'pending_model',
        sourceDocumentChunkIds: chunks.map((chunk) => chunk.id),
        sourceHash,
        modelRunIdsAttempted: [],
        routeIdsAttempted: [route.routeId],
      })
      .returning({ id: extractionBatches.id });
    if (!batch)
      throw new Error('[document-lens-extraction] failed to insert extraction_batches row');

    const outlineJson = outline.outlineJson as {
      recommendedLenses?: string[];
      openQuestions?: string[];
    };
    const blocks = [
      makeBlock({
        id: 'extraction-system',
        label: 'Extraction system prompt + document lens addendum',
        kind: 'stable_system',
        content:
          EXTRACTION_SYSTEM_PROMPT +
          `\n\nDOCUMENT LENS EXTRACTION\nDocument name: ${doc.fileName}\nFile type: ${doc.fileType}\nActive lens: ${payload.lens}\n${lensInstruction(payload.lens)}\n\nThis is a targeted recall pass over one source group. Extract only claims directly supported by the active Document Chunk IDs. Prefer precise, non-duplicative claims that the normal broad pass may miss. Every exactQuote must still be copied verbatim from within ONE provided document chunk, and sourceMessageId must be that exact Document Chunk ID.`,
        reasonIncluded: `document lens extraction prompt v${EXTRACTION_PROMPT_VERSION}`,
      }),
      ...(correctionLessons.promptBlock
        ? [
            makeBlock({
              id: 'reviewer-correction-lessons',
              label: 'Approved reviewer correction lessons',
              kind: 'semi_stable_domain_context' as const,
              content: correctionLessons.promptBlock,
              reasonIncluded: 'approved claim revisions teach extraction corrections',
            }),
          ]
        : []),
      makeBlock({
        id: 'source-outline-guidance',
        label: 'Provisional source outline and group',
        kind: 'semi_stable_domain_context',
        content: [
          'PROVISIONAL SOURCE OUTLINE (GUIDANCE ONLY; NOT CLAIM EVIDENCE)',
          'Never quote this outline. Every exactQuote must come from a Document Chunk ID below.',
          `Outline summary: ${outline.summary ?? 'No summary.'}`,
          `Group: ${group.title} (${group.groupType})`,
          group.description ? `Group description: ${group.description}` : null,
          `Group metadata: ${JSON.stringify(group.metadataJson ?? {})}`,
          outlineJson.recommendedLenses?.length
            ? `Outline recommended lenses: ${outlineJson.recommendedLenses.join(', ')}`
            : null,
          outlineJson.openQuestions?.length
            ? `Open questions: ${outlineJson.openQuestions.slice(0, 8).join(' | ')}`
            : null,
        ]
          .filter(Boolean)
          .join('\n'),
        reasonIncluded: 'macro source outline guides targeted lens extraction',
      }),
      makeBlock({
        id: 'document-text',
        label: 'Lens source group chunks',
        kind: 'retrieved_context',
        content: documentCorpus,
        reasonIncluded: `${chunks.length} source-group chunks for lens ${payload.lens}`,
      }),
      makeBlock({
        id: 'document-lens-request',
        label: 'Document lens extraction request',
        kind: 'dynamic_input',
        content: `Run the ${payload.lens} lens against this source group. Return only atomic, evidence-backed operational claims that are explicit in the provided chunks. Avoid broad restatements of the outline; the outline is context, not evidence.`,
        reasonIncluded: 'targeted lens request',
      }),
    ];

    const client = new OracleAIClient({ adapters: buildStandardAdapters() });
    const plan = client.compile({
      taskType: 'document_claim_extraction',
      routeId: route.routeId,
      promptVersion: EXTRACTION_PROMPT_VERSION,
      blocks,
      observability: { includedDocumentChunkIds: chunks.map((chunk) => chunk.id) },
    });
    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values(buildContextPackInsert(plan))
      .returning({ id: oracleContextPacks.id });
    if (!contextPack)
      throw new Error('[document-lens-extraction] failed to insert oracle_context_packs row');
    await db
      .update(extractionBatches)
      .set({ contextPackId: contextPack.id })
      .where(eq(extractionBatches.id, batch.id));

    const callStartedAt = Date.now();
    const result = await client
      .runObject<ExtractionOutput>({
        taskType: 'document_claim_extraction',
        routeId: route.routeId,
        promptVersion: EXTRACTION_PROMPT_VERSION,
        blocks,
        schema: ExtractionOutputSchema,
        observability: { includedDocumentChunkIds: chunks.map((chunk) => chunk.id) },
        providerOptions: { maxOutputTokens: EXTRACTION_MAX_OUTPUT_TOKENS },
        routeCandidates,
      })
      .catch(async (err) => {
        await logAllCandidatesFailedAttempts({
          db,
          error: err,
          taskType: 'document-lens-extraction',
          slot: 'extraction',
          contextPackId: contextPack.id,
        }).catch((logErr) =>
          console.error(
            '[document-lens-extraction] failed to record failed model attempts',
            logErr,
          ),
        );
        throw err;
      });

    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'document-lens-extraction',
        model: result.modelId ?? route.modelId,
        provider: result.provider ?? route.provider,
        promptVersion: EXTRACTION_PROMPT_VERSION,
        inputHash: plan.metadata.stablePrefixHash,
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs: Date.now() - callStartedAt,
        success: result.validation.ok,
        error: result.validation.ok ? null : result.validation.error.message,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('[document-lens-extraction] failed to insert model_runs row');
    modelRunId = modelRun.id;
    await db.insert(modelRunUsageDetails).values({
      modelRunId,
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
      taskType: 'document-lens-extraction',
      slot: 'extraction',
      contextPackId: contextPack.id,
      modelRunId,
    });
    await db
      .update(oracleContextPacks)
      .set({ modelRunId })
      .where(eq(oracleContextPacks.id, contextPack.id));
    await db
      .update(extractionBatches)
      .set({
        modelRunId,
        modelRunIdsAttempted: [modelRunId],
        rawModelOutput: result.object as unknown as Record<string, unknown>,
        status: result.validation.ok ? 'model_complete' : 'failed',
      })
      .where(eq(extractionBatches.id, batch.id));

    if (!result.validation.ok) {
      throw new Error(
        '[document-lens-extraction] model output failed Zod schema validation: ' +
          result.validation.error.message,
      );
    }

    for (const extracted of result.object.claims) {
      const proposedTopDomainIds = mapLegacyDomainsToTopDomains(
        extracted.domains as KnowledgeDomain[],
      );
      const sourceIdChunk = chunks.find((chunk) => chunk.id === extracted.evidence.sourceMessageId);
      const chunkForEvidence = pickEvidenceChunk(
        extracted.evidence.exactQuote,
        chunks,
        sourceIdChunk,
      );
      const [candidate] = await db
        .insert(extractionCandidates)
        .values({
          extractionBatchId: batch.id,
          status: 'pending_validation',
          claimType: extracted.claimType,
          claimKind: extracted.claimKind ?? 'uncertain',
          claimKindConfidence: extracted.claimKindConfidence ?? 5,
          summary: extracted.summary,
          impactScore: extracted.impactScore,
          confidenceScore: extracted.confidenceScore,
          domains: proposedTopDomainIds satisfies TopLevelDomainId[],
          proposedEntities: (extracted.proposedEntities ?? []).map((e) => ({
            entityType: e.entityType,
            rawString: e.rawString,
          })),
          containsSensitivePersonalData:
            extracted.sensitivityFlags?.containsSensitivePersonalData ?? false,
          containsSensitiveHRData: extracted.sensitivityFlags?.containsSensitiveHRData ?? false,
          isPersonalConflict: extracted.sensitivityFlags?.isPersonalConflict ?? false,
          sensitivityReason: extracted.sensitivityFlags?.sensitivityReason ?? null,
          requiresReview: extracted.requiresReview,
          reviewReason: extracted.requiresReview ? 'extractor requested review' : null,
          rawCandidateJson: {
            ...extracted,
            lens: payload.lens,
            sourceGroupId: payload.sourceGroupId,
            sourceOutlineId: payload.sourceOutlineId,
          } as unknown as Record<string, unknown>,
        })
        .returning({ id: extractionCandidates.id });
      if (!candidate) continue;
      outcome.candidatesStaged += 1;

      if (semanticDedupEnabled && proposedTopDomainIds.length > 0) {
        const nearDuplicate = await findNearDuplicateClaim({
          db,
          summary: extracted.summary,
          topDomainIds: proposedTopDomainIds,
          distance: validationTuning.dedupDistance,
        }).catch((err) => {
          console.warn('[document-lens-extraction] semantic duplicate check failed', err);
          return null;
        });
        if (nearDuplicate) {
          await db
            .update(extractionCandidates)
            .set({
              status: 'duplicate',
              duplicateOfClaimId: nearDuplicate.id,
              validationError: `semantic near-duplicate distance ${nearDuplicate.distance}`,
              validatedAt: new Date(),
            })
            .where(eq(extractionCandidates.id, candidate.id));
          await db.insert(extractionValidationResults).values({
            candidateId: candidate.id,
            checkName: 'semantic_lens_duplicate',
            status: 'fail',
            detail: `Near-duplicate of claim ${nearDuplicate.id}; distance ${nearDuplicate.distance}`,
          });
          outcome.duplicatesFlagged += 1;
          continue;
        }
      }

      const sourcePointerRes = validateSourcePointer({
        sourceType: 'document_chunk',
        sourceDocumentChunkId: chunkForEvidence.id,
      });
      if (!sourcePointerRes.ok) {
        await db.insert(extractionValidationResults).values({
          candidateId: candidate.id,
          checkName: sourcePointerRes.failedCheckName ?? 'source_exists',
          status: 'fail',
          detail: sourcePointerRes.detail,
        });
        await db
          .update(extractionCandidates)
          .set({
            status: 'validation_failed',
            validationError: 'source pointer invalid',
            validatedAt: new Date(),
          })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }

      const [evRow] = await db
        .insert(extractionCandidateEvidence)
        .values({
          candidateId: candidate.id,
          sourceType: 'document_chunk',
          sourceDocumentChunkId: chunkForEvidence.id,
          uploadedByEmployeeId: doc.uploaderId,
          exactQuoteProvided: extracted.evidence.exactQuote,
          validationStatus: 'pending',
          confidence: extracted.evidence.confidence,
          documentClass: null,
          processStage: null,
        })
        .returning({ id: extractionCandidateEvidence.id });
      if (!evRow) continue;

      const quoteRes = validateQuote({
        sourceText: chunkForEvidence.text,
        exactQuoteProvided: extracted.evidence.exactQuote,
        normalizationPolicy: doc.fileType.startsWith('text/')
          ? MARKDOWN_DOCUMENT_NORMALIZATION_POLICY
          : undefined,
      });
      await db
        .update(extractionCandidateEvidence)
        .set({
          validationStatus: quoteRes.validationStatus,
          validationMethod: quoteRes.validationMethod,
          validatedExactQuote: quoteRes.validatedExactQuote ?? null,
          validatedCharStart: quoteRes.validatedCharStart ?? null,
          validatedCharEnd: quoteRes.validatedCharEnd ?? null,
          validatedAt: new Date(),
          validationError:
            quoteRes.verdict === 'exact_match' || quoteRes.verdict === 'normalized_match'
              ? null
              : quoteRes.detail,
        })
        .where(eq(extractionCandidateEvidence.id, evRow.id));
      await db.insert(extractionValidationResults).values({
        candidateId: candidate.id,
        candidateEvidenceId: evRow.id,
        checkName: quoteRes.failedCheckName ?? 'quote_exact_match',
        status:
          quoteRes.verdict === 'exact_match' || quoteRes.verdict === 'normalized_match'
            ? 'pass'
            : 'fail',
        detail: quoteRes.detail,
      });
      if (quoteRes.verdict !== 'exact_match' && quoteRes.verdict !== 'normalized_match') {
        await db
          .update(extractionCandidates)
          .set({
            status: 'validation_failed',
            validationError: quoteRes.detail,
            validatedAt: new Date(),
          })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }

      const taxRes = validateTaxonomy({
        proposedTopDomainIds,
        activeTopDomainIds,
        proposedEntities: (extracted.proposedEntities ?? []).map((e) => ({
          entityType: e.entityType as EntityType,
          rawString: e.rawString,
        })),
        entityRegistry,
      });
      const taxonomyAllowsPromotion = taxRes.ok || taxRes.blockedByOnlyUnknownEntities;
      await db.insert(extractionValidationResults).values({
        candidateId: candidate.id,
        checkName: 'domain_valid',
        status: taxonomyAllowsPromotion ? 'pass' : 'fail',
        detail: taxRes.ok
          ? `Top-domains validated: ${taxRes.validTopDomainIds.join(', ')}`
          : taxRes.blockedByOnlyUnknownEntities
            ? `Top-domains validated: ${taxRes.validTopDomainIds.join(', ')}; unknown entity proposals staged for admin review.`
            : taxRes.failures.map((f) => f.detail).join('; '),
      });
      for (const p of taxRes.entityProposalsToCreate) {
        await stageEntityProposal(db, {
          proposedEntityType: p.proposedEntityType,
          proposedCanonicalValue: p.proposedCanonicalValue,
          rawString: p.rawString,
          observedInSourceType: 'claim_candidate',
          observedInSourceId: candidate.id,
          proposedByModelRunId: modelRunId,
        });
      }
      if (!taxonomyAllowsPromotion) {
        await db
          .update(extractionCandidates)
          .set({
            status: 'validation_failed',
            validationError: taxRes.failureSummary ?? 'taxonomy invalid',
            validatedAt: new Date(),
          })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }

      if (hasSensitivityFlags(extracted)) {
        await db.insert(extractionValidationResults).values({
          candidateId: candidate.id,
          checkName: 'sensitivity_gate',
          status: 'fail',
          detail:
            extracted.sensitivityFlags?.sensitivityReason ?? 'extractor flagged sensitive content',
        });
        await db
          .update(extractionCandidates)
          .set({
            status: 'quarantined_sensitive',
            validationError:
              extracted.sensitivityFlags?.sensitivityReason ??
              'sensitive content flagged by extractor',
            validatedAt: new Date(),
          })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }
      await db.insert(extractionValidationResults).values({
        candidateId: candidate.id,
        checkName: 'sensitivity_gate',
        status: 'pass',
        detail: 'extractor reported no sensitive content',
      });

      await db
        .update(extractionCandidates)
        .set({ status: 'validated', validatedAt: new Date() })
        .where(eq(extractionCandidates.id, candidate.id));
      const validatedQuote = quoteRes.validatedExactQuote ?? extracted.evidence.exactQuote;
      const candidateHash = computeCandidateHash({
        summary: extracted.summary,
        topDomainIds: taxRes.validTopDomainIds,
        validatedQuotes: [validatedQuote],
        sourcePointers: [`document_chunk:${chunkForEvidence.id}`],
      });
      try {
        const promotion = await executePromotion({
          db,
          candidateId: candidate.id,
          candidateHash,
          auxiliaryInputs: { taxonomy: taxRes },
          modelRunId: modelRunId ?? undefined,
        });
        if (promotion.outcome === 'inserted_new_claim') outcome.claimsPromoted += 1;
        else if (promotion.outcome === 'appended_to_existing_claim')
          outcome.duplicatesAppended += 1;
        else outcome.rejections += 1;

        if (promotion.outcome !== 'recorded_rejection') {
          const autoApproved = await autoApproveDocumentClaimIfEligible({
            db,
            candidateId: candidate.id,
            extracted,
            result: promotion,
            quoteVerdict: quoteRes.verdict,
            validTopDomainIds: taxRes.validTopDomainIds,
          });
          if (autoApproved) outcome.claimsAutoApproved += 1;
          for (const topDomainId of taxRes.validTopDomainIds) {
            await db
              .insert(documentTopDomains)
              .values({
                documentId: payload.documentId,
                topDomainId,
                assignmentReason: 'lens_extraction',
              })
              .onConflictDoNothing();
            await db
              .insert(documentChunkTopDomains)
              .values({
                documentChunkId: chunkForEvidence.id,
                topDomainId,
                assignmentReason: 'lens_extraction',
              })
              .onConflictDoNothing();
          }
        }
      } catch (err) {
        if (err instanceof AdvisoryLockBusyError) {
          await db.insert(extractionValidationResults).values({
            candidateId: candidate.id,
            checkName: 'duplicate_promotion_lock',
            status: 'skipped',
            detail: 'Advisory lock busy; another worker holds it.',
          });
        } else {
          await db.insert(extractionValidationResults).values({
            candidateId: candidate.id,
            checkName: 'promotion_transaction',
            status: 'fail',
            detail: err instanceof Error ? err.message : String(err),
          });
          outcome.rejections += 1;
        }
      }
    }

    await db
      .update(extractionBatches)
      .set({ status: 'validation_complete', finishedAt: new Date(), validationSummary: outcome })
      .where(eq(extractionBatches.id, batch.id));
    await db
      .update(jobRuns)
      .set({
        status: 'complete',
        finishedAt: new Date(),
        outputJson: outcome,
      })
      .where(eq(jobRuns.id, jobRun.id));
    const macroFollowups = await maybeTriggerMacroFollowupsAfterLensCompletion({
      db,
      documentId: payload.documentId,
      outlineId: payload.sourceOutlineId,
    }).catch((err) => {
      console.warn('[document-lens-extraction] macro followup check failed', err);
      return { triggered: false, reason: 'macro_followup_check_failed' };
    });
    await db
      .update(jobRuns)
      .set({ outputJson: { ...outcome, macroFollowups } })
      .where(eq(jobRuns.id, jobRun.id));

    return { status: 'complete' as const, ...payload, ...outcome };
  } catch (err) {
    await db
      .update(jobRuns)
      .set({
        status: 'failed',
        finishedAt: new Date(),
        error: err instanceof Error ? err.message : String(err),
      })
      .where(eq(jobRuns.id, jobRun.id));
    throw err;
  }
}

export const documentLensExtractionTask = task({
  id: 'document-lens-extraction',
  run: async (rawPayload: unknown, { ctx }) => {
    return runDocumentLensExtraction(rawPayload, ctx.run.id);
  },
});
