import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import {
  buildResponsibilitySourceInventory,
  responsibilityCompletionRequest,
} from '../lib/responsibility-reader';
import {
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
} from '../lib/responsibility-answer-key';

const sourcePath =
  process.env.R2_PINNED_FIXTURE_PATH ??
  'Z:/Documentation/company process - Oracle/Licensed Team Responsibilities 2 - tagged.txt';
let source: string;
try {
  source = readFileSync(sourcePath, 'utf8');
} catch {
  throw new Error(
    `Pinned R2 fixture is required for this explicit verifier. Set R2_PINNED_FIXTURE_PATH or make ${sourcePath} available.`,
  );
}
const answerKey = JSON.parse(
  readFileSync(
    new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
    'utf8',
  ),
) as {
  sourceSha256: string;
  version: string;
  records: Array<{ role: string; action: string; object: string }>;
};
assert.equal(createHash('sha256').update(source).digest('hex'), answerKey.sourceSha256);
assert.equal(answerKey.version, 'licensed-team-responsibilities-v1');
assert.equal(RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION, 'field-aware-v3');
assert.equal(answerKey.records.length, 30);

const inventory = buildResponsibilitySourceInventory([{
  id: 'pinned_fixture_inventory_chunk',
  documentId: 'pinned_fixture_inventory_document',
  rawText: source,
}]);
const ignored = new Set([
  'the', 'and', 'to', 'from', 'in', 'into', 'of', 'for', 'by', 'against', 'before', 'with',
]);
const tokens = (value: string) =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/)
    .filter((token) => token.length > 2 && !ignored.has(token))
    .map((token) => token.replace(/(ing|ed|es|s)$/, '').replace(/e$/, ''));
const tokenMatches = (left: string, right: string) => left === right;
const ownerAt = (span: string): string | null => {
  const bracketOwner = span.match(/^\s*\[(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\]/i)?.[1];
  if (bracketOwner) return /^Licensing Manager$/i.test(bracketOwner) ? 'Lic Manager' : bracketOwner;
  const nestedSubject = span.match(
    /^\s*\[[^\]]+\]\s*(?:\d+[.)]\s*)?(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\b/i,
  )?.[1];
  if (nestedSubject) return /^Licensing Manager$/i.test(nestedSubject) ? 'Lic Manager' : nestedSubject;
  const explicitSubject = span.match(
    /^\s*(?:\[[^\]]+\]\s*)?(Licensed Team|Lic Manager|Lic Coordinator)\b/i,
  )?.[1];
  if (explicitSubject) return explicitSubject;
  return null;
};
const compatibleAction = (expected: string, sourceActionTokens: readonly string[]) => {
  const expectedTokens = tokens(expected);
  if (expectedTokens.some((token) => sourceActionTokens.some((sourceToken) => tokenMatches(sourceToken, token)))) {
    return true;
  }
  const aliases: Record<string, string[]> = {
    maintain: ['ensur'],
  };
  return expectedTokens.some((token) =>
    (aliases[token] ?? []).some((alias) => sourceActionTokens.includes(alias))
  );
};
const crossDutyInventory = buildResponsibilitySourceInventory([{
  id: 'cross_duty_guard_chunk',
  documentId: 'cross_duty_guard_document',
  rawText: '- Service Desk reviews packets.\n- Service Desk sends notices.',
}]);
const reviewSeed = crossDutyInventory.seeds.find((seed) => /reviews packets/i.test(seed.sourceSpan))!;
assert.equal(
  compatibleAction('send', tokens(reviewSeed.sourceSpan)),
  false,
  'an action in a neighboring duty cannot make this seed eligible',
);

const candidates = answerKey.records.map((record) => {
  const objectTokens = [...new Set(tokens(record.object))];
  return inventory.seeds.flatMap((seed, seedIndex) => {
    if (ownerAt(seed.sourceSpan)?.toLowerCase() !== record.role.toLowerCase()) {
      return [];
    }
    const seedTokens = tokens(seed.sourceSpan);
    const request = responsibilityCompletionRequest(seed);
    const contextualObjectTokens = tokens(request.sourceSpan);
    // This P5 gate asks whether each normalized answer row has a credible source span for the
    // completion model. It intentionally does not require raw source wording to equal the final
    // normalized object: the frozen answer key paraphrases several source phrases. The later P7
    // gate applies field-aware-v3 to completed model records. Here we require exact owner context,
    // an action-family match, multiple object anchors, and a unique seed assignment.
    const actionSupported = compatibleAction(record.action, seedTokens);
    const objectOverlap = objectTokens.filter((token) =>
      contextualObjectTokens.some((seedToken) => tokenMatches(seedToken, token))
    ).length;
    const structurallyEligible =
      seed.evidenceQuote.length > 0 &&
      seed.sourceEnd > seed.sourceStart &&
      !seed.parseDiagnostics.includes('ambiguous_multi_verb');
    return actionSupported && objectOverlap >= Math.min(2, objectTokens.length) && structurallyEligible
      ? [seedIndex]
      : [];
  });
});
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
const supported = answerKey.records.reduce(
  (count, _record, rowIndex) => count + (assign(rowIndex, new Set()) ? 1 : 0),
  0,
);
const supportedRows = [...new Set(assigned.values())].sort((a, b) => a - b);
const unsupportedRows = answerKey.records
  .map((_record, index) => index)
  .filter((index) => !supportedRows.includes(index));
console.log(
  `Pinned fixture inventory support: ${supported}/30 unique role-aware rows from ${inventory.seeds.length} source-bound seeds`,
);
console.log(`Supported answer rows (1-based): ${supportedRows.map((index) => index + 1).join(', ')}`);
console.log(`Unsupported answer rows (1-based): ${unsupportedRows.map((index) => index + 1).join(', ') || 'none'}`);
assert.ok(supported >= 27, `Pinned inventory supports only ${supported}/30 unique role-aware rows.`);
