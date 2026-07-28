import { normalizeResponsibilityPart } from '@oracle/engines';

export const RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION = 'field-aware-v3';

export type ResponsibilityAnswerKeyRecord = {
  role: string;
  action: string;
  object: string;
};

export type ResponsibilityAnswerKeyMatchEvidence = {
  expected: ResponsibilityAnswerKeyRecord;
  actual: ResponsibilityAnswerKeyRecord | null;
  matched: boolean;
  method: 'exact' | 'field_aware' | 'none';
  roleExact: boolean;
  actionMatched: boolean;
  objectTokenCoverage: number;
  negationConflict: boolean;
  qualityRank: number;
};

const STOP_WORDS = new Set([
  'a', 'an', 'and', 'at', 'by', 'for', 'from', 'in', 'into', 'of', 'on', 'the', 'to', 'with',
]);
const NEGATIONS = new Set(['no', 'not', 'never', 'without']);
const PLURAL_EQUIVALENTS: Record<string, string> = {
  assets: 'asset',
  approvals: 'approval',
  audits: 'audit',
  contracts: 'contract',
  forms: 'form',
  guides: 'guide',
  lines: 'line',
  logos: 'logo',
  partners: 'partner',
  photos: 'photo',
  reports: 'report',
  revisions: 'revision',
  submissions: 'submission',
  systems: 'system',
  tests: 'test',
  units: 'unit',
};
const ACTION_EQUIVALENTS = [
  ['request', 'reach out'],
  ['fill out', 'complete'],
  ['maintain', 'ensure'],
] as const;

function tokens(value: string): string[] {
  const compounds = normalizeResponsibilityPart(value)
    .replace(/\bmaster data\b/g, 'masterdata')
    .replace(/\bdesign flow\b/g, 'designflow')
    .replace(/\bshared lic\b/g, 'sharedlic')
    .replace(/\bcold lion\b/g, 'coldlion');
  return compounds
    .split(' ')
    .filter(Boolean)
    .map((token) => PLURAL_EQUIVALENTS[token] ?? token);
}

function contentTokens(value: string): string[] {
  return tokens(value).filter((token) => !STOP_WORDS.has(token));
}

function hasNegationConflict(expected: string, actual: string): boolean {
  const normalizedNegations = (value: string): Set<string> => {
    const normalized = normalizeResponsibilityPart(value)
      .replace(/\bdon t\b|\bdont\b|\bcan t\b|\bcant\b|\bcannot\b|\bcan not\b/g, ' not ');
    return new Set(tokens(normalized).filter((token) => NEGATIONS.has(token)));
  };
  const expectedNegations = normalizedNegations(expected);
  const actualNegations = normalizedNegations(actual);
  return (
    expectedNegations.size !== actualNegations.size ||
    [...expectedNegations].some((token) => !actualNegations.has(token))
  );
}

function actionMatches(expected: string, actual: string): boolean {
  const expectedNormalized = normalizeResponsibilityPart(expected);
  const actualNormalized = normalizeResponsibilityPart(actual);
  if (expectedNormalized === actualNormalized) return true;
  const expectedTokens = contentTokens(expected);
  const actualTokens = new Set(contentTokens(actual));
  if (expectedTokens.length > 0 && expectedTokens.every((token) => actualTokens.has(token))) return true;
  return ACTION_EQUIVALENTS.some(
    (group) =>
      group.some((phrase) => phrase === expectedNormalized) &&
      group.some((phrase) => actualNormalized.includes(phrase)),
  );
}

function objectCoverage(expected: string, actual: string): number {
  const expectedTokens = [...new Set(contentTokens(expected))];
  if (expectedTokens.length === 0) return 0;
  const actualTokens = new Set(contentTokens(actual));
  return expectedTokens.filter((token) => actualTokens.has(token)).length / expectedTokens.length;
}

function evidenceFor(
  expected: ResponsibilityAnswerKeyRecord,
  actual: ResponsibilityAnswerKeyRecord,
): ResponsibilityAnswerKeyMatchEvidence {
  const exact =
    [expected.role, expected.action, expected.object].map(normalizeResponsibilityPart).join('|') ===
    [actual.role, actual.action, actual.object].map(normalizeResponsibilityPart).join('|');
  const roleExact =
    normalizeResponsibilityPart(expected.role) === normalizeResponsibilityPart(actual.role);
  const negationConflict = hasNegationConflict(
    `${expected.action} ${expected.object}`,
    `${actual.action} ${actual.object}`,
  );
  const actionMatched = actionMatches(expected.action, actual.action);
  const objectTokenCoverage = objectCoverage(expected.object, actual.object);
  const expectedObjectTokens = contentTokens(expected.object).length;
  const objectMatched =
    expectedObjectTokens >= 2
      ? objectTokenCoverage === 1
      : normalizeResponsibilityPart(expected.object) === normalizeResponsibilityPart(actual.object);
  const matched = exact || (roleExact && actionMatched && objectMatched && !negationConflict);
  return {
    expected,
    actual,
    matched,
    method: exact ? 'exact' : matched ? 'field_aware' : 'none',
    roleExact,
    actionMatched,
    objectTokenCoverage,
    negationConflict,
    qualityRank: exact ? 0 : matched ? 1 : 2,
  };
}

export function scoreResponsibilityAnswerKey(args: {
  expected: readonly ResponsibilityAnswerKeyRecord[];
  actual: readonly ResponsibilityAnswerKeyRecord[];
}): {
  matcherVersion: typeof RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION;
  matched: number;
  expected: number;
  recall: number;
  missing: ResponsibilityAnswerKeyRecord[];
  evidence: ResponsibilityAnswerKeyMatchEvidence[];
} {
  const stableActuals = [...args.actual].sort((a, b) =>
    [a.role, a.action, a.object]
      .map(normalizeResponsibilityPart)
      .join('|')
      .localeCompare([b.role, b.action, b.object].map(normalizeResponsibilityPart).join('|')),
  );
  const allCandidates = args.expected.flatMap((expected, expectedIndex) =>
    stableActuals.map((actual, actualIndex) => ({
      expectedIndex,
      actualIndex,
      evidence: evidenceFor(expected, actual),
      actionSurplus: Math.max(0, contentTokens(actual.action).length - contentTokens(expected.action).length),
      objectSurplus: Math.max(0, contentTokens(actual.object).length - contentTokens(expected.object).length),
    })),
  );
  const assignable = allCandidates
    .filter((candidate) => candidate.evidence.matched)
    .sort(
      (a, b) =>
        a.evidence.qualityRank - b.evidence.qualityRank ||
        a.objectSurplus - b.objectSurplus ||
        a.actionSurplus - b.actionSurplus ||
        a.expectedIndex - b.expectedIndex ||
        a.actualIndex - b.actualIndex,
    );
  const assignedExpected = new Map<number, ResponsibilityAnswerKeyMatchEvidence>();
  const assignedActual = new Set<number>();
  for (const candidate of assignable) {
    if (assignedExpected.has(candidate.expectedIndex) || assignedActual.has(candidate.actualIndex)) continue;
    assignedExpected.set(candidate.expectedIndex, candidate.evidence);
    assignedActual.add(candidate.actualIndex);
  }
  const evidence = args.expected.map((expected, expectedIndex) => {
    const assigned = assignedExpected.get(expectedIndex);
    if (assigned) return assigned;
    const best = allCandidates
      .filter((candidate) => candidate.expectedIndex === expectedIndex)
      .sort(
        (a, b) =>
          Number(b.evidence.roleExact) - Number(a.evidence.roleExact) ||
          Number(b.evidence.actionMatched) - Number(a.evidence.actionMatched) ||
          b.evidence.objectTokenCoverage - a.evidence.objectTokenCoverage ||
          a.actualIndex - b.actualIndex,
      )[0]?.evidence;
    return best ? { ...best, matched: false, method: 'none' as const, qualityRank: 2 } : {
      expected,
      actual: null,
      matched: false,
      method: 'none' as const,
      roleExact: false,
      actionMatched: false,
      objectTokenCoverage: 0,
      negationConflict: false,
      qualityRank: 2,
    };
  });
  const missing = evidence.filter((item) => !item.matched).map((item) => item.expected);
  return {
    matcherVersion: RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
    matched: args.expected.length - missing.length,
    expected: args.expected.length,
    recall: args.expected.length === 0 ? 1 : (args.expected.length - missing.length) / args.expected.length,
    missing,
    evidence,
  };
}
