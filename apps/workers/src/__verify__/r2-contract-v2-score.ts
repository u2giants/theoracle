/** SELECT-only scorer for the owner-approved R2 evaluation contract v2. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import postgres from 'postgres';
import {
  resolveEnclosingResponsibilityDutySpan,
  validateResponsibilityFieldFidelity,
} from '../lib/responsibility-reader';
import {
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  scoreResponsibilityAnswerKey,
  type ResponsibilityAnswerKeyRecord,
} from '../lib/responsibility-answer-key';

const mapId = process.env.R2_FRESH_MAP_ID ?? '';
if (!mapId) throw new Error('Missing R2_FRESH_MAP_ID.');
const suppliedUrl = process.env.R2_REPLAY_DATABASE_URL;
if (!suppliedUrl) throw new Error('Missing R2_REPLAY_DATABASE_URL. This scorer is SELECT-only.');
const directHost = suppliedUrl.match(
  /^postgres(?:ql)?:\/\/([^:]+):([^@]+)@db\.([a-z0-9]+)\.supabase\.co:\d+\/(\S+)$/,
);
const databaseUrl = directHost
  ? `postgresql://${directHost[1]}.${directHost[3]}:${directHost[2]}@${
      process.env.R2_REPLAY_POOLER_HOST ?? 'aws-1-us-east-1.pooler.supabase.com'
    }:5432/${directHost[4]}`
  : suppliedUrl;

const answerKey = JSON.parse(readFileSync(
  new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
  'utf8',
)) as { version: string; sourceSha256: string; records: ResponsibilityAnswerKeyRecord[] };
const contract = JSON.parse(readFileSync(
  new URL('../__fixtures__/licensed-team-responsibilities-contract-v2.json', import.meta.url),
  'utf8',
)) as {
  version: string;
  sourceAnswerKeyVersion: string;
  sourceSha256: string;
  matcherVersion: string;
  eligibleRows: number[];
  unsupportedRows: number[];
  passThreshold: number;
};
assert.equal(contract.sourceAnswerKeyVersion, answerKey.version);
assert.equal(contract.sourceSha256, answerKey.sourceSha256);
assert.equal(contract.matcherVersion, RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION);
assert.equal(contract.eligibleRows.length, 25);
assert.equal(contract.passThreshold, 23);

const eligibleExpected = contract.eligibleRows.map((row) => answerKey.records[row - 1]!);
const unsupportedExpected = contract.unsupportedRows.map((row) => answerKey.records[row - 1]!);
const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  const maps = await sql<Array<{
    id: string;
    document_id: string;
    status: string;
    elements_json: unknown;
    file_name: string;
    file_type: string;
  }>>`
    SELECT swm.id, swm.document_id, swm.status, swm.elements_json, d.file_name, d.file_type
    FROM source_workflow_maps swm
    JOIN documents d ON d.id = swm.document_id
    WHERE swm.id = ${mapId}::uuid
  `;
  const map = maps[0];
  if (!map) throw new Error(`Map ${mapId} was not found.`);
  const stored = (map.elements_json as Array<Record<string, unknown>>)
    .filter((element) =>
      element.shape === 'responsibilities' && element.elementKind === 'responsibility')
    .map((element) => ({
      elementId: String(element.elementId ?? ''),
      role: String(element.role ?? ''),
      action: String(element.action ?? ''),
      object: String(element.object ?? ''),
      trigger: element.trigger == null ? null : String(element.trigger),
      evidenceQuote: String(element.evidenceQuote ?? ''),
      chunkId: String(element.chunkId ?? ''),
    }));
  const chunks = await sql<Array<{ id: string; raw_text: string }>>`
    SELECT id, raw_text FROM document_chunks WHERE document_id = ${map.document_id}::uuid
  `;
  const chunkText = new Map(chunks.map((chunk) => [chunk.id, chunk.raw_text]));
  const score = scoreResponsibilityAnswerKey({ expected: eligibleExpected, actual: stored });
  const matchedRows = score.evidence.flatMap((item, index) =>
    item.matched ? [contract.eligibleRows[index]!] : []);
  const missedRows = contract.eligibleRows.filter((row) => !matchedRows.includes(row));
  const sourceFaithfulMatchedRows = score.evidence.flatMap((item, index) => {
    if (!item.matched || !item.actual) return [];
    const record = stored.find((candidate) =>
      candidate.role === item.actual!.role &&
      candidate.action === item.actual!.action &&
      candidate.object === item.actual!.object);
    if (!record) return [];
    const rawText = chunkText.get(record.chunkId);
    if (!rawText) return [];
    const sourceSpan = resolveEnclosingResponsibilityDutySpan({
      rawText,
      evidenceQuote: record.evidenceQuote,
      fileType: map.file_type,
      fileName: map.file_name,
    });
    return sourceSpan && validateResponsibilityFieldFidelity(sourceSpan, record).passed
      ? [contract.eligibleRows[index]!] : [];
  });
  const unsupportedMatches = contract.unsupportedRows.filter((_row, index) =>
    scoreResponsibilityAnswerKey({ expected: [unsupportedExpected[index]!], actual: stored }).matched === 1);
  console.log(JSON.stringify({
    mapId: map.id,
    documentId: map.document_id,
    persistedStatus: map.status,
    contractVersion: contract.version,
    matcherVersion: score.matcherVersion,
    storedRecordCount: stored.length,
    matched: score.matched,
    outOf: contract.eligibleRows.length,
    passThreshold: contract.passThreshold,
    matchedRows,
    sourceFaithfulMatchedRows,
    missedRows,
    unsupportedMatches,
  }, null, 2));
  assert.deepEqual(unsupportedMatches, [], 'unsupported rows must remain unmatched');
  assert.deepEqual(
    sourceFaithfulMatchedRows,
    matchedRows,
    'every matched eligible row must have a persisted one-span source-fidelity witness',
  );
  assert.ok(
    score.matched >= contract.passThreshold,
    `map scored ${score.matched}/${contract.eligibleRows.length}, below ${contract.passThreshold}`,
  );
  console.log(`R2 contract v2 PASSED: ${score.matched}/${contract.eligibleRows.length}`);
} finally {
  await sql.end({ timeout: 5 });
}
