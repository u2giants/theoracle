// Source outline worker: creates provisional macro context for a document.
//
// Outlines are guidance only. They are not claim evidence, never promote
// claims, and can only reference persisted document chunks for inspectability.

import { task, tasks } from '@trigger.dev/sdk/v3';
import { and, desc, eq, inArray } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { z } from 'zod';
import {
  OracleAIClient,
  SOURCE_OUTLINE_PROMPT_VERSION,
  SOURCE_OUTLINE_SYSTEM_PROMPT,
  SourceOutlineSchema,
  buildStandardAdapters,
  embedMany,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type OraclePromptPlan,
  type SourceOutlineOutput,
} from '@oracle/ai';
import { getDirectDb } from '@oracle/db/client';
import {
  documentChunks,
  documents,
  jobRuns,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  sourceGroupItems,
  sourceGroups,
  sourceOutlineSourceRefs,
  sourceOutlineSources,
  sourceOutlines,
  type OracleDb,
} from '@oracle/db';
import { buildLensDispatchPlan } from '../lib/document-lens-budget';
import { markMacroFailed, markMacroPending } from '../lib/macro-health';
import { triggerMacroFollowupsOnce } from '../lib/macro-followups';

const payloadSchema = z.object({
  documentId: z.string().uuid(),
  force: z.boolean().optional(),
});

type ChunkRow = {
  id: string;
  chunkIndex: number;
  pageNumber: number | null;
  rawText: string;
  contentHash: string | null;
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
    includedDocumentChunkIds: plan.metadata.includedDocumentChunkIds ?? null,
  };
}

function buildDocumentCorpus(chunks: ChunkRow[]): string {
  return chunks
    .map((chunk) => {
      const page = chunk.pageNumber ? ` page=${chunk.pageNumber}` : '';
      return `--- Document Chunk ID: ${chunk.id} index=${chunk.chunkIndex}${page} ---\n${chunk.rawText}`;
    })
    .join('\n\n');
}

function normalizeOutlineRefs(
  outline: SourceOutlineOutput,
  chunkIds: Set<string>,
): SourceOutlineOutput {
  const validRefs = outline.refs.filter((ref) => chunkIds.has(ref.chunkId));
  const groups = outline.groups
    .map((group) => ({
      ...group,
      chunkIds: Array.from(new Set(group.chunkIds.filter((id) => chunkIds.has(id)))),
    }))
    .filter((group) => group.chunkIds.length > 0);

  return {
    ...outline,
    refs: validRefs,
    groups,
    entities: outline.entities.map((entity) => ({
      ...entity,
      chunkIds: entity.chunkIds?.filter((id) => chunkIds.has(id)),
    })),
    terms: outline.terms.map((term) => ({
      ...term,
      chunkIds: term.chunkIds?.filter((id) => chunkIds.has(id)),
    })),
    stages: outline.stages.map((stage) => ({
      ...stage,
      chunkIds: stage.chunkIds?.filter((id) => chunkIds.has(id)),
    })),
  };
}

async function supersedeExistingDocumentOutlines(db: OracleDb, documentId: string): Promise<void> {
  const existing = await db
    .select({ outlineId: sourceOutlineSources.sourceOutlineId })
    .from(sourceOutlineSources)
    .where(
      and(
        eq(sourceOutlineSources.sourceType, 'document'),
        eq(sourceOutlineSources.documentId, documentId),
      ),
    );

  const ids = Array.from(new Set(existing.map((row) => row.outlineId)));
  if (ids.length === 0) return;

  await db
    .update(sourceOutlines)
    .set({ status: 'superseded', updatedAt: new Date() })
    .where(and(inArray(sourceOutlines.id, ids), eq(sourceOutlines.status, 'provisional')));
}

async function persistOutline(args: {
  db: OracleDb;
  documentId: string;
  sourceHash: string;
  outline: SourceOutlineOutput;
  modelRunId: string | null;
  contextPackId: string | null;
}): Promise<string> {
  const { db, documentId, sourceHash, outline, modelRunId, contextPackId } = args;

  await supersedeExistingDocumentOutlines(db, documentId);

  const groupTexts = outline.groups.map((group) =>
    [group.title, group.description, group.recommendedLenses?.join(', ')]
      .filter(Boolean)
      .join('\n'),
  );
  let groupEmbeddings: number[][] = [];
  if (groupTexts.length > 0) {
    try {
      groupEmbeddings = (await embedMany(groupTexts)).vectors;
    } catch (err) {
      console.warn('[source-outline] group embedding failed; storing groups without vectors', err);
      groupEmbeddings = [];
    }
  }

  const [outlineRow] = await db
    .insert(sourceOutlines)
    .values({
      sourceType: 'document',
      status: 'provisional',
      outlineVersion: SOURCE_OUTLINE_PROMPT_VERSION,
      modelRunId,
      contextPackId,
      sourceHash,
      outlineJson: outline,
      summary: outline.summary,
      budgetJson: outline.budget,
    })
    .returning({ id: sourceOutlines.id });
  if (!outlineRow) throw new Error('[source-outline] failed to insert source_outlines row');

  await db.insert(sourceOutlineSources).values({
    sourceOutlineId: outlineRow.id,
    sourceType: 'document',
    documentId,
    sourceHash,
  });

  const refRows = outline.refs.map((ref) => ({
    sourceOutlineId: outlineRow.id,
    outlineElementId: null,
    refType: 'document_chunk',
    documentChunkId: ref.chunkId,
    refRole: ref.role,
    metadataJson: ref.note ? { note: ref.note } : null,
  }));
  if (refRows.length > 0) {
    await db.insert(sourceOutlineSourceRefs).values(refRows);
  }

  for (let i = 0; i < outline.groups.length; i++) {
    const group = outline.groups[i]!;
    const [groupRow] = await db
      .insert(sourceGroups)
      .values({
        sourceOutlineId: outlineRow.id,
        groupType: group.groupType,
        title: group.title,
        description: group.description ?? null,
        embedding: groupEmbeddings[i] ?? null,
        sortOrder: group.sortOrder ?? i,
        metadataJson: {
          elementId: group.elementId,
          recommendedLenses: group.recommendedLenses ?? [],
          uncertainty: group.uncertainty ?? null,
        },
      })
      .returning({ id: sourceGroups.id });
    if (!groupRow) continue;

    await db.insert(sourceGroupItems).values(
      group.chunkIds.map((chunkId, index) => ({
        sourceGroupId: groupRow.id,
        itemType: 'document_chunk',
        documentChunkId: chunkId,
        sortOrder: index,
      })),
    );
  }

  return outlineRow.id;
}

async function countSourceOutlineGroups(db: OracleDb, outlineId: string): Promise<number> {
  const rows = await db
    .select({ id: sourceGroups.id })
    .from(sourceGroups)
    .where(eq(sourceGroups.sourceOutlineId, outlineId));
  return rows.length;
}

async function triggerDocumentLensFanout(args: {
  db: OracleDb;
  documentId: string;
  outlineId: string;
}): Promise<{
  triggered: number;
  planned: number;
  skipped: Array<{ sourceGroupId?: string; groupTitle?: string; lens?: string; reason: string }>;
}> {
  const plan = await buildLensDispatchPlan(args.db, args.outlineId);
  let triggered = 0;
  for (const selected of plan.selected) {
    await tasks
      .trigger('document-lens-extraction', {
        documentId: args.documentId,
        sourceOutlineId: args.outlineId,
        sourceGroupId: selected.sourceGroupId,
        lens: selected.lens,
      })
      .then(() => {
        triggered += 1;
      })
      .catch((err) =>
        console.warn('[source-outline] failed to trigger document lens extraction', {
          sourceGroupId: selected.sourceGroupId,
          lens: selected.lens,
          err,
        }),
      );
  }
  return { triggered, planned: plan.selected.length, skipped: plan.skipped };
}

async function generateDocumentOutline(documentId: string, force: boolean, triggerRunId: string) {
  const db = getDirectDb();

  const [doc] = await db
    .select({
      id: documents.id,
      fileName: documents.fileName,
      fileType: documents.fileType,
      status: documents.status,
      context: documents.context,
    })
    .from(documents)
    .where(eq(documents.id, documentId))
    .limit(1);
  if (!doc) return { documentId, status: 'skipped_not_found' as const };

  const chunks = await db
    .select({
      id: documentChunks.id,
      chunkIndex: documentChunks.chunkIndex,
      pageNumber: documentChunks.pageNumber,
      rawText: documentChunks.rawText,
      contentHash: documentChunks.contentHash,
    })
    .from(documentChunks)
    .where(eq(documentChunks.documentId, documentId))
    .orderBy(documentChunks.chunkIndex);
  if (chunks.length === 0) return { documentId, status: 'skipped_no_chunks' as const };

  const documentCorpus = buildDocumentCorpus(chunks);
  const sourceHash = sha256(
    JSON.stringify({
      documentId,
      chunks: chunks.map((chunk) => [chunk.id, chunk.chunkIndex, chunk.contentHash, chunk.rawText]),
    }),
  );

  if (!force) {
    const [existing] = await db
      .select({ id: sourceOutlines.id })
      .from(sourceOutlines)
      .innerJoin(sourceOutlineSources, eq(sourceOutlineSources.sourceOutlineId, sourceOutlines.id))
      .where(
        and(
          eq(sourceOutlineSources.documentId, documentId),
          eq(sourceOutlineSources.sourceType, 'document'),
          eq(sourceOutlines.status, 'provisional'),
          eq(sourceOutlines.sourceHash, sourceHash),
        ),
      )
      .orderBy(desc(sourceOutlines.createdAt))
      .limit(1);
    if (existing) {
      const lensFanout = await triggerDocumentLensFanout({
        db,
        documentId,
        outlineId: existing.id,
      });
      const followups =
        lensFanout.planned === 0
          ? await triggerMacroFollowupsOnce({
              db,
              documentId,
              outlineId: existing.id,
              groupCount: await countSourceOutlineGroups(db, existing.id),
              reason: 'source_outline_no_lens_jobs',
            })
          : await markMacroPending(db, documentId).then(() => ({
              triggered: false,
              reason: 'deferred_until_lens_fanout_complete',
            }));
      return {
        documentId,
        status: 'skipped_existing' as const,
        outlineId: existing.id,
        lensFanout,
        macroFollowups: followups,
      };
    }
  }

  const [jobRun] = await db
    .insert(jobRuns)
    .values({
      triggerRunId,
      jobType: 'source-outline',
      status: 'running',
      startedAt: new Date(),
      inputJson: { documentId, force },
    })
    .returning({ id: jobRuns.id });
  if (!jobRun) throw new Error('[source-outline] failed to insert job_runs row');

  try {
    const client = new OracleAIClient({ adapters: buildStandardAdapters() });
    const resolved = await resolveRouteCandidates(db, 'macro');
    for (const skipped of resolved.skipped) {
      console.warn('[source-outline] skipped general route candidate', skipped);
    }
    const routeCandidates = resolved.candidates;
    const route = routeCandidates[0]!.route;
    const chunkIds = chunks.map((chunk) => chunk.id);

    const blocks = [
      makeBlock({
        id: 'source-outline-system',
        label: 'Source outline system prompt',
        kind: 'stable_system',
        content: SOURCE_OUTLINE_SYSTEM_PROMPT,
        reasonIncluded: `source outline prompt v${SOURCE_OUTLINE_PROMPT_VERSION}`,
      }),
      makeBlock({
        id: 'document-metadata',
        label: 'Document metadata',
        kind: 'semi_stable_domain_context',
        content: [
          `Document name: ${doc.fileName}`,
          `File type: ${doc.fileType}`,
          doc.context ? `Uploader context:\n${doc.context}` : null,
        ]
          .filter(Boolean)
          .join('\n\n'),
        reasonIncluded: 'document-level context for macro outline',
      }),
      makeBlock({
        id: 'document-chunks',
        label: 'Document chunks',
        kind: 'retrieved_context',
        content: documentCorpus,
        reasonIncluded: `${chunks.length} persisted document chunks; outline refs must use these chunk IDs`,
      }),
      makeBlock({
        id: 'source-outline-request',
        label: 'Source outline request',
        kind: 'dynamic_input',
        content:
          'Create a provisional macro outline for this document. Identify process stages, handoffs, exception branches, terms, entities, source groups, recommended extraction lenses, and open questions. Use only provided document chunk IDs in refs and groups.',
        reasonIncluded: 'request current outline output',
      }),
    ];

    const plan = client.compile({
      taskType: 'source_outline',
      routeId: route.routeId,
      promptVersion: SOURCE_OUTLINE_PROMPT_VERSION,
      blocks,
      observability: { includedDocumentChunkIds: chunkIds },
    });
    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values(buildContextPackInsert(plan))
      .returning({ id: oracleContextPacks.id });
    if (!contextPack) throw new Error('[source-outline] failed to insert context pack');

    const started = Date.now();
    let modelRunId: string | null = null;
    const result = await client
      .runObject<SourceOutlineOutput>({
        taskType: 'source_outline',
        routeId: route.routeId,
        promptVersion: SOURCE_OUTLINE_PROMPT_VERSION,
        blocks,
        schema: SourceOutlineSchema,
        observability: { includedDocumentChunkIds: chunkIds },
        providerOptions: { maxOutputTokens: 16_000 },
        routeCandidates,
      })
      .catch(async (err) => {
        await logAllCandidatesFailedAttempts({
          db,
          error: err,
          taskType: 'source-outline',
          slot: 'macro',
          contextPackId: contextPack.id,
        }).catch((logErr) =>
          console.error('[source-outline] failed to record failed model attempts', logErr),
        );
        throw err;
      });

    const actualRouteId = result.routeId ?? route.routeId;
    const actualProvider = result.provider ?? route.provider;
    const actualModelId = result.modelId ?? route.modelId;
    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'source-outline',
        model: actualModelId,
        provider: actualProvider,
        promptVersion: SOURCE_OUTLINE_PROMPT_VERSION,
        inputHash: plan.metadata.stablePrefixHash,
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs: Date.now() - started,
        success: result.validation.ok,
        error: result.validation.ok ? null : result.validation.error.message,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('[source-outline] failed to insert model_runs row');
    modelRunId = modelRun.id;

    await db.insert(modelRunUsageDetails).values({
      modelRunId,
      contextPackId: contextPack.id,
      routeId: actualRouteId,
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
      taskType: 'source-outline',
      slot: 'macro',
      contextPackId: contextPack.id,
      modelRunId,
    });
    await db
      .update(oracleContextPacks)
      .set({ modelRunId })
      .where(eq(oracleContextPacks.id, contextPack.id));

    if (!result.validation.ok) {
      throw new Error(
        '[source-outline] model output failed Zod schema validation: ' +
          result.validation.error.message,
      );
    }

    const outline = normalizeOutlineRefs(result.object, new Set(chunkIds));
    const outlineId = await persistOutline({
      db,
      documentId,
      sourceHash,
      outline,
      modelRunId,
      contextPackId: contextPack.id,
    });
    const lensFanout = await triggerDocumentLensFanout({
      db,
      documentId,
      outlineId,
    });
    const followups =
      lensFanout.planned === 0
        ? await triggerMacroFollowupsOnce({
            db,
            documentId,
            outlineId,
            groupCount: outline.groups.length,
            reason: 'source_outline_no_lens_jobs',
          })
        : await markMacroPending(db, documentId).then(() => ({
            triggered: false,
            reason: 'deferred_until_lens_fanout_complete',
          }));

    await db
      .update(jobRuns)
      .set({
        status: 'complete',
        finishedAt: new Date(),
        outputJson: {
          documentId,
          outlineId,
          groupCount: outline.groups.length,
          refCount: outline.refs.length,
          lensFanout,
          macroFollowups: followups,
        },
      })
      .where(eq(jobRuns.id, jobRun.id));

    return { documentId, status: 'outlined' as const, outlineId };
  } catch (err) {
    await db
      .update(jobRuns)
      .set({
        status: 'failed',
        finishedAt: new Date(),
        error: err instanceof Error ? err.message : String(err),
      })
      .where(eq(jobRuns.id, jobRun.id));
    // Outline itself failed => no holistic layer at all for this document.
    await markMacroFailed(db, documentId);
    throw err;
  }
}

export const sourceOutlineTask = task({
  id: 'source-outline',
  run: async (rawPayload: unknown, { ctx }) => {
    const { documentId, force = false } = payloadSchema.parse(rawPayload);
    return generateDocumentOutline(documentId, force, ctx.run.id);
  },
});
