import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  assertCoverageFindingEligible,
  modelCoverageSourcesEqual,
  requireModelCoverageSource,
} from '../model-coverage-conversion';

const root = resolve(import.meta.dirname, '../../../../');
const actions = readFileSync(resolve(root, 'apps/web/app/admin/gaps/_actions.ts'), 'utf8');
const page = readFileSync(resolve(root, 'apps/web/app/admin/gaps/page.tsx'), 'utf8');
const retrieval = readFileSync(resolve(root, 'packages/ai/src/retrieval.ts'), 'utf8');
const lull = readFileSync(resolve(root, 'apps/workers/src/trigger/lull-interjection.ts'), 'utf8');
const writer = readFileSync(resolve(root, 'apps/workers/src/lib/map-coverage-gaps.ts'), 'utf8');
const schema = readFileSync(resolve(root, 'packages/db/src/schema.ts'), 'utf8');
const migration = readFileSync(
  resolve(root, 'packages/db/migrations/sql/100_model_coverage_conversions.sql'),
  'utf8',
);

const source = {
  sourceType: 'document',
  sourceId: 'doc-1',
  mapId: 'map-1',
  mapElementRef: 'map-1:relation:a_to_b',
  mapElementKind: 'relation',
  mapShape: 'process',
  mapElementLocalId: 'a_to_b',
};
assert.deepEqual(requireModelCoverageSource(source), source);
assert.deepEqual(
  assertCoverageFindingEligible({ gapType: 'model_coverage', status: 'open', sourceContext: source }),
  source,
);
assert.throws(
  () => assertCoverageFindingEligible({ gapType: 'coverage_question', status: 'open', sourceContext: source }),
  /Only model coverage/,
);
assert.throws(
  () => assertCoverageFindingEligible({ gapType: 'model_coverage', status: 'resolved', sourceContext: source }),
  /Only an open/,
);
assert.throws(() => requireModelCoverageSource({ ...source, mapElementRef: '' }), /mapElementRef/);
const reorderedSource = {
  mapElementLocalId: source.mapElementLocalId,
  mapShape: source.mapShape,
  mapElementKind: source.mapElementKind,
  mapElementRef: source.mapElementRef,
  mapId: source.mapId,
  sourceId: source.sourceId,
  sourceType: source.sourceType,
};
assert.equal(
  modelCoverageSourcesEqual(source, reorderedSource),
  true,
  'jsonb key order must not change source equality',
);
assert.equal(
  modelCoverageSourcesEqual(source, { ...reorderedSource, mapElementRef: 'map-1:relation:other' }),
  false,
);

assert.match(actions, /await requireAdmin\(\)/, 'every conversion action must be admin guarded');
assert.equal(
  (actions.match(/FOR UPDATE/g) ?? []).length,
  4,
  'draft source, send draft/source, and cancel must use row locks',
);
assert.match(actions, /onConflictDoNothing/, 'draft creation must be idempotent');
assert.match(actions, /modelCoverageConversionEvents/, 'actions must write append-only audit events');
assert.match(actions, /sourceSnapshot/, 'audit must retain stable source provenance');
assert.match(actions, /status !== 'draft'/, 'terminal conversion states must fail loudly');
assert.match(
  migration,
  /UNIQUE INDEX[\s\S]*source_gap_id\)[\s\S]*WHERE status IN \('draft', 'sent'\)/,
  'cancelled drafts must permit redraft while draft/sent rows remain unique',
);
assert.match(schema, /\.where\(sql`\$\{t\.status\} IN \('draft', 'sent'\)`\)/);
assert.match(
  page,
  /inArray\(modelCoverageConversions\.status, \['draft', 'sent'\]\)/,
  'cancelled drafts must leave an explicit redraft UI path',
);
assert.match(migration, /action IN \('draft_created', 'sent', 'cancelled'\)/);
assert.match(migration, /BEFORE UPDATE OR DELETE/, 'audit events must be database-enforced append-only');
const createGapsAt = actions.indexOf('.insert(gaps)');
const resolveSourceAt = actions.indexOf(".set({ status: 'resolved'");
const sendAuditAt = actions.indexOf("action: 'sent'");
assert.ok(createGapsAt > 0 && resolveSourceAt > createGapsAt && sendAuditAt > resolveSourceAt,
  'source resolution and send audit must follow successful employee-gap creation in one transaction');
assert.match(actions, /if \(draft\.status === 'sent'\) return;/, 'double send must be a no-op');
assert.match(actions, /if \(draft\.status === 'cancelled'\) return;/, 'double cancel must be a no-op');
assert.match(actions, /recipients\.length !== draft\.target_employee_ids\.length/,
  'send must revalidate every recipient');
assert.match(actions, /assertCoverageFindingEligible\([\s\S]*finding\.source_context/,
  'send must revalidate source type, status, and provenance under lock');
assert.doesNotMatch(
  actions,
  /JSON\.stringify\(currentSource\)[\s\S]*JSON\.stringify\(draft\.source_snapshot\)/,
  'send must not compare raw jsonb objects by key order',
);
assert.match(actions, /modelCoverageSourcesEqual\(currentSource, draft\.source_snapshot\)/);
assert.match(actions, /gap\.gapType === 'model_coverage'/,
  'generic status changes must not resolve administrative findings');
assert.match(writer, /const sourceContext = \{[\s\S]*mapElementRef: omission\.ref/,
  'worker must write stable map provenance');
assert.match(writer, /WHEN \$\{gaps\.status\} = 'resolved' THEN \$\{gaps\.status\}/,
  'worker must preserve a successfully converted source finding');
assert.match(
  writer,
  /WHEN \$\{gaps\.status\} = 'resolved' THEN \$\{gaps\.sourceContext\}/,
  'worker must preserve terminal source provenance',
);
assert.match(page, /ne\(gaps\.gapType, 'model_coverage'\)/, 'raw findings must be outside normal gap rows');
assert.match(retrieval, /ne\(gaps\.gapType, 'model_coverage'\)/, 'chat retrieval must exclude raw findings');
assert.match(lull, /ne\(gaps\.gapType, 'model_coverage'\)/, 'lull questions must exclude raw findings');

console.log('model coverage conversion guard passed');
