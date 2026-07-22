/**
 * Read-only release audit for a post-R0 source workflow map.
 *
 * This reports the persisted validator, evidence-coverage, and budget telemetry
 * needed by the R0 production release gate without printing source content.
 */
import postgres from 'postgres';

type Diagnostic = {
  failureClass?: unknown;
  failureOrigin?: unknown;
  policySelected?: unknown;
  validationMethod?: unknown;
  passesAlternatePolicies?: unknown;
};

type ProcessSegment = {
  segmentId?: unknown;
  policySelected?: unknown;
  dropped?: unknown;
  diagnosticCount?: unknown;
  droppedCount?: unknown;
  rootDroppedCount?: unknown;
  cascadeDroppedCount?: unknown;
  keptCount?: unknown;
  droppedRatio?: unknown;
  crossSegmentCitationRatio?: unknown;
  importantRelationEvidenceCoverage?: unknown;
  degradationReasons?: unknown;
};

const databaseUrl = process.env.R0_AUDIT_DATABASE_URL;
if (!databaseUrl) {
  throw new Error('Missing R0_AUDIT_DATABASE_URL. This audit is SELECT-only.');
}
const mapId = process.env.R0_AUDIT_MAP_ID;
if (!mapId || !/^[0-9a-f-]{36}$/i.test(mapId)) {
  throw new Error('R0_AUDIT_MAP_ID must be a UUID.');
}

function number(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  const rows = await sql<
    Array<{
      id: string;
      document_id: string | null;
      file_name: string | null;
      status: string;
      created_at: Date;
      finalized_at: Date | null;
      elements_json: unknown;
      relations_json: unknown;
      validation_json: Record<string, unknown>;
    }>
  >`
    SELECT swm.id, swm.document_id, d.file_name, swm.status,
           swm.created_at, swm.finalized_at, swm.elements_json,
           swm.relations_json, swm.validation_json
    FROM source_workflow_maps swm
    LEFT JOIN documents d ON d.id = swm.document_id
    WHERE swm.id = ${mapId}::uuid
  `;
  const map = rows[0];
  if (!map) throw new Error(`No source_workflow_maps row found for ${mapId}`);

  const segments = Array.isArray(map.validation_json.processSegments)
    ? (map.validation_json.processSegments as ProcessSegment[])
    : [];
  const diagnostics = segments.flatMap((segment) =>
    Array.isArray(segment.dropped) ? (segment.dropped as Diagnostic[]) : [],
  );
  const diagnosticCounts = diagnostics.reduce<Record<string, number>>((result, item) => {
    const alternatePolicies = Array.isArray(item.passesAlternatePolicies)
      ? item.passesAlternatePolicies.join(',') || 'none'
      : 'not_recorded';
    const key = [
      String(item.failureClass ?? 'unknown'),
      String(item.failureOrigin ?? 'unknown'),
      String(item.policySelected ?? 'unknown'),
      String(item.validationMethod ?? 'unknown'),
      alternatePolicies,
    ].join(':');
    result[key] = (result[key] ?? 0) + 1;
    return result;
  }, {});
  const readerBudget = map.validation_json.readerBudget as
    | { readCalls?: unknown; inputTokens?: unknown; estimatedCostUsd?: unknown; repairAttempts?: unknown; limits?: unknown }
    | undefined;
  const relationCount = Array.isArray(map.relations_json) ? map.relations_json.length : 0;
  const rejectedRelationCount = diagnostics.filter(
    (item) => item.failureClass === 'missing_endpoint_cascade',
  ).length;

  console.log(
    JSON.stringify(
      {
        map: {
          id: map.id,
          documentId: map.document_id,
          fileName: map.file_name,
          status: map.status,
          createdAt: map.created_at,
          finalizedAt: map.finalized_at,
          pipelineVersion: map.validation_json.pipelineVersion,
          elementCount: Array.isArray(map.elements_json) ? map.elements_json.length : 0,
          relationCount,
          importantRelationEvidenceCoverage:
            relationCount + rejectedRelationCount === 0
              ? 1
              : relationCount / (relationCount + rejectedRelationCount),
          droppedCount: number(map.validation_json.droppedCount),
          keptCount: number(map.validation_json.keptCount),
        },
        budget: readerBudget,
        diagnosticCounts,
        segments: segments.map((segment) => ({
          segmentId: segment.segmentId,
          policySelected: segment.policySelected,
          diagnosticCount: number(segment.diagnosticCount),
          droppedCount: number(segment.droppedCount),
          rootDroppedCount: number(segment.rootDroppedCount),
          cascadeDroppedCount: number(segment.cascadeDroppedCount),
          keptCount: number(segment.keptCount),
          droppedRatio: number(segment.droppedRatio),
          crossSegmentCitationRatio: number(segment.crossSegmentCitationRatio),
          importantRelationEvidenceCoverage: number(segment.importantRelationEvidenceCoverage),
          degradationReasons: Array.isArray(segment.degradationReasons)
            ? segment.degradationReasons
            : [],
        })),
      },
      null,
      2,
    ),
  );
} finally {
  await sql.end({ timeout: 5 });
}
