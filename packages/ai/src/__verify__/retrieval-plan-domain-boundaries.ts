import assert from 'node:assert/strict';
import { buildRetrievalPlanFromQuery } from '../retrieval-plan';

function assertDomains(query: string, expected: string[]) {
  const plan = buildRetrievalPlanFromQuery(query);
  assert.deepEqual(
    plan.topDomainHints,
    expected,
    `Unexpected domain hints for query: ${query}`,
  );
  assert.equal(plan.searchScope, 'domain_filtered', `Expected domain-filtered plan for: ${query}`);
  return plan;
}

{
  const plan = assertDomains(
    'How should designers name files so the server does not reject invalid characters?',
    ['design_file_operations'],
  );
  assert.deepEqual(
    plan.excludedTopDomains,
    ['product_development', 'production_lifecycle', 'it_systems'],
    'Design file naming should not retrieve product workflow domains by default.',
  );
}

{
  const plan = assertDomains(
    'How do we keep Photoshop and Illustrator files from becoming bloated?',
    ['design_file_operations'],
  );
  assert.deepEqual(
    plan.excludedTopDomains,
    ['product_development', 'production_lifecycle', 'it_systems'],
    'Creative-app file-size questions should stay in file operations.',
  );
}

{
  const plan = buildRetrievalPlanFromQuery('Is the server down or is this a permission issue?');
  assert.equal(
    plan.topDomainHints.includes('design_file_operations'),
    false,
    'Generic server/permission problems should not route to design_file_operations.',
  );
  assert.equal(
    plan.topDomainHints.includes('it_systems'),
    true,
    'Generic server/permission problems should stay in it_systems.',
  );
}

{
  const plan = assertDomains(
    'How should we move OrderList, MasterData, and TaskList from Google Sheets into Designflow PLM?',
    ['operations_systems'],
  );
  assert.equal(
    plan.excludedDocumentClasses?.includes('vendor_manual'),
    true,
    'Operations-system integration questions should exclude vendor manuals by default.',
  );
}

{
  const query = 'How does our overall company process work from customer request through shipping?';
  const plan = buildRetrievalPlanFromQuery(query);
  assert.equal(plan.searchScope, 'domain_filtered', `Expected domain-filtered plan for: ${query}`);
  for (const domain of [
    'business_process',
    'licensing_approvals',
    'product_development',
    'production_lifecycle',
    'supply_chain',
    'customer_ops',
    'logistics_shipping',
  ]) {
    assert.equal(
      plan.topDomainHints.includes(domain),
      true,
      `Broad process query should include ${domain}.`,
    );
  }
}

{
  const plan = assertDomains(
    'What training checklist should a new hire follow to learn proof setup?',
    ['training_enablement'],
  );
  assert.deepEqual(
    plan.excludedTopDomains,
    ['people_org'],
    'Training questions should not retrieve org-ownership records by default.',
  );
}

{
  const query = 'Who owns onboarding for the design team?';
  const plan = buildRetrievalPlanFromQuery(query);
  assert.equal(plan.searchScope, 'domain_filtered', `Expected domain-filtered plan for: ${query}`);
  assert.equal(
    plan.topDomainHints.includes('people_org'),
    true,
    'Ownership questions about onboarding should still include people_org.',
  );
  assert.equal(
    plan.topDomainHints.includes('training_enablement'),
    false,
    'Ownership questions should not route to training_enablement without learning/training intent.',
  );
}

{
  const plan = assertDomains(
    'Where is this product in the design approval workflow before production?',
    ['licensing_approvals', 'product_development', 'production_lifecycle'],
  );
  assert.equal(
    plan.excludedTopDomains,
    undefined,
    'Product/design approval workflow must not be treated like file operations.',
  );
}

{
  const query = 'When should product design hand off the tech pack for a new sample?';
  const plan = buildRetrievalPlanFromQuery(query);
  assert.equal(plan.searchScope, 'domain_filtered', `Expected domain-filtered plan for: ${query}`);
  assert.equal(
    plan.topDomainHints.includes('product_development'),
    true,
    'Product development handoff questions should include product_development.',
  );
  assert.equal(
    plan.topDomainHints.includes('design_file_operations'),
    false,
    'Product development handoff questions should not route to design_file_operations.',
  );
  assert.equal(
    plan.excludedTopDomains,
    undefined,
    'Product development handoff questions should not inherit file-ops exclusions.',
  );
}

for (const [query, domains] of [
  ['How does Designflow PLM support licensing approvals?', ['operations_systems', 'licensing_approvals']],
  ['How does PLM support licensing across our overall company workflow?', ['business_process', 'licensing_approvals', 'operations_systems', 'supply_chain', 'logistics_shipping']],
  ['How do artwork files hand off to the production workflow before production?', ['design_file_operations', 'production_lifecycle']],
  ['How do design files support tech pack and sample handoffs?', ['design_file_operations', 'product_development']],
  ['How does PLM track customer purchase orders?', ['operations_systems', 'customer_ops']],
  ['How does PLM connect the creative brief to packaging design?', ['operations_systems', 'creative_design']],
  ['Who owns the training checklist and who is responsible for onboarding?', ['training_enablement', 'people_org']],
  ['How do file naming rules interact with login permission and SSO?', ['design_file_operations', 'it_systems']],
] as Array<[string, string[]]>) {
  const plan = buildRetrievalPlanFromQuery(query);
  for (const domain of domains) {
    assert.ok(plan.topDomainHints.includes(domain), `${query}: must include ${domain}`);
    assert.ok(!plan.excludedTopDomains?.includes(domain), `${query}: must not exclude ${domain}`);
  }
}

{
  const plan = buildRetrievalPlanFromQuery('Move OrderList from Google Sheets into Designflow PLM');
  assert.deepEqual(plan.topDomainHints, ['operations_systems']);
  assert.deepEqual(plan.excludedTopDomains, ['customer_ops', 'licensing_approvals', 'creative_design']);
  assert.ok(plan.excludedEntityTypes?.includes('licensor'));
  assert.ok(plan.excludedEntityTypes?.includes('vendor'));
}

for (const [query, entityTypes] of [
  ['How does Designflow PLM support licensing approvals?', ['licensor']],
  ['How does PLM track supplier evaluation and factory approval?', ['vendor', 'factory']],
  ['How do Disney approvals affect factory and freight handoffs?', ['factory', 'freight_provider']],
] as Array<[string, string[]]>) {
  const plan = buildRetrievalPlanFromQuery(query);
  for (const entityType of entityTypes) {
    assert.ok(!plan.excludedEntityTypes?.includes(entityType), `${query}: must not exclude ${entityType}`);
  }
}

{
  const plan = buildRetrievalPlanFromQuery('How does PLM support licensing approvals?', {
    excludedTopDomains: ['licensing_approvals'],
    excludedEntityTypes: ['licensor'],
  });
  assert.ok(plan.excludedTopDomains?.includes('licensing_approvals'), 'Explicit caller exclusions stay authoritative.');
  assert.ok(!plan.topDomainHints.includes('licensing_approvals'));
  assert.ok(plan.excludedEntityTypes?.includes('licensor'), 'Explicit caller entity exclusions stay authoritative.');
}

console.log('retrieval-plan-domain-boundaries: ok');
