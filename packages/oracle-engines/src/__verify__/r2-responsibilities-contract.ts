import assert from 'node:assert/strict';
import {
  enforceResponsibilityCreateGuard,
  normalizedResponsibilitySlug,
  responsibilityProposalInputHash,
  responsibilitySemanticKey,
  resolveResponsibilityCandidateEntities,
  validateResponsibilityVerdict,
  type ResponsibilityCandidate,
  type ResponsibilityMergeVerdict,
} from '../model/responsibility-merge';
import { assertBusinessModelApplyAllowed } from '../model/lifecycle';

const sourceMapId = '11111111-1111-4111-8111-111111111111';
const claimId = '22222222-2222-4222-8222-222222222222';
const item: ResponsibilityCandidate = {
  mapElementRef: `${sourceMapId}:element:designer_preflight`,
  claimId,
  label: 'Designer checks art files',
  role: 'Licensed Team Designer',
  action: 'checks',
  object: 'art files for completeness',
  trigger: 'before handoff',
  requiredSystem: 'Designflow',
  evidenceQuote: 'The Licensed Team Designer checks art files for completeness before handoff.',
  chunkId: '33333333-3333-4333-8333-333333333333',
};

assert.equal(
  responsibilitySemanticKey(item),
  'licensed team designer|checks|art files for completeness|before handoff|designflow',
);
assert.equal(normalizedResponsibilitySlug(' Licensed Team Responsibilities '), 'licensed-team-responsibilities');

const create: ResponsibilityMergeVerdict = {
  verdict: 'create_object',
  proposedName: 'Licensed Team Responsibilities',
  proposedSlug: 'licensed-team-responsibilities',
  summary: 'Create the responsibility model.',
  omittedSourceElementRefs: [],
  operations: [
    {
      type: 'add_responsibility',
      sourceElementRef: item.mapElementRef,
      evidenceClaimId: claimId,
      fields: item,
    },
  ],
};
assert.deepEqual(validateResponsibilityVerdict({ verdict: create, candidates: [item] }), []);

const hashA = responsibilityProposalInputHash({
  sourceMapId,
  baseVersionId: null,
  promptVersion: 'responsibility-merge-v1',
  modelVersion: 'fixture',
  candidates: [item],
});
const hashB = responsibilityProposalInputHash({
  sourceMapId,
  baseVersionId: null,
  promptVersion: 'responsibility-merge-v1',
  modelVersion: 'fixture',
  candidates: [item],
});
assert.equal(hashA, hashB, 'same-map redispatch must have the same deterministic input hash');

const blocked = enforceResponsibilityCreateGuard({
  verdict: create,
  exactNamespaceObjectId: '44444444-4444-4444-8444-444444444444',
});
assert.equal(blocked.verdict, 'needs_review');
assert.equal(blocked.operations.length, 0);

const nearMatch = enforceResponsibilityCreateGuard({
  verdict: create,
  plausibleObjectIds: ['55555555-5555-4555-8555-555555555555'],
});
assert.equal(nearMatch.verdict, 'needs_review');

const refine: ResponsibilityMergeVerdict = {
  ...create,
  verdict: 'refine_object',
  operations: [
    {
      ...create.operations[0]!,
      type: 'update_responsibility',
      targetElementKey: 'designer_preflight',
    },
  ],
};
assert.deepEqual(
  validateResponsibilityVerdict({
    verdict: refine,
    candidates: [item],
    durableElementKeys: new Set(['designer_preflight']),
  }),
  [],
);
assert.equal(refine.operations.length, 1, 'doctored responsibility produces one bounded operation');
assert.ok(
  validateResponsibilityVerdict({
    verdict: refine,
    candidates: [item],
    durableElementKeys: new Set(),
  }).some((error) => error.includes('unknown durable key')),
);

const resolved = resolveResponsibilityCandidateEntities({
  mapId: sourceMapId,
  candidate: { ...item, ownerName: 'Licensed Team', requiredSystem: 'Designflow' },
  entityRegistry: [
    {
      id: '66666666-6666-4666-8666-666666666666',
      entityType: 'department',
      canonicalValue: 'licensed team',
      aliases: [],
    },
    {
      id: '77777777-7777-4777-8777-777777777777',
      entityType: 'system',
      canonicalValue: 'designflow',
      aliases: [],
    },
  ],
});
assert.equal(resolved.ownerEntityId, '66666666-6666-4666-8666-666666666666');
assert.deepEqual(resolved.systemEntityIds, ['77777777-7777-4777-8777-777777777777']);

assert.throws(
  () => assertBusinessModelApplyAllowed({ settingValue: false }),
  /fail-safe setting/,
);
assert.throws(
  () =>
    assertBusinessModelApplyAllowed({
      settingValue: true,
      operationsJson: { shadow: true, applyEligible: false },
    }),
  /read-only/,
);

console.log('R2 responsibility merge, identity, guard, and idempotency contract passed');
