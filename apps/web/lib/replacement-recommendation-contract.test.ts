import assert from 'node:assert/strict';
import {test} from 'node:test';
import documentaryItem from '../tests/oracle2/recommendation-documentary.fixture.json';
import {canonicalJson} from '../../../packages/shared/src/protected-canonical-json';
import {validateRecommendationRequestV1,parseRecommendationIndexV1,parseRecommendationReceiptV1,parseRecommendationViewV1} from '../../../packages/shared/src/protected-recommendation-contract';
const id='11111111-1111-4111-8111-111111111111';
const until='2026-10-21T00:00:20Z';
const bytes=(p:unknown)=>new TextEncoder().encode(canonicalJson(p));
const selector={schema_version:1,artifact_id:id,artifact_version:1,artifact_sha256:'a'.repeat(64),recommendation_id:id};
const common={schema_version:1,caller_deadline:until};
test('closed listing has no caller scope or numeric inputs',()=>{
 assert.equal(validateRecommendationRequestV1(bytes({...common,operation:'list'})).operation,'list');
 for(const [key,value] of Object.entries({actor:id,model_id:id,selector,amount:'12',role:'admin',config:'x'}))assert.throws(()=>validateRecommendationRequestV1(bytes({...common,operation:'list',[key]:value})));
});
test('all personal decisions require exact option and reason without authority claims',()=>{
 for(const decision of ['accept','reject','defer'])assert.equal(validateRecommendationRequestV1(bytes({...common,operation:'feedback',selector,expected_head:0,command_id:id,decision,option_id:decision==='accept'?'opt:1':null,reason:'Personal preference only'})).operation,'feedback');
 for(const damage of [{decision:['accept']},{expected_head:'0'},{option_id:null},{reason:' '},{approved:true}])assert.throws(()=>validateRecommendationRequestV1(bytes({...common,operation:'feedback',selector,expected_head:0,command_id:id,decision:'accept',option_id:'opt:1',reason:'Personal preference',...damage})));
});
test('measurement is exact qualified assertion selector and never caller numbers',()=>{
 const value={...common,operation:'measurement',selector,expected_head:0,command_id:id,experiment_id:id,phase:'baseline',assertion_id:id,assertion_revision:1};
 assert.equal(validateRecommendationRequestV1(bytes(value)).operation,'measurement');
 for(const damage of [{amount:'12.5'},{currency:'USD'},{phase:['baseline']},{assertion_revision:'1'}])assert.throws(()=>validateRecommendationRequestV1(bytes({...value,...damage})));
});
test('noncanonical, duplicate, invalid date and renewed-format inputs are refused',()=>{
 for(const raw of ['{"schema_version":1,"schema_version":1,"operation":"list","caller_deadline":"'+until+'"}',JSON.stringify({...common,operation:'list'})])assert.throws(()=>validateRecommendationRequestV1(new TextEncoder().encode(raw)));
 for(const caller_deadline of ['2026-02-31T00:00:20Z','2026-10-21T00:00:20.000000Z','2026-10-21T00:00:20+00:00'])assert.throws(()=>validateRecommendationRequestV1(bytes({...common,operation:'list',caller_deadline})));
});
test('index represents coverage gap and refuses duplicate or authority-laundered entries',()=>{
 const index={schema_version:1,kind:'recommendation-index-v1',entries:[{selector,label:'Review reported delay',label_truncated:false,lens:'approval_exception'}],coverage_gap:false,list_complete:true,scope:'current-permitted-model-advice',valid_until:until,policy_accepted:false,effect_executed:false,business_acceptance:false};
 assert.equal(parseRecommendationIndexV1(bytes(index)).entries.length,1);
 assert.equal(parseRecommendationIndexV1(bytes({...index,coverage_gap:true,list_complete:false})).list_complete,false);
 for(const damage of [{policy_accepted:true},{entries:[...index.entries,...index.entries]},{coverage_gap:true},{entries:[{...index.entries[0],lens:['approval_exception']}]}])assert.throws(()=>parseRecommendationIndexV1(bytes({...index,...damage})));
});
test('late original write receipt remains read-only rather than renewed permission',()=>{
 const receipt={schema_version:1,receipt_kind:'action',artifact_id:id,artifact_version:1,recommendation_id:id,artifact_sha256:'a'.repeat(64),command_id:id,event_id:id,sequence:1,kind:'feedback',recorded_at:until,original_operation_valid_until:until,original_operation_window_unexpired:false,receipt_read_only:true,write_authorized:false,dispatch_authorized:false,stale:true,redacted:true,valid_until:until,policy_accepted:false,effect_executed:false,causal_savings:false,business_acceptance:false};
 assert.equal(parseRecommendationReceiptV1(bytes(receipt)).original_operation_window_unexpired,false);
 for(const damage of [{write_authorized:true},{dispatch_authorized:true},{reason:'leak'},{payload:{}}])assert.throws(()=>parseRecommendationReceiptV1(bytes({...receipt,...damage})));
});

test('lone Unicode surrogates are refused before transport',()=>{
 assert.throws(()=>validateRecommendationRequestV1(bytes({...common,operation:'feedback',selector,expected_head:0,command_id:id,decision:'reject',option_id:null,reason:'\ud800'})));
});


test('readable documentary fields cannot carry private context, false authority or redacted content',()=>{
 const view={schema_version:1,artifact_id:id,artifact_version:1,recommendation_id:id,head_revision:0,stale:false,redacted:false,events:[],valid_until:until,policy_accepted:false,effect_executed:false,causal_savings:false,realized_savings_verified:false,business_acceptance:false,recommendation:documentaryItem,parent_version:1,comparisons:[],measurement_sources:[],measurement_coverage_gap:false,evidence:{supporting:[],opposing:[],unknown:[],temporal:[]},evidence_coverage_gap:false};
 assert.equal(parseRecommendationViewV1(bytes(view)).parent_version,1);
 for(const fault of ['private','enum','authority','redacted','decimal']){
  const value=structuredClone(view);
  if(fault==='private')Object.assign(value.recommendation,{database_url:'private'});
  if(fault==='enum')Object.assign(value.recommendation.advice,{lens:['approval_exception']});
  if(fault==='authority')Object.assign(value.recommendation,{policy_accepted:true});
  if(fault==='redacted')value.redacted=true;
  if(fault==='decimal')Object.assign(value.recommendation.advice.options[1]!.forecast!.baseline,{amount:'NaN'});
  assert.throws(()=>parseRecommendationViewV1(bytes(value)),fault);
 }
});
