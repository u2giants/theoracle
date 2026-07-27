import { and, desc, eq, inArray, ne, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import {
  OracleAIClient,
  RESPONSIBILITY_READ_PROMPT_VERSION,
  RESPONSIBILITY_READ_SYSTEM_PROMPT,
  ResponsibilityReadSchema,
  SOURCE_READER_PIPELINE_VERSION,
  SOURCE_STRUCTURE_SHAPE_REGISTRY,
  SOURCE_SEGMENTATION_PROMPT_VERSION,
  SOURCE_SEGMENTATION_SYSTEM_PROMPT,
  WORKFLOW_READ_PROMPT_VERSION,
  WORKFLOW_READ_SYSTEM_PROMPT,
  WORKFLOW_QUOTE_REPAIR_SYSTEM_PROMPT,
  SourceSegmentationSchema,
  WorkflowReadSchema,
  WorkflowQuoteRepairSchema,
  buildStandardAdapters,
  estimateTokens,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type OraclePromptPlan,
  type ResponsibilityReadOutput,
  type SourceSegmentationOutput,
  type SourceStructureSegment,
  type SourceStructureShape,
  type WorkflowReadEdge,
  type WorkflowReadLane,
  type WorkflowReadNode,
  type WorkflowReadOutput,
  type WorkflowQuoteRepairOutput,
  type WorkflowReadPath,
  type SourceStructureElement,
  type SourceStructureMap,
  type SourceStructureRelation,
} from '@oracle/ai';
import {
  businessProcesses,
  documentChunks,
  documents,
  entities,
  jobRuns,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  settings,
  sourceWorkflowMaps,
  type OracleDb,
} from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import { quoteSourceKindForDocument } from '@oracle/engines';
import {
  markMacroComplete,
  markMacroDegraded,
  markMacroMapFailed,
  markMacroPending,
} from './macro-health';
import {
  validateWorkflowMap,
  type WorkflowMapChunkContext,
  type WorkflowMapStatus,
} from './workflow-map-validator';
import {
  responsibilityRawAuditArtifact,
  validateResponsibilityRead,
} from './responsibility-reader';
import {
  mapWithConcurrency,
  SourceReaderBudget,
  SourceReaderBudgetExceededError,
  type SourceReaderBudgetLimits,
} from './source-reader-budget';
import type {
  WorkflowMapRejectionDiagnostic,
  WorkflowMapValidationResult,
} from './workflow-map-validator';

type ChunkRow = {
  id: string;
  chunkIndex: number;
  pageNumber: number | null;
  rawText: string;
  contentHash: string | null;
};

type ReusableWorkflowMapStatus = 'validated' | 'degraded';

export type WorkflowQuoteRepairMetadata = {
  repairAttempts: number;
  repairSkipped: string | null;
  rootDroppedBefore: number;
  cascadeDroppedBefore: number;
  rootDroppedAfter: number;
  cascadeDroppedAfter: number;
};

export function eligibleWorkflowQuoteRepairs(
  validation: WorkflowMapValidationResult,
): WorkflowMapRejectionDiagnostic[] {
  return validation.diagnostics.filter(
    (item) =>
      item.failureOrigin === 'root' &&
      (item.elementType === 'node' || item.elementType === 'edge') &&
      (item.failureClass === 'quote_mismatch' || item.failureClass === 'quote_ambiguous') &&
      item.citedChunkId !== null,
  );
}

export function patchWorkflowQuoteRepairs(args: {
  original: WorkflowReadOutput;
  requested: readonly WorkflowMapRejectionDiagnostic[];
  response: WorkflowQuoteRepairOutput;
}): { ok: true; output: WorkflowReadOutput } | { ok: false; reason: string } {
  const requested = new Map(
    args.requested.map((item) => [`${item.elementType}:${item.elementId}`, item]),
  );
  const seen = new Set<string>();
  const replacements = new Map<string, string>();
  for (const repair of args.response.repairs) {
    const key = `${repair.elementType}:${repair.elementId}`;
    if (seen.has(key)) return { ok: false, reason: 'duplicate_repair' };
    seen.add(key);
    const target = requested.get(key);
    if (!target) return { ok: false, reason: 'unknown_or_wrong_element_type' };
    if (target.citedChunkId !== repair.chunkId) return { ok: false, reason: 'chunk_move' };
    replacements.set(key, repair.evidenceQuote);
  }
  if (seen.size !== requested.size) return { ok: false, reason: 'missing_repair' };
  return {
    ok: true,
    output: {
      ...args.original,
      nodes: args.original.nodes.map((node) => ({
        ...node,
        evidenceQuote: replacements.get(`node:${node.nodeId}`) ?? node.evidenceQuote,
      })),
      edges: args.original.edges.map((edge) => ({
        ...edge,
        evidenceQuote: replacements.get(`edge:${edge.edgeId}`) ?? edge.evidenceQuote,
      })),
      lanes: args.original.lanes.map((lane) => ({ ...lane })),
      paths: args.original.paths.map((path) => ({
        ...path,
        nodeIdsOrdered: [...path.nodeIdsOrdered],
      })),
    },
  };
}

export function chooseWorkflowQuoteRepair(
  original: WorkflowMapValidationResult,
  repaired: WorkflowMapValidationResult,
): WorkflowMapValidationResult {
  return repaired.rootDroppedCount < original.rootDroppedCount ? repaired : original;
}

export function selectWorkflowQuoteRepairCandidate(
  candidates: readonly WorkflowMapValidationResult[],
): number | null {
  let selected: number | null = null;
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index]!;
    const candidateEligibleRootCount = eligibleWorkflowQuoteRepairs(candidate).length;
    if (candidateEligibleRootCount === 0) continue;
    if (selected === null) {
      selected = index;
      continue;
    }
    const current = candidates[selected]!;
    const currentEligibleRootCount = eligibleWorkflowQuoteRepairs(current).length;
    if (
      candidateEligibleRootCount > currentEligibleRootCount ||
      (candidateEligibleRootCount === currentEligibleRootCount &&
        candidate.cascadeDroppedCount > current.cascadeDroppedCount) ||
      (candidateEligibleRootCount === currentEligibleRootCount &&
        candidate.cascadeDroppedCount === current.cascadeDroppedCount &&
        candidate.rootDroppedCount > current.rootDroppedCount) ||
      (candidateEligibleRootCount === currentEligibleRootCount &&
        candidate.cascadeDroppedCount === current.cascadeDroppedCount &&
        candidate.rootDroppedCount === current.rootDroppedCount &&
        candidate.droppedCount > current.droppedCount)
    ) {
      selected = index;
    }
  }
  return selected;
}

export type SourceWorkflowReadResult = {
  documentId: string;
  status:
    | 'validated'
    | 'degraded'
    | 'failed'
    | 'skipped_existing'
    | 'skipped_no_chunks'
    | 'skipped_not_found';
  mapId?: string;
  existingMapStatus?: 'validated' | 'degraded';
  mapKind?: 'workflow' | 'reference';
  documentShape?: SourceStructureShape;
  droppedCount?: number;
  keptCount?: number;
  segmentCount?: number;
  elementCount?: number;
  relationCount?: number;
  laneCount?: number;
  pathCount?: number;
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

function sourceHashForDocument(documentId: string, chunks: ChunkRow[]): string {
  return sha256(
    JSON.stringify({
      documentId,
      readerPipelineVersion: SOURCE_READER_PIPELINE_VERSION,
      segmentationPromptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      workflowPromptVersion: WORKFLOW_READ_PROMPT_VERSION,
      chunks: chunks.map((chunk) => [chunk.id, chunk.chunkIndex, chunk.contentHash, chunk.rawText]),
    }),
  );
}

async function readNumberSetting(db: OracleDb, key: string, fallback: number): Promise<number> {
  const [row] = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, key))
    .limit(1);
  const value = row?.value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  return fallback;
}

async function buildReferentPack(db: OracleDb): Promise<string> {
  const [entityRows, processRows] = await Promise.all([
    db
      .select({
        canonicalValue: entities.canonicalValue,
        displayLabel: entities.displayLabel,
        entityType: entities.entityType,
        aliases: entities.aliases,
      })
      .from(entities)
      .orderBy(entities.entityType, entities.canonicalValue)
      .limit(300),
    db
      .select({ name: businessProcesses.name, summary: businessProcesses.summary })
      .from(businessProcesses)
      .orderBy(desc(businessProcesses.updatedAt))
      .limit(80),
  ]);

  const lines = [
    'REFERENT PACK (names and acronyms only; do not copy existing structure):',
    '',
    'Known entities:',
  ];
  for (const entity of entityRows) {
    const aliases =
      Array.isArray(entity.aliases) && entity.aliases.length > 0
        ? ` aliases=${entity.aliases.join(', ')}`
        : '';
    lines.push(`- ${entity.entityType}: ${entity.displayLabel ?? entity.canonicalValue}${aliases}`);
  }
  if (processRows.length > 0) {
    lines.push('', 'Existing process names only:');
    for (const process of processRows) {
      lines.push(`- ${process.name}${process.summary ? `: ${process.summary.slice(0, 180)}` : ''}`);
    }
  }
  return lines.join('\n');
}

function chunkWindows(chunks: ChunkRow[], maxEstimatedInputTokens: number): ChunkRow[][] {
  const maxChars = Math.max(8_000, maxEstimatedInputTokens * 4);
  const windows: ChunkRow[][] = [];
  let current: ChunkRow[] = [];
  for (const chunk of chunks) {
    const next = [...current, chunk];
    if (current.length > 0 && buildDocumentCorpus(next).length > maxChars) {
      windows.push(current);
      current = [chunk];
    } else {
      current = next;
    }
  }
  if (current.length > 0) windows.push(current);
  return windows;
}

function isReusableWorkflowMapStatus(
  status: string | null | undefined,
): status is ReusableWorkflowMapStatus {
  return status === 'validated' || status === 'degraded';
}

function prefixWindowIds(
  output: WorkflowReadOutput,
  windowIndex: number,
  totalWindows: number,
  priorNodeIds: ReadonlySet<string>,
): WorkflowReadOutput {
  if (totalWindows <= 1) return output;
  const prefix = `w${windowIndex + 1}_`;
  const remap = new Map<string, string>();
  for (const node of output.nodes) {
    remap.set(node.nodeId, priorNodeIds.has(node.nodeId) ? node.nodeId : `${prefix}${node.nodeId}`);
  }
  const mapNodeRef = (nodeId: string) => {
    const mapped = remap.get(nodeId);
    if (mapped) return mapped;
    if (priorNodeIds.has(nodeId)) return nodeId;
    return `${prefix}${nodeId}`;
  };
  return {
    ...output,
    nodes: output.nodes.map((node) => ({ ...node, nodeId: mapNodeRef(node.nodeId) })),
    edges: output.edges.map((edge) => ({
      ...edge,
      edgeId: `${prefix}${edge.edgeId}`,
      fromNodeId: mapNodeRef(edge.fromNodeId),
      toNodeId: mapNodeRef(edge.toNodeId),
    })),
    lanes: output.lanes.map((lane) => ({ ...lane, laneId: `${prefix}${lane.laneId}` })),
    paths: output.paths.map((path) => ({
      ...path,
      pathId: `${prefix}${path.pathId}`,
      nodeIdsOrdered: path.nodeIdsOrdered.map(mapNodeRef),
    })),
  };
}

function mergeWorkflowOutputs(outputs: WorkflowReadOutput[]): WorkflowReadOutput {
  if (outputs.length === 1) return outputs[0]!;
  const mapKind = outputs.some((output) => output.mapKind === 'workflow')
    ? 'workflow'
    : 'reference';
  return {
    mapKind,
    summary: outputs.map((output, index) => `Window ${index + 1}: ${output.summary}`).join('\n'),
    nodes: outputs.flatMap((output) => output.nodes),
    edges: outputs.flatMap((output) => output.edges),
    lanes: outputs.flatMap((output) => output.lanes),
    paths: outputs.flatMap((output) => output.paths),
  };
}

function contiguousRuns(
  chunkIds: string[],
  chunkIndexById: ReadonlyMap<string, number>,
): string[][] {
  const sorted = [...chunkIds].sort(
    (a, b) =>
      (chunkIndexById.get(a) ?? Number.MAX_SAFE_INTEGER) -
      (chunkIndexById.get(b) ?? Number.MAX_SAFE_INTEGER),
  );
  const runs: string[][] = [];
  for (const chunkId of sorted) {
    const current = runs.at(-1);
    if (!current) {
      runs.push([chunkId]);
      continue;
    }
    const previousIndex = chunkIndexById.get(current.at(-1)!);
    const nextIndex = chunkIndexById.get(chunkId);
    if (previousIndex !== undefined && nextIndex === previousIndex + 1) current.push(chunkId);
    else runs.push([chunkId]);
  }
  return runs;
}

function validateSegmentation(
  output: SourceSegmentationOutput,
  chunks: ChunkRow[],
): {
  status: 'validated' | 'degraded';
  documentShape: SourceStructureShape;
  summary: string;
  segments: SourceStructureSegment[];
  integrityRepairCount: number;
  validationJson: Record<string, unknown>;
} {
  const chunkIndexById = new Map(chunks.map((chunk) => [chunk.id, chunk.chunkIndex]));
  const covered = new Set<string>();
  const usedSegmentIds = new Set<string>();
  const repairs: Array<Record<string, unknown>> = [];
  let integrityRepairCount = 0;
  const segments: SourceStructureSegment[] = [];

  const uniqueSegmentId = (requested: string) => {
    let candidate = requested;
    let suffix = 2;
    while (usedSegmentIds.has(candidate)) candidate = `${requested}_${suffix++}`;
    usedSegmentIds.add(candidate);
    return candidate;
  };

  for (const proposed of output.segments) {
    const accepted: string[] = [];
    const seenWithinSegment = new Set<string>();
    for (const chunkId of proposed.chunkIds) {
      if (!chunkIndexById.has(chunkId)) {
        repairs.push({ segmentId: proposed.segmentId, chunkId, reason: 'unknown_chunk_id' });
        integrityRepairCount += 1;
        continue;
      }
      if (seenWithinSegment.has(chunkId)) {
        repairs.push({
          segmentId: proposed.segmentId,
          chunkId,
          reason: 'duplicate_chunk_within_segment',
        });
        integrityRepairCount += 1;
        continue;
      }
      seenWithinSegment.add(chunkId);
      covered.add(chunkId);
      accepted.push(chunkId);
    }
    const runs = contiguousRuns(accepted, chunkIndexById);
    if (runs.length > 1) {
      repairs.push({
        segmentId: proposed.segmentId,
        reason: 'non_contiguous_segment_split',
        runCount: runs.length,
      });
    }
    for (let runIndex = 0; runIndex < runs.length; runIndex++) {
      const run = runs[runIndex]!;
      segments.push({
        segmentId: uniqueSegmentId(
          runIndex === 0 ? proposed.segmentId : `${proposed.segmentId}_${runIndex + 1}`,
        ),
        shape: proposed.shape,
        title: runIndex === 0 ? proposed.title : `${proposed.title} (continued)`,
        summary: proposed.summary ?? null,
        chunkIds: run,
      });
    }
    if (accepted.length === 0) {
      repairs.push({ segmentId: proposed.segmentId, reason: 'empty_segment_dropped' });
    }
  }

  const missingIds = chunks.filter((chunk) => !covered.has(chunk.id)).map((chunk) => chunk.id);
  const missingRuns = contiguousRuns(missingIds, chunkIndexById);
  for (let index = 0; index < missingRuns.length; index++) {
    const segmentId = uniqueSegmentId(`unclassified_${index + 1}`);
    segments.push({
      segmentId,
      shape: 'narrative',
      title: 'Unclassified source material',
      summary: 'Chunks omitted by the model and retained as narrative fallback material.',
      chunkIds: missingRuns[index]!,
    });
    repairs.push({ segmentId, reason: 'missing_chunks_recovered', chunkIds: missingRuns[index] });
    integrityRepairCount += 1;
  }

  segments.sort((a, b) => {
    const aIndex = chunkIndexById.get(a.chunkIds[0]!) ?? Number.MAX_SAFE_INTEGER;
    const bIndex = chunkIndexById.get(b.chunkIds[0]!) ?? Number.MAX_SAFE_INTEGER;
    return aIndex - bIndex;
  });

  const shapeCounts = new Map<SourceStructureShape, number>();
  for (const segment of segments) {
    shapeCounts.set(segment.shape, (shapeCounts.get(segment.shape) ?? 0) + segment.chunkIds.length);
  }
  const documentShape = output.documentShape;

  return {
    status: integrityRepairCount === 0 ? 'validated' : 'degraded',
    documentShape,
    summary: output.summary,
    segments,
    integrityRepairCount,
    validationJson: {
      promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      proposedDocumentShape: output.documentShape,
      documentShape,
      segmentChunkAssignmentsByShape: Object.fromEntries(shapeCounts),
      suppliedChunkCount: chunks.length,
      coveredChunkCount: covered.size + missingIds.length,
      segmentChunkAssignmentCount: segments.reduce(
        (sum, segment) => sum + segment.chunkIds.length,
        0,
      ),
      segmentCount: segments.length,
      integrityRepairCount,
      repairs,
    },
  };
}

function nodeSystemsToScalar(systems: string[] | null | undefined): string | null {
  if (!systems || systems.length === 0) return null;
  return (
    systems
      .map((system) => system.trim())
      .filter(Boolean)
      .join('; ') || null
  );
}

function workflowToProcessStructureMap(args: {
  output: WorkflowReadOutput;
  chunks: ChunkRow[];
  title: string;
  segment?: SourceStructureSegment;
  documentShape?: SourceStructureShape;
  prefixIds?: boolean;
}): SourceStructureMap {
  const { output, chunks, title } = args;
  const segment =
    args.segment ??
    ({
      segmentId: 'process',
      shape: 'process',
      title,
      summary: output.summary,
      chunkIds: chunks.map((chunk) => chunk.id),
    } satisfies SourceStructureSegment);
  const prefix = args.prefixIds ? `${segment.segmentId}_` : '';
  const mapElementId = (id: string) => `${prefix}${id}`;
  const elements: SourceStructureElement[] = output.nodes.map((node) => ({
    elementId: mapElementId(node.nodeId),
    segmentId: segment.segmentId,
    shape: 'process',
    elementKind: node.nodeType,
    label: node.label,
    lane: node.lane ?? null,
    ownerName: node.ownerName ?? null,
    systems: nodeSystemsToScalar(node.systems),
    evidenceQuote: node.evidenceQuote,
    chunkId: node.chunkId,
  }));
  const relations: SourceStructureRelation[] = output.edges.map((edge) => ({
    relationId: mapElementId(edge.edgeId),
    segmentId: segment.segmentId,
    fromElementId: mapElementId(edge.fromNodeId),
    toElementId: mapElementId(edge.toNodeId),
    shape: 'process',
    relationKind: edge.edgeType,
    condition: edge.condition ?? null,
    evidenceQuote: edge.evidenceQuote,
    chunkId: edge.chunkId,
  }));

  return {
    documentShape: args.documentShape ?? 'process',
    summary: output.summary,
    segments: [segment],
    elements,
    relations,
    lanes: output.lanes.map((lane) => ({ ...lane, laneId: mapElementId(lane.laneId) })),
    paths: output.paths.map((path) => ({
      ...path,
      pathId: mapElementId(path.pathId),
      nodeIdsOrdered: path.nodeIdsOrdered.map(mapElementId),
    })),
  };
}

async function createPendingMap(args: {
  db: OracleDb;
  documentId: string;
  sourceContentHash: string;
  force: boolean;
}): Promise<{
  mapId: string;
  skippedExisting: boolean;
  existingStatus?: ReusableWorkflowMapStatus;
}> {
  const { db, documentId, sourceContentHash, force } = args;
  if (!force) {
    const [existing] = await db
      .select({ id: sourceWorkflowMaps.id, status: sourceWorkflowMaps.status })
      .from(sourceWorkflowMaps)
      .where(
        and(
          eq(sourceWorkflowMaps.sourceType, 'document'),
          eq(sourceWorkflowMaps.documentId, documentId),
          eq(sourceWorkflowMaps.sourceContentHash, sourceContentHash),
          sql`${sourceWorkflowMaps.status} IN ('validated', 'degraded')`,
        ),
      )
      .orderBy(desc(sourceWorkflowMaps.createdAt))
      .limit(1);
    if (existing) {
      if (!isReusableWorkflowMapStatus(existing.status)) {
        throw new Error(`[source-workflow-read] unexpected reusable map status ${existing.status}`);
      }
      return {
        mapId: existing.id,
        skippedExisting: true,
        existingStatus: existing.status,
      };
    }
  }

  return db.transaction(async (tx) => {
    const oldRows = await tx
      .select({ id: sourceWorkflowMaps.id })
      .from(sourceWorkflowMaps)
      .where(
        and(
          eq(sourceWorkflowMaps.sourceType, 'document'),
          eq(sourceWorkflowMaps.documentId, documentId),
          ne(sourceWorkflowMaps.status, 'superseded'),
        ),
      );
    const oldIds = oldRows.map((row) => row.id);
    if (oldIds.length > 0) {
      await tx
        .update(sourceWorkflowMaps)
        .set({ status: 'superseded', updatedAt: new Date() })
        .where(inArray(sourceWorkflowMaps.id, oldIds));
    }

    const [inserted] = await tx
      .insert(sourceWorkflowMaps)
      .values({
        sourceType: 'document',
        documentId,
        sourceContentHash,
        status: 'pending',
        documentShape: 'process',
        mapKind: 'workflow',
        validationJson: {
          pipelineVersion: SOURCE_READER_PIPELINE_VERSION,
          segmentationPromptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
          workflowPromptVersion: WORKFLOW_READ_PROMPT_VERSION,
          status: 'pending',
        },
      })
      .returning({ id: sourceWorkflowMaps.id });
    if (!inserted)
      throw new Error('[source-workflow-read] failed to insert pending source_workflow_maps row');

    if (oldIds.length > 0) {
      await tx
        .update(sourceWorkflowMaps)
        .set({ supersededByMapId: inserted.id, updatedAt: new Date() })
        .where(inArray(sourceWorkflowMaps.id, oldIds));
    }

    return { mapId: inserted.id, skippedExisting: false };
  });
}

async function runSegmentationModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  chunks: ChunkRow[];
  mapId: string;
  repairFeedback?: string;
  budget: SourceReaderBudget;
}): Promise<{ output: SourceSegmentationOutput; modelRunId: string; contextPackId: string }> {
  const { db, client, doc, chunks, mapId, repairFeedback, budget } = args;
  const resolved = await resolveRouteCandidates(db, 'workflow_read');
  for (const skipped of resolved.skipped) {
    console.warn('[source-workflow-read] skipped segmentation route candidate', skipped);
  }
  const routeCandidates = resolved.candidates;
  const route = routeCandidates[0]!.route;
  const chunkIds = chunks.map((chunk) => chunk.id);
  const blocks = [
    makeBlock({
      id: 'source-segmentation-system',
      label: 'Source segmentation system prompt',
      kind: 'stable_system',
      content: SOURCE_SEGMENTATION_SYSTEM_PROMPT,
      reasonIncluded: `source segmentation prompt ${SOURCE_SEGMENTATION_PROMPT_VERSION}`,
    }),
    makeBlock({
      id: 'document-metadata',
      label: 'Document metadata',
      kind: 'semi_stable_domain_context',
      content: [
        `Document name: ${doc.fileName}`,
        `File type: ${doc.fileType}`,
        doc.context ? `Uploader context:\n${doc.context}` : null,
        `Source structure map row: ${mapId}`,
      ]
        .filter(Boolean)
        .join('\n\n'),
      reasonIncluded: 'document-level context for source segmentation',
    }),
    makeBlock({
      id: 'document-chunks',
      label: 'Document chunks',
      kind: 'retrieved_context',
      content: buildDocumentCorpus(chunks),
      reasonIncluded: 'complete ordered source; every chunk must be assigned exactly once',
    }),
    makeBlock({
      id: 'source-segmentation-request',
      label: 'Source segmentation request',
      kind: 'dynamic_input',
      content:
        'Segment these chunks into the fewest coherent shape-focused passages. Cover every supplied chunk at least once and preserve source order. A genuinely composite chunk may appear in multiple differently shaped segments.' +
        (repairFeedback
          ? `\n\nREPAIR REQUIRED: The prior output failed deterministic validation. Return a complete corrected segmentation, copying chunk IDs exactly from this valid list:\n${chunks.map((chunk) => chunk.id).join('\n')}\n\nValidator feedback:\n${repairFeedback}`
          : ''),
      reasonIncluded: repairFeedback
        ? 'bounded deterministic segmentation repair request'
        : 'current source-segmentation request',
    }),
  ];
  budget.reserveRead({
    estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
    label: repairFeedback ? 'source segmentation repair' : 'source segmentation',
  });
  const plan = client.compile({
    taskType: 'source_segmentation',
    routeId: route.routeId,
    promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
    blocks,
    observability: { includedDocumentChunkIds: chunkIds },
  });
  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack)
    throw new Error('[source-workflow-read] failed to insert segmentation context pack');

  const started = Date.now();
  const result = await client
    .runObject<SourceSegmentationOutput>({
      taskType: 'source_segmentation',
      routeId: route.routeId,
      promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      blocks,
      schema: SourceSegmentationSchema,
      observability: { includedDocumentChunkIds: chunkIds },
      providerOptions: { maxOutputTokens: 12_000 },
      routeCandidates,
    })
    .catch(async (err) => {
      await logAllCandidatesFailedAttempts({
        db,
        error: err,
        taskType: 'source-segmentation',
        slot: 'workflow_read',
        contextPackId: contextPack.id,
      }).catch((logErr) =>
        console.error(
          '[source-workflow-read] failed to record segmentation model attempts',
          logErr,
        ),
      );
      throw err;
    });

  const actualRouteId = result.routeId ?? route.routeId;
  const actualProvider = result.provider ?? route.provider;
  const actualModelId = result.modelId ?? route.modelId;
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'source-segmentation',
      model: actualModelId,
      provider: actualProvider,
      promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[source-workflow-read] failed to insert segmentation model run');

  await db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
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
    taskType: 'source-segmentation',
    slot: 'workflow_read',
    contextPackId: contextPack.id,
    modelRunId: modelRun.id,
  });
  await db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));

  if (!result.validation.ok) {
    throw new Error(
      '[source-workflow-read] segmentation output failed Zod schema validation: ' +
        result.validation.error.message,
    );
  }
  return { output: result.object, modelRunId: modelRun.id, contextPackId: contextPack.id };
}

async function runWorkflowReadModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  chunks: ChunkRow[];
  referentPack: string;
  triggerRunId: string;
  mapId: string;
  force: boolean;
  segment?: SourceStructureSegment;
  budget: SourceReaderBudget;
}): Promise<{ output: WorkflowReadOutput; modelRunIds: string[]; contextPackIds: string[] }> {
  const { db, client, doc, chunks, referentPack, mapId, segment, budget } = args;
  const maxEstimatedTokens = await readNumberSetting(
    db,
    'workflow_read_max_estimated_input_tokens',
    150_000,
  );
  const windows =
    estimateTokens(buildDocumentCorpus(chunks)) > maxEstimatedTokens
      ? chunkWindows(chunks, maxEstimatedTokens)
      : [chunks];
  const resolved = await resolveRouteCandidates(db, 'workflow_read');
  for (const skipped of resolved.skipped) {
    console.warn('[source-workflow-read] skipped workflow_read route candidate', skipped);
  }
  const routeCandidates = resolved.candidates;
  const route = routeCandidates[0]!.route;
  const outputs: WorkflowReadOutput[] = [];
  const modelRunIds: string[] = [];
  const contextPackIds: string[] = [];
  const carriedRegistry: string[] = [];
  const priorNodeIds = new Set<string>();

  for (let windowIndex = 0; windowIndex < windows.length; windowIndex++) {
    const windowChunks = windows[windowIndex]!;
    const chunkIds = windowChunks.map((chunk) => chunk.id);
    const blocks = [
      makeBlock({
        id: 'workflow-read-system',
        label: 'Workflow read system prompt',
        kind: 'stable_system',
        content: WORKFLOW_READ_SYSTEM_PROMPT,
        reasonIncluded: `workflow read prompt v${WORKFLOW_READ_PROMPT_VERSION}`,
      }),
      makeBlock({
        id: 'document-metadata',
        label: 'Document metadata',
        kind: 'semi_stable_domain_context',
        content: [
          `Document name: ${doc.fileName}`,
          `File type: ${doc.fileType}`,
          doc.context ? `Uploader context:\n${doc.context}` : null,
          `Source workflow map row: ${mapId}`,
          segment
            ? `Process segment: ${segment.segmentId} | ${segment.title}${segment.summary ? ` | ${segment.summary}` : ''}`
            : null,
        ]
          .filter(Boolean)
          .join('\n\n'),
        reasonIncluded: 'document-level context for source workflow read',
      }),
      makeBlock({
        id: 'referent-pack',
        label: 'Referent pack',
        kind: 'semi_stable_domain_context',
        content: referentPack,
        reasonIncluded: 'known names and acronyms only; existing process graphs withheld by design',
      }),
      ...(carriedRegistry.length > 0
        ? [
            makeBlock({
              id: 'carried-node-registry',
              label: 'Prior window node labels',
              kind: 'semi_stable_domain_context' as const,
              content: carriedRegistry.join('\n'),
              reasonIncluded: 'large-source windowing continuity without truncation',
            }),
          ]
        : []),
      makeBlock({
        id: 'document-chunks',
        label: 'Document chunks',
        kind: 'retrieved_context',
        content: buildDocumentCorpus(windowChunks),
        reasonIncluded: `window ${windowIndex + 1}/${windows.length}; map elements must cite these chunk IDs`,
      }),
      makeBlock({
        id: 'workflow-read-request',
        label: 'Workflow read request',
        kind: 'dynamic_input',
        content:
          'Read these process-segment chunks in order and produce the source workflow map. Capture only topology visible in this source, not what you expect from prior knowledge. Every node and edge must cite a verbatim quote from one chunk.',
        reasonIncluded: 'current workflow-read request',
      }),
    ];
    budget.reserveRead({
      estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
      label: `workflow read ${segment?.segmentId ?? 'full-source'} window ${windowIndex + 1}/${windows.length}`,
    });

    const plan = client.compile({
      taskType: 'source_workflow_read',
      routeId: route.routeId,
      promptVersion: WORKFLOW_READ_PROMPT_VERSION,
      blocks,
      observability: { includedDocumentChunkIds: chunkIds },
    });
    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values(buildContextPackInsert(plan))
      .returning({ id: oracleContextPacks.id });
    if (!contextPack)
      throw new Error('[source-workflow-read] failed to insert oracle_context_packs row');
    contextPackIds.push(contextPack.id);

    const started = Date.now();
    const result = await client
      .runObject<WorkflowReadOutput>({
        taskType: 'source_workflow_read',
        routeId: route.routeId,
        promptVersion: WORKFLOW_READ_PROMPT_VERSION,
        blocks,
        schema: WorkflowReadSchema,
        observability: { includedDocumentChunkIds: chunkIds },
        providerOptions: { maxOutputTokens: 32_000 },
        routeCandidates,
      })
      .catch(async (err) => {
        await logAllCandidatesFailedAttempts({
          db,
          error: err,
          taskType: 'source-workflow-read',
          slot: 'workflow_read',
          contextPackId: contextPack.id,
        }).catch((logErr) =>
          console.error('[source-workflow-read] failed to record failed model attempts', logErr),
        );
        throw err;
      });

    const actualRouteId = result.routeId ?? route.routeId;
    const actualProvider = result.provider ?? route.provider;
    const actualModelId = result.modelId ?? route.modelId;
    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'source-workflow-read',
        model: actualModelId,
        provider: actualProvider,
        promptVersion: WORKFLOW_READ_PROMPT_VERSION,
        inputHash: plan.metadata.stablePrefixHash,
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs: Date.now() - started,
        success: result.validation.ok,
        error: result.validation.ok ? null : result.validation.error.message,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('[source-workflow-read] failed to insert model_runs row');
    modelRunIds.push(modelRun.id);

    await db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
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
      taskType: 'source-workflow-read',
      slot: 'workflow_read',
      contextPackId: contextPack.id,
      modelRunId: modelRun.id,
    });
    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));

    if (!result.validation.ok) {
      throw new Error(
        '[source-workflow-read] model output failed Zod schema validation: ' +
          result.validation.error.message,
      );
    }
    const output = prefixWindowIds(result.object, windowIndex, windows.length, priorNodeIds);
    outputs.push(output);
    for (const node of output.nodes) priorNodeIds.add(node.nodeId);
    carriedRegistry.push(...output.nodes.map((node) => `- ${node.nodeId}: ${node.label}`));
  }

  return { output: mergeWorkflowOutputs(outputs), modelRunIds, contextPackIds };
}

async function runResponsibilityReadModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  chunks: ChunkRow[];
  triggerRunId: string;
  mapId: string;
  segment: SourceStructureSegment;
  budget: SourceReaderBudget;
}): Promise<{ output: ResponsibilityReadOutput; modelRunId: string; contextPackId: string }> {
  const resolved = await resolveRouteCandidates(args.db, 'workflow_read');
  for (const skipped of resolved.skipped) {
    console.warn('[source-workflow-read] skipped responsibility route candidate', skipped);
  }
  const route = resolved.candidates[0]!.route;
  const blocks = [
    makeBlock({
      id: 'responsibility-read-system',
      label: 'Responsibility read system prompt',
      kind: 'stable_system',
      content: RESPONSIBILITY_READ_SYSTEM_PROMPT,
      reasonIncluded: RESPONSIBILITY_READ_PROMPT_VERSION,
    }),
    makeBlock({
      id: 'responsibility-metadata',
      label: 'Responsibility segment metadata',
      kind: 'semi_stable_domain_context',
      content: [
        `Document: ${args.doc.fileName}`,
        `Segment: ${args.segment.segmentId} | ${args.segment.title}`,
        args.segment.summary ? `Non-quotable segment summary: ${args.segment.summary}` : null,
        args.doc.context ? `Uploader context: ${args.doc.context}` : null,
        `Source map row: ${args.mapId}`,
      ]
        .filter(Boolean)
        .join('\n'),
      reasonIncluded: 'responsibility segment routing and audit context',
    }),
    makeBlock({
      id: 'responsibility-chunks',
      label: 'Document chunks',
      kind: 'retrieved_context',
      content: buildDocumentCorpus(args.chunks),
      reasonIncluded: 'only valid evidence source for this responsibility segment',
    }),
    makeBlock({
      id: 'responsibility-request',
      label: 'Responsibility read request',
      kind: 'dynamic_input',
      content:
        'Extract every distinct responsibility record. Keep the result flat and copy each quote exactly from one chunk.',
      reasonIncluded: 'current responsibilities pass-2 request',
    }),
  ];
  args.budget.reserveRead({
    estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
    label: `responsibility read ${args.segment.segmentId}`,
  });
  const plan = args.client.compile({
    taskType: 'source_workflow_read',
    routeId: route.routeId,
    promptVersion: RESPONSIBILITY_READ_PROMPT_VERSION,
    blocks,
    observability: { includedDocumentChunkIds: args.chunks.map((chunk) => chunk.id) },
  });
  const [contextPack] = await args.db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[source-workflow-read] failed responsibility context pack');
  const started = Date.now();
  const result = await args.client.runObject<ResponsibilityReadOutput>({
    taskType: 'source_workflow_read',
    routeId: route.routeId,
    promptVersion: RESPONSIBILITY_READ_PROMPT_VERSION,
    blocks,
    schema: ResponsibilityReadSchema,
    observability: { includedDocumentChunkIds: args.chunks.map((chunk) => chunk.id) },
    providerOptions: { maxOutputTokens: 32_000 },
    routeCandidates: resolved.candidates,
  });
  const [modelRun] = await args.db
    .insert(modelRuns)
    .values({
      taskType: 'source-responsibility-read',
      model: result.modelId ?? route.modelId,
      provider: result.provider ?? route.provider,
      promptVersion: RESPONSIBILITY_READ_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[source-workflow-read] failed responsibility model run');
  await args.db.insert(modelRunUsageDetails).values({
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
    db: args.db,
    metadata: result,
    taskType: 'source-responsibility-read',
    slot: 'workflow_read',
    contextPackId: contextPack.id,
    modelRunId: modelRun.id,
  });
  await args.db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));
  if (!result.validation.ok) {
    throw new Error(
      `[source-workflow-read] responsibility schema failed: ${result.validation.error.message}`,
    );
  }
  return { output: result.object, modelRunId: modelRun.id, contextPackId: contextPack.id };
}

async function runWorkflowQuoteRepairModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  mapId: string;
  chunks: ChunkRow[];
  failures: readonly WorkflowMapRejectionDiagnostic[];
  budget: SourceReaderBudget;
}): Promise<{ output: WorkflowQuoteRepairOutput; modelRunId: string; contextPackId: string }> {
  const resolved = await resolveRouteCandidates(args.db, 'workflow_read');
  const route = resolved.candidates[0]!.route;
  const neededChunkIds = new Set(args.failures.map((failure) => failure.citedChunkId!));
  const repairChunks = args.chunks.filter((chunk) => neededChunkIds.has(chunk.id));
  const blocks = [
    makeBlock({
      id: 'workflow-quote-repair-system',
      label: 'Workflow quote-copy repair system prompt',
      kind: 'stable_system',
      content: WORKFLOW_QUOTE_REPAIR_SYSTEM_PROMPT,
      reasonIncluded: `bounded quote-copy repair ${WORKFLOW_READ_PROMPT_VERSION}`,
    }),
    makeBlock({
      id: 'workflow-quote-repair-document',
      label: 'Document metadata and source chunks',
      kind: 'retrieved_context',
      content: `Document: ${args.doc.fileName}\nMap: ${args.mapId}\n\n${buildDocumentCorpus(repairChunks)}`,
      reasonIncluded: 'exact source text for failed quotes only',
    }),
    makeBlock({
      id: 'workflow-quote-repair-request',
      label: 'Failed quote-copy records',
      kind: 'dynamic_input',
      content: JSON.stringify(
        args.failures.map((failure) => ({
          elementId: failure.elementId,
          elementType: failure.elementType,
          chunkId: failure.citedChunkId,
          rejectedEvidenceQuote: failure.failingQuoteExcerpt,
          failureClass: failure.failureClass,
        })),
      ),
      reasonIncluded: 'repair only eligible root quote-copy failures',
    }),
  ];
  args.budget.reserveRead({
    estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
    label: 'workflow quote-copy repair',
  });
  const plan = args.client.compile({
    taskType: 'source_workflow_read',
    routeId: route.routeId,
    promptVersion: WORKFLOW_READ_PROMPT_VERSION,
    blocks,
    observability: { includedDocumentChunkIds: [...neededChunkIds] },
  });
  const [contextPack] = await args.db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[source-workflow-read] failed to insert repair context pack');
  const started = Date.now();
  const result = await args.client
    .runObject<WorkflowQuoteRepairOutput>({
      taskType: 'source_workflow_read',
      routeId: route.routeId,
      promptVersion: WORKFLOW_READ_PROMPT_VERSION,
      blocks,
      schema: WorkflowQuoteRepairSchema,
      observability: { includedDocumentChunkIds: [...neededChunkIds] },
      providerOptions: { maxOutputTokens: 8_000 },
      routeCandidates: resolved.candidates,
    })
    .catch(async (error) => {
      await logAllCandidatesFailedAttempts({
        db: args.db,
        error,
        taskType: 'source-workflow-read',
        slot: 'workflow_read',
        contextPackId: contextPack.id,
      }).catch((logError) =>
        console.error('[source-workflow-read] failed to log quote repair attempts', logError),
      );
      throw error;
    });
  const [modelRun] = await args.db
    .insert(modelRuns)
    .values({
      taskType: 'source-workflow-read-quote-repair',
      model: result.modelId ?? route.modelId,
      provider: result.provider ?? route.provider,
      promptVersion: WORKFLOW_READ_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[source-workflow-read] failed to insert repair model run');
  await args.db.insert(modelRunUsageDetails).values({
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
    db: args.db,
    metadata: result,
    taskType: 'source-workflow-read',
    slot: 'workflow_read',
    contextPackId: contextPack.id,
    modelRunId: modelRun.id,
  });
  await args.db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));
  if (!result.validation.ok) {
    throw new Error(
      `[source-workflow-read] quote repair failed schema validation: ${result.validation.error.message}`,
    );
  }
  return { output: result.object, modelRunId: modelRun.id, contextPackId: contextPack.id };
}

export function renderWorkflowMapGuidance(mapId: string, map: SourceStructureMap): string {
  const lines = [
    'SOURCE STRUCTURE MAP (GUIDANCE ONLY - NEVER QUOTE THIS BLOCK)',
    `Map ID: ${mapId}`,
    `Document shape: ${map.documentShape}`,
    `Summary: ${map.summary}`,
  ];
  if (map.segments.length > 0) {
    lines.push('', 'Segments:');
    for (const segment of map.segments) {
      lines.push(
        `- ${segment.segmentId} [${segment.shape}] ${segment.title}${segment.summary ? ` | ${segment.summary}` : ''}`,
      );
    }
  }
  if (map.lanes.length > 0) {
    lines.push('', 'Lanes:');
    for (const lane of map.lanes)
      lines.push(
        `- ${lane.laneId}: ${lane.label}${lane.ownerName ? ` (owner: ${lane.ownerName})` : ''}`,
      );
  }
  if (map.elements.length > 0) {
    lines.push('', 'Elements:');
    for (const element of map.elements) {
      const ref = `${mapId}:element:${element.elementId}`;
      lines.push(
        `- ${ref} [${element.elementKind}] ${element.label}${element.lane ? ` | lane=${element.lane}` : ''}${element.ownerName ? ` | owner=${element.ownerName}` : ''}${element.systems ? ` | systems=${element.systems}` : ''}`,
      );
    }
  }
  if (map.relations.length > 0) {
    lines.push('', 'Relations:');
    for (const relation of map.relations) {
      const ref = `${mapId}:relation:${relation.relationId}`;
      lines.push(
        `- ${ref} [${relation.relationKind}] ${relation.fromElementId} -> ${relation.toElementId}${relation.condition ? ` | condition=${relation.condition}` : ''}`,
      );
    }
  }
  if (map.paths.length > 0) {
    lines.push('', 'Paths:');
    for (const path of map.paths)
      lines.push(
        `- ${path.pathId} [${path.pathType}] ${path.name}: ${path.nodeIdsOrdered.join(' -> ')}`,
      );
  }
  lines.push(
    '',
    'Shape-directed extraction:',
    ...[...new Set(map.segments.map((segment) => segment.shape))].map(
      (shape) => `- ${shape}: ${SOURCE_STRUCTURE_SHAPE_REGISTRY[shape].extractionDirective}`,
    ),
    '',
    'Extraction instruction: when a claim supports a listed element or relation, set mapElementRef to the exact ref shown above. Claims still require a verbatim exactQuote from a Document Chunk ID.',
  );
  return lines.join('\n');
}

export type ActiveWorkflowMapRef = {
  ref: string;
  kind: 'element' | 'relation';
  localId: string;
  segmentId: string;
  shape: SourceStructureShape;
  chunkId: string;
};

export type ActiveWorkflowMapContext = {
  mapId: string;
  map: SourceStructureMap;
  guidance: string;
  refs: ReadonlyMap<string, ActiveWorkflowMapRef>;
};

export type MapElementRefMembershipResult =
  | { ok: true; target: ActiveWorkflowMapRef }
  | {
      ok: false;
      failureClass: 'no_active_map' | 'wrong_map' | 'unknown_map_ref' | 'outside_extraction_window';
      detail: string;
    };

export function buildActiveWorkflowMapRefIndex(
  mapId: string,
  map: SourceStructureMap,
): Map<string, ActiveWorkflowMapRef> {
  const refs = new Map<string, ActiveWorkflowMapRef>();
  for (const element of map.elements) {
    const ref = `${mapId}:element:${element.elementId}`;
    refs.set(ref, {
      ref,
      kind: 'element',
      localId: element.elementId,
      segmentId: element.segmentId,
      shape: element.shape,
      chunkId: element.chunkId,
    });
  }
  for (const relation of map.relations) {
    const ref = `${mapId}:relation:${relation.relationId}`;
    refs.set(ref, {
      ref,
      kind: 'relation',
      localId: relation.relationId,
      segmentId: relation.segmentId,
      shape: relation.shape,
      chunkId: relation.chunkId,
    });
  }
  return refs;
}

async function loadSourceReaderBudgetLimits(db: OracleDb): Promise<SourceReaderBudgetLimits> {
  const [
    maxReadCalls,
    maxInputTokens,
    maxEstimatedCostUsd,
    estimatedInputCostPerMillionTokensUsd,
    maxRepairAttempts,
    maxConcurrency,
  ] = await Promise.all([
    readNumberSetting(db, 'source_reader_max_read_calls_per_source', 40),
    readNumberSetting(db, 'source_reader_max_input_tokens_per_source', 500_000),
    readNumberSetting(db, 'source_reader_max_estimated_cost_usd_per_source', 10),
    readNumberSetting(db, 'source_reader_estimated_input_cost_per_million_tokens_usd', 5),
    readNumberSetting(db, 'source_reader_max_repair_attempts_per_source', 1),
    readNumberSetting(db, 'source_reader_max_concurrency_per_source', 4),
  ]);
  return {
    maxReadCalls: Math.trunc(maxReadCalls),
    maxInputTokens: Math.trunc(maxInputTokens),
    maxEstimatedCostUsd,
    estimatedInputCostPerMillionTokensUsd,
    maxRepairAttempts: Math.trunc(maxRepairAttempts),
    maxConcurrency: Math.trunc(maxConcurrency),
  };
}

export function validateMapElementRefMembership(args: {
  mapElementRef: string;
  activeMap: ActiveWorkflowMapContext | null;
  eligibleChunkIds: ReadonlySet<string>;
}): MapElementRefMembershipResult {
  if (!args.activeMap) {
    return {
      ok: false,
      failureClass: 'no_active_map',
      detail: 'Candidate supplied mapElementRef but no active validated/degraded map exists.',
    };
  }
  if (!args.mapElementRef.startsWith(`${args.activeMap.mapId}:`)) {
    return {
      ok: false,
      failureClass: 'wrong_map',
      detail: `mapElementRef does not belong to active map ${args.activeMap.mapId}.`,
    };
  }
  const target = args.activeMap.refs.get(args.mapElementRef);
  if (!target) {
    return {
      ok: false,
      failureClass: 'unknown_map_ref',
      detail: `mapElementRef is well-formed but is not a member of active map ${args.activeMap.mapId}.`,
    };
  }
  if (!args.eligibleChunkIds.has(target.chunkId)) {
    return {
      ok: false,
      failureClass: 'outside_extraction_window',
      detail: `mapElementRef cites chunk ${target.chunkId}, which is outside the active extraction window.`,
    };
  }
  return { ok: true, target };
}

export async function loadLatestWorkflowMapContext(
  db: OracleDb,
  documentId: string,
): Promise<ActiveWorkflowMapContext | null> {
  const [row] = await db
    .select({
      id: sourceWorkflowMaps.id,
      status: sourceWorkflowMaps.status,
      summary: sourceWorkflowMaps.summary,
      documentShape: sourceWorkflowMaps.documentShape,
      segmentsJson: sourceWorkflowMaps.segmentsJson,
      elementsJson: sourceWorkflowMaps.elementsJson,
      relationsJson: sourceWorkflowMaps.relationsJson,
      nodesJson: sourceWorkflowMaps.nodesJson,
      edgesJson: sourceWorkflowMaps.edgesJson,
      lanesJson: sourceWorkflowMaps.lanesJson,
      pathsJson: sourceWorkflowMaps.pathsJson,
    })
    .from(sourceWorkflowMaps)
    .where(
      and(
        eq(sourceWorkflowMaps.sourceType, 'document'),
        eq(sourceWorkflowMaps.documentId, documentId),
        sql`${sourceWorkflowMaps.status} IN ('validated', 'degraded')`,
      ),
    )
    .orderBy(desc(sourceWorkflowMaps.createdAt))
    .limit(1);
  if (!row) return null;
  const elements = row.elementsJson as SourceStructureElement[];
  const relations = row.relationsJson as SourceStructureRelation[];
  const segments = row.segmentsJson as SourceStructureMap['segments'];
  const map =
    segments.length > 0
      ? ({
          documentShape: row.documentShape as SourceStructureShape,
          summary: row.summary ?? 'No summary.',
          segments,
          elements,
          relations,
          lanes: row.lanesJson as WorkflowReadLane[],
          paths: row.pathsJson as WorkflowReadPath[],
        } satisfies SourceStructureMap)
      : workflowToProcessStructureMap({
          output: {
            summary: row.summary ?? 'No summary.',
            mapKind: 'workflow',
            nodes: row.nodesJson as WorkflowReadNode[],
            edges: row.edgesJson as WorkflowReadEdge[],
            lanes: row.lanesJson as WorkflowReadLane[],
            paths: row.pathsJson as WorkflowReadPath[],
          },
          chunks: [
            {
              id: '00000000-0000-4000-8000-000000000000',
              chunkIndex: 0,
              pageNumber: null,
              rawText: '',
              contentHash: null,
            },
          ],
          title: 'Full process',
        });
  return {
    mapId: row.id,
    map,
    guidance: renderWorkflowMapGuidance(row.id, map),
    refs: buildActiveWorkflowMapRefIndex(row.id, map),
  };
}

export async function loadLatestWorkflowMapGuidance(
  db: OracleDb,
  documentId: string,
): Promise<string | null> {
  return (await loadLatestWorkflowMapContext(db, documentId))?.guidance ?? null;
}

async function buildWorkflowValidationChunkContexts(args: {
  db: OracleDb;
  documentId: string;
  output: WorkflowReadOutput;
  documentChunks: ChunkRow[];
  coveredChunkIds: ReadonlySet<string>;
}): Promise<Map<string, WorkflowMapChunkContext>> {
  const contexts = new Map<string, WorkflowMapChunkContext>(
    args.documentChunks.map((chunk) => [
      chunk.id,
      {
        documentId: args.documentId,
        text: chunk.rawText,
        coveredBySegmentation: args.coveredChunkIds.has(chunk.id),
      },
    ]),
  );
  const citedIds = new Set([
    ...args.output.nodes.map((node) => node.chunkId),
    ...args.output.edges.map((edge) => edge.chunkId),
  ]);
  const unresolvedIds = [...citedIds].filter((chunkId) => !contexts.has(chunkId));
  if (unresolvedIds.length === 0) return contexts;

  const referencedRows = await args.db
    .select({
      id: documentChunks.id,
      documentId: documentChunks.documentId,
      rawText: documentChunks.rawText,
    })
    .from(documentChunks)
    .where(inArray(documentChunks.id, unresolvedIds));
  for (const row of referencedRows) {
    contexts.set(row.id, {
      documentId: row.documentId,
      text: row.rawText,
      coveredBySegmentation: false,
    });
  }
  return contexts;
}

export async function generateSourceWorkflowMap(args: {
  documentId: string;
  triggerRunId: string;
  force?: boolean;
  db?: OracleDb;
  client?: OracleAIClient;
}): Promise<SourceWorkflowReadResult> {
  const db = args.db ?? getDirectDb();
  const client = args.client ?? new OracleAIClient({ adapters: buildStandardAdapters() });
  const force = args.force ?? false;

  const [doc] = await db
    .select({
      id: documents.id,
      fileName: documents.fileName,
      fileType: documents.fileType,
      context: documents.context,
    })
    .from(documents)
    .where(eq(documents.id, args.documentId))
    .limit(1);
  if (!doc) return { documentId: args.documentId, status: 'skipped_not_found' };

  const chunks = await db
    .select({
      id: documentChunks.id,
      chunkIndex: documentChunks.chunkIndex,
      pageNumber: documentChunks.pageNumber,
      rawText: documentChunks.rawText,
      contentHash: documentChunks.contentHash,
    })
    .from(documentChunks)
    .where(eq(documentChunks.documentId, args.documentId))
    .orderBy(documentChunks.chunkIndex);
  if (chunks.length === 0) return { documentId: args.documentId, status: 'skipped_no_chunks' };

  await markMacroPending(db, args.documentId);
  const sourceContentHash = sourceHashForDocument(args.documentId, chunks);
  const pending = await createPendingMap({
    db,
    documentId: args.documentId,
    sourceContentHash,
    force,
  });
  if (pending.skippedExisting) {
    if (pending.existingStatus === 'degraded') await markMacroDegraded(db, args.documentId);
    else await markMacroComplete(db, args.documentId);
    return {
      documentId: args.documentId,
      status: 'skipped_existing',
      mapId: pending.mapId,
      existingMapStatus: pending.existingStatus,
    };
  }

  const [jobRun] = await db
    .insert(jobRuns)
    .values({
      triggerRunId: args.triggerRunId,
      jobType: 'source-workflow-read',
      status: 'running',
      startedAt: new Date(),
      inputJson: { documentId: args.documentId, force, mapId: pending.mapId },
    })
    .returning({ id: jobRuns.id });
  if (!jobRun) throw new Error('[source-workflow-read] failed to insert job_runs row');

  let readerBudget: SourceReaderBudget | null = null;
  try {
    readerBudget = new SourceReaderBudget(await loadSourceReaderBudgetLimits(db));
    const referentPack = await buildReferentPack(db);
    const firstSegmentationModel = await runSegmentationModel({
      db,
      client,
      doc,
      chunks,
      mapId: pending.mapId,
      budget: readerBudget,
    });
    const segmentationModels = [firstSegmentationModel];
    const segmentationValidations = [validateSegmentation(firstSegmentationModel.output, chunks)];
    let segmentation = segmentationValidations[0]!;
    while (
      segmentation.integrityRepairCount > 0 &&
      segmentationModels.length - 1 < readerBudget.limits.maxRepairAttempts
    ) {
      readerBudget.reserveRepair('source segmentation integrity repair');
      const retryModel = await runSegmentationModel({
        db,
        client,
        doc,
        chunks,
        mapId: pending.mapId,
        repairFeedback: JSON.stringify(segmentation.validationJson),
        budget: readerBudget,
      });
      const retryValidation = validateSegmentation(retryModel.output, chunks);
      segmentationModels.push(retryModel);
      segmentationValidations.push(retryValidation);
      if (retryValidation.integrityRepairCount >= segmentation.integrityRepairCount) break;
      segmentation = retryValidation;
    }
    const chunkById = new Map(chunks.map((chunk) => [chunk.id, chunk]));
    const coveredChunkIds = new Set(segmentation.segments.flatMap((segment) => segment.chunkIds));
    const quoteSourceKind = quoteSourceKindForDocument(doc);
    const maxDroppedRatio = await readNumberSetting(db, 'workflow_map_max_dropped_ratio', 0.2);
    const processSegments = segmentation.segments.filter((segment) => segment.shape === 'process');
    const responsibilitySegments = segmentation.segments.filter(
      (segment) => segment.shape === 'responsibilities',
    );
    const processReads = await mapWithConcurrency<
      SourceStructureSegment,
      {
        segment: SourceStructureSegment;
        validation: ReturnType<typeof validateWorkflowMap>;
        output: WorkflowReadOutput;
        segmentChunks: ChunkRow[];
        validationChunks: Map<string, WorkflowMapChunkContext>;
        eligibleFailures: WorkflowMapRejectionDiagnostic[];
        modelRunIds: string[];
        contextPackIds: string[];
        repair: WorkflowQuoteRepairMetadata;
      }
    >({
      inputs: processSegments,
      concurrency: readerBudget.limits.maxConcurrency,
      run: async (segment) => {
        const segmentChunks = segment.chunkIds
          .map((chunkId) => chunkById.get(chunkId))
          .filter((chunk): chunk is ChunkRow => Boolean(chunk));
        const modelResult = await runWorkflowReadModel({
          db,
          client,
          doc,
          chunks: segmentChunks,
          referentPack,
          triggerRunId: args.triggerRunId,
          mapId: pending.mapId,
          force,
          segment,
          budget: readerBudget!,
        });
        const validationChunks = await buildWorkflowValidationChunkContexts({
          db,
          documentId: args.documentId,
          output: modelResult.output,
          documentChunks: chunks,
          coveredChunkIds,
        });
        const originalValidation = validateWorkflowMap({
          output: modelResult.output,
          activeDocumentId: args.documentId,
          activeSegmentChunkIds: new Set(segment.chunkIds),
          chunksById: validationChunks,
          sourceKind: quoteSourceKind,
          maxDroppedRatio,
        });
        const eligibleFailures = eligibleWorkflowQuoteRepairs(originalValidation);
        const repair: WorkflowQuoteRepairMetadata = {
          repairAttempts: 0,
          repairSkipped:
            eligibleFailures.length === 0
              ? 'no_eligible_root_quote_failure'
              : 'not_selected_lower_impact',
          rootDroppedBefore: originalValidation.rootDroppedCount,
          cascadeDroppedBefore: originalValidation.cascadeDroppedCount,
          rootDroppedAfter: originalValidation.rootDroppedCount,
          cascadeDroppedAfter: originalValidation.cascadeDroppedCount,
        };
        return {
          segment,
          validation: originalValidation,
          output: modelResult.output,
          segmentChunks,
          validationChunks,
          eligibleFailures,
          modelRunIds: modelResult.modelRunIds,
          contextPackIds: modelResult.contextPackIds,
          repair,
        };
      },
    });

    const repairCandidateIndex = selectWorkflowQuoteRepairCandidate(
      processReads.map((read) => read.validation),
    );
    if (repairCandidateIndex !== null) {
      const read = processReads[repairCandidateIndex]!;
      read.repair.repairSkipped = null;
      try {
        readerBudget.reserveRepair('workflow quote-copy repair');
        read.repair.repairAttempts = 1;
        const repairResult = await runWorkflowQuoteRepairModel({
          db,
          client,
          doc,
          mapId: pending.mapId,
          chunks,
          failures: read.eligibleFailures,
          budget: readerBudget,
        });
        read.modelRunIds.push(repairResult.modelRunId);
        read.contextPackIds.push(repairResult.contextPackId);
        const patched = patchWorkflowQuoteRepairs({
          original: read.output,
          requested: read.eligibleFailures,
          response: repairResult.output,
        });
        if (!patched.ok) {
          read.repair.repairSkipped = patched.reason;
        } else {
          const repairedValidation = validateWorkflowMap({
            output: patched.output,
            activeDocumentId: args.documentId,
            activeSegmentChunkIds: new Set(read.segment.chunkIds),
            chunksById: read.validationChunks,
            sourceKind: quoteSourceKind,
            maxDroppedRatio,
          });
          read.repair.rootDroppedAfter = repairedValidation.rootDroppedCount;
          read.repair.cascadeDroppedAfter = repairedValidation.cascadeDroppedCount;
          const selectedValidation = chooseWorkflowQuoteRepair(
            read.validation,
            repairedValidation,
          );
          if (selectedValidation === read.validation) {
            read.repair.repairSkipped = 'no_root_improvement';
          } else {
            read.validation = selectedValidation;
          }
        }
      } catch (error) {
        if (
          error instanceof SourceReaderBudgetExceededError &&
          (error.check === 'max_repair_attempts' ||
            error.check === 'max_read_calls' ||
            error.check === 'max_input_tokens' ||
            error.check === 'max_estimated_cost_usd')
        ) {
          read.repair.repairSkipped = 'budget_exhausted';
        } else {
          read.repair.repairSkipped = 'repair_call_failed';
          console.error('[source-workflow-read] optional quote-copy repair failed', error);
        }
      }
    }

    const responsibilityReads = await mapWithConcurrency({
      inputs: responsibilitySegments,
      concurrency: readerBudget.limits.maxConcurrency,
      run: async (segment) => {
        const segmentChunkIds = new Set(segment.chunkIds);
        const segmentChunks = chunks.filter((chunk) => segmentChunkIds.has(chunk.id));
        const model = await runResponsibilityReadModel({
          db,
          client,
          doc,
          chunks: segmentChunks,
          triggerRunId: args.triggerRunId,
          mapId: pending.mapId,
          segment,
          budget: readerBudget!,
        });
        const validation = validateResponsibilityRead({
          output: model.output,
          documentId: args.documentId,
          segment,
          fileType: doc.fileType,
          fileName: doc.fileName,
          allCoveredChunkIds: new Set(segmentation.segments.flatMap((item) => item.chunkIds)),
          chunks: chunks.map((chunk) => ({
            id: chunk.id,
            documentId: args.documentId,
            rawText: chunk.rawText,
          })),
        });
        return { segment, model, validation };
      },
    });

    const finalizedProcessReads = processReads.map((read) => ({
      ...read,
      map: workflowToProcessStructureMap({
        output: read.validation.map,
        chunks: read.segmentChunks,
        title: read.segment.title,
        segment: read.segment,
        documentShape: segmentation.documentShape,
        prefixIds: processSegments.length > 1,
      }),
    }));

    const structureMap: SourceStructureMap = {
      documentShape: segmentation.documentShape,
      summary: segmentation.summary,
      segments: segmentation.segments,
      elements: [
        ...finalizedProcessReads.flatMap((read) => read.map.elements),
        ...responsibilityReads.flatMap((read) => read.validation.elements),
      ],
      relations: finalizedProcessReads.flatMap((read) => read.map.relations),
      lanes: finalizedProcessReads.flatMap((read) => read.map.lanes),
      paths: finalizedProcessReads.flatMap((read) => read.map.paths),
    };
    const workflowOutputs = processReads.map((read) => read.validation.map);
    const droppedCount =
      processReads.reduce((sum, read) => sum + read.validation.droppedCount, 0) +
      responsibilityReads.reduce((sum, read) => sum + read.validation.diagnostics.length, 0);
    const keptCount =
      processReads.reduce((sum, read) => sum + read.validation.keptCount, 0) +
      responsibilityReads.reduce((sum, read) => sum + read.validation.elements.length, 0);
    const status: WorkflowMapStatus =
      segmentation.status === 'degraded' ||
      processReads.some((read) => read.validation.status === 'degraded') ||
      responsibilityReads.some(
        (read) =>
          read.validation.diagnostics.length > 0 ||
          read.validation.crossSegmentCitations.length /
            Math.max(1, read.validation.elements.length) >
            0.2,
      )
        ? 'degraded'
        : 'validated';
    const mapKind: WorkflowReadOutput['mapKind'] = processReads.some(
      (read) => read.validation.map.mapKind === 'workflow',
    )
      ? 'workflow'
      : 'reference';
    const modelRunIds = [
      ...segmentationModels.map((model) => model.modelRunId),
      ...processReads.flatMap((read) => read.modelRunIds),
      ...responsibilityReads.map((read) => read.model.modelRunId),
    ];
    const contextPackIds = [
      ...segmentationModels.map((model) => model.contextPackId),
      ...processReads.flatMap((read) => read.contextPackIds),
      ...responsibilityReads.map((read) => read.model.contextPackId),
    ];
    const lastModelRunId = modelRunIds.at(-1) ?? null;
    const lastContextPackId = contextPackIds.at(-1) ?? null;
    const validationJson = {
      pipelineVersion: SOURCE_READER_PIPELINE_VERSION,
      segmentation: segmentation.validationJson,
      segmentationAttempts: segmentationValidations.map((validation) => validation.validationJson),
      processSegments: processReads.map((read) => ({
        segmentId: read.segment.segmentId,
        promptVersion: WORKFLOW_READ_PROMPT_VERSION,
        ...read.validation.validationJson,
        quoteRepair: read.repair,
      })),
      responsibilitySegments: responsibilityReads.map((read) => ({
        segmentId: read.segment.segmentId,
        promptVersion: RESPONSIBILITY_READ_PROMPT_VERSION,
        keptCount: read.validation.elements.length,
        droppedCount: read.validation.diagnostics.length,
        primaryCount: read.validation.primaryCount,
        crossSegmentCitations: read.validation.crossSegmentCitations,
        rawOutputAudit: responsibilityRawAuditArtifact(read.model.output),
        diagnostics: read.validation.diagnostics,
      })),
      droppedCount,
      keptCount,
      readerBudget: readerBudget.snapshot(),
    };

    await db
      .update(sourceWorkflowMaps)
      .set({
        status,
        documentShape: structureMap.documentShape,
        mapKind,
        summary: structureMap.summary,
        segmentsJson: structureMap.segments,
        elementsJson: structureMap.elements,
        relationsJson: structureMap.relations,
        nodesJson: workflowOutputs.flatMap((output) => output.nodes),
        edgesJson: workflowOutputs.flatMap((output) => output.edges),
        lanesJson: workflowOutputs.flatMap((output) => output.lanes),
        pathsJson: workflowOutputs.flatMap((output) => output.paths),
        validationJson,
        modelRunId: lastModelRunId,
        contextPackId: lastContextPackId,
        updatedAt: new Date(),
        finalizedAt: new Date(),
      })
      .where(eq(sourceWorkflowMaps.id, pending.mapId));

    await db
      .update(jobRuns)
      .set({
        status: 'complete',
        finishedAt: new Date(),
        outputJson: {
          documentId: args.documentId,
          mapId: pending.mapId,
          status,
          mapKind,
          documentShape: structureMap.documentShape,
          droppedCount,
          keptCount,
          elementCount: structureMap.elements.length,
          relationCount: structureMap.relations.length,
          segmentCount: structureMap.segments.length,
          segmentShapeCounts: Object.fromEntries(
            structureMap.segments.map((segment) => [
              segment.shape,
              structureMap.segments.filter((candidate) => candidate.shape === segment.shape).length,
            ]),
          ),
          modelRunIds,
          readerBudget: readerBudget.snapshot(),
        },
      })
      .where(eq(jobRuns.id, jobRun.id));

    if (status === 'degraded') await markMacroDegraded(db, args.documentId);
    else await markMacroComplete(db, args.documentId);

    return {
      documentId: args.documentId,
      status,
      mapId: pending.mapId,
      mapKind,
      documentShape: structureMap.documentShape,
      droppedCount,
      keptCount,
      segmentCount: structureMap.segments.length,
      elementCount: structureMap.elements.length,
      relationCount: structureMap.relations.length,
      laneCount: structureMap.lanes.length,
      pathCount: structureMap.paths.length,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await db
      .update(sourceWorkflowMaps)
      .set({
        status: 'failed',
        validationJson: {
          pipelineVersion: SOURCE_READER_PIPELINE_VERSION,
          segmentationPromptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
          workflowPromptVersion: WORKFLOW_READ_PROMPT_VERSION,
          readerBudget: readerBudget?.snapshot() ?? null,
          error: message,
        },
        updatedAt: new Date(),
        finalizedAt: new Date(),
      })
      .where(eq(sourceWorkflowMaps.id, pending.mapId));
    await db
      .update(jobRuns)
      .set({
        status: 'failed',
        finishedAt: new Date(),
        error: message,
        outputJson: { readerBudget: readerBudget?.snapshot() ?? null },
      })
      .where(eq(jobRuns.id, jobRun.id));
    await markMacroMapFailed(db, args.documentId);
    throw err;
  }
}

export const __sourceWorkflowReadTestHooks = {
  validateSegmentation,
  validateWorkflowMap,
  isReusableWorkflowMapStatus,
  prefixWindowIds,
  workflowToProcessStructureMap,
};
