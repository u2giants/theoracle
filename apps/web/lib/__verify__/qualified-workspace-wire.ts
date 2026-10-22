/** Actual protected response decoder; no runtime or source issuance. */
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {parseWorkspaceAnswerV1} from '@oracle/shared/protected-natural-question-contract';
const p=parseWorkspaceAnswerV1(readFileSync(process.argv[2]!));
assert.equal(p.protocol,'qualified-workspace-answer-v1');
assert.equal(p.business_accepted,false);
assert.equal(p.result.source_health_observed,false);
console.log('Current protected workspace response decoded');
