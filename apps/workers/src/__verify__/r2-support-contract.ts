/**
 * Licensed-fixture R2 support-contract audit.
 *
 * Compares three competing definitions without printing source or answer text:
 * the historical partial-overlap gate, literal answer-row fidelity, and a
 * canonical source-faithful record judged by the real matcher.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import {
  buildResponsibilitySourceInventory,
  buildResponsibilitySourceSupportRecord,
  validateResponsibilityFieldFidelity,
} from '../lib/responsibility-reader';
import {
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  scoreResponsibilityAnswerKey,
  type ResponsibilityAnswerKeyRecord,
} from '../lib/responsibility-answer-key';

const sourcePath = process.env.R2_PINNED_FIXTURE_PATH ??
  'Z:/Documentation/company process - Oracle/Licensed Team Responsibilities 2 - tagged.txt';
const source = readFileSync(sourcePath, 'utf8');
const answerKey = JSON.parse(readFileSync(
  new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
  'utf8',
)) as { sourceSha256: string; version: string; records: ResponsibilityAnswerKeyRecord[] };
assert.equal(createHash('sha256').update(source).digest('hex'), answerKey.sourceSha256);
assert.equal(answerKey.version, 'licensed-team-responsibilities-v1');
assert.equal(RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION, 'field-aware-v3');
assert.equal(answerKey.records.length, 30);

const inventory = buildResponsibilitySourceInventory([{
  id: 'support_contract_chunk',
  documentId: 'support_contract_document',
  rawText: source,
}]);
const ignored = new Set([
  'the', 'and', 'to', 'from', 'in', 'into', 'of', 'for', 'by', 'against', 'before', 'with',
]);
const tokens = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
  .split(/\s+/)
  .filter((token) => token.length > 2 && !ignored.has(token))
  .map((token) => token.replace(/(ing|ed|es|s)$/, '').replace(/e$/, ''));
const ownerAt = (span: string): string | null => {
  const value = span.match(
    /^\s*\[(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\]/i,
  )?.[1] ?? span.match(
    /^\s*\[[^\]]+\]\s*(?:\d+[.)]\s*)?(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\b/i,
  )?.[1] ?? span.match(
    /^\s*(?:\[[^\]]+\]\s*)?(Licensed Team|Lic Manager|Lic Coordinator)\b/i,
  )?.[1] ?? null;
  return value && /^Licensing Manager$/i.test(value) ? 'Lic Manager' : value;
};
const compatibleAction = (expected: string, sourceTokens: readonly string[]) => {
  const expectedTokens = tokens(expected);
  if (expectedTokens.some((token) => sourceTokens.includes(token))) return true;
  const aliases: Record<string, string[]> = { maintain: ['ensur'] };
  return expectedTokens.some((token) =>
    (aliases[token] ?? []).some((alias) => sourceTokens.includes(alias)),
  );
};
const structurallyEligible = (seed: (typeof inventory.seeds)[number]) =>
  seed.evidenceQuote.length > 0 &&
  seed.sourceEnd > seed.sourceStart &&
  !seed.parseDiagnostics.includes('ambiguous_multi_verb');

const assignRows = (candidates: number[][]) => {
  const assigned = new Map<number, number>();
  const assign = (rowIndex: number, visited: Set<number>): boolean => {
    for (const seedIndex of candidates[rowIndex] ?? []) {
      if (visited.has(seedIndex)) continue;
      visited.add(seedIndex);
      const prior = assigned.get(seedIndex);
      if (prior === undefined || assign(prior, visited)) {
        assigned.set(seedIndex, rowIndex);
        return true;
      }
    }
    return false;
  };
  answerKey.records.forEach((_record, rowIndex) => assign(rowIndex, new Set()));
  const supportedRows = [...new Set(assigned.values())].sort((a, b) => a - b);
  return {
    count: supportedRows.length,
    supportedRows: supportedRows.map((row) => row + 1),
    unsupportedRows: answerKey.records
      .map((_record, row) => row + 1)
      .filter((row) => !supportedRows.includes(row - 1)),
  };
};

const legacy = assignRows(answerKey.records.map((expected) => {
  const expectedObjectTokens = [...new Set(tokens(expected.object))];
  return inventory.seeds.flatMap((seed, seedIndex) => {
    const sourceTokens = tokens(seed.sourceSpan);
    const overlap = expectedObjectTokens.filter((token) => sourceTokens.includes(token)).length;
    return structurallyEligible(seed) &&
      ownerAt(seed.sourceSpan)?.toLowerCase() === expected.role.toLowerCase() &&
      compatibleAction(expected.action, sourceTokens) &&
      overlap >= Math.min(2, expectedObjectTokens.length)
      ? [seedIndex] : [];
  });
}));

const literalFidelity = assignRows(answerKey.records.map((expected) =>
  inventory.seeds.flatMap((seed, seedIndex) =>
    structurallyEligible(seed) && validateResponsibilityFieldFidelity(seed.sourceSpan, expected).passed
      ? [seedIndex] : [],
  ),
));

const canonicalMatcher = assignRows(answerKey.records.map((expected) =>
  inventory.seeds.flatMap((seed, seedIndex) => {
    const record = buildResponsibilitySourceSupportRecord(seed);
    return structurallyEligible(seed) && record &&
      scoreResponsibilityAnswerKey({ expected: [expected], actual: [record] }).matched === 1
      ? [seedIndex] : [];
  }),
));

assert.equal(legacy.count, 28, 'historical partial-overlap result drifted');
assert.equal(literalFidelity.count, 2, 'literal answer-row fidelity result drifted');
assert.equal(canonicalMatcher.count, 23, 'canonical source-record matcher result drifted');
console.log(JSON.stringify({
  fixtureSha256: answerKey.sourceSha256,
  answerKeyVersion: answerKey.version,
  matcherVersion: RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  threshold: 27,
  inventorySeedCount: inventory.seeds.length,
  definitions: {
    historicalPartialOverlap: legacy,
    literalAnswerRowFidelity: literalFidelity,
    canonicalSourceRecordThroughMatcher: canonicalMatcher,
  },
  conclusion: 'NO_CURRENT_SUPPORT_DEFINITION_PROVES_THE_27_OF_30_THRESHOLD_FEASIBLE',
}, null, 2));
