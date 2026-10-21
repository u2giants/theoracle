/** Closed model-review wire only. These DTO tests issue no authority. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { canonicalJson } from './replacement-server-binding';
import { parseModelReviewResponse,validateModelReviewRequest } from './replacement-protected-client';
const id='11111111-1111-4111-8111-111111111111',hash='a'.repeat(64);
const scope=()=>({schema_version:1,...Object.fromEntries(['process','customer','product','region'].map(k=>[k,{schema_version:1,mode:'unknown',identities:[]}]))});
const inspect=()=>({schema_version:1,operation:'inspect',model_id:id,base_version:1,caller_deadline:'2099-01-01T00:00:00Z'});
const assertion=()=>({schema_version:1,assertion_id:id,revision:1,predecessor_hash:null,subject_id:id,predicate:'reported_step',value:'Invented reported account',unit:null,provenance:'employee_account',scope:scope(),valid_time:'unknown',valid_from:null,valid_to:null,supporting_observations:[],opposing_observations:[],unknown_finding_ids:[],temporal_observations:[]});
const view=()=>({modelId:id,currentVersion:1,currentContentHash:hash,conflict:false,basePermitted:true,message:'Review exact changes before a new decision.',automaticRebase:false,policyEligibility:'unknown',baseRecordedAt:'2099-01-01T00:00:00Z',currentRecordedAt:'2099-01-01T00:00:00Z',currentAssertions:[{assertion:assertion(),evidence:{supporting:[],opposing:[],unknown:[],temporal:[]}}],totalAssertions:1,businessDecisions:[],changes:[],totalChanges:0,truncated:false});
const bytes=(value:unknown)=>Buffer.from(canonicalJson(value));
test('strict inspect and same exact decision assertion tuple preserve original narrowing',()=>{
 assert.equal(validateModelReviewRequest(bytes(inspect())).caller_deadline,'2099-01-01T00:00:00Z');
 const decision={...inspect(),operation:'decide',version:1,expected_hash:hash,decision:'accept',decision_kind:'employee-account',scope:scope(),assertions:[{assertion_id:id,revision:1}],command_id:id};delete (decision as Partial<{base_version:number}>).base_version;
 assert.equal(validateModelReviewRequest(bytes(decision)).decision_kind,'employee-account');
});
for(const key of ['actor','workspace','role','config','url','provider','grant','advance'])test('request refuses caller selector '+key,()=>assert.throws(()=>validateModelReviewRequest(bytes({...inspect(),[key]:id}))));
test('duplicates, noncanonical bytes and boolean revisions refuse',()=>{
 assert.throws(()=>validateModelReviewRequest(Buffer.from(canonicalJson(inspect()).replace('"base_version":1','"base_version":1,"base_version":1'))));
 assert.throws(()=>validateModelReviewRequest(Buffer.from(JSON.stringify(inspect()))));assert.throws(()=>validateModelReviewRequest(bytes({...inspect(),base_version:true})));
});
test('actual readonly response remains documentary, exact and bounded',()=>assert.equal(parseModelReviewResponse(bytes(view())).policyEligibility,'unknown'));
for(const damage of ['top','assertion','evidence','approval','unbounded'])test('peer cannot insert private data or authority '+damage,()=>{
 const value=view();if(damage==='top')Object.assign(value,{role:'private'});else if(damage==='assertion')Object.assign(value.currentAssertions[0]!.assertion,{database_url:'private'});else if(damage==='evidence')Object.assign(value.currentAssertions[0]!.evidence,{config:'private'});else if(damage==='approval')value.policyEligibility='accepted';else value.currentAssertions=Array(65).fill(value.currentAssertions[0]);
 assert.throws(()=>parseModelReviewResponse(bytes(value)));
});

for(const damage of ['provenance-array','scope-array'])test('response refuses coercible enum '+damage,()=>{
 const value=view();if(damage==='provenance-array')Object.assign(value.currentAssertions[0]!.assertion,{provenance:['employee_account']});else Object.assign(Reflect.get(value.currentAssertions[0]!.assertion.scope,'process'),{mode:['unknown']});
 assert.throws(()=>parseModelReviewResponse(bytes(value)));
});
for(const damage of ['decision','decision_kind','scope'])test('request refuses coercible enum '+damage,()=>{
 const decision={schema_version:1,operation:'decide',model_id:id,caller_deadline:'2099-01-01T00:00:00Z',version:1,expected_hash:hash,decision:'accept',decision_kind:'employee-account',scope:scope(),assertions:[{assertion_id:id,revision:1}],command_id:id};
 if(damage==='scope')Object.assign(Reflect.get(decision.scope,'process'),{mode:['unknown']});else Object.assign(decision,{[damage]:[decision[damage as 'decision'|'decision_kind']]});
 assert.throws(()=>validateModelReviewRequest(bytes(decision)));
});
