import {type ConnectedAnswerPacket} from './protected-client-contracts';
import {parseQualifiedAnswerResponseV1,type NaturalAnswerPacketV1} from './protected-natural-question-contract';
/** Closed conversation wire only. Descriptive data never grants permission. */
import { canonicalJson, canonicalUuid, canonicalHash, parseClosedJson } from './protected-server-binding';
const fail=():never=>{throw new Error('Conversation unavailable');};
const exact=(v:unknown,keys:readonly string[]):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
export interface ConversationEvent {event_id:string;sequence:number;operation:string;origin:'employee'|'control'|'display';turn_id:string|null;original_text:string|null;original_language:string|null;original_sha256:string|null;corrects_event_id:string|null;question_id:string|null;need:string|null;response_kind:string|null;payload:Record<string,unknown>;created_at:string;}
export interface ConversationSnapshot {qualified_answer?:ConnectedAnswerPacket|NaturalAnswerPacketV1|null;schema_version:1;thread_id:string;workspace_id:string;principal_id:string;mode:'ordinary'|'interview';revision:number;topic:string;language:string;state:'active'|'paused'|'recap'|'stopped';question_count:number;pending_question_id:string|null;segment_started_at:string;segment_deadline:string;events:ConversationEvent[];recap:Record<string,unknown>;recap_sha256:string;reviewed_revision:number|null;reviewed_sha256:string|null;company_policy_confirmed:false;source_qualified:false;question:string|null;question_id:string|null;answer_first:string|null;offer_start_interview:boolean;qualification_state:'pending';original_registration_state:'not_registered'|'registered'|'UNKNOWN';account_acknowledgement_only:true;}
export interface ConversationIndex {schema_version:1;state:'index';principal_id:string;workspace_id:string;company_policy_confirmed:false;source_qualified:false;threads:{thread_id:string;topic:string;mode:'ordinary'|'interview';state:string;revision:number;language:string}[];}
export type ConversationPacket=ConversationSnapshot|ConversationIndex|{schema_version:1;state:'committed'|'UNKNOWN'|'DENIED'|'CONFLICT';resend_authorized:false;thread_id?:string;sequence?:number;command_sha256?:string};
export function validateConversationRequest(bytes:Uint8Array):Readonly<Record<string,unknown>>{
 const q=parseClosedJson(bytes,65536);if(!q||typeof q!=='object'||Array.isArray(q))return fail();const v=q as Record<string,unknown>;
 if(v.schema_version!==1||typeof v.caller_deadline!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?(?:Z|\+00:00)$/.test(v.caller_deadline)||canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return fail();
 const op=v.operation;if(op!==undefined&&typeof op!=='string')return fail();let keys=['schema_version','caller_deadline'];
 if(op===undefined){keys.push('command_id','mode','topic','language');if((typeof v.mode!=='string'||!['ordinary','interview'].includes(v.mode))||typeof v.topic!=='string'||!v.topic.trim()||[...v.topic].length>1000)return fail();}
 else if(op==='list'){keys.push('operation');}
 else if(op==='status'){keys.push('operation','command_id');}
 else if(op==='snapshot'){keys.push('operation','thread_id');}
 else{
  keys.push('operation','command_id','thread_id','expected_revision');
  if(typeof v.expected_revision!=='number'||!Number.isSafeInteger(v.expected_revision)||v.expected_revision<1)return fail();
  if(['employee_turn','correct','skip','unknown','referral'].includes(String(op))){keys.push('turn_id','text','language');if(!canonicalUuid(v.turn_id)||typeof v.text!=='string'||!v.text.trim()||v.text.includes('\0')||Buffer.byteLength(v.text)>32768)return fail();if(op==='correct'){keys.push('corrects_event_id','corrects_original_sha256');if(!canonicalUuid(v.corrects_event_id)||!canonicalHash(v.corrects_original_sha256))return fail();}}
  else if(op==='review_recap'){keys.push('recap_revision','recap_sha256');if(!Number.isSafeInteger(v.recap_revision)||!canonicalHash(v.recap_sha256))return fail();}
  else if(!['pause','resume','stop'].includes(String(op)))return fail();
 }
 if(!exact(v,keys)||('thread_id'in v&&!canonicalUuid(v.thread_id))||('command_id'in v&&!canonicalUuid(v.command_id)))return fail();
 if('language'in v&&(typeof v.language!=='string'||v.language.length>40||! /^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$/.test(v.language)))return fail();
 return Object.freeze(v);
}
export function parseConversationResponse(bytes:Uint8Array):ConversationPacket{
 const q=parseClosedJson(bytes,4194304);if(!q||typeof q!=='object'||Array.isArray(q)||canonicalJson(q)!==Buffer.from(bytes).toString('utf8'))return fail();const v=q as Record<string,unknown>;
 if(v.schema_version!==1)return fail();
 if(typeof v.state!=='string')return fail();
 if(['UNKNOWN','DENIED','CONFLICT'].includes(v.state)){if(!exact(v,['schema_version','state','resend_authorized'])||v.resend_authorized!==false)return fail();return v as unknown as ConversationPacket;}
 if(v.state==='committed'){if(!exact(v,['schema_version','state','thread_id','sequence','command_sha256','resend_authorized'])||!canonicalUuid(v.thread_id)||!Number.isSafeInteger(v.sequence)||!canonicalHash(v.command_sha256)||v.resend_authorized!==false)return fail();return v as unknown as ConversationPacket;}
 if(!canonicalUuid(v.workspace_id)||!canonicalUuid(v.principal_id)||v.company_policy_confirmed!==false||v.source_qualified!==false)return fail();
 if(v.state==='index'){
  if(!exact(v,['schema_version','state','principal_id','workspace_id','company_policy_confirmed','source_qualified','threads'])||!Array.isArray(v.threads)||v.threads.length>20)return fail();
  for(const t of v.threads)if(!exact(t,['thread_id','topic','mode','state','revision','language'])||!canonicalUuid(t.thread_id)||typeof t.topic!=='string'||!Number.isSafeInteger(t.revision))return fail();
  return v as unknown as ConversationIndex;
 }
 const fields=['schema_version','thread_id','workspace_id','principal_id','mode','revision','topic','language','state','question_count','pending_question_id','segment_started_at','segment_deadline','events','recap','recap_sha256','reviewed_revision','reviewed_sha256','company_policy_confirmed','source_qualified','question','question_id','answer_first','offer_start_interview','qualification_state','account_acknowledgement_only','original_registration_state'];
 if(Object.hasOwn(v,'qualified_answer')){fields.push('qualified_answer');if(v.qualified_answer!==null){const answer=parseQualifiedAnswerResponseV1(Buffer.from(canonicalJson(v.qualified_answer)));if(answer.protocol==='qualified-industry-answer-v1'||answer.protocol==='qualified-workspace-answer-v1'||answer.principal_id!==v.principal_id||answer.workspace_id!==v.workspace_id||answer.channel!=='web')return fail();}}
 if(!exact(v,fields)||!canonicalUuid(v.thread_id)||!Number.isSafeInteger(v.revision)||!Number.isSafeInteger(v.question_count)||(v.question_count as number)<0||(v.question_count as number)>8||!Array.isArray(v.events)||!canonicalHash(v.recap_sha256)||v.qualification_state!=='pending'||v.account_acknowledgement_only!==true||(typeof v.original_registration_state!=='string'||!['not_registered','registered','UNKNOWN'].includes(v.original_registration_state)))return fail();
 for(const e of v.events){if(!exact(e,['event_id','sequence','operation','origin','turn_id','original_text','original_language','original_sha256','corrects_event_id','question_id','need','response_kind','payload','created_at'])||!canonicalUuid(e.event_id)||!Number.isSafeInteger(e.sequence)||(typeof e.origin!=='string'||!['employee','control','display'].includes(e.origin)))return fail();if(e.origin==='employee'&&(typeof e.original_text!=='string'||!canonicalHash(e.original_sha256)||!canonicalUuid(e.turn_id)))return fail();}
 if((v.question!==null&&typeof v.question!=='string')||(v.answer_first!==null&&typeof v.answer_first!=='string')||typeof v.offer_start_interview!=='boolean')return fail();
 return v as unknown as ConversationSnapshot;
}
