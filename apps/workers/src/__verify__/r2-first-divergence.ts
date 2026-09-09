/**
 * SELECT-only R2 first-divergence analysis.
 *
 * Traces each missed answer row from the pinned inventory support heuristic through
 * source fidelity, model discovery, validation/merge readiness, correction, final
 * persistence, isolated matching, and global assignment. It prints identifiers,
 * booleans, counts, ratios, and reason-code families only — never licensed text,
 * answer-key text, source spans, model output, or production row content.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import postgres from 'postgres';
import {
  buildResponsibilitySourceInventory,
  resolveEnclosingResponsibilityDutySpan,
  validateResponsibilityFieldFidelity,
  type ResponsibilityInventorySeed,
} from '../lib/responsibility-reader';
import {
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  scoreResponsibilityAnswerKey,
  type ResponsibilityAnswerKeyRecord,
} from '../lib/responsibility-answer-key';

const MAP_ID = process.env.R2_FRESH_MAP_ID ?? '';
if (!MAP_ID) throw new Error('Missing R2_FRESH_MAP_ID.');
const MISSED_ROWS = (process.env.R2_MISSED_ROWS ?? '5,14,15,23')
  .split(',')
  .map((value) => Number(value.trim()))
  .filter((value) => Number.isInteger(value) && value >= 1);
const suppliedUrl = process.env.R2_REPLAY_DATABASE_URL;
if (!suppliedUrl) throw new Error('Missing R2_REPLAY_DATABASE_URL. This diagnostic is SELECT-only.');
const directHost = suppliedUrl.match(
  /^postgres(?:ql)?:\/\/([^:]+):([^@]+)@db\.([a-z0-9]+)\.supabase\.co:\d+\/(\S+)$/,
);
const databaseUrl = directHost
  ? `postgresql://${directHost[1]}.${directHost[3]}:${directHost[2]}@${
      process.env.R2_REPLAY_POOLER_HOST ?? 'aws-1-us-east-1.pooler.supabase.com'
    }:5432/${directHost[4]}`
  : suppliedUrl;

const answerKey = JSON.parse(
  readFileSync(
    new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
    'utf8',
  ),
) as { version: string; records: ResponsibilityAnswerKeyRecord[] };
assert.equal(answerKey.version, 'licensed-team-responsibilities-v1');
assert.equal(RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION, 'field-aware-v3');

const ignored = new Set([
  'the', 'and', 'to', 'from', 'in', 'into', 'of', 'for', 'by', 'against', 'before', 'with',
]);
const tokens = (value: string) =>
  value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/)
    .filter((token) => token.length > 2 && !ignored.has(token))
    .map((token) => token.replace(/(ing|ed|es|s)$/, '').replace(/e$/, ''));
const reasonFamilies = (reasons: readonly string[]) =>
  [...new Set(reasons.map((reason) => reason.split(':', 1)[0]))].sort();
const ownerAt = (span: string): string | null => {
  const bracket = span.match(
    /^\s*\[(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\]/i,
  )?.[1];
  const nested = span.match(
    /^\s*\[[^\]]+\]\s*(?:\d+[.)]\s*)?(Licensed Team|Lic Manager|Licensing Manager|Lic Coordinator)\b/i,
  )?.[1];
  const direct = span.match(
    /^\s*(?:\[[^\]]+\]\s*)?(Licensed Team|Lic Manager|Lic Coordinator)\b/i,
  )?.[1];
  const value = bracket ?? nested ?? direct ?? null;
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

type StoredRecord = {
  elementId: string;
  role: string;
  action: string;
  object: string;
  trigger: string | null;
  evidenceQuote: string;
  chunkId: string;
};
type JsonObject = Record<string, unknown>;
const stringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
const objects = (value: unknown): JsonObject[] =>
  Array.isArray(value)
    ? value.filter((item): item is JsonObject => Boolean(item) && typeof item === 'object')
    : [];

const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  const maps = await sql<Array<{
    id: string;
    document_id: string;
    status: string;
    file_name: string;
    file_type: string;
    elements_json: unknown;
    validation_json: unknown;
  }>>`
    SELECT swm.id, swm.document_id, swm.status, d.file_name, d.file_type,
           swm.elements_json, swm.validation_json
    FROM source_workflow_maps swm
    JOIN documents d ON d.id = swm.document_id
    WHERE swm.id = ${MAP_ID}::uuid
  `;
  const map = maps[0];
  if (!map) throw new Error(`Map ${MAP_ID} was not found.`);
  const validation = map.validation_json as JsonObject;
  const segmentAudits = objects(validation.responsibilitySegments);
  const completion = (validation.responsibilityCompletion ?? {}) as JsonObject;
  const completionOutcomes = objects(completion.outcomes);
  const correction = (validation.responsibilityFinalRecordCorrection ?? {}) as JsonObject;
  const correctionRows = objects(correction.corrections);
  const inventoryAudit = (validation.responsibilityInventory ?? {}) as JsonObject;

  const stored: StoredRecord[] = objects(map.elements_json)
    .filter((item) => item.shape === 'responsibilities' && item.elementKind === 'responsibility')
    .map((item) => ({
      elementId: String(item.elementId ?? ''),
      role: String(item.role ?? ''),
      action: String(item.action ?? ''),
      object: String(item.object ?? ''),
      trigger: item.trigger == null ? null : String(item.trigger),
      evidenceQuote: String(item.evidenceQuote ?? ''),
      chunkId: String(item.chunkId ?? ''),
    }));
  const chunkRows = await sql<Array<{ id: string; raw_text: string }>>`
    SELECT id, raw_text FROM document_chunks
    WHERE document_id = ${map.document_id}::uuid ORDER BY chunk_index
  `;
  const chunkText = new Map(chunkRows.map((chunk) => [chunk.id, chunk.raw_text]));
  const inventory = buildResponsibilitySourceInventory(
    chunkRows.map((chunk) => ({ id: chunk.id, documentId: map.document_id, rawText: chunk.raw_text })),
  );

  const recordsOnSeed = (seed: ResponsibilityInventorySeed) => stored.filter((record) => {
    if (record.elementId === seed.inventorySeedId) return true;
    if (record.chunkId !== seed.chunkId) return false;
    const rawText = chunkText.get(record.chunkId);
    if (!rawText) return false;
    return resolveEnclosingResponsibilityDutySpan({
      rawText,
      evidenceQuote: record.evidenceQuote,
      fileType: map.file_type,
      fileName: map.file_name,
    }) === seed.sourceSpan;
  });
  const supportingSeeds = (expected: ResponsibilityAnswerKeyRecord) => {
    const expectedObjectTokens = [...new Set(tokens(expected.object))];
    return inventory.seeds
      .map((seed, seedIndex) => ({ seed, seedIndex }))
      .filter(({ seed }) => {
        const contextual = tokens(seed.sourceSpan);
        const overlap = expectedObjectTokens.filter((token) => contextual.includes(token)).length;
        return (
          ownerAt(seed.sourceSpan)?.toLowerCase() === expected.role.toLowerCase() &&
          compatibleAction(expected.action, contextual) &&
          overlap >= Math.min(2, expectedObjectTokens.length) &&
          seed.evidenceQuote.length > 0 &&
          seed.sourceEnd > seed.sourceStart &&
          !seed.parseDiagnostics.includes('ambiguous_multi_verb')
        );
      });
  };

  const rowReports = MISSED_ROWS.map((row) => {
    const expected = answerKey.records[row - 1];
    if (!expected) throw new Error(`Answer key has no row ${row}.`);
    const seeds = supportingSeeds(expected).map(({ seed, seedIndex }) => {
      const segments = segmentAudits.filter((segment) =>
        stringArray(segment.sourceInventoryIds).includes(seed.inventorySeedId),
      );
      const outcome = completionOutcomes.find(
        (item) => item.responsibilityId === seed.inventorySeedId,
      );
      const correctionRow = correctionRows.find((item) => item.seedId === seed.inventorySeedId);
      const records = recordsOnSeed(seed);
      const answerFidelity = validateResponsibilityFieldFidelity(seed.sourceSpan, expected);
      const recordStages = records.map((record) => {
        const isolated = scoreResponsibilityAnswerKey({ expected: [expected], actual: [record] });
        const evidence = isolated.evidence[0]!;
        const fidelity = validateResponsibilityFieldFidelity(seed.sourceSpan, record);
        return {
          elementId: record.elementId,
          sourceFidelityPassed: fidelity.passed,
          sourceFidelityReasonFamilies: reasonFamilies(fidelity.reasons),
          matcherRoleExact: evidence.roleExact,
          matcherActionMatched: evidence.actionMatched,
          matcherObjectCoverage: Number(evidence.objectTokenCoverage.toFixed(3)),
          matcherNegationConflict: evidence.negationConflict,
          matchesRowInIsolation: isolated.matched === 1,
        };
      });
      return {
        seedIndex,
        seedId: seed.inventorySeedId,
        chunkId: seed.chunkId,
        parseDiagnostics: seed.parseDiagnostics,
        pinnedSupportHeuristic: true,
        answerKeyPassesSourceFidelity: answerFidelity.passed,
        answerKeyFidelityReasonFamilies: reasonFamilies(answerFidelity.reasons),
        inventoryRegistered: segments.length > 0,
        modelDiscovered: segments.some((segment) =>
          stringArray(segment.modelDiscoveredInventoryIds).includes(seed.inventorySeedId),
        ),
        mergeReadyInSegment: segments.some((segment) =>
          stringArray(segment.mergeReadyInventoryIds).includes(seed.inventorySeedId),
        ),
        mergeReadyGlobally: stringArray(inventoryAudit.mergeReadyInventoryIds)
          .includes(seed.inventorySeedId),
        markedIncomplete: stringArray(inventoryAudit.incompleteSeedIds).includes(seed.inventorySeedId),
        completionStatus: outcome ? String(outcome.status ?? 'unknown') : 'not_scheduled',
        completionReasonFamilies: outcome ? reasonFamilies(stringArray(outcome.reasons)) : [],
        correctionOffered: Boolean(correctionRow),
        correctionAccepted: Boolean(correctionRow?.accepted),
        correctionReasonFamilies: correctionRow
          ? reasonFamilies(stringArray(correctionRow.reasons))
          : [],
        persistedRecordCount: records.length,
        records: recordStages,
      };
    });

    const faithfulSeeds = seeds.filter((seed) => seed.answerKeyPassesSourceFidelity);
    const records = seeds.flatMap((seed) => seed.records);
    const anyIsolatedMatch = records.some((record) => record.matchesRowInIsolation);
    const anyCorrectionAccepted = seeds.some((seed) => seed.correctionAccepted);
    const anyRecord = records.length > 0;
    const firstDivergence =
      seeds.length === 0
        ? 'NO_PINNED_SUPPORTING_SEED'
        : faithfulSeeds.length === 0
          ? 'PINNED_SUPPORT_HEURISTIC_OVERSTATES_SOURCE_FIDELITY'
          : anyIsolatedMatch
            ? 'GLOBAL_ONE_TO_ONE_ASSIGNMENT_CONFLICT'
            : !anyRecord
              ? seeds.some((seed) => seed.modelDiscovered && !seed.mergeReadyGlobally)
                ? 'VALIDATION_OR_MERGE_REJECTED_THE_SUPPORTED_SEED'
                : 'NO_FINAL_RECORD_FOR_SUPPORTED_SEED'
              : anyCorrectionAccepted
                ? 'CORRECTION_ACCEPTED_BUT_MATCHER_GAP_REMAINS'
                : records.some((record) => !record.matcherRoleExact)
                  ? 'FINAL_RECORD_ROLE_DIVERGENCE'
                  : records.some((record) => !record.matcherActionMatched)
                    ? 'FINAL_RECORD_ACTION_DIVERGENCE'
                    : records.some((record) => record.matcherObjectCoverage < 1)
                      ? 'FINAL_RECORD_OBJECT_DIVERGENCE'
                      : 'UNCLASSIFIED_FINAL_RECORD_DIVERGENCE';
    return {
      row,
      supportingSeedCount: seeds.length,
      sourceFaithfulSupportingSeedCount: faithfulSeeds.length,
      firstDivergence,
      seeds,
    };
  });

  console.log(JSON.stringify({
    mapId: map.id,
    documentId: map.document_id,
    persistedStatus: map.status,
    matcherVersion: RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
    answerKeyVersion: answerKey.version,
    storedRecordCount: stored.length,
    inventorySeedCount: inventory.seeds.length,
    rows: rowReports,
    conclusionCounts: Object.fromEntries(
      [...new Set(rowReports.map((item) => item.firstDivergence))].map((cause) => [
        cause,
        rowReports.filter((item) => item.firstDivergence === cause).map((item) => item.row),
      ]),
    ),
  }, null, 2));
} finally {
  await sql.end({ timeout: 5 });
}
