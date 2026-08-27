/**
 * Correction-cycle diagnostic (2026-08-27, authorized after the 22/30 production gate).
 *
 * The one authorized fresh run scored 22/30. Rows 5, 14, 15, 19 and 23 are the real
 * shortfall (16 and 26 are unsupported by the source; 16/24/26 are the negative controls).
 * This script answers ONE question per missed row, read-only:
 *
 *   Did the reader produce NO candidate record on that duty's source span at all,
 *   or did it produce one that fails field fidelity / the frozen matcher?
 *
 * Those two causes need completely different fixes, and guessing between them is what the
 * previous cycle did. SELECT-only: it reads one map and its chunks, writes nothing, calls
 * no model, and prints only row numbers, counts, reason codes and field-level token
 * diagnostics — never licensed source text.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import postgres from 'postgres';
import {
  buildResponsibilitySourceInventory,
  correctResponsibilityFinalRecord,
  resolveEnclosingResponsibilityDutySpan,
  responsibilityCompletionRequest,
  validateResponsibilityFieldFidelity,
  type ResponsibilityInventorySeed,
} from '../lib/responsibility-reader';
import {
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  scoreResponsibilityAnswerKey,
} from '../lib/responsibility-answer-key';

const MAP_ID = process.env.R2_FRESH_MAP_ID ?? 'aa713247-e30f-4b0c-9b93-e02fdefd4048';
const MISSED_ROWS = (process.env.R2_MISSED_ROWS ?? '5,14,15,19,23')
  .split(',')
  .map((value) => Number(value.trim()))
  .filter((value) => Number.isInteger(value) && value >= 1);

const suppliedUrl = process.env.R2_REPLAY_DATABASE_URL;
if (!suppliedUrl) throw new Error('Missing R2_REPLAY_DATABASE_URL. This diagnostic is SELECT-only.');
const R2_REPLAY_DEFAULT_POOLER_HOST = 'aws-1-us-east-1.pooler.supabase.com';
const directHost = suppliedUrl.match(
  /^postgres(?:ql)?:\/\/([^:]+):([^@]+)@db\.([a-z0-9]+)\.supabase\.co:\d+\/(\S+)$/,
);
const databaseUrl = directHost
  ? `postgresql://${directHost[1]}.${directHost[3]}:${directHost[2]}@${
      process.env.R2_REPLAY_POOLER_HOST ?? R2_REPLAY_DEFAULT_POOLER_HOST
    }:5432/${directHost[4]}`
  : suppliedUrl;

const answerRow = (row: number) => {
  const record = answerKeyRecords[row - 1];
  if (!record) throw new Error(`Answer key has no row ${row}.`);
  return record;
};

const answerKey = JSON.parse(
  readFileSync(
    new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
    'utf8',
  ),
) as { version: string; records: Array<{ role: string; action: string; object: string }> };
assert.equal(answerKey.version, 'licensed-team-responsibilities-v1');
const answerKeyRecords = answerKey.records;
assert.equal(RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION, 'field-aware-v3');

// Same normalization the pinned-inventory gate uses, so "does the source support this row"
// is answered here exactly as that gate answers it.
const ignored = new Set([
  'the', 'and', 'to', 'from', 'in', 'into', 'of', 'for', 'by', 'against', 'before', 'with',
]);
const tokens = (value: string) =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/)
    .filter((token) => token.length > 2 && !ignored.has(token))
    .map((token) => token.replace(/(ing|ed|es|s)$/, '').replace(/e$/, ''));
const ownerAt = (span: string): string | null => {
  const bracketOwner = span.match(
    /^\s*\[(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\]/i,
  )?.[1];
  if (bracketOwner) return /^Licensing Manager$/i.test(bracketOwner) ? 'Lic Manager' : bracketOwner;
  const nested = span.match(
    /^\s*\[[^\]]+\]\s*(?:\d+[.)]\s*)?(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\b/i,
  )?.[1];
  if (nested) return /^Licensing Manager$/i.test(nested) ? 'Lic Manager' : nested;
  return span.match(/^\s*(?:\[[^\]]+\]\s*)?(Licensed Team|Lic Manager|Lic Coordinator)\b/i)?.[1] ?? null;
};
const compatibleAction = (expected: string, sourceActionTokens: readonly string[]) => {
  const expectedTokens = tokens(expected);
  if (expectedTokens.some((token) => sourceActionTokens.includes(token))) return true;
  const aliases: Record<string, string[]> = { maintain: ['ensur'] };
  return expectedTokens.some((token) =>
    (aliases[token] ?? []).some((alias) => sourceActionTokens.includes(alias)),
  );
};

type StoredRecord = {
  elementId: string;
  role: string;
  action: string;
  object: string;
  trigger: string | null;
  evidenceQuote: string;
  chunkId: string;
};

const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  const maps = await sql<Array<{
    id: string;
    document_id: string;
    status: string;
    file_name: string;
    file_type: string;
    elements_json: unknown;
  }>>`
    SELECT swm.id, swm.document_id, swm.status, d.file_name, d.file_type, swm.elements_json
    FROM source_workflow_maps swm JOIN documents d ON d.id = swm.document_id
    WHERE swm.id = ${MAP_ID}::uuid
  `;
  const map = maps[0];
  if (!map) throw new Error(`Map ${MAP_ID} was not found.`);

  const stored: StoredRecord[] = (map.elements_json as Array<Record<string, unknown>>)
    .filter((e) => e.shape === 'responsibilities' && e.elementKind === 'responsibility')
    .map((e) => ({
      elementId: String(e.elementId ?? ''),
      role: String(e.role ?? ''),
      action: String(e.action ?? ''),
      object: String(e.object ?? ''),
      trigger: e.trigger === null || e.trigger === undefined ? null : String(e.trigger),
      evidenceQuote: String(e.evidenceQuote ?? ''),
      chunkId: String(e.chunkId ?? ''),
    }));

  const chunkRows = await sql<Array<{ id: string; raw_text: string }>>`
    SELECT id, raw_text
    FROM document_chunks
    WHERE document_id = ${map.document_id}::uuid
    ORDER BY chunk_index
  `;
  const chunkText = new Map(chunkRows.map((c) => [c.id, c.raw_text]));
  const inventory = buildResponsibilitySourceInventory(
    chunkRows.map((c) => ({ id: c.id, documentId: map.document_id, rawText: c.raw_text })),
  );

  // Which seed(s) in the REAL document support each missed row, by the pinned gate's rule.
  const supportingSeeds = (row: number) => {
    const record = answerRow(row);
    const objectTokens = [...new Set(tokens(record.object))];
    return inventory.seeds
      .map((seed, seedIndex) => ({ seed, seedIndex }))
      .filter(({ seed }) => {
        if (ownerAt(seed.sourceSpan)?.toLowerCase() !== record.role.toLowerCase()) return false;
        const contextual = tokens(responsibilityCompletionRequest(seed).sourceSpan);
        const overlap = objectTokens.filter((token) => contextual.includes(token)).length;
        return (
          compatibleAction(record.action, tokens(seed.sourceSpan)) &&
          overlap >= Math.min(2, objectTokens.length) &&
          seed.evidenceQuote.length > 0 &&
          seed.sourceEnd > seed.sourceStart &&
          !seed.parseDiagnostics.includes('ambiguous_multi_verb')
        );
      });
  };

  // Which stored record, if any, sits on a given seed's span.
  const recordsOnSeed = (seed: ResponsibilityInventorySeed) =>
    stored.filter((record) => {
      if (record.chunkId !== seed.chunkId) return false;
      const rawText = chunkText.get(record.chunkId);
      if (!rawText) return false;
      const span = resolveEnclosingResponsibilityDutySpan({
        rawText,
        evidenceQuote: record.evidenceQuote,
        fileType: map.file_type,
        fileName: map.file_name,
      });
      return span === seed.sourceSpan;
    });

  // Does one record, in isolation, satisfy the row under the frozen matcher?
  const matchesRowAlone = (row: number, record: { role: string; action: string; object: string }) =>
    scoreResponsibilityAnswerKey({
      expected: [answerRow(row)],
      actual: [{ role: record.role, action: record.action, object: record.object }],
    }).matched === 1;

  const report = MISSED_ROWS.map((row) => {
    const expected = answerRow(row);
    const seeds = supportingSeeds(row);
    const perSeed = seeds.map(({ seed, seedIndex }) => {
      const records = recordsOnSeed(seed);
      return {
        seedIndex,
        chunkId: seed.chunkId,
        seedParseDiagnostics: seed.parseDiagnostics,
        storedRecordsOnThisSpan: records.length,
        records: records.map((record) => {
          const fidelity = validateResponsibilityFieldFidelity(seed.sourceSpan, record);
          const correction = correctResponsibilityFinalRecord({
            seed,
            candidate: {
              role: record.role,
              action: record.action,
              object: record.object,
              trigger: record.trigger,
            },
          });
          const after = correction.accepted && correction.after ? correction.after : record;
          const expectedObjectTokens = [...new Set(tokens(expected.object))];
          const actualObjectTokens = tokens(after.object);
          return {
            elementId: record.elementId,
            roleMatchesExpected: record.role.toLowerCase() === expected.role.toLowerCase(),
            actionMatchesExpected: compatibleAction(expected.action, tokens(after.action)),
            fidelityPassed: fidelity.passed,
            fidelityDetail: fidelity.passed ? null : fidelity,
            correctionAccepted: correction.accepted,
            correctionReasons: correction.reasons,
            matchesRowInIsolation: matchesRowAlone(row, after),
            expectedObjectTokenCount: expectedObjectTokens.length,
            expectedObjectTokensPresent: expectedObjectTokens.filter((t) =>
              actualObjectTokens.includes(t),
            ).length,
            expectedObjectTokensMissing: expectedObjectTokens.filter(
              (t) => !actualObjectTokens.includes(t),
            ).length,
            actualObjectTokenCount: actualObjectTokens.length,
            actualObjectTokensNotExpected: actualObjectTokens.filter(
              (t) => !expectedObjectTokens.includes(t),
            ).length,
          };
        }),
      };
    });
    const anyRecord = perSeed.some((entry) => entry.storedRecordsOnThisSpan > 0);
    const anyMatch = perSeed.some((entry) => entry.records.some((r) => r.matchesRowInIsolation));
    const anyFidelity = perSeed.some((entry) => entry.records.some((r) => r.fidelityPassed));
    const cause =
      seeds.length === 0
        ? 'NO_SUPPORTING_SEED_IN_DOCUMENT'
        : !anyRecord
          ? 'NO_RECORD_PRODUCED_ON_THE_SUPPORTING_SPAN'
          : anyMatch
            ? 'RECORD_MATCHES_ALONE_BUT_LOST_GLOBAL_ASSIGNMENT'
            : anyFidelity
              ? 'RECORD_PASSES_FIDELITY_BUT_FAILS_THE_MATCHER'
              : 'RECORD_PRODUCED_BUT_FAILS_FIDELITY';
    return { row, expectedRole: expected.role, supportingSeedCount: seeds.length, cause, seeds: perSeed };
  });

  console.log(
    JSON.stringify(
      {
        mapId: map.id,
        documentId: map.document_id,
        persistedStatus: map.status,
        storedRecords: stored.length,
        inventorySeeds: inventory.seeds.length,
        missedRows: MISSED_ROWS,
        causeSummary: Object.fromEntries(
          [...new Set(report.map((r) => r.cause))].map((cause) => [
            cause,
            report.filter((r) => r.cause === cause).map((r) => r.row),
          ]),
        ),
        report,
      },
      null,
      2,
    ),
  );
} finally {
  await sql.end({ timeout: 5 });
}
