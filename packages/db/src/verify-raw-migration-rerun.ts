import { config as loadEnv } from 'dotenv';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import postgres from 'postgres';
import { assertRawMigrationRerunTarget } from './raw-migration-rerun-guard';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');
loadEnv({ path: resolve(repoRoot, '.env.local') });
loadEnv({ path: resolve(repoRoot, '.env') });

const phase = process.argv[2];
if (phase !== 'prepare' && phase !== 'verify') {
  throw new Error('Expected phase "prepare" or "verify".');
}

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
const guardedTarget = assertRawMigrationRerunTarget({
  url,
  optIn: process.env.ORACLE_MIGRATION_RERUN_TEST,
});

const batchId = '97000000-0000-4000-8000-000000000001';
const candidateId = '97000000-0000-4000-8000-000000000002';
const resultId = '97000000-0000-4000-8000-000000000003';
const currentCheckName = 'map_element_ref_membership';
const sql = postgres(guardedTarget.toString(), { max: 1, prepare: true });

try {
  const [databaseRow] = await sql<{ database: string }[]>`
    SELECT current_database() AS database
  `;
  if (!databaseRow) throw new Error('Could not read the current database name.');
  const { database } = databaseRow;
  if (database !== 'oracle_fresh') {
    throw new Error(`Refusing migration rerun fixture outside oracle_fresh.`);
  }

  if (phase === 'prepare') {
    await sql.begin(async (tx) => {
      await tx`
        INSERT INTO extraction_batches (
          id, batch_type, status, source_hash
        ) VALUES (
          ${batchId}, 'document_chunk', 'pending_model', ${'9'.repeat(64)}
        )
        ON CONFLICT (id) DO NOTHING
      `;
      await tx`
        INSERT INTO extraction_candidates (
          id, extraction_batch_id, status, claim_type, summary, impact_score,
          domains, raw_candidate_json
        ) VALUES (
          ${candidateId}, ${batchId}, 'pending_validation', 'fact',
          'Migration rerun safety fixture', 1, '[]'::jsonb, '{}'::jsonb
        )
        ON CONFLICT (id) DO NOTHING
      `;
      await tx`
        INSERT INTO extraction_validation_results (
          id, candidate_id, check_name, status, detail
        ) VALUES (
          ${resultId}, ${candidateId}, ${currentCheckName}, 'pass',
          'Must survive a complete raw migration rerun'
        )
        ON CONFLICT (id) DO UPDATE SET check_name = EXCLUDED.check_name
      `;
    });
    console.log('PASS prepared current populated-schema migration rerun fixture');
  } else {
    const [fixture] = await sql<{ check_name: string }[]>`
      SELECT check_name
      FROM extraction_validation_results
      WHERE id = ${resultId}
    `;
    if (fixture?.check_name !== currentCheckName) {
      throw new Error('Current validation-result fixture did not survive the complete migration rerun.');
    }
    const [constraint] = await sql<{ definition: string }[]>`
      SELECT pg_get_constraintdef(oid) AS definition
      FROM pg_constraint
      WHERE conname = 'extraction_validation_results_check_name_check'
    `;
    if (!constraint?.definition.includes(currentCheckName)) {
      throw new Error(`Final validation-result constraint is missing ${currentCheckName}.`);
    }
    console.log('PASS complete migration runner reruns safely against current populated data');
  }
} finally {
  await sql.end({ timeout: 5 });
}
