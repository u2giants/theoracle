import { config as loadEnv } from 'dotenv';
import { getTableColumns } from 'drizzle-orm';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import postgres from 'postgres';
import { documents } from './schema';

const repoRoot = resolve(import.meta.dirname, '..', '..', '..');
const migrationsDir = resolve(import.meta.dirname, '..', 'migrations');
loadEnv({ path: resolve(repoRoot, '.env.local') });
loadEnv({ path: resolve(repoRoot, '.env') });

type Journal = {
  entries: Array<{ idx: number; tag: string }>;
};

type SnapshotColumn = {
  type?: string;
  notNull?: boolean;
};

type Snapshot = {
  tables?: Record<
    string,
    {
      columns?: Record<string, SnapshotColumn>;
    }
  >;
};

const expectedColumns = [
  {
    schemaKey: 'context',
    databaseName: 'context',
    sqlType: 'text',
    drizzleType: 'PgText',
  },
  {
    schemaKey: 'domainHints',
    databaseName: 'domain_hints',
    sqlType: 'jsonb',
    drizzleType: 'PgJsonb',
  },
] as const;

const schemaColumns = getTableColumns(documents);
for (const expected of expectedColumns) {
  const column = schemaColumns[expected.schemaKey];
  if (
    !column ||
    column.name !== expected.databaseName ||
    column.columnType !== expected.drizzleType ||
    column.notNull
  ) {
    throw new Error(
      `schema.ts has the wrong documents.${expected.schemaKey} shape: ` +
        `expected nullable ${expected.drizzleType} named ${expected.databaseName}.`,
    );
  }
}

const journal = JSON.parse(
  await readFile(resolve(migrationsDir, 'meta', '_journal.json'), 'utf8'),
) as Journal;
const latestEntry = [...journal.entries].sort((left, right) => right.idx - left.idx)[0];
if (!latestEntry) throw new Error('Drizzle migration journal has no entries.');
const latestSnapshotName = `${String(latestEntry.idx).padStart(4, '0')}_snapshot.json`;

const snapshot = JSON.parse(
  await readFile(resolve(migrationsDir, 'meta', latestSnapshotName), 'utf8'),
) as Snapshot;
const snapshotColumns = snapshot.tables?.['public.documents']?.columns;
for (const expected of expectedColumns) {
  const column = snapshotColumns?.[expected.databaseName];
  if (!column) {
    throw new Error(`Latest Drizzle snapshot is missing documents.${expected.databaseName}.`);
  }
  if (column.type !== expected.sqlType || column.notNull !== false) {
    throw new Error(
      `Latest Drizzle snapshot has the wrong documents.${expected.databaseName} shape: ` +
        `expected nullable ${expected.sqlType}.`,
    );
  }
}

const rawMigration = await readFile(
  resolve(migrationsDir, 'sql', '65_document_context_and_domain_hints.sql'),
  'utf8',
);
for (const expected of expectedColumns) {
  const ownershipPattern = new RegExp(
    'ALTER\\s+TABLE\\s+documents\\s+ADD\\s+COLUMN\\s+IF\\s+NOT\\s+EXISTS\\s+' +
      `${expected.databaseName}\\s+${expected.sqlType}\\s*;`,
    'i',
  );
  if (!ownershipPattern.test(rawMigration)) {
    throw new Error(
      `Migration 65 does not idempotently own documents.${expected.databaseName} ` +
        `as ${expected.sqlType}.`,
    );
  }
}

if (process.argv.includes('--contract-only')) {
  console.log(
    `PASS document context migration files: migration 65 and snapshot ${latestEntry.tag} ` +
      'agree on nullable documents.context (text) and documents.domain_hints (jsonb).',
  );
  process.exit(0);
}

const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) {
  throw new Error(
    'DIRECT_URL or DATABASE_URL is required to verify the applied document context schema.',
  );
}

const sql = postgres(url, { max: 1, prepare: true });
try {
  const rows = await sql<
    {
      column_name: string;
      data_type: string;
      is_nullable: 'YES' | 'NO';
    }[]
  >`
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'documents'
      AND column_name IN ('context', 'domain_hints')
  `;
  const liveColumns = new Map(rows.map((row) => [row.column_name, row]));

  for (const expected of expectedColumns) {
    const column = liveColumns.get(expected.databaseName);
    if (!column) {
      throw new Error(`Applied database is missing documents.${expected.databaseName}.`);
    }
    if (column.data_type !== expected.sqlType || column.is_nullable !== 'YES') {
      throw new Error(
        `Applied database has the wrong documents.${expected.databaseName} shape: ` +
          `expected nullable ${expected.sqlType}.`,
      );
    }
  }

  console.log(
    `PASS document context migration contract: migration 65, snapshot ${latestEntry.tag}, ` +
      'and applied database agree on nullable documents.context (text) and ' +
      'documents.domain_hints (jsonb).',
  );
} finally {
  await sql.end({ timeout: 5 });
}
