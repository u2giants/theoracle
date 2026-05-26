/**
 * Metric definitions per docs/oracle/06-evaluation-framework.md "Metric definitions".
 *
 * Every metric here is computed identically across all eval runs so route
 * comparisons stay apples-to-apples. Pure functions.
 */

export interface ExtractionMetrics {
  fixtureId: string;
  expectedClaims: number;
  extractedClaims: number;
  validExtractedClaims: number;
  truePositives: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  quoteValidity: number | null;
  wrongDomainRate: number | null;
  sensitiveQuarantinePass: boolean;
  duplicateRate: number;
  schemaValidity: number | null;
  /** Whether the fixture's mustBePromoted/mustBeQuarantined expectations all held. */
  gateStatus: 'PASS' | 'FAIL';
  failureNotes: string[];
}

export interface AggregateMetrics {
  fixtures: number;
  totalExpectedClaims: number;
  totalExtractedClaims: number;
  totalValidExtractedClaims: number;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  quoteValidity: number | null;
  wrongDomainRate: number | null;
  sensitiveQuarantineFixtures: number;
  sensitiveQuarantinePassRate: number | null;
  fixturesPassed: number;
  fixturesFailed: number;
}

export function safeRatio(numerator: number, denominator: number): number | null {
  if (denominator === 0) return null;
  return numerator / denominator;
}

export function f1Score(precision: number | null, recall: number | null): number | null {
  if (precision == null || recall == null) return null;
  if (precision === 0 && recall === 0) return 0;
  return (2 * precision * recall) / (precision + recall);
}

/**
 * Summary-similarity match per docs/oracle/06-evaluation-framework.md
 * "Precision" definition: "A claim is true-positive if it matches an
 * expected claim by summary similarity ≥0.85 AND has a valid exact quote."
 *
 * We use case-insensitive Jaccard similarity on word sets as the
 * deterministic approximation. 0.85 is a coarse-but-stable threshold that
 * tolerates word order shuffles + minor paraphrase but rejects unrelated
 * sentences. Tighter scorers (sentence embeddings) can replace this without
 * changing the runner contract.
 */
export function summaryMatch(a: string, b: string, threshold = 0.85): boolean {
  return jaccardSimilarity(tokenize(a), tokenize(b)) >= threshold;
}

function tokenize(s: string): Set<string> {
  return new Set(
    s
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter((w) => w.length > 0),
  );
}

function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  let intersection = 0;
  for (const x of a) {
    if (b.has(x)) intersection += 1;
  }
  const union = a.size + b.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

export function aggregateExtractionMetrics(per: ExtractionMetrics[]): AggregateMetrics {
  const totalExpected = per.reduce((s, m) => s + m.expectedClaims, 0);
  const totalExtracted = per.reduce((s, m) => s + m.extractedClaims, 0);
  const totalValid = per.reduce((s, m) => s + m.validExtractedClaims, 0);
  const totalTP = per.reduce((s, m) => s + m.truePositives, 0);

  const precision = safeRatio(totalTP, totalExtracted);
  const recall = safeRatio(totalTP, totalExpected);

  const quoteValidityNumerator = per.reduce((s, m) => s + Math.round((m.quoteValidity ?? 0) * m.extractedClaims), 0);
  const quoteValidityDenominator = totalExtracted;
  const quoteValidity = safeRatio(quoteValidityNumerator, quoteValidityDenominator);

  const wrongDomainNumerator = per.reduce(
    (s, m) => s + Math.round((m.wrongDomainRate ?? 0) * m.extractedClaims),
    0,
  );
  const wrongDomainRate = safeRatio(wrongDomainNumerator, quoteValidityDenominator);

  const sensitiveFixtures = per.filter((m) => m.failureNotes.length === 0 || m.failureNotes.some((n) => n.toLowerCase().includes('sensitive')))
    .length;
  const sensitivePassed = per.filter((m) => m.sensitiveQuarantinePass).length;
  const sensitivePassRate = per.length === 0 ? null : sensitivePassed / per.length;

  return {
    fixtures: per.length,
    totalExpectedClaims: totalExpected,
    totalExtractedClaims: totalExtracted,
    totalValidExtractedClaims: totalValid,
    precision,
    recall,
    f1: f1Score(precision, recall),
    quoteValidity,
    wrongDomainRate,
    sensitiveQuarantineFixtures: sensitiveFixtures,
    sensitiveQuarantinePassRate: sensitivePassRate,
    fixturesPassed: per.filter((m) => m.gateStatus === 'PASS').length,
    fixturesFailed: per.filter((m) => m.gateStatus === 'FAIL').length,
  };
}
