import { and, desc, eq, inArray, ne, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import {
  OracleAIClient,
  SOURCE_READER_PIPELINE_VERSION,
  SOURCE_SEGMENTATION_PROMPT_VERSION,
  SOURCE_SEGMENTATION_SYSTEM_PROMPT,
  WORKFLOW_READ_PROMPT_VERSION,
  WORKFLOW_READ_SYSTEM_PROMPT,
  SourceSegmentationSchema,
  WorkflowReadSchema,
  buildStandardAdapters,
  estimateTokens,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type OraclePromptPlan,
  type SourceSegmentationOutput,
  type SourceStructureSegment,
  type SourceStructureShape,
  type WorkflowReadEdge,
  type WorkflowReadLane,
  type WorkflowReadNode,
  type WorkflowReadOutput,
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
import { validateQuote } from '@oracle/engines';
import {
  markMacroComplete,
  markMacroDegraded,
  markMacroMapFailed,
  markMacroPending,
} from './macro-health';

type ChunkRow = {
  id: string;
  chunkIndex: number;
  pageNumber: number | null;
  rawText: string;
  contentHash: string | null;
};

type WorkflowMapStatus = 'validated' | 'degraded' | 'failed';
type ReusableWorkflowMapStatus = 'validated' | 'degraded';

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

function validateWorkflowMap(
  output: WorkflowReadOutput,
  chunkTextById: Map<string, string>,
  maxDroppedRatio: number,
): {
  status: WorkflowMapStatus;
  map: WorkflowReadOutput;
  validationJson: Record<string, unknown>;
  droppedCount: number;
  keptCount: number;
} {
  const dropped: Array<{ elementType: string; elementId: string; reason: string }> = [];
  const nodeIds = new Set<string>();
  const lanes = output.lanes.filter((lane) => {
    const ok = Boolean(lane.laneId && lane.label);
    if (!ok)
      dropped.push({
        elementType: 'lane',
        elementId: lane.laneId ?? 'unknown',
        reason: 'missing lane id or label',
      });
    return ok;
  });

  const nodes: WorkflowReadNode[] = [];
  for (const node of output.nodes) {
    const chunkText = chunkTextById.get(node.chunkId);
    const quote = chunkText
      ? validateQuote({ sourceText: chunkText, exactQuoteProvided: node.evidenceQuote })
      : null;
    if (!chunkText) {
      dropped.push({
        elementType: 'node',
        elementId: node.nodeId,
        reason: `unknown chunkId ${node.chunkId}`,
      });
      continue;
    }
    if (quote?.verdict !== 'exact_match' && quote?.verdict !== 'normalized_match') {
      dropped.push({
        elementType: 'node',
        elementId: node.nodeId,
        reason: quote?.detail ?? 'quote did not validate',
      });
      continue;
    }
    if (nodeIds.has(node.nodeId)) {
      dropped.push({ elementType: 'node', elementId: node.nodeId, reason: 'duplicate nodeId' });
      continue;
    }
    nodeIds.add(node.nodeId);
    nodes.push(node);
  }

  const edges: WorkflowReadEdge[] = [];
  for (const edge of output.edges) {
    const chunkText = chunkTextById.get(edge.chunkId);
    const quote = chunkText
      ? validateQuote({ sourceText: chunkText, exactQuoteProvided: edge.evidenceQuote })
      : null;
    if (!nodeIds.has(edge.fromNodeId) || !nodeIds.has(edge.toNodeId)) {
      dropped.push({
        elementType: 'edge',
        elementId: edge.edgeId,
        reason: 'edge endpoint does not exist after node validation',
      });
      continue;
    }
    if (!chunkText) {
      dropped.push({
        elementType: 'edge',
        elementId: edge.edgeId,
        reason: `unknown chunkId ${edge.chunkId}`,
      });
      continue;
    }
    if (quote?.verdict !== 'exact_match' && quote?.verdict !== 'normalized_match') {
      dropped.push({
        elementType: 'edge',
        elementId: edge.edgeId,
        reason: quote?.detail ?? 'quote did not validate',
      });
      continue;
    }
    edges.push(edge);
  }

  const laneLabels = new Set(lanes.map((lane) => lane.label.toLowerCase()));
  const orphanLaneRefs = nodes
    .filter((node) => node.lane && !laneLabels.has(node.lane.toLowerCase()))
    .map((node) => ({ nodeId: node.nodeId, lane: node.lane }));

  const paths: WorkflowReadPath[] = [];
  for (const path of output.paths) {
    const missing = path.nodeIdsOrdered.filter((id) => !nodeIds.has(id));
    if (missing.length > 0) {
      dropped.push({
        elementType: 'path',
        elementId: path.pathId,
        reason: `missing node IDs: ${missing.join(', ')}`,
      });
      continue;
    }
    paths.push(path);
  }

  const keptCount = nodes.length + edges.length + lanes.length + paths.length;
  const droppedCount = dropped.length;
  const ratio = keptCount + droppedCount === 0 ? 0 : droppedCount / (keptCount + droppedCount);
  const status: WorkflowMapStatus =
    droppedCount > 0 && ratio > maxDroppedRatio ? 'degraded' : 'validated';
  return {
    status,
    map: { ...output, nodes, edges, lanes, paths },
    validationJson: {
      promptVersion: WORKFLOW_READ_PROMPT_VERSION,
      dropped,
      droppedCount,
      keptCount,
      droppedRatio: ratio,
      maxDroppedRatio,
      orphanLaneRefs,
    },
    droppedCount,
    keptCount,
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
}): Promise<{ output: SourceSegmentationOutput; modelRunId: string; contextPackId: string }> {
  const { db, client, doc, chunks, mapId, repairFeedback } = args;
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
}): Promise<{ output: WorkflowReadOutput; modelRunIds: string[]; contextPackIds: string[] }> {
  const { db, client, doc, chunks, referentPack, mapId, segment } = args;
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
    'Extraction instruction: when a claim supports a listed element or relation, set mapElementRef to the exact ref shown above. Claims still require a verbatim exactQuote from a Document Chunk ID.',
  );
  return lines.join('\n');
}

export async function loadLatestWorkflowMapGuidance(
  db: OracleDb,
  documentId: string,
): Promise<string | null> {
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
  return renderWorkflowMapGuidance(row.id, map);
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

  try {
    const referentPack = await buildReferentPack(db);
    const firstSegmentationModel = await runSegmentationModel({
      db,
      client,
      doc,
      chunks,
      mapId: pending.mapId,
    });
    const segmentationModels = [firstSegmentationModel];
    const segmentationValidations = [validateSegmentation(firstSegmentationModel.output, chunks)];
    let segmentation = segmentationValidations[0]!;
    if (segmentation.integrityRepairCount > 0) {
      const retryModel = await runSegmentationModel({
        db,
        client,
        doc,
        chunks,
        mapId: pending.mapId,
        repairFeedback: JSON.stringify(segmentation.validationJson),
      });
      const retryValidation = validateSegmentation(retryModel.output, chunks);
      segmentationModels.push(retryModel);
      segmentationValidations.push(retryValidation);
      if (retryValidation.integrityRepairCount <= segmentation.integrityRepairCount) {
        segmentation = retryValidation;
      }
    }
    const chunkById = new Map(chunks.map((chunk) => [chunk.id, chunk]));
    const maxDroppedRatio = await readNumberSetting(db, 'workflow_map_max_dropped_ratio', 0.2);
    const processSegments = segmentation.segments.filter((segment) => segment.shape === 'process');
    const processReads: Array<{
      segment: SourceStructureSegment;
      validation: ReturnType<typeof validateWorkflowMap>;
      map: SourceStructureMap;
      modelRunIds: string[];
      contextPackIds: string[];
    }> = [];

    for (const segment of processSegments) {
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
      });
      const validation = validateWorkflowMap(
        modelResult.output,
        new Map(segmentChunks.map((chunk) => [chunk.id, chunk.rawText])),
        maxDroppedRatio,
      );
      processReads.push({
        segment,
        validation,
        map: workflowToProcessStructureMap({
          output: validation.map,
          chunks: segmentChunks,
          title: segment.title,
          segment,
          documentShape: segmentation.documentShape,
          prefixIds: processSegments.length > 1,
        }),
        modelRunIds: modelResult.modelRunIds,
        contextPackIds: modelResult.contextPackIds,
      });
    }

    const structureMap: SourceStructureMap = {
      documentShape: segmentation.documentShape,
      summary: segmentation.summary,
      segments: segmentation.segments,
      elements: processReads.flatMap((read) => read.map.elements),
      relations: processReads.flatMap((read) => read.map.relations),
      lanes: processReads.flatMap((read) => read.map.lanes),
      paths: processReads.flatMap((read) => read.map.paths),
    };
    const workflowOutputs = processReads.map((read) => read.validation.map);
    const droppedCount = processReads.reduce((sum, read) => sum + read.validation.droppedCount, 0);
    const keptCount = processReads.reduce((sum, read) => sum + read.validation.keptCount, 0);
    const status: WorkflowMapStatus =
      segmentation.status === 'degraded' ||
      processReads.some((read) => read.validation.status === 'degraded')
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
    ];
    const contextPackIds = [
      ...segmentationModels.map((model) => model.contextPackId),
      ...processReads.flatMap((read) => read.contextPackIds),
    ];
    const lastModelRunId = modelRunIds.at(-1) ?? null;
    const lastContextPackId = contextPackIds.at(-1) ?? null;
    const validationJson = {
      pipelineVersion: SOURCE_READER_PIPELINE_VERSION,
      segmentation: segmentation.validationJson,
      segmentationAttempts: segmentationValidations.map((validation) => validation.validationJson),
      processSegments: processReads.map((read) => ({
        segmentId: read.segment.segmentId,
        ...read.validation.validationJson,
      })),
      droppedCount,
      keptCount,
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
          error: message,
        },
        updatedAt: new Date(),
        finalizedAt: new Date(),
      })
      .where(eq(sourceWorkflowMaps.id, pending.mapId));
    await db
      .update(jobRuns)
      .set({ status: 'failed', finishedAt: new Date(), error: message })
      .where(eq(jobRuns.id, jobRun.id));
    await markMacroMapFailed(db, args.documentId);
    throw err;
  }
}

export const __sourceWorkflowReadTestHooks = {
  validateSegmentation,
  isReusableWorkflowMapStatus,
  prefixWindowIds,
  workflowToProcessStructureMap,
};
