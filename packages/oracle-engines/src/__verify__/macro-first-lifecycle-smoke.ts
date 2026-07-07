import {
  businessModelAdvisoryLockKey,
  canTransitionBusinessModelChange,
  canTransitionBusinessProcessVersion,
  canTransitionSourceWorkflowMap,
  assertBusinessModelChangeTransition,
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

console.log('macro-first lifecycle smoke passed');
