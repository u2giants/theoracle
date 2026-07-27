/**
 * REL-4 read-only production audit.
 *
 * The caller must provide REL4_AUDIT_DATABASE_URL explicitly. The script never
 * prints the connection string, environment values, provider errors, prompts,
 * or model output.
 */

import { sql } from 'drizzle-orm';

const auditUrl = process.env.REL4_AUDIT_DATABASE_URL;
if (!auditUrl) {
  throw new Error('REL4_AUDIT_DATABASE_URL is required');
}
process.env.DATABASE_URL = auditUrl;

const [{ getPooledDb }, { resolveRouteCandidates, shouldEnforceCapabilities }] = await Promise.all([
  import('@oracle/db'),
  import('../routes/candidates'),
]);

const db = getPooledDb();
const slots = ['workflow_read', 'macro', 'model_merge', 'transcript_summary', 'general'] as const;
const deepSchemaSlots = new Set(['workflow_read', 'macro', 'model_merge', 'general']);
const resolutions = new Map<
  typeof slots[number],
  Awaited<ReturnType<typeof resolveRouteCandidates>>
>();

for (const slot of slots) {
  const resolved = await resolveRouteCandidates(db, slot);
  resolutions.set(slot, resolved);
  console.log(JSON.stringify({
    slot,
    candidates: resolved.candidates.map((candidate) => ({
      provider: candidate.route.provider,
      modelId: candidate.route.modelId,
      approvedModelId: candidate.approvedModelId,
      isPrimary: candidate.isPrimary,
    })),
    skipped: resolved.skipped.map((candidate) => ({
      modelIdOrRouteId: candidate.modelIdOrRouteId,
      reason: candidate.reason,
    })),
  }));
}

const enforcementRows = await db.execute(sql`
  SELECT value
  FROM settings
  WHERE key = 'enforce_model_capabilities'
  LIMIT 1
`);
const capabilityEnforcementEnabled = enforcementRows[0]?.value === true;
console.log(JSON.stringify({
  capabilityEnforcementConfigured: capabilityEnforcementEnabled,
  mandatorySlotEnforcement: {
    workflow_read: shouldEnforceCapabilities('workflow_read', capabilityEnforcementEnabled),
    macro: shouldEnforceCapabilities('macro', capabilityEnforcementEnabled),
    model_merge: shouldEnforceCapabilities('model_merge', capabilityEnforcementEnabled),
  },
}));

const deepSeekCapabilities = await db.execute(sql`
  SELECT
    id,
    provider,
    context_length,
    structured_outputs,
    strict_json_schema,
    deep_schema_accepted,
    adapter_params_safe,
    source
  FROM model_capabilities
  WHERE provider = 'deepseek'
  ORDER BY id
`);
console.log(JSON.stringify({
  deepseekCapabilities: deepSeekCapabilities.map((row) => ({
    id: row.id,
    provider: row.provider,
    contextLength: row.context_length,
    structuredOutputs: row.structured_outputs,
    strictJsonSchema: row.strict_json_schema,
    deepSchemaAccepted: row.deep_schema_accepted,
    adapterParamsSafe: row.adapter_params_safe,
    source: row.source,
  })),
}));

const deepSeekAttempts = await db.execute(sql`
  SELECT
    slot,
    model_id,
    status,
    count(*)::int AS attempt_count,
    max(created_at) AS latest_attempt_at
  FROM model_run_attempts
  WHERE provider = 'deepseek'
  GROUP BY slot, model_id, status
  ORDER BY slot, model_id, status
`);
console.log(JSON.stringify({
  deepseekAttempts: deepSeekAttempts.map((row) => ({
    slot: row.slot,
    modelId: row.model_id,
    status: row.status,
    attemptCount: row.attempt_count,
    latestAttemptAt: row.latest_attempt_at,
  })),
}));

function assertAudit(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

try {
  for (const slot of ['workflow_read', 'macro', 'model_merge'] as const) {
    assertAudit(
      shouldEnforceCapabilities(slot, capabilityEnforcementEnabled),
      `${slot} capability enforcement must be mandatory`,
    );
  }

  for (const [slot, resolved] of resolutions) {
    const advertised = [
      ...resolved.candidates.map((candidate) => candidate.approvedModelId),
      ...resolved.skipped.map((candidate) => candidate.modelIdOrRouteId),
    ];
    const deepSeekAdvertised = advertised.filter((id) => id.startsWith('deepseek/'));
    if (deepSchemaSlots.has(slot)) {
      assertAudit(
        deepSeekAdvertised.length === 0,
        `DeepSeek must be absent from the ${slot} approved pool`,
      );
    } else {
      assertAudit(
        slot === 'transcript_summary',
        `DeepSeek is only allowed in transcript_summary, not ${slot}`,
      );
    }
  }

  const transcriptSummary = resolutions.get('transcript_summary');
  assertAudit(
    transcriptSummary?.candidates.some((candidate) => candidate.route.provider === 'deepseek'),
    'transcript_summary must retain its audited DeepSeek candidate',
  );

  assertAudit(deepSeekCapabilities.length > 0, 'DeepSeek capability rows are missing');
  for (const row of deepSeekCapabilities) {
    assertAudit(row.structured_outputs === false, `${row.id} structured_outputs must remain false`);
    assertAudit(row.strict_json_schema === false, `${row.id} strict_json_schema must remain false`);
    assertAudit(row.deep_schema_accepted === false, `${row.id} deep_schema_accepted must remain false`);
  }

  console.log(JSON.stringify({ status: 'PASS', invariantCount: 4 }));
  process.exit(0);
} catch (error) {
  const reason = error instanceof Error ? error.message : 'unknown REL-4 invariant failure';
  console.error(JSON.stringify({ status: 'FAIL', reason }));
  process.exit(1);
}
