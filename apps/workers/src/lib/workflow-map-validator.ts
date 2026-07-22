import { createHash } from 'node:crypto';
import type {
  WorkflowReadEdge,
  WorkflowReadLane,
  WorkflowReadNode,
  WorkflowReadOutput,
  WorkflowReadPath,
} from '@oracle/ai';
import {
  alternateSourceQuotePolicies,
  quoteValidationOptionsForSource,
  resolveSourceQuotePolicy,
  validateQuote,
  type QuoteSourceKind,
  type SourceQuotePolicyName,
  type ValidationMethod,
} from '@oracle/engines';

export type WorkflowMapStatus = 'validated' | 'degraded' | 'failed';

export type CrossSegmentCitationStatus =
  | 'in_segment'
  | 'covered_same_document'
  | 'uncovered_document'
  | 'foreign_document'
  | 'unknown_chunk';

export type WorkflowMapFailureClass =
  | 'missing_required_field'
  | 'duplicate_id'
  | 'unknown_chunk_id'
  | 'foreign_document_citation'
  | 'uncovered_document_citation'
  | 'quote_ambiguous'
  | 'quote_mismatch'
  | 'missing_endpoint_cascade'
  | 'missing_path_node_cascade';

export type WorkflowMapRejectionDiagnostic = {
  shape: 'process';
  elementType: 'lane' | 'node' | 'edge' | 'path';
  elementId: string;
  citedChunkId: string | null;
  failingQuoteExcerpt: string | null;
  failureClass: WorkflowMapFailureClass;
  checkName: string;
  detail: string;
  policySelected: SourceQuotePolicyName;
  validationMethod: ValidationMethod | 'not_run';
  passesAlternatePolicies: SourceQuotePolicyName[];
  failureOrigin: 'root' | 'cascade';
  cascadeFromElementIds: string[];
  crossSegmentStatus: CrossSegmentCitationStatus;
};

export type WorkflowMapChunkContext = {
  documentId: string;
  text: string;
  coveredBySegmentation: boolean;
};

export type ValidateWorkflowMapInput = {
  output: WorkflowReadOutput;
  activeDocumentId: string;
  activeSegmentChunkIds: ReadonlySet<string>;
  chunksById: ReadonlyMap<string, WorkflowMapChunkContext>;
  sourceKind: QuoteSourceKind;
  maxDroppedRatio: number;
  crossSegmentAlertRatio?: number;
  maxDiagnostics?: number;
  maxAuditChars?: number;
};

export type WorkflowMapValidationResult = {
  status: WorkflowMapStatus;
  map: WorkflowReadOutput;
  validationJson: Record<string, unknown>;
  diagnostics: WorkflowMapRejectionDiagnostic[];
  droppedCount: number;
  rootDroppedCount: number;
  cascadeDroppedCount: number;
  keptCount: number;
  crossSegmentCitationCount: number;
  importantRelationCoverage: number;
};

const DEFAULT_MAX_DIAGNOSTICS = 500;
const DEFAULT_MAX_AUDIT_CHARS = 64_000;
const DEFAULT_QUOTE_EXCERPT_CHARS = 240;
const DEFAULT_DETAIL_CHARS = 500;

function bounded(value: string, max: number): string {
  return value.length <= max ? value : `${value.slice(0, max)}…`;
}

function auditArtifact(output: WorkflowReadOutput, maxChars: number) {
  const serialized = JSON.stringify(output);
  return {
    sha256: createHash('sha256').update(serialized, 'utf8').digest('hex'),
    serializedChars: serialized.length,
    truncated: serialized.length > maxChars,
    boundedJson: serialized.slice(0, maxChars),
    counts: {
      nodes: output.nodes.length,
      edges: output.edges.length,
      lanes: output.lanes.length,
      paths: output.paths.length,
    },
  };
}

function citationStatus(args: {
  chunkId: string;
  activeDocumentId: string;
  activeSegmentChunkIds: ReadonlySet<string>;
  chunksById: ReadonlyMap<string, WorkflowMapChunkContext>;
}): CrossSegmentCitationStatus {
  const chunk = args.chunksById.get(args.chunkId);
  if (!chunk) return 'unknown_chunk';
  if (chunk.documentId !== args.activeDocumentId) return 'foreign_document';
  if (!chunk.coveredBySegmentation) return 'uncovered_document';
  if (!args.activeSegmentChunkIds.has(args.chunkId)) return 'covered_same_document';
  return 'in_segment';
}

function failureClassForQuote(verdict: string): WorkflowMapFailureClass {
  return verdict === 'ambiguous' ? 'quote_ambiguous' : 'quote_mismatch';
}

function validateEvidence(args: {
  chunkId: string;
  evidenceQuote: string;
  input: ValidateWorkflowMapInput;
}):
  | {
      ok: true;
      crossSegmentStatus: CrossSegmentCitationStatus;
      validationMethod: ValidationMethod;
      policySelected: SourceQuotePolicyName;
    }
  | {
      ok: false;
      failureClass: WorkflowMapFailureClass;
      checkName: string;
      detail: string;
      crossSegmentStatus: CrossSegmentCitationStatus;
      validationMethod: ValidationMethod | 'not_run';
      policySelected: SourceQuotePolicyName;
      passesAlternatePolicies: SourceQuotePolicyName[];
    } {
  const selected = resolveSourceQuotePolicy(args.input.sourceKind);
  const crossSegmentStatus = citationStatus({
    chunkId: args.chunkId,
    activeDocumentId: args.input.activeDocumentId,
    activeSegmentChunkIds: args.input.activeSegmentChunkIds,
    chunksById: args.input.chunksById,
  });
  if (crossSegmentStatus === 'unknown_chunk') {
    return {
      ok: false,
      failureClass: 'unknown_chunk_id',
      checkName: 'source_chunk_exists',
      detail: `Chunk ${args.chunkId} does not exist in the supplied source context.`,
      crossSegmentStatus,
      validationMethod: 'not_run',
      policySelected: selected.name,
      passesAlternatePolicies: [],
    };
  }
  if (crossSegmentStatus === 'foreign_document') {
    return {
      ok: false,
      failureClass: 'foreign_document_citation',
      checkName: 'source_document_membership',
      detail: `Chunk ${args.chunkId} belongs to another document.`,
      crossSegmentStatus,
      validationMethod: 'not_run',
      policySelected: selected.name,
      passesAlternatePolicies: [],
    };
  }
  if (crossSegmentStatus === 'uncovered_document') {
    return {
      ok: false,
      failureClass: 'uncovered_document_citation',
      checkName: 'segmentation_coverage',
      detail: `Chunk ${args.chunkId} belongs to this document but is not covered by segmentation.`,
      crossSegmentStatus,
      validationMethod: 'not_run',
      policySelected: selected.name,
      passesAlternatePolicies: [],
    };
  }

  const chunk = args.input.chunksById.get(args.chunkId)!;
  const result = validateQuote({
    sourceText: chunk.text,
    exactQuoteProvided: args.evidenceQuote,
    ...quoteValidationOptionsForSource(args.input.sourceKind),
  });
  if (result.verdict === 'exact_match' || result.verdict === 'normalized_match') {
    return {
      ok: true,
      crossSegmentStatus,
      validationMethod: result.validationMethod,
      policySelected: selected.name,
    };
  }

  const passesAlternatePolicies = alternateSourceQuotePolicies(selected.name)
    .filter((alternate) => {
      const alternateResult = validateQuote({
        sourceText: chunk.text,
        exactQuoteProvided: args.evidenceQuote,
        normalizationPolicy: alternate.normalizationPolicy,
        allowFuzzy: alternate.allowFuzzy,
        fuzzyMinOverlap: alternate.fuzzyMinOverlap,
      });
      return (
        alternateResult.verdict === 'exact_match' || alternateResult.verdict === 'normalized_match'
      );
    })
    .map((alternate) => alternate.name);
  return {
    ok: false,
    failureClass: failureClassForQuote(result.verdict),
    checkName: result.failedCheckName ?? 'quote_exact_match',
    detail: result.detail,
    crossSegmentStatus,
    validationMethod: result.validationMethod,
    policySelected: selected.name,
    passesAlternatePolicies,
  };
}

/** DB-free deterministic validation for one process-segment reader output. */
export function validateWorkflowMap(input: ValidateWorkflowMapInput): WorkflowMapValidationResult {
  const diagnostics: WorkflowMapRejectionDiagnostic[] = [];
  const selectedPolicy = resolveSourceQuotePolicy(input.sourceKind);
  const maxDiagnostics = input.maxDiagnostics ?? DEFAULT_MAX_DIAGNOSTICS;
  let totalDiagnosticCount = 0;
  let rootDroppedCount = 0;
  let cascadeDroppedCount = 0;
  let crossSegmentCitationCount = 0;
  let validatedCitationCount = 0;

  const addDiagnostic = (
    diagnostic: Omit<WorkflowMapRejectionDiagnostic, 'shape' | 'detail' | 'failingQuoteExcerpt'> & {
      detail: string;
      failingQuoteExcerpt?: string | null;
    },
  ) => {
    totalDiagnosticCount += 1;
    if (diagnostic.failureOrigin === 'root') rootDroppedCount += 1;
    else cascadeDroppedCount += 1;
    if (diagnostics.length >= maxDiagnostics) return;
    diagnostics.push({
      shape: 'process',
      ...diagnostic,
      detail: bounded(diagnostic.detail, DEFAULT_DETAIL_CHARS),
      failingQuoteExcerpt: diagnostic.failingQuoteExcerpt
        ? bounded(diagnostic.failingQuoteExcerpt, DEFAULT_QUOTE_EXCERPT_CHARS)
        : null,
    });
  };

  const laneIds = new Set<string>();
  const lanes: WorkflowReadLane[] = [];
  for (const lane of input.output.lanes) {
    if (!lane.laneId || !lane.label) {
      addDiagnostic({
        elementType: 'lane',
        elementId: lane.laneId || 'unknown',
        citedChunkId: null,
        failureClass: 'missing_required_field',
        checkName: 'lane_required_fields',
        detail: 'Lane is missing an id or label.',
        policySelected: selectedPolicy.name,
        validationMethod: 'not_run',
        passesAlternatePolicies: [],
        failureOrigin: 'root',
        cascadeFromElementIds: [],
        crossSegmentStatus: 'unknown_chunk',
      });
      continue;
    }
    if (laneIds.has(lane.laneId)) {
      addDiagnostic({
        elementType: 'lane',
        elementId: lane.laneId,
        citedChunkId: null,
        failureClass: 'duplicate_id',
        checkName: 'lane_id_unique',
        detail: `Duplicate laneId ${lane.laneId}.`,
        policySelected: selectedPolicy.name,
        validationMethod: 'not_run',
        passesAlternatePolicies: [],
        failureOrigin: 'root',
        cascadeFromElementIds: [],
        crossSegmentStatus: 'unknown_chunk',
      });
      continue;
    }
    laneIds.add(lane.laneId);
    lanes.push(lane);
  }

  const seenNodeIds = new Set<string>();
  const validNodeIds = new Set<string>();
  const nodes: WorkflowReadNode[] = [];
  for (const node of input.output.nodes) {
    if (seenNodeIds.has(node.nodeId)) {
      addDiagnostic({
        elementType: 'node',
        elementId: node.nodeId,
        citedChunkId: node.chunkId,
        failingQuoteExcerpt: node.evidenceQuote,
        failureClass: 'duplicate_id',
        checkName: 'node_id_unique',
        detail: `Duplicate nodeId ${node.nodeId}.`,
        policySelected: selectedPolicy.name,
        validationMethod: 'not_run',
        passesAlternatePolicies: [],
        failureOrigin: 'root',
        cascadeFromElementIds: [],
        crossSegmentStatus: citationStatus({
          chunkId: node.chunkId,
          activeDocumentId: input.activeDocumentId,
          activeSegmentChunkIds: input.activeSegmentChunkIds,
          chunksById: input.chunksById,
        }),
      });
      continue;
    }
    seenNodeIds.add(node.nodeId);
    const evidence = validateEvidence({
      chunkId: node.chunkId,
      evidenceQuote: node.evidenceQuote,
      input,
    });
    if (!evidence.ok) {
      addDiagnostic({
        elementType: 'node',
        elementId: node.nodeId,
        citedChunkId: node.chunkId,
        failingQuoteExcerpt: node.evidenceQuote,
        failureClass: evidence.failureClass,
        checkName: evidence.checkName,
        detail: evidence.detail,
        policySelected: evidence.policySelected,
        validationMethod: evidence.validationMethod,
        passesAlternatePolicies: evidence.passesAlternatePolicies,
        failureOrigin: 'root',
        cascadeFromElementIds: [],
        crossSegmentStatus: evidence.crossSegmentStatus,
      });
      continue;
    }
    validatedCitationCount += 1;
    if (evidence.crossSegmentStatus === 'covered_same_document') crossSegmentCitationCount += 1;
    validNodeIds.add(node.nodeId);
    nodes.push(node);
  }

  const seenEdgeIds = new Set<string>();
  const edges: WorkflowReadEdge[] = [];
  for (const edge of input.output.edges) {
    if (seenEdgeIds.has(edge.edgeId)) {
      addDiagnostic({
        elementType: 'edge',
        elementId: edge.edgeId,
        citedChunkId: edge.chunkId,
        failingQuoteExcerpt: edge.evidenceQuote,
        failureClass: 'duplicate_id',
        checkName: 'edge_id_unique',
        detail: `Duplicate edgeId ${edge.edgeId}.`,
        policySelected: selectedPolicy.name,
        validationMethod: 'not_run',
        passesAlternatePolicies: [],
        failureOrigin: 'root',
        cascadeFromElementIds: [],
        crossSegmentStatus: citationStatus({
          chunkId: edge.chunkId,
          activeDocumentId: input.activeDocumentId,
          activeSegmentChunkIds: input.activeSegmentChunkIds,
          chunksById: input.chunksById,
        }),
      });
      continue;
    }
    seenEdgeIds.add(edge.edgeId);
    const missingEndpoints = [edge.fromNodeId, edge.toNodeId].filter(
      (nodeId) => !validNodeIds.has(nodeId),
    );
    if (missingEndpoints.length > 0) {
      addDiagnostic({
        elementType: 'edge',
        elementId: edge.edgeId,
        citedChunkId: edge.chunkId,
        failingQuoteExcerpt: edge.evidenceQuote,
        failureClass: 'missing_endpoint_cascade',
        checkName: 'relation_endpoints_survive_validation',
        detail: `Relation endpoints did not survive node validation: ${missingEndpoints.join(', ')}.`,
        policySelected: selectedPolicy.name,
        validationMethod: 'not_run',
        passesAlternatePolicies: [],
        failureOrigin: 'cascade',
        cascadeFromElementIds: missingEndpoints,
        crossSegmentStatus: citationStatus({
          chunkId: edge.chunkId,
          activeDocumentId: input.activeDocumentId,
          activeSegmentChunkIds: input.activeSegmentChunkIds,
          chunksById: input.chunksById,
        }),
      });
      continue;
    }
    const evidence = validateEvidence({
      chunkId: edge.chunkId,
      evidenceQuote: edge.evidenceQuote,
      input,
    });
    if (!evidence.ok) {
      addDiagnostic({
        elementType: 'edge',
        elementId: edge.edgeId,
        citedChunkId: edge.chunkId,
        failingQuoteExcerpt: edge.evidenceQuote,
        failureClass: evidence.failureClass,
        checkName: evidence.checkName,
        detail: evidence.detail,
        policySelected: evidence.policySelected,
        validationMethod: evidence.validationMethod,
        passesAlternatePolicies: evidence.passesAlternatePolicies,
        failureOrigin: 'root',
        cascadeFromElementIds: [],
        crossSegmentStatus: evidence.crossSegmentStatus,
      });
      continue;
    }
    validatedCitationCount += 1;
    if (evidence.crossSegmentStatus === 'covered_same_document') crossSegmentCitationCount += 1;
    edges.push(edge);
  }

  const seenPathIds = new Set<string>();
  const paths: WorkflowReadPath[] = [];
  for (const path of input.output.paths) {
    if (seenPathIds.has(path.pathId)) {
      addDiagnostic({
        elementType: 'path',
        elementId: path.pathId,
        citedChunkId: null,
        failureClass: 'duplicate_id',
        checkName: 'path_id_unique',
        detail: `Duplicate pathId ${path.pathId}.`,
        policySelected: selectedPolicy.name,
        validationMethod: 'not_run',
        passesAlternatePolicies: [],
        failureOrigin: 'root',
        cascadeFromElementIds: [],
        crossSegmentStatus: 'unknown_chunk',
      });
      continue;
    }
    seenPathIds.add(path.pathId);
    const missing = path.nodeIdsOrdered.filter((nodeId) => !validNodeIds.has(nodeId));
    if (missing.length > 0) {
      addDiagnostic({
        elementType: 'path',
        elementId: path.pathId,
        citedChunkId: null,
        failureClass: 'missing_path_node_cascade',
        checkName: 'path_nodes_survive_validation',
        detail: `Path nodes did not survive validation: ${missing.join(', ')}.`,
        policySelected: selectedPolicy.name,
        validationMethod: 'not_run',
        passesAlternatePolicies: [],
        failureOrigin: 'cascade',
        cascadeFromElementIds: missing,
        crossSegmentStatus: 'unknown_chunk',
      });
      continue;
    }
    paths.push(path);
  }

  const laneLabels = new Set(lanes.map((lane) => lane.label.toLowerCase()));
  const orphanLaneRefs = nodes
    .filter((node) => node.lane && !laneLabels.has(node.lane.toLowerCase()))
    .map((node) => ({ nodeId: node.nodeId, lane: node.lane }));
  const keptCount = nodes.length + edges.length + lanes.length + paths.length;
  const droppedCount = totalDiagnosticCount;
  const droppedRatio =
    keptCount + droppedCount === 0 ? 0 : droppedCount / (keptCount + droppedCount);
  const crossSegmentRatio =
    validatedCitationCount === 0 ? 0 : crossSegmentCitationCount / validatedCitationCount;
  const crossSegmentAlertRatio = input.crossSegmentAlertRatio ?? 0.2;
  const importantRelationCoverage =
    input.output.edges.length === 0 ? 1 : edges.length / input.output.edges.length;
  const degradationReasons = [
    ...(droppedRatio > input.maxDroppedRatio ? ['dropped_ratio_exceeded'] : []),
    ...(crossSegmentRatio > crossSegmentAlertRatio
      ? ['cross_segment_citation_ratio_exceeded']
      : []),
  ];
  const status: WorkflowMapStatus = degradationReasons.length > 0 ? 'degraded' : 'validated';

  return {
    status,
    map: { ...input.output, nodes, edges, lanes, paths },
    diagnostics,
    validationJson: {
      policySelected: selectedPolicy.name,
      sourceKind: input.sourceKind,
      dropped: diagnostics,
      diagnosticCount: totalDiagnosticCount,
      diagnosticsTruncated: totalDiagnosticCount > diagnostics.length,
      droppedCount,
      rootDroppedCount,
      cascadeDroppedCount,
      keptCount,
      droppedRatio,
      maxDroppedRatio: input.maxDroppedRatio,
      crossSegmentCitationCount,
      validatedCitationCount,
      crossSegmentCitationRatio: crossSegmentRatio,
      crossSegmentAlertRatio,
      importantRelationEvidenceCoverage: importantRelationCoverage,
      degradationReasons,
      orphanLaneRefs,
      readerOutputAudit: auditArtifact(
        input.output,
        input.maxAuditChars ?? DEFAULT_MAX_AUDIT_CHARS,
      ),
    },
    droppedCount,
    rootDroppedCount,
    cascadeDroppedCount,
    keptCount,
    crossSegmentCitationCount,
    importantRelationCoverage,
  };
}
