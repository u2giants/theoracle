-- Shape-aware source reader Stage 1: add the unified source-structure map
-- columns while preserving the readable process/workflow columns.
--
-- Stage 1 wires only the process shape. Existing workflow rows are backfilled
-- by mapping nodes -> elements and edges -> relations. Lanes and paths stay as
-- map-level arrays for process readability and validation continuity.

BEGIN;

ALTER TABLE source_workflow_maps
  ADD COLUMN IF NOT EXISTS document_shape varchar(50) NOT NULL DEFAULT 'process',
  ADD COLUMN IF NOT EXISTS segments_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS elements_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS relations_json jsonb NOT NULL DEFAULT '[]'::jsonb;

UPDATE source_workflow_maps AS m
SET document_shape = 'process'
WHERE document_shape IS NULL;

UPDATE source_workflow_maps AS m
SET segments_json = jsonb_build_array(
  jsonb_build_object(
    'segmentId', 'process',
    'shape', 'process',
    'title', COALESCE(d.file_name, 'Full process'),
    'summary', m.summary,
    'chunkIds', COALESCE(
      (
        SELECT jsonb_agg(dc.id ORDER BY dc.chunk_index)
        FROM document_chunks dc
        WHERE dc.document_id = m.document_id
      ),
      '[]'::jsonb
    )
  )
)
FROM documents d
WHERE m.document_id = d.id
  AND m.segments_json = '[]'::jsonb
  AND (m.nodes_json <> '[]'::jsonb OR m.edges_json <> '[]'::jsonb);

UPDATE source_workflow_maps AS m
SET elements_json = COALESCE(
  (
    SELECT jsonb_agg(
      jsonb_strip_nulls(
        jsonb_build_object(
          'elementId', node.value->>'nodeId',
          'segmentId', 'process',
          'shape', 'process',
          'elementKind', node.value->>'nodeType',
          'label', node.value->>'label',
          'lane', node.value->>'lane',
          'ownerName', node.value->>'ownerName',
          'systems', CASE
            WHEN jsonb_typeof(node.value->'systems') = 'array' THEN (
              SELECT string_agg(system_name, '; ')
              FROM jsonb_array_elements_text(node.value->'systems') AS system(system_name)
            )
            ELSE NULL
          END,
          'evidenceQuote', node.value->>'evidenceQuote',
          'chunkId', node.value->>'chunkId'
        )
      )
      ORDER BY node.ordinality
    )
    FROM jsonb_array_elements(m.nodes_json) WITH ORDINALITY AS node(value, ordinality)
  ),
  '[]'::jsonb
)
WHERE m.elements_json = '[]'::jsonb
  AND m.nodes_json <> '[]'::jsonb;

UPDATE source_workflow_maps AS m
SET relations_json = COALESCE(
  (
    SELECT jsonb_agg(
      jsonb_strip_nulls(
        jsonb_build_object(
          'relationId', edge.value->>'edgeId',
          'segmentId', 'process',
          'fromElementId', edge.value->>'fromNodeId',
          'toElementId', edge.value->>'toNodeId',
          'shape', 'process',
          'relationKind', edge.value->>'edgeType',
          'condition', edge.value->>'condition',
          'evidenceQuote', edge.value->>'evidenceQuote',
          'chunkId', edge.value->>'chunkId'
        )
      )
      ORDER BY edge.ordinality
    )
    FROM jsonb_array_elements(m.edges_json) WITH ORDINALITY AS edge(value, ordinality)
  ),
  '[]'::jsonb
)
WHERE m.relations_json = '[]'::jsonb
  AND m.edges_json <> '[]'::jsonb;

COMMIT;
