/**
 * One-off: invokes refreshModelCatalog() against the live DB. Same effect as
 * an admin clicking "Refresh catalog" in the model-pool UI. Use when:
 *   - You just added a new provider's API key and want to populate its rows
 *   - You changed enrichment logic and want to re-write all rows
 *
 * Pass keys via env (don't hardcode):
 *   $env:ANTHROPIC_API_KEY = '...'; $env:OPENAI_API_KEY = '...';
 *   $env:GOOGLE_APPLICATION_CREDENTIALS_JSON = '...';
 *   $env:DEEPSEEK_API_KEY = '...'; $env:DASHSCOPE_API_KEY = '...';
 *   $env:DIRECT_URL = '...';
 *   node_modules\.bin\tsx.CMD scripts/refresh-catalog.ts
 */

import { refreshModelCatalog } from '../packages/ai/src/model-capabilities';
import { getDirectDb } from '../packages/db/src/client';

async function main() {
  console.log('=== refreshModelCatalog() ===\n');
  const db = getDirectDb();
  const result = await refreshModelCatalog(db);

  console.log(`✓ refreshedAt: ${result.refreshedAt}`);
  console.log(`✓ written: ${result.written} rows`);

  // Group by provider
  const byProvider: Record<string, number> = {};
  for (const m of result.catalog) {
    byProvider[m.provider] = (byProvider[m.provider] ?? 0) + 1;
  }
  console.log('\nPer-provider counts:');
  for (const [p, n] of Object.entries(byProvider)) {
    console.log(`  ${p.padEnd(10)} ${n}`);
  }

  if (result.errors.length) {
    console.log('\nNon-fatal errors:');
    result.errors.forEach((e) => console.log(`  • ${e}`));
  }
  if (result.unenrichedIds.length) {
    console.log(`\nUnenriched: ${result.unenrichedIds.length} models`);
    result.unenrichedIds.slice(0, 20).forEach((id) => console.log(`  • ${id}`));
    if (result.unenrichedIds.length > 20) console.log(`  ... and ${result.unenrichedIds.length - 20} more`);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
