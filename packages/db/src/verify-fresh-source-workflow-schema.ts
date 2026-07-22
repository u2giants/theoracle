import { config as loadEnv } from 'dotenv';
import { resolve } from 'node:path';
import postgres from 'postgres';

loadEnv({ path: resolve(process.cwd(), '.env.local') });
loadEnv({ path: resolve(process.cwd(), '.env') });

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) throw new Error('DIRECT_URL or DATABASE_URL is required for fresh-schema verification.');

const sql = postgres(url, { max: 1, prepare: true });
try {
  const columns = await sql<{ column_name: string }[]>`
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'source_workflow_maps'
  `;
  const names = new Set(columns.map((row) => row.column_name));
  const required = [
    'id',
    'source_type',
    'document_id',
    'channel_id',
    'source_content_hash',
    'status',
    'map_kind',
    'segments_json',
    'elements_json',
    'relations_json',
    'validation_json',
    'superseded_by_map_id',
    'finalized_at',
  ];
  const missing = required.filter((column) => !names.has(column));
  if (missing.length > 0) {
    throw new Error(`fresh source_workflow_maps schema is missing: ${missing.join(', ')}`);
  }
  const forbidden = ['source_outline_id', 'workflow_version', 'coverage_json'].filter((column) =>
    names.has(column),
  );
  if (forbidden.length > 0) {
    throw new Error(`superseded source_workflow_maps columns survived: ${forbidden.join(', ')}`);
  }
  const [statusConstraint] = await sql<{ definition: string }[]>`
    SELECT pg_get_constraintdef(oid) AS definition
    FROM pg_constraint
    WHERE conname = 'source_workflow_maps_status_check'
  `;
  for (const status of ['pending', 'validated', 'degraded', 'failed', 'superseded']) {
    if (!statusConstraint?.definition.includes(status)) {
      throw new Error(`source_workflow_maps_status_check is missing ${status}`);
    }
  }
  const [validationConstraint] = await sql<{ definition: string }[]>`
    SELECT pg_get_constraintdef(oid) AS definition
    FROM pg_constraint
    WHERE conname = 'extraction_validation_results_check_name_check'
  `;
  if (!validationConstraint?.definition.includes('map_element_ref_membership')) {
    throw new Error('fresh validation-result constraint is missing map_element_ref_membership');
  }
  console.log('PASS fresh source_workflow_maps schema');
} finally {
  await sql.end({ timeout: 5 });
}
