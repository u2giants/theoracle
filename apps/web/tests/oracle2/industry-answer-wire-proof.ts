/** Parses actual retained invented service wire; this creates no read permission. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {canonicalJson,sha256} from '../../lib/replacement-server-binding';
import {parseIndustryAnswerV1,parseQualifiedAnswerResponseV1} from '@oracle/shared/protected-natural-question-contract';
const raw=readFileSync(process.argv[2]!);const value=JSON.parse(raw.toString());
assert.equal(parseIndustryAnswerV1(raw).protocol,'qualified-industry-answer-v1');
const parsed=parseQualifiedAnswerResponseV1(raw);assert.equal(parsed.protocol,'qualified-industry-answer-v1');if(parsed.protocol!=='qualified-industry-answer-v1')throw new Error('industry wire required');assert.equal(parsed.operation,value.operation);
const rejects=(v:unknown)=>assert.throws(()=>parseIndustryAnswerV1(Buffer.from(canonicalJson(v))));
for(const patch of [{company_policy:true},{business_accepted:true},{automatic_action_authorized:true},{current_read_lease_only:false},{expires_at:value.checked_at},{principal_id:'invalid'}])rejects({...value,...patch});
if(value.operation==='brief'){
 assert.ok(value.result.references.length);
 for(const row of value.result.references){assert.match(row.registered_source_id,/^[0-9a-f-]{36}$/);assert.equal(typeof row.reference.source_id,'string');}
 const changed=structuredClone(value);changed.result.references[0].reference.publisher='A different publisher';changed.result.comparison_sha256=sha256(Buffer.from(canonicalJson(changed.result.references)));
 rejects(changed); // Reference digest and whole comparison remain bound to actual original wire.
 const foreign=structuredClone(value);const quotes=foreign.result.references[0].evidence.supporting;
 assert.ok(quotes.length);quotes[0].ref.workspace_id='22222222-2222-4222-8222-222222222222';foreign.result.comparison_sha256=sha256(Buffer.from(canonicalJson(foreign.result.references)));rejects(foreign);
}else{rejects({...value,result:{...value.result,qualified_context_count:value.result.qualified_context_count+1}});}
console.log('ACTUAL_INVENTED_SERVICE_WIRE_PARSE_AND_TAMPER_CONTROLS_PASS',value.operation);
