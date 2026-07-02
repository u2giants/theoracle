import {
  validateMacroRelationshipSummaryEntities,
  extractLikelyNamedEntities,
} from '../macro/validation';
import {
  statusAfterDroppingMacroSupport,
  statusAfterMacroSupportChange,
  statusForGeneratedMacroRelationship,
} from '../macro/lifecycle';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
  console.log(`✓ ${message}`);
}

function main() {
  console.log('Macro validation smoke test\n');

  const extracted = extractLikelyNamedEntities(
    'Designflow sends Carlos to Walmart only after POP Creations signs off.',
  );
  assert(extracted.includes('Designflow'), 'extracts system-like titlecase entity');
  assert(extracted.includes('POP Creations'), 'extracts multi-word titlecase entity');

  const supported = validateMacroRelationshipSummaryEntities({
    summary: 'Designflow waits for Walmart approval before Sourcing starts vendor work.',
    supportClaimSummaries: [
      'Designflow waits for Walmart approval.',
      'Sourcing starts vendor work after approval.',
    ],
  });
  assert(supported.ok, 'entities present in support claims pass');

  const registrySupported = validateMacroRelationshipSummaryEntities({
    summary: 'Designflow is the system that gates the approval workflow.',
    supportClaimSummaries: ['The approval workflow has a gate.'],
    registryEntityNames: ['Designflow'],
  });
  assert(registrySupported.ok, 'entities present in registry pass');

  const unsupported = validateMacroRelationshipSummaryEntities({
    summary: 'Designflow waits for Target approval before Sourcing starts vendor work.',
    supportClaimSummaries: [
      'Designflow waits for Walmart approval.',
      'Sourcing starts vendor work after approval.',
    ],
    registryEntityNames: ['Designflow', 'Walmart'],
  });
  assert(!unsupported.ok, 'unsupported entity fails validation');
  assert(unsupported.unsupportedEntities.includes('Target'), 'reports unsupported entity');

  assert(
    statusForGeneratedMacroRelationship(['approved', 'approved']) === 'pending_review',
    'generated macro with approved support is pending review',
  );
  assert(
    statusForGeneratedMacroRelationship(['approved', 'pending_review']) === 'blocked_pending_support',
    'generated macro with pending support is blocked',
  );
  assert(
    statusAfterDroppingMacroSupport(['approved']) === 'needs_review',
    'dropping below two support claims needs review',
  );
  assert(
    statusAfterMacroSupportChange({ currentStatus: 'approved', supportStatuses: ['approved', 'rejected'] }) === 'stale_support',
    'approved macro becomes stale when support leaves approved status',
  );
  assert(
    statusAfterMacroSupportChange({ currentStatus: 'blocked_pending_support', supportStatuses: ['approved', 'approved'] }) === 'pending_review',
    'blocked macro requeues when all support is approved',
  );

  console.log('\nMacro validation smoke gate: PASS');
}

main();
