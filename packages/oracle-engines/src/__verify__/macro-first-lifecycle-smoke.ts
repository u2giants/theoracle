import {
  businessModelAdvisoryLockKey,
  canTransitionBusinessModelChange,
  canTransitionBusinessProcessVersion,
  canTransitionSourceWorkflowMap,
  evaluateBusinessModelApplyPrecondition,
  assertBusinessModelChangeTransition,
  shouldMarkFailedApply,
} from '../model/lifecycle';
import { resolveWorkflowMapNodeEntities } from '../model/entity-resolution';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

assert(canTransitionSourceWorkflowMap('pending', 'validated'), 'pending map can validate');
assert(canTransitionSourceWorkflowMap('validated', 'superseded'), 'validated map can supersede');
assert(!canTransitionSourceWorkflowMap('validated', 'failed'), 'validated map is immutable except supersede');
assert(!canTransitionSourceWorkflowMap('failed', 'validated'), 'failed map is terminal');

assert(
  canTransitionBusinessModelChange('pending_review', 'approved'),
  'pending proposal can be approved',
);
assert(
  canTransitionBusinessModelChange('pending_review', 'auto_applied'),
  'pending confirm proposal can auto-apply',
);
assert(
  canTransitionBusinessModelChange('pending_review', 'needs_rebase'),
  'pending proposal can need rebase',
);
assert(
  canTransitionBusinessModelChange('needs_rebase', 'superseded'),
  'rebased proposal can supersede stale proposal',
);
assert(
  !canTransitionBusinessModelChange('approved', 'needs_rebase'),
  'approved proposal is terminal',
);

assert(
  canTransitionBusinessProcessVersion('pending_review', 'approved'),
  'pending process version can approve',
);
assert(
  canTransitionBusinessProcessVersion('approved', 'superseded'),
  'approved process version can supersede',
);
assert(
  !canTransitionBusinessProcessVersion('rejected', 'approved'),
  'rejected process version is terminal',
);

let threw = false;
try {
  assertBusinessModelChangeTransition('approved', 'rejected');
} catch {
  threw = true;
}
assert(threw, 'invalid transition throws');

assert(
  businessModelAdvisoryLockKey('process-1', 'proposal-1') === 'business_process:process-1',
  'process proposals lock per process',
);
assert(
  businessModelAdvisoryLockKey(null, 'proposal-1') === 'business_model_change:proposal-1',
  'create-process proposals lock per proposal',
);

const readyPrecondition = evaluateBusinessModelApplyPrecondition(
  {
    id: 'proposal-ready',
    status: 'pending_review',
    processId: 'process-1',
    baseVersionId: 'version-1',
  },
  'version-1',
);
assert(readyPrecondition.status === 'ready', 'matching base version is ready to apply');

const stalePrecondition = evaluateBusinessModelApplyPrecondition(
  {
    id: 'proposal-stale',
    status: 'pending_review',
    processId: 'process-1',
    baseVersionId: 'version-1',
  },
  'version-2',
);
assert(stalePrecondition.status === 'needs_rebase', 'stale base version needs rebase');
assert(
  stalePrecondition.status === 'needs_rebase' &&
    stalePrecondition.actualVersionId === 'version-2',
  'stale precondition carries the current version id',
);

const terminalPrecondition = evaluateBusinessModelApplyPrecondition(
  {
    id: 'proposal-approved',
    status: 'approved',
    processId: 'process-1',
    baseVersionId: 'version-1',
  },
  'version-2',
);
assert(terminalPrecondition.status === 'noop', 'terminal proposal no-ops after locked re-read');

assert(shouldMarkFailedApply('pending_review'), 'pending proposal may be marked failed_apply');
assert(!shouldMarkFailedApply('approved'), 'approved proposal must not be overwritten by failed_apply');
assert(
  !shouldMarkFailedApply('auto_applied'),
  'auto-applied proposal must not be overwritten by failed_apply',
);
assert(
  !shouldMarkFailedApply('needs_rebase'),
  'needs_rebase proposal must not be overwritten by failed_apply',
);

const entityRegistry = [
  {
    id: 'entity-designflow',
    entityType: 'system' as const,
    canonicalValue: 'Designflow',
    aliases: ['DFlow'],
  },
  {
    id: 'entity-sharepoint',
    entityType: 'system' as const,
    canonicalValue: 'SharePoint',
    aliases: ['SP'],
  },
  {
    id: 'entity-uma',
    entityType: 'person' as const,
    canonicalValue: 'Uma',
    aliases: ['Uma Design'],
  },
];

const resolvedNodeRefs = resolveWorkflowMapNodeEntities({
  mapId: 'map-1',
  modelRunId: '11111111-1111-1111-1111-111111111111',
  nodeKey: 'node-1',
  ownerName: 'Design',
  systems: ['DFlow', 'SharePoint', 'DFlow'],
  chunkId: '22222222-2222-2222-2222-222222222222',
  entityRegistry,
  departmentRegistry: [{ id: 'design', displayLabel: 'Design' }],
});

assert(resolvedNodeRefs.ownerDepartmentId === 'design', 'owner resolves to department FK');
assert(resolvedNodeRefs.ownerEntityId === null, 'department owner does not also set entity FK');
assert(resolvedNodeRefs.ownerRaw === null, 'resolved owner does not keep owner_raw');
assert(resolvedNodeRefs.systemEntityIds.length === 2, 'systems resolve and dedupe to entity IDs');
assert(
  resolvedNodeRefs.systemEntityIds.includes('entity-designflow') &&
    resolvedNodeRefs.systemEntityIds.includes('entity-sharepoint'),
  'system aliases resolve against entity aliases',
);
assert(resolvedNodeRefs.entityProposalsToStage.length === 0, 'resolved refs stage no proposals');

const unknownNodeRefs = resolveWorkflowMapNodeEntities({
  mapId: 'map-2',
  modelRunId: null,
  nodeKey: 'node-2',
  ownerName: 'Packaging Steering',
  systems: ['PPS'],
  chunkId: '33333333-3333-3333-3333-333333333333',
  entityRegistry,
  departmentRegistry: [{ id: 'design', displayLabel: 'Design' }],
});

assert(unknownNodeRefs.ownerDepartmentId === null, 'unknown owner has no department FK');
assert(unknownNodeRefs.ownerEntityId === null, 'unknown owner has no entity FK');
assert(unknownNodeRefs.ownerRaw === 'Packaging Steering', 'unknown owner preserves raw owner');
assert(unknownNodeRefs.systemEntityIds.length === 0, 'unknown system has no system FK');
assert(unknownNodeRefs.unresolved.length === 2, 'unknown owner and system are reported');
assert(
  unknownNodeRefs.entityProposalsToStage.length === 2,
  'unknown owner and system create proposal inputs',
);
assert(
  unknownNodeRefs.entityProposalsToStage.some(
    (proposal) =>
      proposal.proposedEntityType === 'department' &&
      proposal.proposedCanonicalValue === 'Packaging Steering' &&
      proposal.observedInSourceType === 'document_chunk',
  ),
  'unknown owner stages a department proposal against the cited chunk',
);
assert(
  unknownNodeRefs.entityProposalsToStage.some(
    (proposal) =>
      proposal.proposedEntityType === 'system' &&
      proposal.proposedCanonicalValue === 'PPS' &&
      proposal.observedInSourceId === '33333333-3333-3333-3333-333333333333',
  ),
  'unknown system stages a system proposal against the cited chunk',
);

const personOwnerRefs = resolveWorkflowMapNodeEntities({
  mapId: 'map-3',
  nodeKey: 'node-3',
  ownerName: 'Uma Design',
  systems: [],
  chunkId: '44444444-4444-4444-4444-444444444444',
  entityRegistry,
});

assert(personOwnerRefs.ownerEntityId === 'entity-uma', 'person owner resolves to entity FK');
assert(personOwnerRefs.ownerRaw === null, 'resolved person owner does not keep owner_raw');

console.log('macro-first lifecycle smoke passed');
