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

import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { AggregateMetrics, ExtractionMetrics } from './metrics';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNS_ROOT = resolve(__dirname, '..', '..', 'runs');

export async function writeExtractionReport(args: {
  perFixture: ExtractionMetrics[];
  aggregate: AggregateMetrics;
  mode: 'mock' | 'live';
  routeId: string;
}): Promise<{ runDir: string }> {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
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
