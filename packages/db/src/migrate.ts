// Migration runner for The Oracle.
//
// Order of operations:
//   1. Run 01_extensions.sql (pgvector, uuid-ossp, pgcrypto)
//   2. Apply Drizzle-generated migrations from ./migrations
//   3. Apply raw SQL files in lex order from ./migrations/sql (excluding 01_extensions
//      which we ran in step 1, and 99_vector_indexes which is opt-in).
//   4. If ORACLE_RUN_VECTOR_INDEXES=1, apply 99_vector_indexes.sql
//   5. Seed settings + admin employee (calls seed.ts inline)
//
// Run from repo root:
//   pnpm db:migrate
//
// Requires DIRECT_URL (preferred) or DATABASE_URL.

import { config as loadEnv } from 'dotenv';
import { readFile, readdir } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { drizzle } from 'drizzle-orm/postgres-js';
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import postgres from 'postgres';
import { runSeed } from './seed';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');
// Load .env.local first (takes precedence), then .env as fallback.
loadEnv({ path: resolve(repoRoot, '.env.local') });
loadEnv({ path: resolve(repoRoot, '.env') });

const migrationsDir = join(__dirname, '..', 'migrations');
const rawSqlDir = join(migrationsDir, 'sql');

function getMigrationsUrl(): string {
  const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      'DIRECT_URL (or DATABASE_URL) is required to run migrations. ' +
        'See DECISIONS.md D0.4 — populate the empty Vercel env vars first.',
    );
  }
  return url;
}

async function applySqlFile(client: ReturnType<typeof postgres>, path: string): Promise<void> {
  const sql = await readFile(path, 'utf8');
  // Use unsafe so DDL containing multiple statements / DO blocks runs as-is.
  // The migration runner is admin-only; we trust the on-disk SQL.
  await client.unsafe(sql);
  console.log(`  applied: ${path}`);
}

async function listSqlFiles(dir: string): Promise<string[]> {
  try {
    const entries = await readdir(dir);
    return entries.filter((f) => f.endsWith('.sql')).sort();
  } catch {
    return [];
  }
}

async function main(): Promise<void> {
  const url = getMigrationsUrl();
  console.log('Connecting to Postgres for migrations...');
  const client = postgres(url, { max: 1, prepare: true });

  try {
    // Step 1 — extensions must exist BEFORE Drizzle tries to create vector columns.
    console.log('Step 1: extensions');
    await applySqlFile(client, join(rawSqlDir, '01_extensions.sql'));

    // Step 2 — Drizzle migrations (table DDL, enums, indexes).
    // If the migrations folder has no SQL files yet (first run after `pnpm db:generate`),
    // migrate() is a no-op.
    console.log('Step 2: Drizzle generated migrations');
    const db = drizzle(client);
    try {
      await migrate(db, { migrationsFolder: migrationsDir });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      // Drizzle reports a missing migrations folder two different ways depending on state:
      //   * "No migrations found"          — folder exists but is empty
      //   * "Can't find meta/_journal.json" — folder/journal hasn't been generated yet
      if (message.includes('No migrations found') || message.includes('_journal.json')) {
        console.log('  (no generated migrations — run `pnpm db:generate` first)');
      } else {
        throw err;
      }
    }

    // Step 3 — raw SQL files, in lex order, skipping the extensions file and the
    // opt-in vector index file.
    console.log('Step 3: raw SQL (constraints, RLS, views)');
    const files = await listSqlFiles(rawSqlDir);
    for (const f of files) {
      if (f === '01_extensions.sql' || f === '99_vector_indexes.sql') continue;
      await applySqlFile(client, join(rawSqlDir, f));
    }

    // Step 4 — optional HNSW vector indexes.
    if (process.env.ORACLE_RUN_VECTOR_INDEXES === '1') {
      console.log('Step 4: HNSW vector indexes (opt-in)');
      await applySqlFile(client, join(rawSqlDir, '99_vector_indexes.sql'));
    } else {
      console.log(
        'Step 4: skipping HNSW vector indexes (set ORACLE_RUN_VECTOR_INDEXES=1 to apply)',
      );
    }

    // Step 5 — seeds.
    console.log('Step 5: seed (settings + admin employee)');
    await runSeed(client);

    console.log('\nMigrations + seed complete.');
  } finally {
    await client.end({ timeout: 5 });
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
