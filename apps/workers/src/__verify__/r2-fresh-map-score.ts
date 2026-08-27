/**
 * P3 production gate scorer: SELECT-only scoring of the ONE authorized fresh R2
 * production map against the frozen answer key and the unchanged matcher.
 *
 * It never writes, never calls a model, never supersedes a map, and never prints
 * licensed source text — only row numbers, counts and reason codes.
 *
 * Stop rule (plan_r2_fresh_production_gate.md step 7): below 27/30, any loss of a
 * row the 2026-08-11 production run matched, or any negative-control match is a hard
 * stop. Do not tune the matcher, the answer key or the validator to suit the result.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import postgres from 'postgres';
import {
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  scoreResponsibilityAnswerKey,
} from '../lib/responsibility-answer-key';

const R2_FRESH_MAP_ID = process.env.R2_FRESH_MAP_ID ?? '';
if (!R2_FRESH_MAP_ID) throw new Error('Missing R2_FRESH_MAP_ID.');

const R2_FROZEN_FIXTURE_SHA256 =
  '398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be';
const R2_FROZEN_ANSWER_KEY_VERSION = 'licensed-team-responsibilities-v1';
const R2_FROZEN_MATCHER_VERSION = 'field-aware-v3';
const R2_FROZEN_PASS_THRESHOLD = 27;
const R2_FROZEN_EXPECTED_ROWS = 30;
// The rows the 2026-08-11 production run matched; none of them may be lost.
const R2_PRODUCTION_MISSED_ROWS = [5, 14, 15, 16, 17, 19, 20, 23, 24, 26, 29];
const R2_NEGATIVE_CONTROL_ROWS = [16, 24, 26];

const suppliedUrl = process.env.R2_REPLAY_DATABASE_URL;
if (!suppliedUrl) {
  throw new Error(
    'Missing R2_REPLAY_DATABASE_URL. Supply the production session-pooler URL explicitly; this gate is SELECT-only.',
  );
}
// Supabase retired the direct `db.<ref>.supabase.co` host for IPv4 clients, so a stored
// direct URL no longer resolves. Rewrite it to the session pooler deterministically —
// same credential, same database, SELECT-only — exactly as the F5 replay gate does.
const R2_REPLAY_DEFAULT_POOLER_HOST = 'aws-1-us-east-1.pooler.supabase.com';
const directHost = suppliedUrl.match(
  /^postgres(?:ql)?:\/\/([^:]+):([^@]+)@db\.([a-z0-9]+)\.supabase\.co:\d+\/(\S+)$/,
);
const databaseUrl = directHost
  ? `postgresql://${directHost[1]}.${directHost[3]}:${directHost[2]}@${
      process.env.R2_REPLAY_POOLER_HOST ?? R2_REPLAY_DEFAULT_POOLER_HOST
    }:5432/${directHost[4]}`
  : suppliedUrl;

const answerKey = JSON.parse(
  readFileSync(
    new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
    'utf8',
  ),
) as {
  version: string;
  sourceSha256: string;
  records: Array<{ role: string; action: string; object: string }>;
};
assert.equal(answerKey.version, R2_FROZEN_ANSWER_KEY_VERSION, 'answer key version is frozen');
assert.equal(answerKey.sourceSha256, R2_FROZEN_FIXTURE_SHA256, 'fixture SHA-256 is frozen');
assert.equal(answerKey.records.length, R2_FROZEN_EXPECTED_ROWS, 'answer key still has 30 rows');
assert.equal(
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  R2_FROZEN_MATCHER_VERSION,
  'the gate is measured by the unchanged matcher',
);

const priorMatchedRows = answerKey.records
  .map((_, index) => index + 1)
  .filter((row) => !R2_PRODUCTION_MISSED_ROWS.includes(row));

const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  const maps = await sql<Array<{
    id: string;
    document_id: string;
    status: string;
    elements_json: unknown;
  }>>`
    SELECT id, document_id, status, elements_json
    FROM source_workflow_maps
    WHERE id = ${R2_FRESH_MAP_ID}::uuid
  `;
  const map = maps[0];
  if (!map) throw new Error(`Fresh map ${R2_FRESH_MAP_ID} was not found.`);

  const elements = map.elements_json as Array<Record<string, unknown>>;
  const stored = elements
    .filter(
      (element) =>
        element.shape === 'responsibilities' && element.elementKind === 'responsibility',
    )
    .map((element) => ({
      role: String(element.role ?? ''),
      action: String(element.action ?? ''),
      object: String(element.object ?? ''),
    }));

  const score = scoreResponsibilityAnswerKey({ expected: answerKey.records, actual: stored });
  assert.equal(score.matcherVersion, R2_FROZEN_MATCHER_VERSION, 'scoring used the unchanged matcher');
  const matchedRows = score.evidence
    .map((item, index) => (item.matched ? index + 1 : null))
    .filter((row): row is number => row !== null);
  const matchedSet = new Set(matchedRows);
  const missedRows = answerKey.records
    .map((_, index) => index + 1)
    .filter((row) => !matchedSet.has(row));
  const lostPriorRows = priorMatchedRows.filter((row) => !matchedSet.has(row));
  const recoveredRows = R2_PRODUCTION_MISSED_ROWS.filter((row) => matchedSet.has(row));
  const negativeControlMatches = R2_NEGATIVE_CONTROL_ROWS.filter((row) => matchedSet.has(row));

  console.log(
    JSON.stringify(
      {
        mapId: map.id,
        documentId: map.document_id,
        persistedStatus: map.status,
        matcherVersion: score.matcherVersion,
        answerKeyVersion: answerKey.version,
        storedRecords: stored.length,
        matched: score.matched,
        outOf: R2_FROZEN_EXPECTED_ROWS,
        matchedRows,
        missedRows,
        priorProductionRows: priorMatchedRows,
        lostPriorRows,
        recoveredRows,
        negativeControlMatches,
        frozenPassThreshold: R2_FROZEN_PASS_THRESHOLD,
      },
      null,
      2,
    ),
  );

  assert.deepEqual(lostPriorRows, [], 'every row the 2026-08-11 production run matched is preserved');
  assert.deepEqual(negativeControlMatches, [], 'negative-control rows 16, 24 and 26 remain unmatched');
  assert.ok(
    score.matched >= R2_FROZEN_PASS_THRESHOLD,
    `fresh map scored ${score.matched}/${R2_FROZEN_EXPECTED_ROWS}, below the frozen threshold of ${R2_FROZEN_PASS_THRESHOLD}`,
  );
  console.log(`R2 fresh production gate PASSED: ${score.matched}/${R2_FROZEN_EXPECTED_ROWS}`);
} finally {
  await sql.end({ timeout: 5 });
}
