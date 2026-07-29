import assert from 'node:assert/strict';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  MANUAL_TAXONOMY_RECLASSIFICATION_TYPES,
  SUPPORTED_TAXONOMY_RECLASSIFICATION_TYPES,
  classifyTaxonomyProposalState,
  isActionableTaxonomyProposalState,
} from '../lib/taxonomy-reclassification-contract.js';

async function main() {
  if (!process.env.DIRECT_URL) {
    throw new Error('DIRECT_URL is required for the read-only taxonomy production audit');
  }

  const db = getDirectDb();

const proposalRows = await db.execute(sql`
  WITH latest_state AS (
    SELECT DISTINCT ON (proposal_id)
      proposal_id,
      change_type,
      reason,
      after_state,
      created_at
    FROM taxonomy_change_log
    WHERE proposal_id IS NOT NULL
      AND (
        change_type = 'reclassification_dispatched'
        OR change_type = 'reclassification_failed'
        OR change_type LIKE 'reclassification_applied_%'
        OR change_type LIKE 'reclassification_skipped_%'
      )
    ORDER BY proposal_id, created_at DESC, id DESC
  )
  SELECT
    p.id,
    p.proposal_type,
    p.status,
    p.created_at,
    p.reviewed_at,
    s.change_type AS latest_change_type,
    s.reason AS latest_reason,
    s.after_state->>'triggerRunId' AS trigger_run_id,
    s.created_at AS latest_change_at,
    EXISTS (
      SELECT 1 FROM taxonomy_change_log q
      WHERE q.proposal_id = p.id
        AND q.change_type LIKE 'approve_pending_reclassification_%'
    ) AS has_queued_audit
  FROM taxonomy_proposals p
  LEFT JOIN latest_state s ON s.proposal_id = p.id
  ORDER BY p.created_at DESC
`);

const jobRows = await db.execute(sql`
  SELECT
    trigger_run_id,
    status,
    started_at,
    finished_at,
    retry_count,
    input_json->>'proposalId' AS proposal_id,
    error
  FROM job_runs
  WHERE job_type = 'taxonomy-reclassification'
  ORDER BY started_at DESC
  LIMIT 200
`);

const proposals: Array<Record<string, unknown> & { effective_state: string }> = (
  [...proposalRows] as unknown as Array<Record<string, unknown>>
).map((row) => {
  const effectiveState = classifyTaxonomyProposalState({
    proposalType: String(row.proposal_type),
    status: String(row.status),
    latestChangeType: row.latest_change_type ? String(row.latest_change_type) : null,
    hasQueuedAudit: row.has_queued_audit === true,
  });
  return Object.assign({}, row, { effective_state: effectiveState });
});
const jobs = [...jobRows] as unknown as Array<Record<string, unknown>>;
const supported = new Set<string>(SUPPORTED_TAXONOMY_RECLASSIFICATION_TYPES);
const manual = new Set<string>(MANUAL_TAXONOMY_RECLASSIFICATION_TYPES);
const observedTypes = [...new Set(proposals.map((row) => String(row.proposal_type)))].sort();
const unknownTypes = observedTypes.filter(
  (proposalType) =>
    proposalType !== 'create_top_domain' &&
    !supported.has(proposalType) &&
    !manual.has(proposalType),
);

for (const row of proposals) {
  const proposalType = String(row.proposal_type);
  const effectiveState = String(row.effective_state);
  if (manual.has(proposalType) && effectiveState === 'applied') {
    throw new Error(`manual proposal ${row.id} is unexpectedly marked applied`);
  }
}
assert.equal(
  unknownTypes.length,
  0,
  `production contains proposal types with no handler or manual rule: ${unknownTypes.join(', ')}`,
);

const byTypeAndState = proposals.reduce<Record<string, number>>((counts, row) => {
  const key = `${row.proposal_type}:${row.effective_state}`;
  counts[key] = (counts[key] ?? 0) + 1;
  return counts;
}, {});
const actionable = proposals.filter((row) =>
  isActionableTaxonomyProposalState(String(row.effective_state)),
);

assert.equal(
  classifyTaxonomyProposalState({
    proposalType: 'create_top_domain',
    status: 'approved',
    latestChangeType: null,
    hasQueuedAudit: false,
  }),
  'applied_inline',
);
assert.equal(isActionableTaxonomyProposalState('applied_inline'), false);
assert.equal(isActionableTaxonomyProposalState('skipped'), false);

const output = JSON.stringify(
    {
      mode: 'SELECT-only',
      handlerTypes: [...SUPPORTED_TAXONOMY_RECLASSIFICATION_TYPES],
      manualTypes: [...MANUAL_TAXONOMY_RECLASSIFICATION_TYPES],
      observedTypes,
      proposalCounts: byTypeAndState,
      actionableProposals: actionable,
      recentJobRuns: jobs,
    },
    null,
    2,
  );
  await new Promise<void>((resolve, reject) => {
    process.stdout.write(`${output}\n`, (error) => (error ? reject(error) : resolve()));
  });
}

main()
  .then(() => process.exit(0))
  .catch(async (error: unknown) => {
    const summary = error instanceof Error ? (error.stack ?? error.message) : String(error);
    await new Promise<void>((resolve) => {
      process.stderr.write(
        `[taxonomy-reclassification-production-audit] ${summary}\n`,
        () => resolve(),
      );
    });
    process.exit(1);
  });
