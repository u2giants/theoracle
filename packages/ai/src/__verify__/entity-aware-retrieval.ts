import assert from 'node:assert/strict';
import {
  buildRetrievalPlanFromQuery,
  buildRetrievalPlanWithModel,
  entityLookupTokens,
  strictEntityMatches,
  type RegistryEntityCandidate,
} from '../retrieval-plan';

const registry: RegistryEntityCandidate[] = [
  { id: '1', entityType: 'person', canonicalValue: 'adam_dweck', displayLabel: 'Adam Dweck', aliases: ['Adam'] },
  { id: '2', entityType: 'system', canonicalValue: 'designflow_plm', displayLabel: 'Designflow PLM', aliases: ['Designflow'] },
  { id: '3', entityType: 'customer', canonicalValue: 'target', displayLabel: 'Target', aliases: [] },
  { id: '4', entityType: 'licensor', canonicalValue: 'disney', displayLabel: 'Disney', aliases: [] },
  { id: '5', entityType: 'vendor', canonicalValue: 'acme_factory', displayLabel: 'Acme Factory', aliases: ['Acme'] },
  { id: '6', entityType: 'sku_or_product_line', canonicalValue: 'stellar_mugs', displayLabel: 'Stellar Mugs', aliases: ['Stellar'] },
];

const fixtures = [
  { query: 'What did Adam Dweck change in Designflow?', expected: ['person:adam_dweck', 'system:designflow_plm'] },
  { query: 'What are Target requirements for Stellar Mugs?', expected: ['customer:target', 'sku_or_product_line:stellar_mugs'] },
  { query: 'Compare Disney approval steps with Acme Factory production steps.', expected: ['licensor:disney', 'vendor:acme_factory'] },
  { query: 'Who owns the Acme handoff to Designflow PLM?', expected: ['vendor:acme_factory', 'system:designflow_plm'] },
  { query: 'What does Unknown Person do in Mystery ERP?', expected: [] },
];

const startedAt = performance.now();
let expectedCount = 0;
let resolvedCount = 0;
let wrongCount = 0;

for (const fixture of fixtures) {
  const strict = strictEntityMatches(fixture.query, registry);
  const strictKeys = strict.map((item) => `${item.entityType}:${item.canonicalValue}`);
  expectedCount += fixture.expected.length;
  resolvedCount += fixture.expected.filter((key) => strictKeys.includes(key)).length;
  wrongCount += strictKeys.filter((key) => !fixture.expected.includes(key)).length;

  const plan = await buildRetrievalPlanWithModel(fixture.query, {
    lookupCandidates: async () => registry,
    selectWithModel: async (_query, candidates) =>
      candidates.map(({ entityType, canonicalValue }) => ({ entityType, canonicalValue })),
  });
  assert.deepEqual(
    plan.requiredEntities.map((item) => `${item.entityType}:${item.canonicalValue}`).sort(),
    fixture.expected.slice().sort(),
  );
}

const baselineResolved = fixtures.reduce(
  (sum, fixture) => sum + buildRetrievalPlanFromQuery(fixture.query).requiredEntities.length,
  0,
);
const recall = expectedCount === 0 ? 1 : resolvedCount / expectedCount;
const wrongEntityRate = resolvedCount + wrongCount === 0 ? 0 : wrongCount / (resolvedCount + wrongCount);
assert.equal(baselineResolved, 0, 'keyword planner fixture baseline must not resolve entities');
assert.equal(recall, 1, 'entity-aware fixture recall must be 100%');
assert.equal(wrongEntityRate, 0, 'wrong-entity rate must be 0%');

const inventedPlan = await buildRetrievalPlanWithModel('Tell me about Unknown Person', {
  lookupCandidates: async () => registry,
  selectWithModel: async () => [{ entityType: 'person', canonicalValue: 'invented_id' }],
});
assert.deepEqual(inventedPlan.requiredEntities, [], 'unresolved names must not invent canonical IDs');

const mixedInventedPlan = await buildRetrievalPlanWithModel('What did Adam Dweck change?', {
  lookupCandidates: async () => registry,
  selectWithModel: async () => [
    { entityType: 'person', canonicalValue: 'invented_id' },
    { entityType: 'person', canonicalValue: 'adam_dweck' },
  ],
});
assert.deepEqual(
  mixedInventedPlan.requiredEntities,
  [{ entityType: 'person', canonicalValue: 'adam_dweck' }],
  'an invented ID must be discarded even when a real registry candidate exists',
);

const designflowVendorPlan = await buildRetrievalPlanWithModel(
  'Who owns the Acme handoff to Designflow PLM?',
  {
    lookupCandidates: async () => registry,
    selectWithModel: async (_query, candidates) => candidates,
  },
);
assert(designflowVendorPlan.requiredEntities.some((entity) => entity.entityType === 'vendor'));
assert(
  !designflowVendorPlan.excludedEntityTypes?.includes('vendor'),
  'a required vendor must override Designflow vendor exclusion',
);

const disneyVendorPlan = await buildRetrievalPlanWithModel(
  'Compare Disney approval steps with Acme Factory production steps.',
  {
    lookupCandidates: async () => registry,
    selectWithModel: async (_query, candidates) => candidates,
  },
);
assert(disneyVendorPlan.requiredEntities.some((entity) => entity.entityType === 'vendor'));
assert(
  !disneyVendorPlan.excludedEntityTypes?.includes('vendor'),
  'a required vendor must override Disney vendor exclusion',
);

const longQuery =
  'Hey Oracle can you please remind me what happened during the review and explain ' +
  'the latest notes from last week about the customer requirements for Target';
assert(
  entityLookupTokens(longQuery).includes('target'),
  'candidate lookup must retain a named entity late in a long query',
);

const fallbackEvents: string[] = [];
const fallbackPlan = await buildRetrievalPlanWithModel('What did Adam do?', {
  lookupCandidates: async () => registry,
  selectWithModel: async () => {
    throw new Error('fixture model unavailable');
  },
  onFallback: (event) => fallbackEvents.push(event.reason),
});
assert.deepEqual(fallbackEvents, ['model_selection_failed'], 'model fallback must be observable');
assert.deepEqual(fallbackPlan.requiredEntities, [], 'model failure must use the keyword-only plan');

const latencyMs = performance.now() - startedAt;
assert(latencyMs < 100, `deterministic fixture planner exceeded 100ms: ${latencyMs.toFixed(2)}ms`);

console.log(JSON.stringify({
  fixtureCount: fixtures.length,
  baselineResolved,
  entityAwareRecall: recall,
  wrongEntityRate,
  unresolvedInventedIds: 0,
  deterministicLatencyMs: Number(latencyMs.toFixed(2)),
  modeledExtraCallsWhenEnabled: 1,
  defaultEnabled: false,
}));
console.log('PASS entity-aware retrieval planning');
