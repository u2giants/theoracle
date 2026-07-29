import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { parseSafeEvalRunSummary } from '@oracle/ai/eval-results';
import {
  filterEvalResults,
  findEvalResult,
  githubArtifactUrl,
  loadEvalResults,
} from '../eval-results';

const root = resolve(import.meta.dirname, '..', '..', '..', '..');
const [layout, listPage, detailPage, reportWriter] = await Promise.all([
  readFile(resolve(root, 'apps/web/app/admin/layout.tsx'), 'utf8'),
  readFile(resolve(root, 'apps/web/app/admin/ai/evals/page.tsx'), 'utf8'),
  readFile(resolve(root, 'apps/web/app/admin/ai/evals/[runId]/page.tsx'), 'utf8'),
  readFile(resolve(root, 'packages/ai/evals/runners/shared/report.ts'), 'utf8'),
]);

assert.match(layout, /requireAdmin\(\)/, 'The eval route must remain inside the admin-only layout.');
for (const field of ['stage', 'commit', 'status', 'from', 'to']) {
  assert.match(listPage, new RegExp(`name="${field}"`), `Missing ${field} filter.`);
}
assert.match(detailPage, /Raw CLI files stay local/, 'Detail must explain raw-artifact exclusion.');
assert.match(detailPage, /notFound\(\)/, 'Unknown run IDs must return the framework 404.');
assert.doesNotMatch(
  `${listPage}\n${detailPage}`,
  /triggerTask|<form[^>]+action=/,
  'The read-only dashboard must not expose an eval execution action.',
);
const safeSummarySource = reportWriter.slice(
  reportWriter.indexOf('const safeSummary'),
  reportWriter.indexOf('await publishSafeSummary(safeSummary)'),
);
for (const forbidden of ['perFixture', 'failureNotes', 'prompt', 'sourceText', 'credential']) {
  assert.doesNotMatch(
    safeSummarySource,
    new RegExp(`${forbidden}\\s*:`),
    `Safe summary must not publish ${forbidden}.`,
  );
}

const safe = {
  schemaVersion: 1,
  runId: 'extraction-2026-01-01',
  startedAt: '2026-01-01T00:00:00.000Z',
  completedAt: '2026-01-01T00:00:01.000Z',
  commitSha: '0123456789abcdef0123456789abcdef01234567',
  fixtureVersion: 'a'.repeat(64),
  promptVersion: '2.4.2',
  mode: 'mock',
  routeId: 'test',
  modelId: null,
  gateStatus: 'PASS',
  stages: [{
    stage: 'extraction',
    gateStatus: 'PASS',
    fixtureCount: 1,
    passedCount: 1,
    failedCount: 0,
    metrics: { quoteValidity: 1 },
  }],
  execution: {
    latencyMs: 100,
    inputTokens: null,
    outputTokens: null,
    costUsd: null,
  },
  artifacts: [{
    label: 'Safe stored summary',
    path: 'packages/ai/evals/published/extraction-2026-01-01.json',
  }],
} as const;
const parsed = parseSafeEvalRunSummary({ ...safe, rawPrompt: 'must be stripped' });
assert.equal(parsed.runId, safe.runId);
assert.equal('rawPrompt' in parsed, false, 'Unknown or forbidden keys must be stripped.');
assert.throws(
  () => parseSafeEvalRunSummary({ ...safe, artifacts: [{ label: 'raw', path: '../runs/raw.json' }] }),
  /Unsafe eval artifact link/,
);
assert.throws(() => parseSafeEvalRunSummary(null), /object/);
assert.throws(() => parseSafeEvalRunSummary({ ...safe, stages: [] }), /no stages/);
assert.throws(
  () => parseSafeEvalRunSummary({ ...safe, stages: [{ ...safe.stages[0], stage: 'secrets' }] }),
  /Invalid eval stage/,
);
assert.throws(
  () => parseSafeEvalRunSummary({ ...safe, stages: [{ ...safe.stages[0], metrics: [] }] }),
  /Invalid eval metrics/,
);
assert.throws(
  () => parseSafeEvalRunSummary({
    ...safe,
    stages: [{ ...safe.stages[0], fixtureCount: 1, passedCount: 1, failedCount: 1 }],
  }),
  /counts exceed/,
);
assert.throws(
  () => parseSafeEvalRunSummary({
    ...safe,
    startedAt: '2026-01-02T00:00:00.000Z',
    completedAt: '2026-01-01T00:00:00.000Z',
  }),
  /after completion/,
);

const safeRun = parseSafeEvalRunSummary(safe);
const otherRun = parseSafeEvalRunSummary({
  ...safe,
  runId: 'retrieval-2026-01-02',
  completedAt: '2026-01-02T00:00:01.000Z',
  gateStatus: 'FAIL',
  stages: [{ ...safe.stages[0], stage: 'retrieval', gateStatus: 'FAIL', passedCount: 0, failedCount: 1 }],
});
assert.deepEqual(filterEvalResults([safeRun, otherRun], { stage: 'extraction' }), [safeRun]);
assert.deepEqual(filterEvalResults([safeRun, otherRun], { status: 'FAIL' }), [otherRun]);
assert.deepEqual(filterEvalResults([safeRun, otherRun], { commit: '0123456' }), [safeRun, otherRun]);
assert.deepEqual(filterEvalResults([safeRun, otherRun], { from: '2026-01-02', to: '2026-01-02' }), [otherRun]);
assert.deepEqual(filterEvalResults([safeRun, otherRun], { stage: '../extraction' }), [safeRun, otherRun]);
assert.equal(
  githubArtifactUrl(safeRun, safeRun.artifacts[0]!.path),
  `https://github.com/u2giants/theoracle/blob/${safeRun.commitSha}/${safeRun.artifacts[0]!.path}`,
);
const traversalResult = findEvalResult('../secret');
const missingResult = findEvalResult('missing-run');
assert.equal(traversalResult.ok && traversalResult.run, undefined, 'Traversal-like IDs must never resolve.');
assert.equal(missingResult.ok && missingResult.run, undefined, 'Unknown IDs must never resolve.');

const currentIndex = loadEvalResults();
assert.equal(currentIndex.ok, true, 'The checked-in safe summary index must validate.');

console.log('eval-results-dashboard: authorization, filters, safe contract, and exclusion guards passed');
