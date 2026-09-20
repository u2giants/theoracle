import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildRetrievalPlanFromQuery, getEligibleRelationshipClaims } from '@oracle/ai';
import type { OracleDb } from '@oracle/db';
import { PgDialect } from 'drizzle-orm/pg-core';
import { buildConversationRetrievalQuery } from '../business-answer-context';
import { retrieveBusinessAnswerContext } from '../business-answer-retrieval';
import { assertKnownBusinessCitations } from '../business-answer-policy';

// Synthetic, approved evidence: three independent source types, not a business truth fixture.
const ids = [1, 2, 3, 4].map((n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`);
const claims = [
  { id: ids[0]!, summary: 'The process document says Design uploads artwork to PLM for licensing review.', impactScore: 7 },
  { id: ids[1]!, summary: 'The responsibility document assigns licensor submission to Licensing.', impactScore: 8 },
  { id: ids[2]!, summary: 'The meeting decision requires China to wait for approval before sample production; rush requests still require review.', impactScore: 9 },
  { id: ids[3]!, summary: 'The warehouse guide requires damaged cartons to be photographed before receiving.', impactScore: 5 },
];
const relationship = {
  id: '10000000-0000-4000-8000-000000000001', relationshipType: 'handoff',
  summary: 'Artwork handoff depends on licensing approval before China begins samples.',
  impactScore: 9, confidenceScore: 90,
  supportClaims: claims.slice(0, 3).map((c) => ({ ...c, claimType: 'fact', claimKind: null, supportRole: 'supports' })),
};
const getEligibleSupports = async () => relationship.supportClaims;
const query = 'How does PLM support licensing approvals across the product workflow?';
const plan = buildRetrievalPlanFromQuery(query);
assert(!plan.excludedTopDomains?.includes('licensing_approvals'), 'explicit licensing must survive domain exclusions');
assert(!plan.excludedEntityTypes?.includes('licensor'), 'explicit licensor evidence must survive entity exclusions');
const searches: typeof plan[] = [];
const result = await retrieveBusinessAnswerContext({
  plan,
  search: async (p) => {
    searches.push(p);
    // Overall ranking favors systems facts. Department pass must recover ownership.
    return p.topDomainHints.length === 1 && p.topDomainHints[0] === 'licensing_approvals'
      ? [claims[1]!] : [claims[0]!];
  },
  getRelationships: async (claimIds) => {
    assert(claimIds.includes(ids[0]!));
    return [relationship];
  },
  getEligibleSupports,
});
assert(searches.length > 1 && searches.length <= 3, 'cross-functional expansion is bounded');
for (const search of searches) {
  assert.deepEqual(search.requiredEntities, plan.requiredEntities);
  assert.equal(search.timeFilter, plan.timeFilter);
  assert.deepEqual(search.excludedDocumentClasses, plan.excludedDocumentClasses);
}
for (const claim of claims.slice(0, 3)) {
  assert(result.text.includes(claim.summary), 'actual support premise reaches answer context');
  assert(result.includedClaimIds.includes(claim.id));
}
assert(!result.includedClaimIds.includes(ids[3]!));
assert.deepEqual(result.includedRelationshipIds, [relationship.id]);
assert.deepEqual(result.evidenceRelationships.map((item) => item.id), [relationship.id]);
assertKnownBusinessCitations(`Licensing owns submission [claim:${ids[1]}]. China waits for approval [claim:${ids[2]}].`, result.includedClaimIds);
assert.throws(() => assertKnownBusinessCitations(`Unrelated fact [claim:${ids[3]}]`, result.includedClaimIds));
assert.doesNotThrow(() => assertKnownBusinessCitations('Hello there.', result.includedClaimIds));
assert.throws(() => assertKnownBusinessCitations('Licensing owns submission.', result.includedClaimIds, { requireAtLeastOne: true }), /without citing any/);

const followup = buildConversationRetrievalQuery([
  { role: 'user', content: query },
  { role: 'assistant', content: 'Unsupported assistant claim: China may skip licensing.' },
  { role: 'user', content: 'And how does that affect China?' },
], 'And how does that affect China?');
assert(followup.includes(query));
assert(!followup.includes('may skip'));

// Held-out topic reset must not inherit the licensed-product workflow.
const nextQuestion = 'How do warehouse staff handle damaged cartons?';
assert.equal(buildConversationRetrievalQuery([{ role: 'user', content: query }], nextQuestion), `Current query: ${nextQuestion}`);
const heldOut = await retrieveBusinessAnswerContext({
  plan: buildRetrievalPlanFromQuery(nextQuestion),
  search: async () => [claims[3]!],
  getRelationships: async () => [],
  getEligibleSupports,
});
assert.deepEqual(heldOut.includedClaimIds, [ids[3]!]);
assert(!heldOut.text.includes('Licensing'));
const empty = await retrieveBusinessAnswerContext({ plan, search: async () => [], getEligibleSupports, getRelationships: async () => { throw new Error('must not fetch unscoped relationships'); } });
assert.deepEqual(empty.includedClaimIds, []);
assert(empty.emptySearches.length > 0);
await assert.rejects(retrieveBusinessAnswerContext({ plan, search: async () => { throw new Error('database unavailable'); }, getEligibleSupports, getRelationships: async () => [] }), /database unavailable/);
const filtered = await retrieveBusinessAnswerContext({
  plan, search: async () => [claims[0]!], getRelationships: async () => [relationship],
  getEligibleSupports: async () => relationship.supportClaims.slice(0, 2),
});
assert.equal(filtered.ineligibleRelationshipCount, 1);
assert.deepEqual(filtered.includedRelationshipIds, []);
assert(!filtered.text.includes(claims[2]!.summary), 'ineligible relationship cannot reintroduce a filtered premise');

// Exercise the production SQL builder: all hard boundaries, localization, bound IDs.
let supportSql = '';
let supportParams: unknown[] = [];
const fakeDb = { execute: async (query: Parameters<PgDialect['sqlToQuery']>[0]) => {
  const compiled = new PgDialect().sqlToQuery(query);
  supportSql = compiled.sql;
  supportParams = compiled.params;
  return [{ id: ids[0]!, summary: 'translated premise', claim_kind: 'rule', localized: true }];
} } as unknown as OracleDb;
const eligibleRows = await getEligibleRelationshipClaims(fakeDb, {
  ...plan, topDomainHints: ['operations_systems'], excludedTopDomains: ['licensing_approvals'],
  excludedDocumentClasses: ['vendor_manual'], excludedEntityTypes: ['vendor'],
  requiredEntities: [{ entityType: 'system', canonicalValue: 'plm' }],
  processStageHints: ['review'], timeFilter: 'current',
}, [ids[0]!], 'zh-CN');
for (const predicate of ["c.status = 'approved'", 'effective_until IS NULL', 'cm.document_class NOT IN',
  '_xtd.top_domain_id IN', '_e.entity_type IN', '_e2.canonical_value', 'cm.process_stage IN',
  "ct.review_status = 'approved'", 'ct.source_hash', 'COALESCE(ct.summary, c.summary)', 'ct.claim_id IS NOT NULL']) {
  assert(supportSql.includes(predicate), `support eligibility must retain ${predicate}`);
}
assert(!supportSql.includes('ctd.top_domain_id IN'), 'only positive domain seed scope may expand');
assert(supportParams.includes('zh-CN'));
assert(supportParams.includes(JSON.stringify([ids[0]!])));
assert.equal(eligibleRows[0]!.summary, 'translated premise');
assert.equal(eligibleRows[0]!.localized, true);

// Wiring guard: both observability paths and dispatch use the same bounded context.
const route = readFileSync(new URL('../../app/api/chat/route.ts', import.meta.url), 'utf8');
assert(route.includes('retrieveBusinessAnswerContext({'));
assert(route.includes('includedClaimIds: answerContext.includedClaimIds'));
assert(route.includes('assertKnownBusinessCitations(oracleText, answerContext.includedClaimIds,'));
assert(route.includes('reconciliationRequiredClaimCount > 0'));
assert(route.indexOf('oracleText = reconciled.text') < route.indexOf('assertKnownBusinessCitations(oracleText'));
assert(route.indexOf('const attachmentRows =') < route.indexOf('const requiresReconciliation ='));
assert(route.includes('const requiresReconciliation = !hasRelevantAttachments'));
assert(route.includes("const reconciliationRelationships = locale === 'zh-CN'"));
assert(route.includes('relationships: reconciliationRelationships'));
assert(route.includes("resolveRouteCandidates(db, 'macro')"));
assert(route.includes('independentProviderCount < 2'));
assert(route.includes('ATTACHMENT_ANSWER_REVIEW_SYSTEM'));
assert(route.includes('const generatorProvider = resolveRunProvider(result, routeCandidates)'));
assert(route.includes('hasBusinessAnswerIntent(latestUserMessage.content)'));
assert(route.includes('selectedDomains: scopeTag(retrievalPlan.topDomainHints'));
assert(route.includes("error: 'no_approved_evidence'"));
assert(route.includes('answerIntegrityRequired && hasRelevantAttachments'));
assert(route.includes('const answerIntegrityRequired = businessAnswerIntent || hasRelevantAttachments'));
assert(route.includes('if (answerIntegrityRequired) assertEvidenceLocale'));
assert(route.includes('finalPlan = reconciliationPlan'));
assert(route.includes('persistFailedAuxiliaryChatRun'));
assert(route.includes('everyInterviewRouteHasIndependentReviewer'));
assert(route.includes("failureCode = 'answer_reconciliation_route_unavailable'"));
console.log('PASS connected business journey: evidence assembly, held-out topic, follow-up, missing evidence, citation integrity, route wiring (0 skipped). Live model comprehension is a separate gate.');
