import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
  console.log(`✓ ${message}`);
}

const root = resolve(process.cwd(), '../..');
const schema = readFileSync(resolve(root, 'packages/db/src/schema.ts'), 'utf8');
const migration = readFileSync(
  resolve(root, 'packages/db/migrations/sql/101_gap_topical_embeddings.sql'),
  'utf8',
);
const metaDir = resolve(root, 'packages/db/migrations/meta');
const latestSnapshotName = readdirSync(metaDir)
  .filter((name) => /^\d+_snapshot\.json$/.test(name))
  .sort()
  .at(-1);
assert(latestSnapshotName, 'latest Drizzle snapshot exists');
const snapshot = JSON.parse(
  readFileSync(resolve(metaDir, latestSnapshotName), 'utf8'),
) as {
  tables?: Record<string, { columns?: Record<string, unknown> }>;
};
const snapshotGapColumns = snapshot.tables?.['public.gaps']?.columns ?? {};

for (const [schemaName, sqlName] of [
  ['embedding', 'embedding'],
  ['embeddingModel', 'embedding_model'],
  ['embeddingSourceHash', 'embedding_source_hash'],
] as const) {
  assert(
    schema.includes(`${schemaName}:`) && schema.includes(`'${sqlName}'`),
    `Drizzle schema declares gaps.${sqlName}`,
  );
  assert(
    migration.includes(`ADD COLUMN IF NOT EXISTS ${sqlName}`),
    `migration 101 rerun-safely owns gaps.${sqlName}`,
  );
  assert(
    !(sqlName in snapshotGapColumns),
    `latest generated snapshot leaves raw-owned gaps.${sqlName} to migration 101`,
  );
}
assert(
  migration.includes("'lull_gap_minimum_relevance'") &&
    migration.includes('ON CONFLICT (key) DO NOTHING'),
  'migration 101 rerun-safely seeds the relevance setting',
);

console.log(
  `Topical gap schema contract passed against raw migration 101 and ${latestSnapshotName}.`,
);
