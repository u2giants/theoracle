/** Invented display contract only; no employee, SQL, provider or spend authority. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {canonicalJson,sha256} from '@oracle/shared/protected-server-binding';
import {validateQuestionEffectV1,parseConversationResponse} from '@oracle/shared/protected-conversation-contract';
import {validateDocumentaryAnswerV1,validateQualifiedAnswerContentsV1} from '@oracle/shared/protected-client-contracts';
const id='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222',hash='a'.repeat(64);
const original=' 不允许未经复核就发货。仅限样品。 ';
const scope={principal_id:id,workspace_id:id,thread_id:id,revision:2,mode:'ordinary' as const,event_id:id,original_text:original,original_sha256:sha256(original)};
const query=sha256(canonicalJson({schema_version:1,protocol:'qualified-natural-question-v1',question:original}));
const coverage={schema_version:1,declared_population:'Invented bounded scope',declared_process_count:1,represented_process_ids:['invented-process'],declared_assertion_count:1,selected_assertion_count:0,returned_assertion_count:0,complete_within_declared_model:false,entire_company_verified:false};
const old={schema_version:1,state:'missing',answer_text:'Qualified records do not establish an answer.',model_version:1,model_content_hash:hash,selection:'deterministic-qualified-records-v1',mode:'global',valid_at:'2026-10-21T00:00:00Z',known_at:null,records:[],findings:[],coverage,continuation_page:null,plan_sha256:hash,caveats:['No semantic or business acceptance.'],provider_generation_used:false,query_embedding_used:false,business_accepted:false,business_decisions_as_of:[],process_choices:[]};
const vector={...old,selection:'qualified-vector-records-v1',query_embedding_used:true};
const synthesis={...old,selection:'qualified-retained-facts-synthesis-v1',provider_generation_used:true};
const rendered={protocol:'qualified-answer-synthesis-references-v1',factual_groups:[],gap_codes:['coverage_incomplete','missing_evidence','unconfirmed_policy'],interpretation:null,coverage,semantic_entailment_verified:false,business_accepted:false};
const common={schema_version:1,protocol:'question-effect-result-v1',principal_id:id,workspace_id:id,thread_id:id,thread_revision:2,employee_event_id:id,original_sha256:scope.original_sha256,query_sha256:query,channel:'web',checked_at:'2026-10-21T00:00:01Z',expires_at:'2026-10-21T00:00:02Z',automatic_retry_allowed:false,semantic_entailment_verified:false,business_accepted:false};
const observed={...common,state:'observed',purpose:'qualified-query-embedding-v1',operation_id:id,model_id:id,model_version:1,model_content_hash:hash,accepted_projection_event_id:id,accepted_receipt_body_sha256:hash,native_receipt_sha256:hash,wire_sha256:hash,settled_response_sha256:hash,answer:vector,synthesis:null,clarification:null,provider_dispatched:true};
const unknown={...common,state:'unknown',purpose:null,operation_id:null,model_id:null,model_version:null,model_content_hash:null,accepted_projection_event_id:null,accepted_receipt_body_sha256:null,native_receipt_sha256:null,wire_sha256:null,settled_response_sha256:null,answer:null,synthesis:null,clarification:null,provider_dispatched:null};
const snapshot={schema_version:1,thread_id:id,workspace_id:id,principal_id:id,mode:'ordinary',revision:2,topic:'Invented',language:'zh',state:'active',question_count:0,pending_question_id:null,segment_started_at:'2026-10-21T00:00:00Z',segment_deadline:'2026-10-21T00:00:30Z',events:[{event_id:id,sequence:2,operation:'employee_turn',origin:'employee',turn_id:id,original_text:original,original_language:'zh',original_sha256:scope.original_sha256,corrects_event_id:null,question_id:null,need:null,response_kind:null,payload:{},created_at:'2026-10-21T00:00:00Z'}],recap:{},recap_sha256:hash,reviewed_revision:null,reviewed_sha256:null,company_policy_confirmed:false,source_qualified:false,question:null,question_id:null,answer_first:null,offer_start_interview:false,qualification_state:'pending',account_acknowledgement_only:true,original_registration_state:'not_registered'};
const bytes=(v:unknown)=>Buffer.from(canonicalJson(v));
test('old documentary guards remain exact and new variants cannot masquerade as old',()=>{
 assert.equal(validateDocumentaryAnswerV1(old,{workspace_id:id,checked_at:common.checked_at}).query_embedding_used,false);
 assert.throws(()=>validateDocumentaryAnswerV1(vector,{workspace_id:id,checked_at:common.checked_at}));
 assert.throws(()=>validateQualifiedAnswerContentsV1(vector,{workspace_id:id,checked_at:common.checked_at},'forged' as 'vector'));
});
test('actual variant discriminants remain separate and UNKNOWN never contains an answer or authority',()=>{
 assert.equal(validateQuestionEffectV1(observed,scope).answer?.query_embedding_used,true);
 const s=validateQuestionEffectV1({...observed,purpose:'qualified-answer-synthesis-v1',answer:synthesis,synthesis:rendered},scope);
 assert.equal(s.answer?.provider_generation_used,true);assert.equal(s.semantic_entailment_verified,false);
 assert.equal(validateQuestionEffectV1(unknown,scope).provider_dispatched,null);
 assert.equal(parseConversationResponse(bytes({...snapshot,qualified_effect:observed})).state,'active');
 assert.equal(parseConversationResponse(bytes(snapshot)).state,'active');
});
for(const patch of [{principal_id:other},{workspace_id:other},{thread_id:other},{thread_revision:1},{employee_event_id:other},{original_sha256:hash},{query_sha256:hash},{channel:'mcp'},{expires_at:common.checked_at},{expires_at:'2026-10-21T00:01:00Z'},{schema_version:true},{provider_dispatched:false},{native_receipt_sha256:null},{settled_response_sha256:'not-hash'},{accepted_projection_event_id:null},{model_content_hash:'b'.repeat(64)},{automatic_retry_allowed:true},{semantic_entailment_verified:true},{business_accepted:true},{unknown_authority:true}])test('refuses forged effect scope receipt or window '+JSON.stringify(patch).slice(0,90),()=>assert.throws(()=>validateQuestionEffectV1({...observed,...patch},scope)));
for(const patch of [{answer:vector},{model_id:id},{native_receipt_sha256:hash},{purpose:'qualified-query-embedding-v1'},{provider_dispatched:false},{clarification:'Can I retry?'}])test('UNKNOWN retains no invented observed fields '+JSON.stringify(patch).slice(0,90),()=>assert.throws(()=>validateQuestionEffectV1({...unknown,...patch},scope)));
test('immutable original whitespace and Chinese negation remain bound and no extra interview clarification appears',()=>{
 assert.throws(()=>validateQuestionEffectV1(observed,{...scope,original_text:original.trim()}));
 assert.throws(()=>validateQuestionEffectV1(observed,{...scope,original_text:'允许未经复核就发货。'}));
 assert.throws(()=>validateQuestionEffectV1({...unknown,state:'clarification',provider_dispatched:false,clarification:'Which process?'},{...scope,mode:'interview'}));
 assert.throws(()=>validateQuestionEffectV1(observed,{...scope,original_text:'\ud800',original_sha256:sha256('\ud800')}));
});
test('separately labeled inference remains ordinary-only and cannot masquerade as factual evidence or acceptance',()=>{
 const s={...observed,purpose:'qualified-answer-synthesis-v1',answer:synthesis,synthesis:{...rendered,interpretation:{classification:'inference/unverified interpretation',text:'An unverified possible explanation.'}}};
 assert.equal(validateQuestionEffectV1(s,scope).purpose,'qualified-answer-synthesis-v1');
 assert.throws(()=>validateQuestionEffectV1(s,{...scope,mode:'interview'}));
 for(const patch of [{interpretation:{classification:'company-policy',text:'Approved.'}},{gap_codes:[]},{coverage:{...coverage,entire_company_verified:true}},{semantic_entailment_verified:true},{factual_groups:[{classification:'reported',assertion_ids:[]}]}])assert.throws(()=>validateQuestionEffectV1({...s,synthesis:{...s.synthesis,...patch}},scope));
});
test('same outer snapshot cannot adopt another event revision employee or original',()=>{
 for(const change of [{revision:3},{principal_id:other},{workspace_id:other},{events:[{...snapshot.events[0],event_id:other}]},{events:[]}])assert.throws(()=>parseConversationResponse(bytes({...snapshot,...change,qualified_effect:observed})));
});
