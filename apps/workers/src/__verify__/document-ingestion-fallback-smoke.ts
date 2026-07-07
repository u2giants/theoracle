import { __documentIngestionTestHooks } from '../trigger/document-ingestion';

const { coerceBooleanSetting } = __documentIngestionTestHooks;

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

console.log('PASS document ingestion fallback smoke');
