/** Pure documentary wire syntax. Neither selectors nor feedback grant authority. */
import {canonicalJson} from './protected-canonical-json';
export type AdviceSelectorV1=Readonly<{schema_version:1;artifact_id:string;artifact_version:number;artifact_sha256:string;recommendation_id:string}>;
export type AdviceRequestV1=Readonly<{schema_version:1;operation:'list';caller_deadline:string}>
 |Readonly<{schema_version:1;operation:'inspect';selector:AdviceSelectorV1;caller_deadline:string}>
 |Readonly<{schema_version:1;operation:'feedback';selector:AdviceSelectorV1;expected_head:number;command_id:string;decision:'accept'|'reject'|'defer';option_id:string|null;reason:string;caller_deadline:string}>
 |Readonly<{schema_version:1;operation:'measurement';selector:AdviceSelectorV1;expected_head:number;command_id:string;experiment_id:string;phase:'baseline'|'followup';assertion_id:string;assertion_revision:number;caller_deadline:string}>
 |Readonly<{schema_version:1;operation:'reconcile-feedback'|'reconcile-measurement';selector:AdviceSelectorV1;command_id:string;caller_deadline:string}>;
const fail=():never=>{throw new Error('Recommendation review unavailable');};
export const adviceRecordV1=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:fail();
const exact=(v:unknown,keys:readonly string[])=>{const p=adviceRecordV1(v);return Object.keys(p).length===keys.length&&keys.every(k=>Object.hasOwn(p,k));};
const uuid=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(v);
const hash=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const integer=(v:unknown,min=0,max=2147483647)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=min&&v<=max;
const text=(v:unknown,max:number)=>typeof v==='string'&&[...v].length>0&&[...v].length<=max;
const utc=(v:unknown)=>typeof v==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(Date.parse(v)).toISOString().slice(0,19)===v.slice(0,19);
export function adviceSelectorV1(v:unknown):AdviceSelectorV1{
 const p=adviceRecordV1(v);
 if(!exact(p,['schema_version','artifact_id','artifact_version','artifact_sha256','recommendation_id'])||p.schema_version!==1||!uuid(p.artifact_id)||!integer(p.artifact_version,1)||!hash(p.artifact_sha256)||!uuid(p.recommendation_id))return fail();
 return Object.freeze(p) as AdviceSelectorV1;
}
function closed(bytes:Uint8Array,max:number):Record<string,unknown>{
 if(!(bytes instanceof Uint8Array)||!bytes.byteLength||bytes.byteLength>max)return fail();
 const raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes);const p=adviceRecordV1(JSON.parse(raw));
 const unicode=(v:unknown,depth=0):void=>{if(depth>64)return fail();if(typeof v==='string'){for(let i=0;i<v.length;i++){const n=v.charCodeAt(i);if(n>=0xd800&&n<=0xdbff){const next=v.charCodeAt(++i);if(!(next>=0xdc00&&next<=0xdfff))return fail();}else if(n>=0xdc00&&n<=0xdfff)return fail();}}else if(Array.isArray(v))for(const x of v)unicode(x,depth+1);else if(v&&typeof v==='object')for(const [k,x] of Object.entries(v)){unicode(k,depth+1);unicode(x,depth+1);}};unicode(p);
 if(canonicalJson(p)!==raw)return fail();return p;
}
export function validateRecommendationRequestV1(bytes:Uint8Array):AdviceRequestV1{
 const p=closed(bytes,16384),common=['schema_version','operation','caller_deadline'];
 if(p.schema_version!==1||typeof p.caller_deadline!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.(?!000000)\d{6})?Z$/.test(p.caller_deadline)||!utc(p.caller_deadline))return fail();
 if(p.operation==='list'){if(!exact(p,common))return fail();}
 else{
  adviceSelectorV1(p.selector);const fields=[...common,'selector'];
  if(p.operation==='inspect'){if(!exact(p,fields))return fail();}
  else if(p.operation==='reconcile-feedback'||p.operation==='reconcile-measurement'){
   if(!exact(p,[...fields,'command_id'])||!uuid(p.command_id))return fail();
  }else if(p.operation==='feedback'){
   if(!exact(p,[...fields,'expected_head','command_id','decision','option_id','reason'])||!integer(p.expected_head,0,16383)||!uuid(p.command_id)||typeof p.decision!=='string'||!['accept','reject','defer'].includes(p.decision)||!text(p.reason,1600)||!(p.reason as string).trim()||(p.decision==='accept'?!text(p.option_id,256):p.option_id!==null))return fail();
  }else if(p.operation==='measurement'){
   if(!exact(p,[...fields,'expected_head','command_id','experiment_id','phase','assertion_id','assertion_revision'])||!integer(p.expected_head,0,16383)||!uuid(p.command_id)||!uuid(p.experiment_id)||typeof p.phase!=='string'||!['baseline','followup'].includes(p.phase)||!uuid(p.assertion_id)||!integer(p.assertion_revision,1))return fail();
  }else return fail();
 }
 return Object.freeze(p) as AdviceRequestV1;
}
export type AdviceIndexV1=Readonly<{schema_version:1;kind:'recommendation-index-v1';entries:readonly Readonly<{selector:AdviceSelectorV1;label:string;label_truncated:boolean;lens:'handoff_rework'|'approval_exception'|'information_duplication'}>[];coverage_gap:boolean;list_complete:boolean;scope:'current-permitted-model-advice';valid_until:string;policy_accepted:false;effect_executed:false;business_acceptance:false}>;
export function parseRecommendationIndexV1(bytes:Uint8Array):AdviceIndexV1{
 const p=closed(bytes,262144);
 if(!exact(p,['schema_version','kind','entries','coverage_gap','list_complete','scope','valid_until','policy_accepted','effect_executed','business_acceptance'])||p.schema_version!==1||p.kind!=='recommendation-index-v1'||p.scope!=='current-permitted-model-advice'||!utc(p.valid_until)||p.policy_accepted!==false||p.effect_executed!==false||p.business_acceptance!==false||typeof p.coverage_gap!=='boolean'||p.list_complete!==!p.coverage_gap||!Array.isArray(p.entries)||p.entries.length>64)return fail();
 const seen=new Set<string>();
 for(const entry of p.entries){const e=adviceRecordV1(entry);if(!exact(e,['selector','label','label_truncated','lens'])||!text(e.label,160)||typeof e.label_truncated!=='boolean'||typeof e.lens!=='string'||!['handoff_rework','approval_exception','information_duplication'].includes(e.lens))return fail();const s=adviceSelectorV1(e.selector),key=canonicalJson(s);if(seen.has(key))return fail();seen.add(key);}
 return Object.freeze(p) as unknown as AdviceIndexV1;
}
const stringArray=(v:unknown,max:number,min=0)=>Array.isArray(v)&&v.length>=min&&v.length<=max&&v.every(x=>text(x,4000));
const array=(v:unknown,max:number,min=0):unknown[]=>Array.isArray(v)&&v.length>=min&&v.length<=max?v:fail();
function measure(v:unknown){const p=adviceRecordV1(v);if(!exact(p,['amount','unit','period','currency'])||!text(p.amount,96)||typeof p.amount!=='string'||! /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:E[+-]?[0-9]+)?$/.test(p.amount)||!text(p.unit,100)||!text(p.period,100)||(p.currency!==null&&(typeof p.currency!=='string'||! /^[A-Z]{3}$/.test(p.currency))))return fail();}
function measurement(v:unknown){const p=adviceRecordV1(v);if(!exact(p,['schema_version','contract','amount','unit','currency','period','population_id','window_start','window_end','observed_through','complete','censored'])||p.schema_version!==1||p.contract!=='qualified-measurement-evidence-v1'||!uuid(p.population_id)||!utc(p.window_start)||!utc(p.window_end)||!utc(p.observed_through)||typeof p.complete!=='boolean'||typeof p.censored!=='boolean')return fail();measure({amount:p.amount,unit:p.unit,period:p.period,currency:p.currency});}
function scope(v:unknown){const p=adviceRecordV1(v);if(!exact(p,['schema_version','process','customer','product','region'])||p.schema_version!==1)return fail();for(const key of ['process','customer','product','region']){const d=adviceRecordV1(p[key]);if(!exact(d,['schema_version','mode','identities'])||d.schema_version!==1||typeof d.mode!=='string'||!['unknown','all','exact'].includes(d.mode)||!Array.isArray(d.identities)||d.identities.length>64||d.identities.some(x=>!uuid(x)))return fail();}}
function adviceItem(v:unknown){
 const p=adviceRecordV1(v);if(!exact(p,['schema_version','recommendation_id','advice','scope','problem','competing_explanations','effort','risks','owner_role_description','review_due','experiments','expected_benefit','policy_accepted','effect_executed','realized_savings_verified'])||p.schema_version!==1||!uuid(p.recommendation_id)||!text(p.problem,4000)||!text(p.effort,2000)||!text(p.owner_role_description,500)||!utc(p.review_due)||!stringArray(p.competing_explanations,8,1)||!stringArray(p.risks,16,1)||p.expected_benefit!=='unknown'||p.policy_accepted!==false||p.effect_executed!==false||p.realized_savings_verified!==false)return fail();scope(p.scope);
 const a=adviceRecordV1(p.advice);if(!exact(a,['recommendation_id','lens','evidence','options','opposing_evidence','opposing_unknown','scope_note'])||a.recommendation_id!==p.recommendation_id||typeof a.lens!=='string'||!['handoff_rework','approval_exception','information_duplication'].includes(a.lens)||!stringArray(a.opposing_evidence,256)||typeof a.opposing_unknown!=='boolean'||!text(a.scope_note,4000))return fail();
 const e=adviceRecordV1(a.evidence);if(!exact(e,['revision_id','evidence_refs','evidence_seal'])||!text(e.revision_id,256)||!stringArray(e.evidence_refs,256,1)||!hash(e.evidence_seal))return fail();
 for(const value of array(a.options,16,2)){const o=adviceRecordV1(value);if(!exact(o,['option_id','title','is_no_change','evidence_refs','forecast','downstream_costs','measured_basis'])||!text(o.option_id,256)||!text(o.title,4000)||typeof o.is_no_change!=='boolean'||!stringArray(o.evidence_refs,256,1))return fail();
  if(o.forecast!==null){const f=adviceRecordV1(o.forecast);if(!exact(f,['baseline','alternative','assumptions','kind'])||f.kind!=='forecast'||!stringArray(f.assumptions,32,1))return fail();measure(f.baseline);measure(f.alternative);}
  for(const value of [...array(o.downstream_costs,32,1),...array(o.measured_basis,32)]){const c=adviceRecordV1(value);if(!exact(c,['kind','measure'])||typeof c.kind!=='string'||!['actual_cost','capacity_estimate','forecast_scenario','missing'].includes(c.kind))return fail();if(c.measure!==null)measure(c.measure);}
 }
 for(const value of array(p.experiments,16,1)){const x=adviceRecordV1(value);if(!exact(x,['schema_version','experiment_id','option_id','metric_id','unit','currency','period','population_id','baseline_start','baseline_end','followup_start','followup_end','success_metric','reversible_step'])||x.schema_version!==1||!uuid(x.experiment_id)||!uuid(x.metric_id)||!uuid(x.population_id)||!text(x.option_id,256)||!text(x.unit,100)||!text(x.period,100)||(x.currency!==null&&!text(x.currency,3))||!text(x.success_metric,1000)||!text(x.reversible_step,2000)||['baseline_start','baseline_end','followup_start','followup_end'].some(k=>!utc(x[k])))return fail();}
}
function presentation(v:Record<string,unknown>){
 for(const value of array(v.measurement_sources,64)){const x=adviceRecordV1(value);if(!exact(x,['experiment_id','phase','assertion_id','assertion_revision','measurement','reported_only','causal_savings','realized_savings_verified'])||!uuid(x.experiment_id)||!uuid(x.assertion_id)||!integer(x.assertion_revision,1)||typeof x.phase!=='string'||!['baseline','followup'].includes(x.phase)||x.reported_only!==true||x.causal_savings!==false||x.realized_savings_verified!==false)return fail();measurement(x.measurement);}
 const evidence=adviceRecordV1(v.evidence);let count=0,bytes=0;for(const values of Object.values(evidence))for(const value of array(values,64)){const q=adviceRecordV1(value);if(!exact(q,['source_id','source_revision','start','end','quote','original_sha256','reading_sha256'])||!uuid(q.source_id)||!integer(q.source_revision,1)||!integer(q.start)||!integer(q.end,1)||Number(q.end)<=Number(q.start)||!text(q.quote,32768)||!hash(q.original_sha256)||!hash(q.reading_sha256))return fail();count++;bytes+=new TextEncoder().encode(q.quote as string).length;}if(count>64||bytes>32768)return fail();
 for(const value of array(v.events,128)){const e=adviceRecordV1(value);if(!exact(e,['event_id','sequence','kind','recorded_at','payload'])||!uuid(e.event_id)||!integer(e.sequence,1,16384)||typeof e.kind!=='string'||!['feedback','baseline','followup'].includes(e.kind)||!utc(e.recorded_at))return fail();if(e.payload!==null){const p=adviceRecordV1(e.payload);if(e.kind==='feedback'){if(!exact(p,['decision','option_id','reason','falsifies_facts','policy_accepted','effect_executed'])||typeof p.decision!=='string'||!['accept','reject','defer'].includes(p.decision)||(p.option_id!==null&&!text(p.option_id,256))||!text(p.reason,1600)||p.falsifies_facts!==false||p.policy_accepted!==false||p.effect_executed!==false)return fail();}else{if(!exact(p,['experiment_id','assertion_id','assertion_revision','assertion_sha256','measurement','reported_only','causal_savings','realized_savings_verified'])||!uuid(p.experiment_id)||!uuid(p.assertion_id)||!integer(p.assertion_revision,1)||!hash(p.assertion_sha256)||p.reported_only!==true||p.causal_savings!==false||p.realized_savings_verified!==false)return fail();measurement(p.measurement);}}}
 for(const value of array(v.comparisons,16)){const c=adviceRecordV1(value);const reported=c.state==='reported-difference';if(!exact(c,reported?['experiment_id','state','observed_difference','unit','currency','period','causal_savings','realized_savings_verified']:['experiment_id','state','observed_difference','causal_savings','realized_savings_verified'])||!uuid(c.experiment_id)||typeof c.state!=='string'||!['unavailable','incomplete','reported-difference'].includes(c.state)||c.causal_savings!==false||c.realized_savings_verified!==false||(reported?!text(c.observed_difference,96):c.observed_difference!==null))return fail();if(reported)measure({amount:c.observed_difference,unit:c.unit,period:c.period,currency:c.currency});}
}
/** Preserve server-reported documentary fields without inventing effects or savings. */
export function parseRecommendationViewV1(bytes:Uint8Array):Readonly<Record<string,unknown>>{
 const p=closed(bytes,262144);
 const fields=['schema_version','artifact_id','artifact_version','recommendation_id','head_revision','stale','redacted','events','valid_until','policy_accepted','effect_executed','causal_savings','realized_savings_verified','business_acceptance','recommendation','parent_version','comparisons','measurement_sources','measurement_coverage_gap','evidence','evidence_coverage_gap'];
 if(!exact(p,fields)||p.schema_version!==1||!uuid(p.artifact_id)||!integer(p.artifact_version,1)||!uuid(p.recommendation_id)||!integer(p.head_revision,0,16383)||!utc(p.valid_until)||typeof p.stale!=='boolean'||typeof p.redacted!=='boolean'||['policy_accepted','effect_executed','causal_savings','realized_savings_verified','business_acceptance'].some(k=>p[k]!==false)||!Array.isArray(p.events)||p.events.length>128||!Array.isArray(p.comparisons)||p.comparisons.length>16||!Array.isArray(p.measurement_sources)||p.measurement_sources.length>64||typeof p.measurement_coverage_gap!=='boolean'||typeof p.evidence_coverage_gap!=='boolean')return fail();
 const evidence=adviceRecordV1(p.evidence);if(!exact(evidence,['supporting','opposing','unknown','temporal'])||Object.values(evidence).some(v=>!Array.isArray(v)||v.length>64))return fail();
 if(p.redacted&&p.events.some(e=>adviceRecordV1(e).payload!==null))return fail();
 if(p.redacted&&(p.recommendation!==null||p.parent_version!==null||p.comparisons.length||p.measurement_sources.length||Object.values(evidence).some(v=>(v as unknown[]).length)))return fail();
 presentation(p);
 if(!p.redacted){adviceItem(p.recommendation);const item=adviceRecordV1(p.recommendation);if(item.recommendation_id!==p.recommendation_id||item.policy_accepted!==false||item.effect_executed!==false||item.realized_savings_verified!==false||!integer(p.parent_version,1))return fail();}
 return Object.freeze(p);
}
export function parseRecommendationReceiptV1(bytes:Uint8Array):Readonly<Record<string,unknown>>{
 const p=closed(bytes,4096);
 const fields=['schema_version','receipt_kind','artifact_id','artifact_version','recommendation_id','artifact_sha256','command_id','event_id','sequence','kind','recorded_at','original_operation_valid_until','original_operation_window_unexpired','receipt_read_only','write_authorized','dispatch_authorized','stale','redacted','valid_until','policy_accepted','effect_executed','causal_savings','business_acceptance'];
 if(!exact(p,fields)||p.schema_version!==1||p.receipt_kind!=='action'||!uuid(p.artifact_id)||!integer(p.artifact_version,1)||!uuid(p.recommendation_id)||!hash(p.artifact_sha256)||!uuid(p.command_id)||!uuid(p.event_id)||!integer(p.sequence,1,16384)||typeof p.kind!=='string'||!['feedback','baseline','followup'].includes(p.kind)||!utc(p.recorded_at)||!utc(p.original_operation_valid_until)||!utc(p.valid_until)||typeof p.original_operation_window_unexpired!=='boolean'||typeof p.stale!=='boolean'||typeof p.redacted!=='boolean'||p.receipt_read_only!==true||['write_authorized','dispatch_authorized','policy_accepted','effect_executed','causal_savings','business_acceptance'].some(k=>p[k]!==false))return fail();
 return Object.freeze(p);
}
export type RecommendationPacketV1=Readonly<{advice:AdviceIndexV1|Readonly<Record<string,unknown>>;validUntil:string}>;
export function parseRecommendationResponseV1(bytes:Uint8Array):RecommendationPacketV1{
 const raw=closed(bytes,262144);
 const advice=raw.kind==='recommendation-index-v1'?parseRecommendationIndexV1(bytes):raw.receipt_kind==='action'?parseRecommendationReceiptV1(bytes):parseRecommendationViewV1(bytes);
 return Object.freeze({advice,validUntil:advice.valid_until as string});
}
export function parseRecommendationEnvelopeV1(bytes:Uint8Array,expected:Readonly<{principal_id:string;workspace_id:string;model_id:string;request_sha256:string;request:AdviceRequestV1}>):RecommendationPacketV1{
 const envelope=closed(bytes,262144),q=expected.request;
 if(!exact(envelope,['schema_version','principal_id','workspace_id','model_id','request_sha256','operation','command_id','expected_head','result'])||envelope.schema_version!==1||envelope.principal_id!==expected.principal_id||envelope.workspace_id!==expected.workspace_id||envelope.model_id!==expected.model_id||envelope.request_sha256!==expected.request_sha256||envelope.operation!==q.operation||envelope.command_id!==('command_id'in q?q.command_id:null)||envelope.expected_head!==('expected_head'in q?q.expected_head:null))return fail();
 const body=new TextEncoder().encode(canonicalJson(envelope.result)),packet=parseRecommendationResponseV1(body),result=adviceRecordV1(packet.advice);
 if(q.operation==='list'){if(result.kind!=='recommendation-index-v1')return fail();}
 else{
  if(result.artifact_id!==q.selector.artifact_id||result.artifact_version!==q.selector.artifact_version||result.recommendation_id!==q.selector.recommendation_id)return fail();
  if(q.operation==='reconcile-feedback'||q.operation==='reconcile-measurement'){
   if(result.receipt_kind!=='action'||result.command_id!==q.command_id||result.artifact_sha256!==q.selector.artifact_sha256||(q.operation==='reconcile-feedback'?result.kind!=='feedback':!['baseline','followup'].includes(String(result.kind))))return fail();
  }else{
   if(result.receipt_kind!==undefined||result.kind!==undefined)return fail();
   if(q.operation==='feedback'||q.operation==='measurement'){
    if(result.head_revision!==q.expected_head+1||result.redacted!==false||result.stale!==false)return fail();
    const events=result.events as unknown[],event=events.map(adviceRecordV1).find(e=>e.sequence===q.expected_head+1);if(!event)return fail();const payload=adviceRecordV1(event.payload);
    if(q.operation==='feedback'){
     if(event.kind!=='feedback'||payload.decision!==q.decision||payload.option_id!==q.option_id||payload.reason!==q.reason)return fail();
    }else if(event.kind!==q.phase||payload.experiment_id!==q.experiment_id||payload.assertion_id!==q.assertion_id||payload.assertion_revision!==q.assertion_revision)return fail();
   }
  }
 }
 return packet;
}
