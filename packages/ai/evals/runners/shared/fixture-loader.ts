/**
 * Fixture loader — reads every JSON file in a category's fixtures directory,
 * pairs it with the matching canned mock output (by fixtureId numeric prefix),
 * and validates the shape.
 *
 * Pure file I/O + JSON parsing. No DB, no LLM. Per
 * docs/oracle/06-evaluation-framework.md.
 */

import { readdir, readFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const EVAL_ROOT = resolve(__dirname, '..', '..');

// ─────────────────────────────────────────────────────────────────────────
// Fixture shape (per 06-evaluation-framework.md)
// ─────────────────────────────────────────────────────────────────────────

export type EvalCategory =
  | 'extraction'
  | 'retrieval'
  | 'synthesis'
  | 'validation'
  | 'segmentation'
  | 'cache';

export interface FixtureFile<TInputs = unknown, TExpected = unknown> {
  fixtureId: string;
  category: EvalCategory;
  description: string;
  traps: string[];
  inputs: TInputs;
  expected: TExpected;
  scoringRules?: {
    minPrecision?: number;
    minRecall?: number;
    minQuoteValidity?: number;
    maxWrongDomainRate?: number;
    requireQuarantineFor?: string[];
    forbidExtractionFor?: string[];
  };
}

export interface ExtractionFixtureInputs {
  sourceType: 'message' | 'document_chunk';
  messages?: Array<{
    messageId: string;
    employeeId: string;
    text: string;
    createdAt: string;
  }>;
  documentChunk?: {
    chunkId: string;
    documentId: string;
    text: string;
    pageNumber?: number;
  };
  routeId: string;
  /** Active top-domains the validator should accept for this fixture. */
  activeTopDomainIds?: string[];
  /** Canonical entity registry slice for entity resolution checks. */
  entityRegistry?: Array<{
    id: string;
    entityType: string;
    canonicalValue: string;
    aliases?: string[];
  }>;
}

export interface ExtractionFixtureExpected {
  claims: Array<{
    summary: string;
    claimType: string;
    domains: string[];
    stance?: string;
    exactQuote: string;
    sourceMessageId?: string;
    sourceDocumentChunkId?: string;
    assertedByEmployeeId?: string;
    mustBePromoted: boolean;
    mustBeQuarantined?: boolean;
    mustBeFlaggedSensitive?: boolean;
  }>;
  forbiddenClaims?: Array<{ reason: string; spans?: string[] }>;
  expectedSensitivityFlags?: {
    anyContainsSensitiveHRData?: boolean;
    anyContainsSensitivePersonalData?: boolean;
    anyIsPersonalConflict?: boolean;
  };
}

export type ExtractionFixture = FixtureFile<ExtractionFixtureInputs, ExtractionFixtureExpected>;

// ─────────────────────────────────────────────────────────────────────────
// Canned mock output shape — matches packages/ai/src/prompts/extraction-system.ts
// ExtractionOutputSchema. We keep the shape declaration local so the loader
// doesn't drag the runtime Zod schema into eval scope.
// ─────────────────────────────────────────────────────────────────────────

export interface CannedExtractionClaim {
  claimType: string;
  summary: string;
  impactScore: number;
  confidenceScore: number;
  domains: string[];
  evidence: {
    exactQuote: string;
    sourceMessageId: string;
    confidence: number;
  };
  semanticRole?: string;
  requiresReview: boolean;
  suggestedGaps?: Array<{
    questionToAsk: string;
    whyItMatters: string;
    priority: string;
  }>;
  /** Per-fixture override — model's claim of sensitivity. R5.5 candidate flags. */
  sensitivityFlags?: {
    containsSensitivePersonalData?: boolean;
    containsSensitiveHRData?: boolean;
    isPersonalConflict?: boolean;
    sensitivityReason?: string;
  };
}

export interface CannedExtractionOutput {
  claims: CannedExtractionClaim[];
  segmentSummary?: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Paired fixture + mock loader
// ─────────────────────────────────────────────────────────────────────────

export interface LoadedExtractionFixture {
  fixture: ExtractionFixture;
  cannedOutput: CannedExtractionOutput;
  fixturePath: string;
  mockPath: string;
}

/**
 * Find every extraction fixture file, load it + its paired canned LLM
 * output. The pairing key is the **numeric prefix** of the fixture's
 * filename — `transcript-01-routine-handoff.json` pairs with
 * `mocks/canned-extraction-outputs/transcript-01.json`.
 */
export async function loadExtractionFixtures(): Promise<LoadedExtractionFixture[]> {
  const fixturesDir = join(EVAL_ROOT, 'fixtures', 'extraction');
  const mocksDir = join(EVAL_ROOT, 'mocks', 'canned-extraction-outputs');

  const fixtureFiles = (await readdir(fixturesDir)).filter((f) => f.endsWith('.json')).sort();
  const out: LoadedExtractionFixture[] = [];

  for (const file of fixtureFiles) {
    const fixturePath = join(fixturesDir, file);
    const fixture = JSON.parse(await readFile(fixturePath, 'utf8')) as ExtractionFixture;

    validateFixtureShape(fixture, fixturePath);

    const mockBaseName = extractMockBaseName(file);
    const mockPath = join(mocksDir, `${mockBaseName}.json`);
    let cannedOutput: CannedExtractionOutput;
    try {
      cannedOutput = JSON.parse(await readFile(mockPath, 'utf8')) as CannedExtractionOutput;
    } catch (err) {
      throw new Error(
        `Fixture ${file} expects canned mock at ${mockPath}, but reading failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    out.push({ fixture, cannedOutput, fixturePath, mockPath });
  }
  return out;
}

/**
 * Derive the mock filename from the fixture filename. `transcript-01-foo.json`
 * → `transcript-01`. The numeric prefix is the stable pairing key; everything
 * after the second dash is a human-readable description that can change
 * without breaking the mock pairing.
 */
function extractMockBaseName(fixtureFileName: string): string {
  // Strip `.json`
  const stem = fixtureFileName.replace(/\.json$/, '');
  // Match `<word>-<digits>` at the start.
  const m = stem.match(/^([a-z]+-\d+)/);
  if (m) return m[1]!;
  // Fall back to the full stem (the user can name fixtures + mocks identically
  // if they prefer).
  return stem;
}

function validateFixtureShape(fx: ExtractionFixture, path: string): void {
  if (!fx.fixtureId) throw new Error(`Fixture ${path} is missing fixtureId`);
  if (fx.category !== 'extraction') {
    throw new Error(`Fixture ${path} has category=${fx.category}; expected 'extraction'`);
  }
  if (!Array.isArray(fx.inputs.messages) && !fx.inputs.documentChunk) {
    throw new Error(`Fixture ${path} has no messages[] or documentChunk`);
  }
  if (!Array.isArray(fx.expected.claims)) {
    throw new Error(`Fixture ${path} expected.claims is not an array`);
  }
}
