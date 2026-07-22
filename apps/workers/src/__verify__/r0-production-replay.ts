/**
 * SELECT-only replay of the R0 validator over the current production swimlane map.
 * It does not call a model and does not write or supersede a map.
 */
import postgres from 'postgres';
import type { WorkflowReadOutput } from '@oracle/ai';
import { quoteSourceKindForDocument } from '@oracle/engines';
import { validateWorkflowMap, type WorkflowMapChunkContext } from '../lib/workflow-map-validator';

const SWIMLANE_DOCUMENT_ID = '9d09fa89-3a46-465e-a98b-837287c9e22a';
const databaseUrl = process.env.R0_REPLAY_DATABASE_URL;
if (!databaseUrl) {
  throw new Error(
    'Missing R0_REPLAY_DATABASE_URL. Supply the current production session-pooler URL explicitly; this gate is SELECT-only.',
  );
}

type MapRow = {
  id: string;
  document_id: string;
  file_name: string;
  file_type: string;
  status: string;
  summary: string | null;
  nodes_json: WorkflowReadOutput['nodes'];
  edges_json: WorkflowReadOutput['edges'];
  lanes_json: WorkflowReadOutput['lanes'];
  paths_json: WorkflowReadOutput['paths'];
};

const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  const maps = await sql<MapRow[]>`
    SELECT
      swm.id,
      swm.document_id,
      d.file_name,
      d.file_type,
      swm.status,
      swm.summary,
      swm.nodes_json,
      swm.edges_json,
      swm.lanes_json,
      swm.paths_json
    FROM source_workflow_maps swm
    JOIN documents d ON d.id = swm.document_id
    WHERE swm.document_id = ${SWIMLANE_DOCUMENT_ID}::uuid
      AND swm.status IN ('validated', 'degraded')
    ORDER BY swm.created_at DESC
    LIMIT 1
  `;
  const map = maps[0];
  if (!map) throw new Error(`No active swimlane map found for ${SWIMLANE_DOCUMENT_ID}`);

  const chunkRows = await sql<Array<{ id: string; text: string }>>`
    SELECT id, raw_text AS text
    FROM document_chunks
    WHERE document_id = ${map.document_id}::uuid
    ORDER BY chunk_index
  `;
  const chunksById = new Map<string, WorkflowMapChunkContext>(
    chunkRows.map((chunk) => [
      chunk.id,
      { documentId: map.document_id, text: chunk.text, coveredBySegmentation: true },
    ]),
  );
  const output: WorkflowReadOutput = {
    mapKind: 'workflow',
    summary: map.summary ?? '',
    nodes: map.nodes_json,
    edges: map.edges_json,
    lanes: map.lanes_json,
    paths: map.paths_json,
  };
  const validation = validateWorkflowMap({
    output,
    activeDocumentId: map.document_id,
    activeSegmentChunkIds: new Set(chunkRows.map((chunk) => chunk.id)),
    chunksById,
    sourceKind: quoteSourceKindForDocument({ fileType: map.file_type, fileName: map.file_name }),
    maxDroppedRatio: 0.2,
  });

  const duplicateElementIds = [
    ...output.nodes.map((node) => `node:${node.nodeId}`),
    ...output.edges.map((edge) => `edge:${edge.edgeId}`),
  ].reduce<Record<string, number>>((counts, id) => {
    counts[id] = (counts[id] ?? 0) + 1;
    return counts;
  }, {});
  const duplicateCount = Object.values(duplicateElementIds).filter((count) => count > 1).length;

  const claimDuplication = await sql<
    Array<{ maximum_claims_per_ref: number; refs_with_three_or_more: number }>
  >`
    WITH per_ref AS (
      SELECT c.map_element_ref, count(DISTINCT c.id)::int AS claim_count
      FROM claims c
      JOIN claim_evidence ce ON ce.claim_id = c.id
      JOIN document_chunks dc ON ce.source_document_chunk_id = dc.id
      WHERE dc.document_id = ${map.document_id}::uuid
        AND c.map_element_ref LIKE ${`${map.id}:%`}
        AND c.status NOT IN ('rejected', 'superseded')
      GROUP BY c.map_element_ref
    )
    SELECT
      COALESCE(max(claim_count), 0)::int AS maximum_claims_per_ref,
      count(*) FILTER (WHERE claim_count >= 3)::int AS refs_with_three_or_more
    FROM per_ref
  `;

  const result = {
    documentId: map.document_id,
    fileName: map.file_name,
    mapId: map.id,
    persistedStatus: map.status,
    replayStatus: validation.status,
    sourcePolicy: validation.validationJson.policySelected,
    emitted: {
      nodes: output.nodes.length,
      relations: output.edges.length,
      lanes: output.lanes.length,
      paths: output.paths.length,
    },
    replay: {
      dropped: validation.droppedCount,
      rootDropped: validation.rootDroppedCount,
      cascadeDropped: validation.cascadeDroppedCount,
      importantRelationEvidenceCoverage: validation.importantRelationCoverage,
      duplicateElementIdCount: duplicateCount,
    },
    claims: claimDuplication[0],
  };
  if (validation.droppedCount !== 0 || duplicateCount !== 0) {
    throw new Error(`R0 swimlane replay regression: ${JSON.stringify(result)}`);
  }
  console.log(JSON.stringify(result, null, 2));
} finally {
  await sql.end({ timeout: 5 });
}
