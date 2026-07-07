import {
  businessModelAdvisoryLockKey,
  canTransitionBusinessModelChange,
  canTransitionBusinessProcessVersion,
  canTransitionSourceWorkflowMap,
  evaluateBusinessModelApplyPrecondition,
  assertBusinessModelChangeTransition,
  shouldMarkFailedApply,
} from '../model/lifecycle';

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

console.log('macro-first lifecycle smoke passed');
