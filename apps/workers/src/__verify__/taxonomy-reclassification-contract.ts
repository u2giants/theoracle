import assert from 'node:assert/strict';
import {
  isTerminalReclassificationChange,
  validateTaxonomyReclassificationPayload,
} from '../lib/taxonomy-reclassification-contract.js';

assert.deepEqual(
  validateTaxonomyReclassificationPayload('create_sub_topic', {
    topDomainId: 'operations',
    proposedName: 'Order intake',
    representativeClaimIds: ['claim-1'],
  }),
  { valid: true },
);
assert.equal(
  validateTaxonomyReclassificationPayload('merge_top_domains', {
    sourceTopDomainId: 'same',
    targetTopDomainId: 'same',
  }).valid,
  false,
);
const invalid = validateTaxonomyReclassificationPayload('reassign_claims', {
  fromSubTopicId: 'old',
});
assert.equal(invalid.valid, false);
if (!invalid.valid) assert.match(invalid.reason, /invalid payload/);
const manual = validateTaxonomyReclassificationPayload('split_top_domain', {});
assert.equal(manual.valid, false);
if (!manual.valid) assert.match(manual.reason, /manual admin intervention/);
const unknown = validateTaxonomyReclassificationPayload('not_real', {});
assert.equal(unknown.valid, false);
if (!unknown.valid) assert.match(unknown.reason, /unknown proposal type/);
assert.equal(isTerminalReclassificationChange('reclassification_applied_merge_top_domains'), true);
assert.equal(isTerminalReclassificationChange('reclassification_skipped_split_top_domain'), true);
assert.equal(isTerminalReclassificationChange('reclassification_dispatched'), false);
assert.equal(isTerminalReclassificationChange('reclassification_failed'), false);

console.log('taxonomy reclassification contract checks passed');
