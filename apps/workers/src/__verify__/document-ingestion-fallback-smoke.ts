import { __documentIngestionTestHooks } from '../trigger/document-ingestion';

const {
  coerceBooleanSetting,
  decideWorkflowReadFailureAction,
  formatWorkflowReadFailedProcessingError,
  WORKFLOW_MAP_FAILURE_DEGRADED_NOTE,
} = __documentIngestionTestHooks;

const cases: Array<[unknown, boolean, boolean, string]> = [
  [true, false, true, 'boolean true'],
  [false, true, false, 'boolean false'],
  ['true', false, true, 'string true'],
  [' FALSE ', true, false, 'string false with whitespace'],
  [null, false, false, 'null falls back false'],
  [undefined, true, true, 'undefined falls back true'],
  ['not-a-bool', false, false, 'unknown string falls back'],
];

for (const [value, fallback, expected, label] of cases) {
  const actual = coerceBooleanSetting(value, fallback);
  if (actual !== expected) {
    throw new Error(`${label}: expected ${expected}, got ${actual}`);
  }
}

const degradedAction = decideWorkflowReadFailureAction(false);
if (degradedAction !== 'continue_degraded') {
  throw new Error(
    `require_workflow_map_for_ingestion=false should continue degraded, got ${degradedAction}`,
  );
}

const failAction = decideWorkflowReadFailureAction(true);
if (failAction !== 'fail_document') {
  throw new Error(`require_workflow_map_for_ingestion=true should fail, got ${failAction}`);
}

const failedProcessingError = formatWorkflowReadFailedProcessingError(
  'Model openai/forced-failure-nonexistent is not valid for workflow_read',
);
if (!failedProcessingError.startsWith('Source workflow read failed:')) {
  throw new Error(`strict failure should preserve source-workflow prefix: ${failedProcessingError}`);
}

const degradedProcessingError = `DEGRADED — ${WORKFLOW_MAP_FAILURE_DEGRADED_NOTE}`;
if (
  !degradedProcessingError.startsWith('DEGRADED — ') ||
  !degradedProcessingError.includes('source workflow map failed')
) {
  throw new Error(`unexpected degraded processing error: ${degradedProcessingError}`);
}

console.log('PASS document ingestion fallback smoke');
