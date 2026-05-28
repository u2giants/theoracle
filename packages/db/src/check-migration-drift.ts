// Drift checker for the Drizzle migration journal.
//
// Compares on-disk packages/db/migrations/0*.sql hashes against the
// drizzle.__drizzle_migrations table in the live database. Exits non-zero
// if any on-disk migration is missing from the journal (= someone applied
// a migration outside `pnpm db:migrate` and the journal is now stale).
//
// Run as: `pnpm db:check-drift` — also wired into CI.
//
// Why this exists: see DECISIONS.md / CLAUDE.md → "Drizzle journal hygiene".
// One drift incident reconciled on 2026-05-28; this guardrail catches the
// next one automatically instead of waiting for someone to run db:migrate
// and discover the failure.

import { config as loadEnv } from 'dotenv';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import postgres from 'postgres';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');
loadEnv({ path: resolve(repoRoot, '.env.local') });
loadEnv({ path: resolve(repoRoot, '.env') });

const migrationsDir = join(__dirname, '..', 'migrations');

async function main(): Promise<void> {
  const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
  if (!url) {
    // Graceful skip when no live DB URL is configured (e.g. CI runs that
    // intentionally don't have prod credentials). Exit 0 so the check
    // doesn't break PR builds that lack the secret; the prod-pointing CI
    // job is where the real enforcement happens.
    console.log('[drift] DIRECT_URL/DATABASE_URL not set — skipping drift check.');
    return;
  }

  const files = readdirSync(migrationsDir)
    .filter((f) => /^\d{4}_.+\.sql$/.test(f))
    .sort();
  const onDisk = files.map((f) => ({
    file: f,
    hash: createHash('sha256').update(readFileSync(join(migrationsDir, f), 'utf8')).digest('hex'),
  }));

  const client = postgres(url, { max: 1, prepare: true });
  try {
    const rows = await client<{ hash: string }[]>`
      SELECT hash FROM drizzle.__drizzle_migrations
    `;
    const journal = new Set(rows.map((r) => r.hash));
    const missing = onDisk.filter((m) => !journal.has(m.hash));

    if (missing.length === 0) {
      console.log(`[drift] OK — all ${onDisk.length} on-disk migrations are recorded in the journal.`);
      return;
    }

    console.error('\n[drift] DRIFT DETECTED');
    console.error('The following on-disk migrations are NOT recorded in drizzle.__drizzle_migrations:');
    for (const m of missing) console.error(`  - ${m.file}  (sha256 ${m.hash})`);
    console.error(
      '\nThis means a migration was applied outside `pnpm db:migrate` (e.g. via Supabase MCP, the\n' +
        'dashboard SQL editor, or `drizzle-kit push`). See CLAUDE.md → "Drizzle journal hygiene"\n' +
        'for the reconciliation steps.',
    );
    process.exit(1);
  } finally {
    await client.end({ timeout: 5 });
  }
}

main().catch((err) => {
  console.error('[drift] check failed:', err);
  process.exit(1);
});
