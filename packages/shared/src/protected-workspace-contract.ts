/** Closed descriptive workspace; current permissions belong to the existing channel. */
import {canonicalHash,canonicalJson,canonicalUuid,instant,parseClosedJson,sha256} from './protected-server-binding';
import {validateDocumentaryAnswerV1,validateQualifiedEvidenceV1} from './protected-client-contracts';
const fail=():never=>{throw new Error('Current workspace unavailable');};
const exact=(v:unknown,fields:readonly string[]):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===fields.length&&fields.every(k=>Object.hasOwn(v,k));
const text=(v:unknown,max=4000):v is string=>typeof v==='string'&&!!v.trim()&&!v.includes('\0')&&v.length<=max;
const count=(v:unknown,max=2147483647):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=max;
const complete=(v:unknown)=>['complete','partial','ambiguous','conflicted'].includes(String(v));
export interface WorkspaceQuestionV1 {readonly schema_version:1;readonly protocol:'qualified-workspace-question-v1';readonly operation:'overview'|'process';readonly process_id:string|null;readonly page:number;readonly caller_deadline:string;}
export interface WorkspaceAnswerPacketV1 {readonly schema_version:1;readonly protocol:'qualified-workspace-answer-v1';readonly principal_id:string;readonly workspace_id:string;readonly model_id:string;readonly channel:'web'|'mcp';readonly operation:'overview'|'process';readonly process_id:string|null;readonly page:number;readonly request_sha256:string;readonly query_sha256:string;readonly checked_at:string;readonly expires_at:string;readonly current_read_lease_only:true;readonly retained_receipt_body_sha256:string;readonly retained_delivered_at:string;readonly retained_receipt_recorded_at:string;readonly retained_projection_lease_until:string;readonly result:Readonly<Record<string,unknown>>;readonly company_policy:false;readonly business_accepted:false;readonly automatic_action_authorized:false;}
export function validateWorkspaceQuestionV1(v:unknown):WorkspaceQuestionV1{
 if(!exact(v,['schema_version','protocol','operation','process_id','page','caller_deadline'])||v.schema_version!==1||v.protocol!=='qualified-workspace-question-v1'||!['overview','process'].includes(String(v.operation))||!(v.operation==='process'?text(v.process_id,200)&&v.process_id.trim()===v.process_id:v.process_id===null)||!count(v.page,2047)||typeof v.caller_deadline!=='string')return fail();
 instant(v.caller_deadline);return Object.freeze(v) as unknown as WorkspaceQuestionV1;
}
export function workspaceQuerySHA256V1(q:WorkspaceQuestionV1):string{validateWorkspaceQuestionV1(q);return sha256(Buffer.from(canonicalJson({schema_version:q.schema_version,protocol:q.protocol,operation:q.operation,process_id:q.process_id,page:q.page})));}
function evidence(v:unknown,workspace:string){if(!Array.isArray(v)||!v.length||v.length>1000)return fail();validateQualifiedEvidenceV1({supporting:v,opposing:[],unknown:[],temporal:[]},workspace);}
function process(v:unknown,workspace:string):asserts v is Record<string,unknown>{
 if(!exact(v,['process_id','label','scope','completeness','workflow_count','evidence'])||!text(v.process_id,200)||!text(v.label)||!text(v.scope)||!complete(v.completeness)||!count(v.workflow_count,1000))return fail();evidence(v.evidence,workspace);
}
const itemFields:Record<string,readonly string[]>={steps:['step_id','label','role_id','kind'],gateways:['gateway_id','kind'],transitions:['transition_id','from_id','to_id','condition_id','rework'],conditions:['condition_id','wording','applicability'],roles:['assignment_id','step_id','role_id'],artifacts:['artifact_id','label'],handoffs:['handoff_id','from_step','to_step','artifact_id']};
const identityFields:Record<string,string>={steps:'step_id',gateways:'gateway_id',transitions:'transition_id',conditions:'condition_id',roles:'assignment_id',artifacts:'artifact_id',handoffs:'handoff_id'};
function workflow(v:unknown,workspace:string):asserts v is Record<string,unknown>{
 if(!exact(v,['workflow_id','version','scope','completeness','reported_status','items'])||!text(v.workflow_id,200)||!count(v.version)||v.version===0||!text(v.scope)||!complete(v.completeness)||!['reported','confirmed'].includes(String(v.reported_status))||!Array.isArray(v.items)||v.items.length>512)return fail();
 const ids=new Set<string>(),nodes=new Set<string>(),steps=new Set<string>(),conditions=new Set<string>(),artifacts=new Set<string>();
 for(const row of v.items){
  if(!exact(row,['collection','identity','value','evidence'])||!text(row.collection,32)||!Object.hasOwn(itemFields,row.collection)||!text(row.identity,200)||ids.has(row.identity)||!exact(row.value,itemFields[row.collection]!))return fail();ids.add(row.identity);
  const value=row.value;if(value[identityFields[row.collection]!]!==row.identity)return fail();
  for(const [k,x] of Object.entries(value)){
   if(k==='rework'){if(typeof x!=='boolean')return fail();}
   else if((k==='role_id'&&row.collection==='steps'||k==='condition_id')&&x===null)continue;
   else if(!text(x,k==='wording'||k==='label'?4000:200))return fail();
  }
  if(row.collection==='steps'){if(!['activity','start','end','rejection','call','return'].includes(String(value.kind)))return fail();nodes.add(row.identity);steps.add(row.identity);}
  if(row.collection==='gateways'){if(!['exclusive_split','exclusive_join','parallel_split','parallel_join','unsupported'].includes(String(value.kind)))return fail();nodes.add(row.identity);}
  if(row.collection==='conditions'){if(!['known','unknown'].includes(String(value.applicability)))return fail();conditions.add(row.identity);}
  if(row.collection==='artifacts')artifacts.add(row.identity);
  evidence(row.evidence,workspace);
 }
 if(!steps.size)return fail();
 for(const row of v.items){const value=row.value as Record<string,unknown>;
  if(row.collection==='transitions'&&(!nodes.has(value.from_id as string)||!nodes.has(value.to_id as string)||value.condition_id!==null&&!conditions.has(value.condition_id as string)))return fail();
  if(row.collection==='roles'&&!steps.has(value.step_id as string))return fail();
  if(row.collection==='handoffs'&&(!steps.has(value.from_step as string)||!steps.has(value.to_step as string)||!artifacts.has(value.artifact_id as string)))return fail();
 }
}
export function parseWorkspaceAnswerV1(bytes:Uint8Array):WorkspaceAnswerPacketV1{
 const v=parseClosedJson(bytes,262144);
 if(!exact(v,['schema_version','protocol','principal_id','workspace_id','model_id','channel','operation','process_id','page','request_sha256','query_sha256','checked_at','expires_at','current_read_lease_only','retained_receipt_body_sha256','retained_delivered_at','retained_receipt_recorded_at','retained_projection_lease_until','result','company_policy','business_accepted','automatic_action_authorized'])||canonicalJson(v)!==Buffer.from(bytes).toString('utf8')||v.schema_version!==1||v.protocol!=='qualified-workspace-answer-v1'||!['principal_id','workspace_id','model_id'].every(k=>canonicalUuid(v[k]))||!['web','mcp'].includes(String(v.channel))||!['request_sha256','query_sha256','retained_receipt_body_sha256'].every(k=>canonicalHash(v[k]))||v.current_read_lease_only!==true||!['company_policy','business_accepted','automatic_action_authorized'].every(k=>v[k]===false))return fail();
 validateWorkspaceQuestionV1({schema_version:1,protocol:'qualified-workspace-question-v1',operation:v.operation,process_id:v.process_id,page:v.page,caller_deadline:v.expires_at});
 const checked=instant(v.checked_at),expires=instant(v.expires_at);if(checked>=expires||instant(v.retained_delivered_at)>checked||instant(v.retained_receipt_recorded_at)>checked||instant(v.retained_delivered_at)>=instant(v.retained_projection_lease_until))return fail();
 const r=v.result;
 if(!exact(r,['schema_version','purpose','model_version','model_content_sha256','declared_population','model_completeness','processes','selected_process','process_count','returned_process_count','process_list_complete','selected_process_id','workflows','answer','company_wide_completeness_verified','company_policy_confirmed','source_health_observed','automatic_action_authorized'])||r.schema_version!==1||r.purpose!=='qualified-workspace-view-v1'||!count(r.model_version)||r.model_version===0||!canonicalHash(r.model_content_sha256)||!text(r.declared_population)||!complete(r.model_completeness)||!Array.isArray(r.processes)||r.processes.length>64||!count(r.process_count)||r.process_count===0||r.returned_process_count!==r.processes.length||r.processes.length!==Math.min(64,r.process_count)||r.process_list_complete!==(r.process_count===r.processes.length)||r.selected_process_id!==v.process_id||!Array.isArray(r.workflows)||r.workflows.length>32||!['company_wide_completeness_verified','company_policy_confirmed','source_health_observed','automatic_action_authorized'].every(k=>r[k]===false))return fail();
 const ids=new Set<string>();for(const p of r.processes){process(p,v.workspace_id as string);if(ids.has(p.process_id as string))return fail();ids.add(p.process_id as string);}
 if(canonicalJson([...ids])!==canonicalJson([...ids].sort()))return fail();
 if(v.operation==='overview'){if(r.selected_process!==null||r.workflows.length)return fail();}
 else{process(r.selected_process,v.workspace_id as string);if(r.selected_process.process_id!==v.process_id||r.selected_process.workflow_count!==r.workflows.length)return fail();}
 const workflows=new Set<string>();for(const w of r.workflows){workflow(w,v.workspace_id as string);if(workflows.has(w.workflow_id as string))return fail();workflows.add(w.workflow_id as string);}
 const answer=validateDocumentaryAnswerV1(r.answer,{workspace_id:v.workspace_id as string,checked_at:v.checked_at as string});if(answer.model_version!==r.model_version||answer.model_content_hash!==r.model_content_sha256)return fail();
 return Object.freeze(v) as unknown as WorkspaceAnswerPacketV1;
}
