import postgres from 'postgres';

const documentId = process.env.DOCUMENT_ID ?? '9d09fa89-3a46-465e-a98b-837287c9e22a';
const directUrl = process.env.DIRECT_URL;

if (!directUrl) {
  throw new Error('DIRECT_URL is required');
}

const sql = postgres(directUrl, { max: 1, prepare: false });

try {
  const doc = await sql`
    SELECT id, file_name, status, macro_health, processed_at
    FROM documents
    WHERE id = ${documentId}
  `;

  const maps = await sql`
    SELECT
      id,
      source_outline_id,
      created_at,
      jsonb_array_length(nodes_json) AS nodes,
      jsonb_array_length(edges_json) AS edges,
      jsonb_array_length(paths_json) AS paths
    FROM source_workflow_maps
    WHERE document_id = ${documentId}
    ORDER BY created_at DESC
    LIMIT 5
  `;

  const latestMapId = maps[0]?.id ?? null;

  const traces = latestMapId
    ? await sql`
        SELECT
          count(*)::int AS total_for_map,
          count(*) FILTER (WHERE jsonb_typeof(raw_candidate_json->'workflowTrace') = 'object')::int AS traced,
          count(*) FILTER (WHERE promoted_to_claim_id IS NOT NULL)::int AS traced_promoted
        FROM extraction_candidates
        WHERE raw_candidate_json->'workflowTrace'->>'workflowMapId' = ${latestMapId}
      `
    : [];

  const deterministicRelationships = latestMapId
    ? await sql`
        SELECT
          mr.id,
          mr.status,
          mr.relationship_type,
          mr.confidence,
          mr.metadata_json->>'workflowPathId' AS workflow_path_id,
          count(mrc.claim_id)::int AS support_claims,
          count(*) FILTER (WHERE c.status <> 'approved')::int AS non_approved_support
        FROM macro_relationships mr
        LEFT JOIN macro_relationship_claims mrc ON mrc.macro_relationship_id = mr.id
        LEFT JOIN claims c ON c.id = mrc.claim_id
        WHERE mr.metadata_json->>'workflowMapId' = ${latestMapId}
          AND mr.metadata_json->>'deterministicSource' = 'source_workflow_map'
        GROUP BY mr.id
        ORDER BY mr.created_at DESC
        LIMIT 20
      `
    : [];

  const relationshipStatusSummary = latestMapId
    ? await sql`
        SELECT
          mr.status,
          count(*)::int AS count,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1
              FROM macro_relationship_claims mrc
              JOIN claims c ON c.id = mrc.claim_id
              WHERE mrc.macro_relationship_id = mr.id
                AND c.status <> 'approved'
            )
          )::int AS with_non_approved_support
        FROM macro_relationships mr
        WHERE mr.metadata_json->>'workflowMapId' = ${latestMapId}
          AND mr.metadata_json->>'deterministicSource' = 'source_workflow_map'
        GROUP BY mr.status
        ORDER BY mr.status
      `
    : [];

  const missingEdges = latestMapId
    ? await sql`
        SELECT id, finding_type, severity, status, description, related_source_refs
        FROM source_coverage_findings
        WHERE related_source_refs::text LIKE ${`%workflow-map:${latestMapId}:edge:%`}
        ORDER BY created_at DESC
        LIMIT 20
      `
    : [];

  const recentJobRuns = await sql`
    SELECT id, trigger_run_id, job_type, status, started_at, finished_at, error
    FROM job_runs
    WHERE input_json->>'documentId' = ${documentId}
      AND job_type IN ('source-outline', 'document-ingestion', 'macro-relationship-extraction', 'source-coverage-audit')
    ORDER BY started_at DESC
    LIMIT 20
  `;

  console.log(
    JSON.stringify(
      {
        documentId,
        doc,
        latestMapId,
        maps,
        traces,
        deterministicRelationships,
        relationshipStatusSummary,
        missingEdges,
        recentJobRuns,
      },
      null,
      2,
    ),
  );
} finally {
  await sql.end({ timeout: 5 });
}
