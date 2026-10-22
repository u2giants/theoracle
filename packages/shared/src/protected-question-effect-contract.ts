/** Closed optional SQL019 question-effect display. Parsing never grants access,
 * provider/spend permission, source qualification or semantic/business acceptance.
 * The concrete server proves actual SQL024/native/central-settled custody and
 * current complete recipient/source/ACK scope before publishing this packet.
 */
import {canonicalHash,canonicalJson,canonicalUuid,instant,sha256} from './protected-server-binding';
import {validateQualifiedAnswerContentsV1} from './protected-client-contracts';
const fail=():never=>{throw new Error('Qualified question effect unavailable');};
const exact=(v:unknown,keys:readonly string[]):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const integer=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=1&&v<=2147483647;
const plain=(v:unknown,max=2000):v is string=>typeof v==='string'&&!!v.trim()&&!v.includes('\0')&&[...v].length<=max&&Buffer.byteLength(v,'utf8')<=max*4;
export interface QuestionEffectScopeV1 {
 readonly principal_id:string;readonly workspace_id:string;readonly thread_id:string;readonly revision:number;
 readonly mode:'ordinary'|'interview';readonly event_id:string;readonly original_text:string;readonly original_sha256:string;
}
export interface QuestionEffectPacketV1 {
 readonly schema_version:1;readonly protocol:'question-effect-result-v1';readonly state:'observed'|'clarification'|'unknown'|'unavailable';
 readonly principal_id:string;readonly workspace_id:string;readonly thread_id:string;readonly thread_revision:number;
 readonly employee_event_id:string;readonly original_sha256:string;readonly query_sha256:string;readonly channel:'web';
 readonly checked_at:string;readonly expires_at:string;readonly purpose:'qualified-query-embedding-v1'|'qualified-answer-synthesis-v1'|null;
 readonly operation_id:string|null;readonly model_id:string|null;readonly model_version:number|null;readonly model_content_hash:string|null;
 readonly accepted_projection_event_id:string|null;readonly accepted_receipt_body_sha256:string|null;readonly native_receipt_sha256:string|null;
 readonly wire_sha256:string|null;readonly settled_response_sha256:string|null;readonly answer:Readonly<Record<string,unknown>>|null;
 readonly synthesis:Readonly<Record<string,unknown>>|null;readonly clarification:string|null;readonly provider_dispatched:boolean|null;
 readonly automatic_retry_allowed:false;readonly semantic_entailment_verified:false;readonly business_accepted:false;
}
const keys=['schema_version','protocol','state','principal_id','workspace_id','thread_id','thread_revision','employee_event_id','original_sha256','query_sha256','channel','checked_at','expires_at','purpose','operation_id','model_id','model_version','model_content_hash','accepted_projection_event_id','accepted_receipt_body_sha256','native_receipt_sha256','wire_sha256','settled_response_sha256','answer','synthesis','clarification','provider_dispatched','automatic_retry_allowed','semantic_entailment_verified','business_accepted'] as const;
type EvidenceGroups={readonly supporting:unknown[];readonly opposing:unknown[];readonly unknown:unknown[];readonly temporal:unknown[]};
const observations=['purpose','operation_id','model_id','model_version','model_content_hash','accepted_projection_event_id','accepted_receipt_body_sha256','native_receipt_sha256','wire_sha256','settled_response_sha256','answer','synthesis'] as const;

function validateSynthesis(v:unknown,answer:Readonly<Record<string,unknown>>,interview:boolean):Readonly<Record<string,unknown>>{
 if(!exact(v,['protocol','factual_groups','gap_codes','interpretation','coverage','semantic_entailment_verified','business_accepted'])||v.protocol!=='qualified-answer-synthesis-references-v1'||v.semantic_entailment_verified!==false||v.business_accepted!==false||canonicalJson(v.coverage)!==canonicalJson(answer.coverage)||!Array.isArray(v.factual_groups)||v.factual_groups.length>64||!Array.isArray(v.gap_codes))return fail();
 const records=answer.records as Record<string,unknown>[];const groups=new Map<string,Record<string,unknown>[]>();
 for(const r of records){const a=r.assertion as Record<string,unknown>;const key=canonicalJson([a.subject_id,a.predicate]);groups.set(key,[...(groups.get(key)??[]),r]);}
 if(v.factual_groups.length!==groups.size)return fail();
 const seen=new Set<string>();
 for(const g of v.factual_groups){
  if(!exact(g,['classification','assertion_ids'])||!Array.isArray(g.assertion_ids)||!g.assertion_ids.length||g.assertion_ids.length>64||!g.assertion_ids.every(canonicalUuid))return fail();
  const groupIds=g.assertion_ids;const first=records.find(r=>(r.assertion as Record<string,unknown>).assertion_id===groupIds[0]);if(!first)return fail();
  const a=first.assertion as Record<string,unknown>;const key=canonicalJson([a.subject_id,a.predicate]);const expected=groups.get(key);if(!expected||seen.has(key)||g.assertion_ids.length!==expected.length)return fail();seen.add(key);
  const expectedIds=new Set(expected.map(r=>(r.assertion as Record<string,unknown>).assertion_id));const ids=new Set<unknown>();
  for(const id of g.assertion_ids){if(ids.has(id)||!expectedIds.has(id))return fail();ids.add(id);}
  const classification=expected.some(r=>(r.evidence as EvidenceGroups).opposing.length)?'opposed':expected.some(r=>r.applicability==='unknown'||(r.evidence as EvidenceGroups).unknown.length||!(r.evidence as EvidenceGroups).supporting.length)?'unknown':'reported';
  if(g.classification!==classification)return fail();
 }
 const coverage=answer.coverage as Record<string,unknown>;const gaps=['unconfirmed_policy'];
 if(answer.state==='coverage_incomplete'||answer.continuation_page!==null||coverage.complete_within_declared_model!==true)gaps.push('coverage_incomplete');
 if(!records.length||records.some(r=>!(r.evidence as EvidenceGroups).supporting.length))gaps.push('missing_evidence');
 if(records.some(r=>(r.evidence as EvidenceGroups).opposing.length))gaps.push('opposing_accounts');
 if(records.some(r=>r.applicability==='unknown'||(r.evidence as EvidenceGroups).unknown.length))gaps.push('applicability_unknown');
 if(v.gap_codes.length!==gaps.length||new Set(v.gap_codes).size!==gaps.length||canonicalJson([...v.gap_codes].sort())!==canonicalJson(gaps.sort()))return fail();
 if(v.interpretation!==null&&(interview||!exact(v.interpretation,['classification','text'])||v.interpretation.classification!=='inference/unverified interpretation'||!plain(v.interpretation.text)))return fail();
 return Object.freeze(v);
}

export function validateQuestionEffectV1(value:unknown,scope:QuestionEffectScopeV1):Readonly<QuestionEffectPacketV1>{
 if(!canonicalUuid(scope.principal_id)||!canonicalUuid(scope.workspace_id)||!canonicalUuid(scope.thread_id)||!canonicalUuid(scope.event_id)||!integer(scope.revision)||!plain(scope.original_text,32768)||Buffer.byteLength(scope.original_text,'utf8')>32768||Buffer.from(scope.original_text,'utf8').toString('utf8')!==scope.original_text||!canonicalHash(scope.original_sha256)||sha256(Buffer.from(scope.original_text,'utf8'))!==scope.original_sha256||!['ordinary','interview'].includes(scope.mode))return fail();
 const v=value;if(!exact(v,keys)||v.schema_version!==1||v.protocol!=='question-effect-result-v1'||!['observed','clarification','unknown','unavailable'].includes(String(v.state))||v.principal_id!==scope.principal_id||v.workspace_id!==scope.workspace_id||v.thread_id!==scope.thread_id||v.thread_revision!==scope.revision||v.employee_event_id!==scope.event_id||v.original_sha256!==scope.original_sha256||v.channel!=='web'||v.automatic_retry_allowed!==false||v.semantic_entailment_verified!==false||v.business_accepted!==false)return fail();
 const query=sha256(canonicalJson({schema_version:1,protocol:'qualified-natural-question-v1',question:scope.original_text}));if(v.query_sha256!==query)return fail();
 const checked=instant(v.checked_at),end=instant(v.expires_at);if(end<=checked||end-checked>30000)return fail();
 if(v.state!=='observed'){
  if(observations.some(k=>v[k]!==null)||v.provider_dispatched!==(v.state==='unknown'?null:false))return fail();
  if(v.state==='clarification'){if(scope.mode==='interview'||!plain(v.clarification))return fail();}else if(v.clarification!==null)return fail();
  return Object.freeze(v) as unknown as Readonly<QuestionEffectPacketV1>;
 }
 if(v.provider_dispatched!==true||v.clarification!==null||!canonicalUuid(v.operation_id)||!canonicalUuid(v.model_id)||!integer(v.model_version)||!canonicalUuid(v.accepted_projection_event_id)||!['model_content_hash','accepted_receipt_body_sha256','native_receipt_sha256','wire_sha256','settled_response_sha256'].every(k=>canonicalHash(v[k]))||[...scope.original_text].length>4096||Buffer.byteLength(scope.original_text,'utf8')>16384)return fail();
 if(v.purpose!=='qualified-query-embedding-v1'&&v.purpose!=='qualified-answer-synthesis-v1')return fail();
 const synthesis=v.purpose==='qualified-answer-synthesis-v1';const a=validateQualifiedAnswerContentsV1(v.answer,{workspace_id:scope.workspace_id,checked_at:v.checked_at as string},synthesis?'synthesis':'vector');
 if(a.model_version!==v.model_version||a.model_content_hash!==v.model_content_hash||a.query_embedding_used!==!synthesis)return fail();
 for(const r of a.records as Record<string,unknown>[]){for(const quotes of Object.values(r.evidence as Record<string,unknown>)){if(!Array.isArray(quotes))continue;for(const q of quotes){if(!q||typeof q!=='object'||!('ref'in q)||!q.ref||typeof q.ref!=='object'||!('workspace_id'in q.ref)||q.ref.workspace_id!==scope.workspace_id)return fail();}}}
 if(synthesis)validateSynthesis(v.synthesis,a,scope.mode==='interview');else if(v.synthesis!==null)return fail();
 return Object.freeze(v) as unknown as Readonly<QuestionEffectPacketV1>;
}
