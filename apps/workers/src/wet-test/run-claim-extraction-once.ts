/**
 * Wet-test runner — fires one pass of the claim-extraction worker against the
 * real database WITHOUT going through Trigger.dev.
 *
 * Usage (from repo root):
 *   pnpm --filter @oracle/workers tsx src/wet-test/run-claim-extraction-once.ts
 *
 * Or with a custom run label:
 *   pnpm --filter @oracle/workers tsx src/wet-test/run-claim-extraction-once.ts wet-test-2026-05-26-a
 *
 * Reads DATABASE_URL / DIRECT_URL / OPENROUTER_API_KEY from the repo-root
 * .env.local (already loaded by @oracle/db's getDirectDb()).
 *
 * Side effects:
 *   - Inserts ONE row in job_runs.
 *   - Updates pending messages -> processing -> complete.
 *   - May insert rows in extraction_batches / extraction_candidates /
 *     extraction_candidate_evidence / extraction_validation_results /
 *     model_runs / model_run_usage_details / oracle_context_packs.
 *   - On success of any candidate: inserts rows in claims / claim_evidence /
 *     claim_top_domains.
 *   - Costs one provider call per pending-message segment (~$0.0001 on
 *     Gemini Flash via OpenRouter).
 */

import { config as loadEnv } from 'dotenv';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { runClaimExtractionOnce } from '../trigger/claim-extraction';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..', '..');
// override: true so .env.local wins over any shell-level empty placeholders.
loadEnv({ path: resolve(repoRoot, '.env.local'), override: true });
loadEnv({ path: resolve(repoRoot, '.env'), override: false });

async function main() {
  const runLabel = process.argv[2] ?? `wet-test-${new Date().toISOString()}`;
  console.log(`[wet-test] runLabel=${runLabel}`);
  if (!process.env.DATABASE_URL && !process.env.DIRECT_URL) {
    throw new Error('Neither DATABASE_URL nor DIRECT_URL is set. Check .env.local at repo root.');
  }
  if (!process.env.OPENROUTER_API_KEY) {
    throw new Error('OPENROUTER_API_KEY missing. The OpenRouter bridge adapter needs it.');
  }

  // The triggerRunId column is varchar(255) on job_runs; use a stable string.
  const triggerRunId = `${runLabel}-${randomUUID()}`;
  console.log(`[wet-test] triggerRunId=${triggerRunId}`);
  const startedAt = Date.now();

  const result = await runClaimExtractionOnce(triggerRunId);
  const elapsedMs = Date.now() - startedAt;

  console.log('\n[wet-test] ── result ─────────────────────────');
  console.log(JSON.stringify(result, null, 2));
  console.log(`[wet-test] elapsed: ${elapsedMs} ms`);
}

main()
  .then(() => {
    // Force exit — the postgres-js pool keeps the event loop alive otherwise.
    process.exit(0);
  })
  .catch((err) => {
    console.error('[wet-test] FAILED:', err);
    process.exit(1);
  });
