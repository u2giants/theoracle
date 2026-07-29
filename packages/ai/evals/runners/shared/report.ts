/**
 * Eval report writer.
 *
 * Writes a per-run directory under `evals/runs/<UTC timestamp>/`:
 *   - summary.json      aggregate metrics across all fixtures
 *   - per-fixture.json  per-fixture pass/fail breakdown
 *
 * Also emits a human-readable summary to stdout for the developer running
 * the CLI.
 */

import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { parseSafeEvalRunSummary, type SafeEvalRunSummary } from '../../../src/eval-results';
import { EXTRACTION_PROMPT_VERSION } from '../../../src/prompts/extraction-system';
import type { AggregateMetrics, ExtractionMetrics } from './metrics';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNS_ROOT = resolve(__dirname, '..', '..', 'runs');
const EVALS_ROOT = resolve(__dirname, '..', '..');
const PUBLISHED_ROOT = join(EVALS_ROOT, 'published');
const execFileAsync = promisify(execFile);

async function fixtureVersion(category: string): Promise<string> {
  const root = join(EVALS_ROOT, 'fixtures', category);
  const files = (await readdir(root)).filter((name) => name.endsWith('.json')).sort();
  const hash = createHash('sha256');
  for (const name of files) {
    hash.update(name);
    hash.update(await readFile(join(root, name)));
  }
  return hash.digest('hex');
}

async function currentCommitSha(): Promise<string> {
  const { stdout } = await execFileAsync('git', ['rev-parse', 'HEAD'], { cwd: EVALS_ROOT });
  return stdout.trim();
}

async function hasUncommittedTrackedWork(): Promise<boolean> {
  const { stdout } = await execFileAsync(
    'git',
    [
      'status',
      '--porcelain',
      '--untracked-files=no',
    ],
    { cwd: resolve(EVALS_ROOT, '..', '..', '..') },
  );
  return stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .some((line) => !line.slice(3).replaceAll('\\', '/').startsWith('packages/ai/evals/published/'));
}

async function publishSafeSummary(summary: SafeEvalRunSummary): Promise<void> {
  await mkdir(PUBLISHED_ROOT, { recursive: true });
  const fileName = `${summary.runId}.json`;
  await writeFile(join(PUBLISHED_ROOT, fileName), `${JSON.stringify(summary, null, 2)}\n`, 'utf8');

  const files = (await readdir(PUBLISHED_ROOT))
    .filter((name) => name.endsWith('.json') && name !== 'index.json')
    .sort()
    .reverse();
  const summaries = await Promise.all(
    files.map(async (name) =>
      parseSafeEvalRunSummary(JSON.parse(await readFile(join(PUBLISHED_ROOT, name), 'utf8'))),
    ),
  );
  summaries.sort((a, b) => Date.parse(b.completedAt) - Date.parse(a.completedAt));
  await writeFile(
    join(PUBLISHED_ROOT, 'index.json'),
    `${JSON.stringify({ schemaVersion: 1, runs: summaries }, null, 2)}\n`,
    'utf8',
  );
}

export async function writeExtractionReport(args: {
  perFixture: ExtractionMetrics[];
  aggregate: AggregateMetrics;
  mode: 'mock' | 'live';
  routeId: string;
}): Promise<{ runDir: string }> {
  const startedAt = new Date().toISOString();
  const timestamp = startedAt.replace(/[:.]/g, '-');
  const runDir = join(RUNS_ROOT, `extraction-${timestamp}`);
  await mkdir(runDir, { recursive: true });

  const summaryPayload = {
    runStartedAt: new Date().toISOString(),
    category: 'extraction',
    mode: args.mode,
    routeId: args.routeId,
    aggregate: args.aggregate,
  };
  await writeFile(
    join(runDir, 'summary.json'),
    JSON.stringify(summaryPayload, null, 2),
    'utf8',
  );

  await writeFile(
    join(runDir, 'per-fixture.json'),
    JSON.stringify(args.perFixture, null, 2),
    'utf8',
  );

  if (await hasUncommittedTrackedWork()) {
    console.warn(
      'Safe dashboard summary was not published because tracked work outside evals/published has uncommitted changes.',
    );
  } else {
    const runId = `extraction-${timestamp}`;
    const completedAt = new Date().toISOString();
    const safeSummary: SafeEvalRunSummary = {
      schemaVersion: 1,
      runId,
      startedAt,
      completedAt,
      commitSha: await currentCommitSha(),
      fixtureVersion: await fixtureVersion('extraction'),
      promptVersion: EXTRACTION_PROMPT_VERSION,
      mode: args.mode,
      routeId: args.routeId,
      modelId: null,
      gateStatus: args.aggregate.fixturesFailed === 0 ? 'PASS' : 'FAIL',
      stages: [{
        stage: 'extraction',
        gateStatus: args.aggregate.fixturesFailed === 0 ? 'PASS' : 'FAIL',
        fixtureCount: args.aggregate.fixtures,
        passedCount: args.aggregate.fixturesPassed,
        failedCount: args.aggregate.fixturesFailed,
        metrics: {
          expectedClaims: args.aggregate.totalExpectedClaims,
          extractedClaims: args.aggregate.totalExtractedClaims,
          validExtractedClaims: args.aggregate.totalValidExtractedClaims,
          precision: args.aggregate.precision,
          recall: args.aggregate.recall,
          f1: args.aggregate.f1,
          quoteValidity: args.aggregate.quoteValidity,
          wrongDomainRate: args.aggregate.wrongDomainRate,
          sensitiveQuarantinePassRate: args.aggregate.sensitiveQuarantinePassRate,
        },
      }],
      execution: {
        latencyMs: Math.max(0, Date.parse(completedAt) - Date.parse(startedAt)),
        inputTokens: null,
        outputTokens: null,
        costUsd: null,
      },
      artifacts: [{
        label: 'Safe stored summary',
        path: `packages/ai/evals/published/${runId}.json`,
      }],
    };
    await publishSafeSummary(safeSummary);
  }

  return { runDir };
}

export function printExtractionSummary(args: {
  perFixture: ExtractionMetrics[];
  aggregate: AggregateMetrics;
  mode: 'mock' | 'live';
  routeId: string;
  runDir: string;
}): void {
  const { perFixture, aggregate, mode, routeId, runDir } = args;
  const fmt = (n: number | null, digits = 2) =>
    n == null ? '—' : n.toFixed(digits);
  const fmtPct = (n: number | null) => (n == null ? '—' : `${(n * 100).toFixed(1)}%`);

  console.log('\nExtraction eval summary');
  console.log(`  mode:                       ${mode}`);
  console.log(`  route under test:           ${routeId}`);
  console.log(`  fixtures:                   ${aggregate.fixtures}`);
  console.log(`  expected claims:            ${aggregate.totalExpectedClaims}`);
  console.log(`  extracted claims:           ${aggregate.totalExtractedClaims}`);
  console.log(`  valid extracted claims:     ${aggregate.totalValidExtractedClaims}`);
  console.log(`  precision:                  ${fmt(aggregate.precision)}`);
  console.log(`  recall:                     ${fmt(aggregate.recall)}`);
  console.log(`  F1:                         ${fmt(aggregate.f1)}`);
  console.log(`  exact quote validity:       ${fmtPct(aggregate.quoteValidity)}`);
  console.log(`  wrong top-domain rate:      ${fmtPct(aggregate.wrongDomainRate)}`);
  console.log(`  sensitive quarantine pass:  ${fmtPct(aggregate.sensitiveQuarantinePassRate)}`);
  console.log(`  fixtures passed / failed:   ${aggregate.fixturesPassed} / ${aggregate.fixturesFailed}`);
  console.log('');

  for (const m of perFixture) {
    const status = m.gateStatus === 'PASS' ? '✓' : '✗';
    console.log(
      `  ${status} ${m.fixtureId.padEnd(40)} expected=${m.expectedClaims} extracted=${m.extractedClaims} valid=${m.validExtractedClaims}`,
    );
    for (const note of m.failureNotes) {
      console.log(`      ${note}`);
    }
  }

  console.log(`\n  report written to: ${runDir}`);
  console.log(
    `  overall gate status:        ${aggregate.fixturesFailed === 0 ? 'PASS' : 'FAIL'}`,
  );
}
