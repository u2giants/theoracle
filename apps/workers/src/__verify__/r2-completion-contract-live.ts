/**
 * G9. LIVE prompt-contract probe for the responsibility completion call.
 *
 * Why this exists
 * ---------------
 * On 2026-08-27 a purely additive edit to `RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT` made the
 * model stop returning one record per requested seed. Every completion batch failed, the
 * stage contributed nothing, and the production map fell from 23/30 to 13/30 — losing seven
 * answer rows that had been preserved since 2026-08-11.
 *
 * Every deterministic gate in this repo passed on that change. They test plumbing; none of
 * them tests whether a LIVE model still honours the one-record-per-seed contract. That gap
 * is the reason a broken prompt reached production.
 *
 * This probe closes it. It sends a small batch of REAL seeds through the EXACT production
 * call path — `runResponsibilityCompletionModel` and `canonicalizeResponsibilityCompletionBatch`
 * — and asserts the contract the regression broke:
 *
 *   every requested seed comes back exactly once, with no omissions and no extras.
 *
 * It is deliberately NOT a CI gate: it needs the production database (for routes, settings
 * and durable audit rows) and it spends a real model call. Run it BEFORE any production run
 * that carries a prompt change. It costs a fraction of a cent and would have caught the
 * regression in seconds.
 *
 * It judges obedience to the seed contract only. It does NOT judge answer quality — the
 * frozen scorer and the fidelity validator own that, and this probe must never grow into a
 * second opinion on either.
 *
 * It writes nothing but the ordinary model-run audit rows any completion call writes. It
 * creates no map, supersedes nothing, and never prints licensed source text.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { getDirectDb } from '@oracle/db/client';
import { OracleAIClient, buildStandardAdapters } from '@oracle/ai';
import {
  buildResponsibilitySourceInventory,
  canonicalizeResponsibilityCompletionBatch,
  packResponsibilityCompletions,
} from '../lib/responsibility-reader';
import { runResponsibilityCompletionModel } from '../lib/source-workflow-read';

const FIXTURE_PATH =
  process.env.R2_PINNED_FIXTURE_PATH ??
  'Z:/Documentation/company process - Oracle/Licensed Team Responsibilities 2 - tagged.txt';
// Small on purpose. The contract either holds or it does not; proving it needs a handful of
// seeds, not a full document, and a cheap probe is a probe people actually run.
const SEED_COUNT = Number(process.env.R2_CONTRACT_SEED_COUNT ?? 8);

let source: string;
try {
  source = readFileSync(FIXTURE_PATH, 'utf8');
} catch {
  throw new Error(
    `The licensed fixture is required. Set R2_PINNED_FIXTURE_PATH or make ${FIXTURE_PATH} available.`,
  );
}

const inventory = buildResponsibilitySourceInventory([{
  id: 'completion_contract_probe_chunk',
  documentId: 'completion_contract_probe_document',
  rawText: source,
}]);
assert.ok(
  inventory.seeds.length >= SEED_COUNT,
  `the fixture must yield at least ${SEED_COUNT} seeds; got ${inventory.seeds.length}`,
);
// Spread the sample across the document rather than taking the first N, so a contract that
// only breaks on later, messier duty shapes is still caught.
const stride = Math.max(1, Math.floor(inventory.seeds.length / SEED_COUNT));
const seeds = Array.from({ length: SEED_COUNT }, (_unused, index) =>
  inventory.seeds[index * stride]!);

const pack = packResponsibilityCompletions({
  seeds,
  remainingCalls: 2,
  remainingInputTokens: 200_000,
  remainingCostUsd: 1,
  fixedInputTokensPerCall: 1_024,
  fixedOutputTokensPerCall: 128,
  maxInputTokensPerCall: 60_000,
  maxOutputTokensPerCall: 8_000,
  inputCostPerMillionTokensUsd: 5,
  outputCostPerMillionTokensUsd: 5,
});
assert.equal(pack.unscheduledIds.length, 0, 'every probe seed must be scheduled');
assert.ok(pack.batches.length >= 1, 'the probe must produce at least one batch');

const db = getDirectDb();
const client = new OracleAIClient({ adapters: buildStandardAdapters() });
const failures: string[] = [];
let requested = 0;
let returned = 0;

for (const batch of pack.batches) {
  requested += batch.seedIds.length;
  const execution = await runResponsibilityCompletionModel({
    db,
    client,
    doc: {
      fileName: 'completion-contract-probe',
      fileType: 'text/markdown',
      context: null,
    },
    mapId: 'completion-contract-probe',
    triggerRunId: 'completion-contract-probe',
    batch,
  });

  // THE CONTRACT. `canonicalizeResponsibilityCompletionBatch` throws on an omitted or
  // unexpected seed, which is exactly how the regression surfaced in production — as a
  // thrown batch, reported as `provider_failed`. Catch it here instead, and report the
  // seed ids rather than a stack trace.
  try {
    const canonical = canonicalizeResponsibilityCompletionBatch({ batch, output: execution.output });
    const returnedIds = canonical.map((record) => record.responsibilityId);
    const requestedIds = new Set(batch.seedIds);
    const missing = batch.seedIds.filter((id) => !returnedIds.includes(id));
    const extra = returnedIds.filter((id) => !requestedIds.has(id));
    const duplicated = returnedIds.filter((id, index) => returnedIds.indexOf(id) !== index);
    if (missing.length > 0) failures.push(`batch ${batch.batchIndex}: omitted ${missing.length} seed(s)`);
    if (extra.length > 0) failures.push(`batch ${batch.batchIndex}: returned ${extra.length} unrequested seed(s)`);
    if (duplicated.length > 0) failures.push(`batch ${batch.batchIndex}: duplicated ${duplicated.length} seed(s)`);
    returned += returnedIds.length;
  } catch (error) {
    failures.push(
      `batch ${batch.batchIndex}: canonicalization threw — ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
}

console.log(
  JSON.stringify(
    {
      fixtureSha256: createHash('sha256').update(source).digest('hex'),
      seedsProbed: seeds.length,
      batches: pack.batches.length,
      requestedRecords: requested,
      returnedRecords: returned,
      contractFailures: failures,
    },
    null,
    2,
  ),
);

assert.deepEqual(
  failures,
  [],
  'the completion prompt must return exactly one record for every requested seed',
);
console.log('Responsibility completion contract holds against a live model.');
