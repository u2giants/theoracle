import {
  BUSINESS_MODEL_SHAPES,
  BUSINESS_MODEL_SHAPE_REGISTRY,
  validateBusinessShapeElement,
  validateBusinessShapeRelation,
} from '@oracle/shared';
import {
  businessModelAdvisoryLockKey,
  evaluateBusinessModelApplyPrecondition,
} from '../model/lifecycle';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const fixtures = {
  process: {
    elementKind: 'step',
    detail: { nodeType: 'step', laneLabel: 'Sales' },
  },
  responsibilities: {
    elementKind: 'responsibility',
    detail: { role: 'Sales', action: 'reviews', object: 'buyer brief' },
  },
  ruleset: {
    elementKind: 'rule',
    detail: { scope: 'Licensed items', effect: 'Legal line is required' },
  },
  reference: {
    elementKind: 'attribute',
    detail: {
      entityType: 'product',
      attributeKey: 'sku',
      attributeValue: 'ABC-1',
      referenceKind: 'identifier',
    },
  },
  conversation: {
    elementKind: 'decision',
    detail: { decisionStatus: 'confirmed', contested: false },
  },
  narrative: {
    elementKind: 'asserted_fact',
    detail: { macroKind: 'goal', goal: 'Reduce sample revisions' },
  },
} as const;

for (const shape of BUSINESS_MODEL_SHAPES) {
  const contract = BUSINESS_MODEL_SHAPE_REGISTRY[shape];
  assert(contract.objectKind.length > 0, `${shape} has an object kind`);
  assert(contract.allowedElementKinds.length > 0, `${shape} has element kinds`);
  assert(contract.readInstruction.length > 0, `${shape} has reader instructions`);
  assert(contract.extractionDirective.length > 0, `${shape} has extraction instructions`);
  assert(contract.mergePromptFragment.length > 0, `${shape} has merge instructions`);
  assert(contract.detail.table.length > 0, `${shape} has a typed detail table`);

  const fixture = fixtures[shape];
  const valid = validateBusinessShapeElement({
    shape,
    elementKind: fixture.elementKind,
    detail: fixture.detail,
    elementId: `element-${shape}`,
  });
  assert(valid.errors.length === 0 && valid.row !== null, `${shape} fixture persists`);
  assert(contract.detail.render(valid.row).length > 0, `${shape} fixture renders`);

  const invalid = validateBusinessShapeElement({
    shape,
    elementKind: fixture.elementKind,
    detail: {},
  });
  assert(invalid.row === null && invalid.errors.length > 0, `${shape} rejects missing fields`);

  assert(
    validateBusinessShapeElement({
      shape,
      elementKind: 'definitely_wrong',
      detail: fixture.detail,
    }).errors.length > 0,
    `${shape} rejects an invalid element kind`,
  );
}

assert(
  validateBusinessShapeRelation({ shape: 'process', relationKind: 'handoff' }).length === 0,
  'process handoff relation is accepted',
);
assert(
  validateBusinessShapeRelation({ shape: 'responsibilities', relationKind: 'handoff' }).length > 0,
  'responsibility relation is rejected by its empty relation contract',
);
assert(
  businessModelAdvisoryLockKey(
    null,
    'proposal-1',
    'object-1',
    'responsibility_model',
    null,
  ) === 'business_object:object-1',
  'existing-object proposal locks its generic object',
);
assert(
  businessModelAdvisoryLockKey(
    null,
    'proposal-2',
    null,
    'responsibility_model',
    'licensed-team',
  ) === 'business_object_namespace:responsibility_model:licensed-team',
  'create proposal locks its authoritative kind/slug namespace',
);

const genericStale = evaluateBusinessModelApplyPrecondition(
  {
    id: 'proposal-3',
    status: 'pending_review',
    processId: null,
    baseVersionId: null,
    objectId: 'object-1',
    baseObjectVersionId: 'version-1',
  },
  'version-2',
);
assert(genericStale.status === 'needs_rebase', 'generic stale version needs rebase');

for (const missingBase of [
  {
    id: 'missing-object-base',
    status: 'pending_review',
    processId: null,
    baseVersionId: null,
    objectId: 'object-1',
    baseObjectVersionId: null,
  },
  {
    id: 'missing-process-base',
    status: 'pending_review',
    processId: 'process-1',
    baseVersionId: null,
    objectId: null,
    baseObjectVersionId: null,
  },
]) {
  let rejected = false;
  try {
    evaluateBusinessModelApplyPrecondition(missingBase, 'current-version');
  } catch {
    rejected = true;
  }
  assert(rejected, `${missingBase.id} fails loud before apply`);
}

console.log('R1 cross-shape registry and lifecycle contract passed');
