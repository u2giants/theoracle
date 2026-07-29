import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { providerSupportsTrackedBatch } from '@oracle/ai';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const root = resolve(import.meta.dirname, '..', '..', '..', '..');
const settingsRoute = readFileSync(
  resolve(root, 'apps/web/app/api/admin/settings/route.ts'),
  'utf8',
);
const settingsPage = readFileSync(
  resolve(root, 'apps/web/app/admin/settings/page.tsx'),
  'utf8',
);
const syncWorker = readFileSync(
  resolve(root, 'apps/workers/src/trigger/claim-extraction.ts'),
  'utf8',
);
const batchWorker = readFileSync(
  resolve(root, 'apps/workers/src/trigger/claim-extraction-batch-submit.ts'),
  'utf8',
);

assert(providerSupportsTrackedBatch('anthropic'), 'Anthropic Batch must remain enabled');
assert(providerSupportsTrackedBatch('openai'), 'OpenAI Batch must remain enabled');
assert(providerSupportsTrackedBatch('vertex'), 'Vertex Batch must remain enabled');
assert(!providerSupportsTrackedBatch('google'), 'Google Gemini API Batch must remain disabled');
assert(!providerSupportsTrackedBatch('qwen'), 'Qwen Batch must remain disabled');
assert(!providerSupportsTrackedBatch('deepseek'), 'DeepSeek Batch must remain disabled');

assert(
  settingsPage.includes('providerSupportsTrackedBatch(resolved.provider)') &&
    settingsPage.includes('batchSupported={'),
  'Settings UI must derive Batch availability from the shared provider rule',
);
assert(
  settingsRoute.includes("body.key === 'extraction_dispatch_mode'") &&
    settingsRoute.includes("body.key === 'default_extraction_route'") &&
    settingsRoute.includes('providerSupportsTrackedBatch(provider)') &&
    settingsRoute.includes('{ status: 409 }'),
  'Settings API must reject both ways of creating an unsupported Batch configuration',
);
assert(
  syncWorker.includes('INVALID BATCH CONFIGURATION') &&
    syncWorker.includes('providerSupportsTrackedBatch(batchProvider)'),
  'Sync extraction must fail loudly when a stale Batch setting targets an unsupported provider',
);
assert(
  batchWorker.includes('BATCH PROVIDER UNAVAILABLE') &&
    batchWorker.includes('INVALID BATCH CONFIGURATION') &&
    batchWorker.includes('providerSupportsTrackedBatch(route.provider)'),
  'Batch submit must enforce product policy before checking runtime adapter methods',
);

console.log('PASS provider capability parity guards');
