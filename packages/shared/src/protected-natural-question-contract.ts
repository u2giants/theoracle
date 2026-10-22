/** Closed natural question wire only. No identity, admission or permission owner. */
import {canonicalHash,canonicalJson,canonicalUuid,instant,parseClosedJson,sha256} from './protected-server-binding';
import {validateDocumentaryAnswerV1,parseConnectedAnswerResponse,type ConnectedAnswerPacket} from './protected-client-contracts';
import {parseIndustryAnswerV1,type IndustryAnswerPacketV1} from './protected-industry-contract';
export {validateIndustryQuestionV1,industryQuerySHA256V1,parseIndustryAnswerV1,type IndustryQuestionV1,type IndustryAnswerPacketV1} from './protected-industry-contract';
const refuse=():never=>{throw new Error('Current qualified evidence unavailable');};
const exact=(v:unknown,keys:readonly string[]):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
export type NaturalModeV1='local'|'connected'|'historical'|'global';
const mode=(v:unknown):v is NaturalModeV1=>typeof v==='string'&&['local','connected','historical','global'].includes(v);
export interface NaturalQuestionV1 {readonly schema_version:1;readonly protocol:'qualified-natural-question-v1';readonly caller_deadline:string;readonly question:string;}
export interface NaturalAnswerPacketV1 {
 readonly schema_version:1;readonly protocol:'qualified-natural-answer-v1';readonly principal_id:string;readonly workspace_id:string;readonly model_id:string;
 readonly channel:'web'|'mcp';readonly query_sha256:string;readonly request_sha256:string;readonly state:'answer'|'clarification';
 readonly resolved_mode:NaturalModeV1|null;readonly answer:Readonly<Record<string,unknown>>|null;readonly clarification:string|null;
 readonly checked_at:string;readonly expires_at:string;readonly current_read_lease_only:true;readonly retained_receipt_body_sha256:string;
 readonly retained_delivered_at:string;readonly retained_receipt_recorded_at:string;readonly retained_projection_lease_until:string;
}
function text(v:unknown,maxCharacters:number,maxBytes:number):v is string{
 return typeof v==='string'&&!!v.trim()&&!v.includes('\0')&&[...v].length<=maxCharacters&&Buffer.byteLength(v,'utf8')<=maxBytes
  &&![...v].some(c=>{const n=c.codePointAt(0)!;return n>=0xd800&&n<=0xdfff;});
}
export function validateNaturalQuestionV1(v:unknown):NaturalQuestionV1{
 if(!exact(v,['schema_version','protocol','caller_deadline','question'])||v.schema_version!==1||v.protocol!=='qualified-natural-question-v1'||!text(v.question,4096,16384)||typeof v.caller_deadline!=='string')return refuse();
 instant(v.caller_deadline);return Object.freeze(v) as unknown as NaturalQuestionV1;
}
export function naturalQuerySHA256V1(request:NaturalQuestionV1):string{
 validateNaturalQuestionV1(request);
 return sha256(Buffer.from(canonicalJson({schema_version:request.schema_version,protocol:request.protocol,question:request.question})));
}
export function parseNaturalAnswerResponseV1(bytes:Uint8Array):NaturalAnswerPacketV1{
 const v=parseClosedJson(bytes,262144);
 if(!exact(v,['schema_version','protocol','principal_id','workspace_id','model_id','channel','query_sha256','request_sha256','state','resolved_mode','answer','clarification','checked_at','expires_at','current_read_lease_only','retained_receipt_body_sha256','retained_delivered_at','retained_receipt_recorded_at','retained_projection_lease_until'])
  ||canonicalJson(v)!==Buffer.from(bytes).toString('utf8')||v.schema_version!==1||v.protocol!=='qualified-natural-answer-v1'
  ||!canonicalUuid(v.principal_id)||!canonicalUuid(v.workspace_id)||!canonicalUuid(v.model_id)||!(v.channel==='web'||v.channel==='mcp')
  ||!canonicalHash(v.query_sha256)||!canonicalHash(v.request_sha256)||!canonicalHash(v.retained_receipt_body_sha256)||v.current_read_lease_only!==true)return refuse();
 const checked=instant(v.checked_at),expires=instant(v.expires_at);
 if(checked>=expires||instant(v.retained_delivered_at)>checked||instant(v.retained_receipt_recorded_at)>checked||instant(v.retained_delivered_at)>=instant(v.retained_projection_lease_until))return refuse();
 if(v.state==='answer'){
  if(!mode(v.resolved_mode)||v.clarification!==null||v.answer===null)return refuse();
  const answer=validateDocumentaryAnswerV1(v.answer,{workspace_id:v.workspace_id as string,checked_at:v.checked_at as string});
  if(answer.mode!==v.resolved_mode||answer.state==='clarification')return refuse();
 }else if(v.state==='clarification'){
  if(v.answer!==null||v.resolved_mode!==null||!text(v.clarification,1000,4096))return refuse();
 }else return refuse();
 return Object.freeze(v) as unknown as NaturalAnswerPacketV1;
}
export function parseQualifiedAnswerResponseV1(bytes:Uint8Array):ConnectedAnswerPacket|NaturalAnswerPacketV1|IndustryAnswerPacketV1{
 const value=parseClosedJson(bytes,262144);
 if(value!==null&&typeof value==='object'&&!Array.isArray(value)&&'protocol'in value&&value.protocol==='qualified-industry-answer-v1')return parseIndustryAnswerV1(bytes);
 return value!==null&&typeof value==='object'&&!Array.isArray(value)&&'protocol' in value&&value.protocol==='qualified-natural-answer-v1'?parseNaturalAnswerResponseV1(bytes):parseConnectedAnswerResponse(bytes);
}
