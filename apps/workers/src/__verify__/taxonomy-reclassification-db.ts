import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { eq, sql } from 'drizzle-orm';
import {
  claims,
  claimSubTopics,
  employees,
  knowledgeSubTopics,
  knowledgeTopDomains,
  taxonomyChangeLog,
  taxonomyProposals,
} from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import {
  applyProposal,
  dispatchAffectedBrainSynthesis,
  type PendingProposal,
} from '../trigger/taxonomy-reclassification.js';

let db: ReturnType<typeof getDirectDb>;
const suffix = randomUUID().replaceAll('-', '').slice(0, 12);
const topDomainId = `verify_${suffix}`;
const triggerRunId = `verify-run-${suffix}`;
const proposalIds: string[] = [];
const claimIds: string[] = [];
let reviewerId: string | null = null;

function hasExpectedClaimSubTopicsForeignKey(error: unknown): boolean {
  const seen = new Set<unknown>();
  let current: unknown = error;
  while (current && typeof current === 'object' && !seen.has(current)) {
    seen.add(current);
    const details = current as {
      code?: unknown;
      table_name?: unknown;
      constraint_name?: unknown;
      cause?: unknown;
    };
    if (
      details.code === '23503' &&
      details.table_name === 'claim_sub_topics' &&
      details.constraint_name === 'claim_sub_topics_claim_id_claims_id_fk'
    ) {
      return true;
    }
    current = details.cause;
  }
  return false;
}

async function seedProposal(payload: Record<string, unknown>): Promise<PendingProposal> {
  const [row] = await db
    .insert(taxonomyProposals)
    .values({
      proposalType: 'create_sub_topic',
      payload,
      status: 'approved',
      reviewedByEmployeeId: reviewerId,
      reviewedAt: new Date(),
    })
    .returning({ id: taxonomyProposals.id });
  assert.ok(row);
  proposalIds.push(row.id);
  await db.insert(taxonomyChangeLog).values({
    proposalId: row.id,
    changeType: 'approve_pending_reclassification_create_sub_topic',
  });
  return { id: row.id, proposalType: 'create_sub_topic', payload };
}

async function main() {
  if (!process.env.DIRECT_URL) {
    throw new Error('DIRECT_URL is required for the DB-backed taxonomy guard');
  }
  db = getDirectDb();
  try {
    const [reviewer] = await db
      .insert(employees)
      .values({
        email: `verify-${suffix}@ci.invalid`,
        name: `Verify ${suffix}`,
        role: 'ci-fixture',
      })
      .returning({ id: employees.id });
    assert.ok(reviewer);
    reviewerId = reviewer.id;

    await db.insert(knowledgeTopDomains).values({
      id: topDomainId,
      name: `Verify ${suffix}`,
      description: 'Temporary CI taxonomy concurrency fixture',
      displayOrder: 999999,
    });

    const concurrent = await seedProposal({
      topDomainId,
      proposedName: `Concurrent ${suffix}`,
    });
    const [first, second] = await Promise.all([
      applyProposal(db, concurrent, false, triggerRunId),
      applyProposal(db, concurrent, false, `${triggerRunId}-duplicate`),
    ]);
    assert.equal([first, second].filter((result) => result.note === 'applied').length, 1);
    const terminal = await db.execute(sql`
    SELECT count(*)::int AS count
    FROM taxonomy_change_log
    WHERE proposal_id = ${concurrent.id}
      AND (change_type LIKE 'reclassification_applied_%'
        OR change_type LIKE 'reclassification_skipped_%')
  `);
    assert.equal(Number(([...terminal][0] as { count: number }).count), 1);
    const retry = await applyProposal(db, concurrent, false, `${triggerRunId}-retry`);
    assert.match(retry.note, /already terminal/);
    await dispatchAffectedBrainSynthesis(db, { ...concurrent, payload: {} }, triggerRunId);
    await dispatchAffectedBrainSynthesis(db, concurrent, triggerRunId);
    const [createdSubTopic] = await db
      .select({ id: knowledgeSubTopics.id })
      .from(knowledgeSubTopics)
      .where(eq(knowledgeSubTopics.name, `Concurrent ${suffix}`));
    assert.ok(createdSubTopic);
    await dispatchAffectedBrainSynthesis(
      db,
      {
        ...concurrent,
        payload: { subTopicId: createdSubTopic.id },
      },
      triggerRunId,
    );
    const brainFollowups = await db.execute(sql`
    SELECT count(*)::int AS count
    FROM taxonomy_change_log
    WHERE proposal_id = ${concurrent.id}
      AND change_type = 'brain_resynthesis_dispatched'
  `);
    assert.equal(Number(([...brainFollowups][0] as { count: number }).count), 3);

    const [representativeClaim] = await db
      .insert(claims)
      .values({
        claimType: 'fact',
        summary: `Representative taxonomy claim ${suffix}`,
        impactScore: 50,
        confidenceScore: 90,
        status: 'approved',
      })
      .returning({ id: claims.id });
    assert.ok(representativeClaim);
    claimIds.push(representativeClaim.id);
    const successful = await seedProposal({
      topDomainId,
      proposedName: `Successful ${suffix}`,
      representativeClaimIds: [representativeClaim.id],
    });
    const successfulResult = await applyProposal(db, successful, false, triggerRunId);
    assert.equal(successfulResult.note, 'applied');
    const assignments = await db
      .select({ assignmentReason: claimSubTopics.assignmentReason })
      .from(claimSubTopics)
      .where(eq(claimSubTopics.claimId, representativeClaim.id));
    assert.deepEqual(assignments, [{ assignmentReason: 'reclassification' }]);

    const stale = await seedProposal({
      topDomainId: `missing_${suffix}`,
      proposedName: `Stale ${suffix}`,
    });
    const staleResult = await applyProposal(db, stale, false, triggerRunId);
    assert.equal(staleResult.applied, false);
    assert.match(staleResult.note, /stale base/);

    const rollbackName = `Rollback ${suffix}`;
    const rollback = await seedProposal({
      topDomainId,
      proposedName: rollbackName,
      representativeClaimIds: [randomUUID()],
    });
    await assert.rejects(
      applyProposal(db, rollback, false, triggerRunId),
      hasExpectedClaimSubTopicsForeignKey,
    );
    const rolledBack = await db
      .select({ id: knowledgeSubTopics.id })
      .from(knowledgeSubTopics)
      .where(eq(knowledgeSubTopics.name, rollbackName));
    assert.equal(rolledBack.length, 0);
    const rollbackTerminal = await db.execute(sql`
    SELECT count(*)::int AS count
    FROM taxonomy_change_log
    WHERE proposal_id = ${rollback.id}
      AND (change_type LIKE 'reclassification_applied_%'
        OR change_type LIKE 'reclassification_skipped_%')
  `);
    assert.equal(Number(([...rollbackTerminal][0] as { count: number }).count), 0);

    const captured: Array<Record<string, unknown>> = [];
    const failingDb = {
      execute: async () => {
        throw new Error('forced Brain lookup failure');
      },
      insert: () => ({
        values: async (value: Record<string, unknown>) => {
          captured.push(value);
        },
      }),
    } as unknown as typeof db;
    await assert.doesNotReject(dispatchAffectedBrainSynthesis(failingDb, concurrent, triggerRunId));
    assert.equal(captured[0]?.changeType, 'brain_resynthesis_failed');

    console.log('taxonomy DB concurrency, retry, rollback, and stale-base checks passed');
  } finally {
    for (const proposalId of proposalIds.reverse()) {
      await db.delete(taxonomyChangeLog).where(eq(taxonomyChangeLog.proposalId, proposalId));
      await db.delete(taxonomyProposals).where(eq(taxonomyProposals.id, proposalId));
    }
    for (const claimId of claimIds.reverse()) {
      await db.delete(claimSubTopics).where(eq(claimSubTopics.claimId, claimId));
      await db.delete(claims).where(eq(claims.id, claimId));
    }
    await db.delete(knowledgeSubTopics).where(eq(knowledgeSubTopics.topDomainId, topDomainId));
    await db.delete(knowledgeTopDomains).where(eq(knowledgeTopDomains.id, topDomainId));
    if (reviewerId) await db.delete(employees).where(eq(employees.id, reviewerId));
  }
}

main()
  .then(() => process.exit(0))
  .catch((error: unknown) => {
    const summary = error instanceof Error ? error.message : String(error);
    console.error(`[taxonomy-reclassification-db] ${summary}`);
    process.exit(1);
  });
