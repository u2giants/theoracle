import assert from 'node:assert/strict';
import {
  MANUAL_TAXONOMY_RECLASSIFICATION_TYPES,
  SUPPORTED_TAXONOMY_RECLASSIFICATION_TYPES,
  classifyTaxonomyProposalState,
  isActionableTaxonomyProposalState,
  isTerminalReclassificationChange,
  validateTaxonomyReclassificationPayload,
} from '../lib/taxonomy-reclassification-contract.js';

assert.deepEqual(SUPPORTED_TAXONOMY_RECLASSIFICATION_TYPES, [
  'create_sub_topic',
  'reassign_claims',
  'merge_sub_topics',
  'retire_sub_topic',
  'merge_top_domains',
]);
assert.deepEqual(MANUAL_TAXONOMY_RECLASSIFICATION_TYPES, [
  'split_top_domain',
  'split_sub_topic',
]);
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
assert.equal(
  validateTaxonomyReclassificationPayload('merge_sub_topics', {
    sourceSubTopicId: 'source',
    targetSubTopicId: 'target',
  }).valid,
  true,
);
assert.equal(
  validateTaxonomyReclassificationPayload('merge_sub_topics', {
    sourceSubTopicId: 'same',
    targetSubTopicId: 'same',
  }).valid,
  false,
);
assert.equal(
  validateTaxonomyReclassificationPayload('retire_sub_topic', { subTopicId: 'old' }).valid,
  true,
);
assert.equal(validateTaxonomyReclassificationPayload('retire_sub_topic', {}).valid, false);
assert.equal(
  classifyTaxonomyProposalState({
    proposalType: 'create_top_domain',
    status: 'approved',
    latestChangeType: null,
    hasQueuedAudit: false,
  }),
  'applied_inline',
);
assert.equal(
  classifyTaxonomyProposalState({
    proposalType: 'split_sub_topic',
    status: 'approved',
    latestChangeType: 'reclassification_skipped_split_sub_topic',
    hasQueuedAudit: true,
  }),
  'skipped',
);
assert.equal(isActionableTaxonomyProposalState('applied_inline'), false);
assert.equal(isActionableTaxonomyProposalState('skipped'), false);
assert.equal(isActionableTaxonomyProposalState('approved_not_queued'), true);
assert.equal(isActionableTaxonomyProposalState('queued'), true);
assert.equal(isActionableTaxonomyProposalState('applying'), true);
assert.equal(isActionableTaxonomyProposalState('failed'), true);

console.log('taxonomy reclassification contract checks passed');
