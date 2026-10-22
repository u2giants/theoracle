/** Strict wire refusal; these values appoint no user or runtime. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {canonicalJson} from './replacement-server-binding';
import {validateConversationRequest,parseConversationResponse} from './replacement-conversation-contract';
const id='11111111-1111-4111-8111-111111111111';
const bytes=(v:unknown)=>Buffer.from(canonicalJson(v));
const create={schema_version:1,command_id:id,caller_deadline:'2099-01-01T00:00:00Z',mode:'interview',topic:'Invented interview',language:'zh'};
const pause={schema_version:1,command_id:id,caller_deadline:'2099-01-01T00:00:00Z',operation:'pause',thread_id:id,expected_revision:1};
test('literal create and pause preserve the closed public operations',()=>{
 assert.equal(validateConversationRequest(bytes(create)).mode,'interview');
 assert.equal(validateConversationRequest(bytes(pause)).operation,'pause');
 assert.equal(parseConversationResponse(bytes({schema_version:1,state:'UNKNOWN',resend_authorized:false})).state,'UNKNOWN');
});
for(const mode of [['interview'],true,1])test('coercible create mode refuses '+JSON.stringify(mode),()=>{
 assert.throws(()=>validateConversationRequest(bytes({...create,mode})));
});
for(const operation of [['pause'],['employee_turn'],true])test('coercible operation refuses '+JSON.stringify(operation),()=>{
 assert.throws(()=>validateConversationRequest(bytes({...pause,operation})));
});
test('coercible UNKNOWN response cannot masquerade as the literal state',()=>{
 assert.throws(()=>parseConversationResponse(bytes({schema_version:1,state:['UNKNOWN'],resend_authorized:false})));
});
