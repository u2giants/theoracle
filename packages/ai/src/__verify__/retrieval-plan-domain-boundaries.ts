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

console.log('retrieval-plan-domain-boundaries: ok');
