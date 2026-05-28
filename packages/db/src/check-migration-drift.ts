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
    const journalHashes = new Set(rows.map((r) => r.hash));
    const onDiskHashes = new Set(onDisk.map((m) => m.hash));

    // Direction A — on-disk files not in journal. Two sub-cases hit this:
    //   1. A migration was applied outside `pnpm db:migrate` (Supabase MCP,
    //      dashboard SQL editor, drizzle-kit push) — the schema is live but
    //      the journal never recorded it.
    //   2. A previously-applied migration file was edited after the fact —
    //      its old hash is still in the journal but the new hash is not, so
    //      the runner would attempt to re-apply it and fail.
    const missingFromJournal = onDisk.filter((m) => !journalHashes.has(m.hash));

    // Direction B — journal rows with no matching on-disk file. Hits when
    // someone deletes a migration file but the journal row remains. Less
    // dangerous than Direction A, but still a real inconsistency.
    const orphanJournalHashes = [...journalHashes].filter((h) => !onDiskHashes.has(h));

    if (missingFromJournal.length === 0 && orphanJournalHashes.length === 0) {
      console.log(
        `[drift] OK — ${onDisk.length} on-disk migrations and ${journalHashes.size} journal rows match exactly.`,
      );
      return;
    }

    console.error('\n[drift] DRIFT DETECTED');
    if (missingFromJournal.length > 0) {
      console.error('\nOn-disk migrations NOT recorded in drizzle.__drizzle_migrations:');
      for (const m of missingFromJournal) console.error(`  - ${m.file}  (sha256 ${m.hash})`);
      console.error(
        '  Cause: applied outside `pnpm db:migrate`, OR an applied file was edited after the fact.',
      );
    }
    if (orphanJournalHashes.length > 0) {
      console.error('\nJournal rows with NO matching on-disk file:');
      for (const h of orphanJournalHashes) console.error(`  - ${h}`);
      console.error(
        '  Cause: a migration file was deleted but its journal row was not removed.',
      );
    }
    console.error(
      '\nSee CLAUDE.md → "Drizzle journal hygiene" for the reconciliation steps.',
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
