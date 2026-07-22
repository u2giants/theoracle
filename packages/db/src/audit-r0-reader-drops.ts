/**
 * Read-only audit of the historical Stage 2 business-process reader drops.
 *
 * The legacy validator retained element identity and reason but not the rejected
 * quote or raw reader output. This script therefore classifies all persisted
 * rows and states that limitation explicitly instead of guessing alternate
 * policy results. Future reads retain bounded raw output and full diagnostics.
 */
import postgres from 'postgres';

type LegacyDrop = {
  elementType?: unknown;
  elementId?: unknown;
  reason?: unknown;
};

type LegacySegment = {
  segmentId?: unknown;
  dropped?: unknown;
};

const DEFAULT_MAP_ID = '9e84efda-755d-4a05-be5a-bbbadfce144e';
const databaseUrl = process.env.R0_AUDIT_DATABASE_URL;
if (!databaseUrl) {
  throw new Error(
    'Missing R0_AUDIT_DATABASE_URL. Supply the current production session-pooler URL explicitly; this audit is SELECT-only.',
  );
}
const mapId = process.env.R0_AUDIT_MAP_ID ?? DEFAULT_MAP_ID;
const summaryOnly = process.env.R0_AUDIT_SUMMARY_ONLY === '1';
if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(mapId)) {
  throw new Error(`R0_AUDIT_MAP_ID is not a UUID: ${mapId}`);
}

function classify(reason: string) {
  if (reason === 'exactQuoteProvided was not found in sourceText.') {
    return {
      failureClass: 'quote_not_found' as const,
      failureOrigin: 'root' as const,
      disposition: 'separately_scheduled_post_fix_replay' as const,
      policySelected: 'legacy_implicit_strict' as const,
      alternatePolicyOutcome: 'not_reconstructible_legacy_quote_not_retained' as const,
    };
  }
  if (reason.startsWith('Quote appears more than once')) {
    return {
      failureClass: 'quote_ambiguous' as const,
      failureOrigin: 'root' as const,
      disposition: 'correct_hard_rejection' as const,
      policySelected: 'legacy_implicit_strict' as const,
      alternatePolicyOutcome: 'not_reconstructible_legacy_quote_not_retained' as const,
    };
  }
  if (reason === 'edge endpoint does not exist after node validation') {
    return {
      failureClass: 'missing_endpoint_cascade' as const,
      failureOrigin: 'cascade' as const,
      disposition: 'cascade' as const,
      policySelected: 'not_run' as const,
      alternatePolicyOutcome: 'not_applicable' as const,
    };
  }
  if (reason.startsWith('missing node IDs:')) {
    return {
      failureClass: 'missing_path_node_cascade' as const,
      failureOrigin: 'cascade' as const,
      disposition: 'cascade' as const,
      policySelected: 'not_run' as const,
      alternatePolicyOutcome: 'not_applicable' as const,
    };
  }
  return {
    failureClass: 'unresolved' as const,
    failureOrigin: 'root' as const,
    disposition: 'unresolved' as const,
    policySelected: 'unknown' as const,
    alternatePolicyOutcome: 'unknown' as const,
  };
}

const sql = postgres(databaseUrl, { max: 1, prepare: false });
try {
  const rows = await sql<
    Array<{
      id: string;
      document_id: string | null;
      file_name: string | null;
      status: string;
      validation_json: Record<string, unknown>;
    }>
  >`
    SELECT swm.id, swm.document_id, d.file_name, swm.status, swm.validation_json
    FROM source_workflow_maps swm
    LEFT JOIN documents d ON d.id = swm.document_id
    WHERE swm.id = ${mapId}::uuid
  `;
  const map = rows[0];
  if (!map) throw new Error(`No source_workflow_maps row found for ${mapId}`);

  const segments = Array.isArray(map.validation_json.processSegments)
    ? (map.validation_json.processSegments as LegacySegment[])
    : [];
  const findings = segments.flatMap((segment) => {
    const segmentId = typeof segment.segmentId === 'string' ? segment.segmentId : 'unknown';
    const dropped = Array.isArray(segment.dropped) ? (segment.dropped as LegacyDrop[]) : [];
    return dropped.map((item) => {
      const reason = typeof item.reason === 'string' ? item.reason : 'missing legacy reason';
      return {
        segmentId,
        elementType: typeof item.elementType === 'string' ? item.elementType : 'unknown',
        elementId: typeof item.elementId === 'string' ? item.elementId : 'unknown',
        reason,
        ...classify(reason),
      };
    });
  });
  const persistedDroppedCount = Number(map.validation_json.droppedCount);
  if (!Number.isInteger(persistedDroppedCount) || findings.length !== persistedDroppedCount) {
    throw new Error(
      `Audit count mismatch: expanded ${findings.length}, persisted ${String(map.validation_json.droppedCount)}`,
    );
  }
  const unresolved = findings.filter((finding) => finding.disposition === 'unresolved');
  if (unresolved.length > 0) {
    throw new Error(`R0 audit has ${unresolved.length} unresolved legacy drop classifications`);
  }

  const counts = Object.entries(
    findings.reduce<Record<string, number>>((result, finding) => {
      const key = `${finding.failureClass}:${finding.failureOrigin}:${finding.disposition}`;
      result[key] = (result[key] ?? 0) + 1;
      return result;
    }, {}),
  )
    .map(([classification, count]) => ({ classification, count }))
    .sort((a, b) => a.classification.localeCompare(b.classification));

  console.log(
    JSON.stringify(
      {
        map: {
          id: map.id,
          documentId: map.document_id,
          fileName: map.file_name,
          status: map.status,
          persistedDroppedCount,
        },
        legacyTelemetryLimitation:
          'The rejected quote and raw reader output were not persisted by shape-reader-v2; alternate-policy outcomes for historical root failures cannot be reconstructed. R0 fixes future retention.',
        counts,
        ...(summaryOnly ? {} : { findings }),
      },
      null,
      2,
    ),
  );
} finally {
  await sql.end({ timeout: 5 });
}
