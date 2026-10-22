/** Closed queue observations. A retained run ID is never task/source proof. */
import {canonicalJson,canonicalHash,canonicalUuid,instant,parseClosedJson,sha256,type MeetingQueueBinding} from './protected-server-binding';
const fail=():never=>{throw new Error('Meeting queue unavailable');};
export const QUEUE_TASK_V1='oracle2-meeting-ingress-normalize-v1' as const;
export const MAX_QUEUE_WIRE_V1=20480;
export const QUEUE_PIN_FIELDS_V1=['queue_project_ref','queue_environment_id','queue_account_id','queue_task_id','queue_credential_sha256','queue_installation_receipt_sha256','queue_target_descriptor_sha256'] as const;
export type QueueBodyV1=Readonly<{payload:Readonly<{ingress_event_id:string}>;options:Readonly<{idempotencyKey:string}>}>;
export interface MeetingQueuePacketV1 {
 readonly schema_version:1;readonly purpose:'meeting-ingress-queue-v1';readonly principal_id:string;readonly workspace_id:string;readonly meeting_id:string;
 readonly ingress_event_id:string|null;readonly claim_id:string|null;readonly request_sha256:string|null;
 readonly state:'idle'|'claimed'|'inflight'|'observed'|'UNKNOWN';readonly fresh_claim:boolean;readonly body:QueueBodyV1|null;
 readonly queue_pins:Readonly<Record<typeof QUEUE_PIN_FIELDS_V1[number],string>>;readonly original_effect_deadline:string|null;readonly valid_until:string;
 readonly run_id:string|null;readonly pending_count:number;readonly unresolved_count:number;readonly qualification:false;readonly task_completed_proven:false;
 readonly remote_stop_proven:false;readonly observation_only:true;
}
const keys=['schema_version','purpose','principal_id','workspace_id','meeting_id','ingress_event_id','claim_id','request_sha256','state','fresh_claim','body','queue_pins','original_effect_deadline','valid_until','run_id','pending_count','unresolved_count','qualification','task_completed_proven','remote_stop_proven','observation_only'];
function exact(v:unknown,k:readonly string[]):v is Record<string,unknown>{return !!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===k.length&&k.every(x=>Object.hasOwn(v,x));}
export function queueBodyV1(workspace:string,meeting:string,ingress:string):QueueBodyV1{
 if(![workspace,meeting,ingress].every(canonicalUuid))return fail();
 return Object.freeze({payload:Object.freeze({ingress_event_id:ingress}),options:Object.freeze({idempotencyKey:QUEUE_TASK_V1+':'+workspace+':'+meeting+':'+ingress})});
}
export function parseMeetingQueuePacketV1(bytes:Uint8Array):Readonly<MeetingQueuePacketV1>{
 const v=parseClosedJson(bytes,4096);if(!exact(v,keys)||canonicalJson(v)!==new TextDecoder('utf-8',{fatal:true}).decode(bytes))return fail();
 if(v.schema_version!==1||v.purpose!=='meeting-ingress-queue-v1'||typeof v.state!=='string'||!['idle','claimed','inflight','observed','UNKNOWN'].includes(v.state)||typeof v.fresh_claim!=='boolean'||v.qualification!==false||v.task_completed_proven!==false||v.remote_stop_proven!==false||v.observation_only!==true)return fail();
 for(const k of ['principal_id','workspace_id','meeting_id'])if(!canonicalUuid(v[k]))return fail();
 for(const k of ['ingress_event_id','claim_id'])if(v[k]!==null&&!canonicalUuid(v[k]))return fail();
 if(v.request_sha256!==null&&!canonicalHash(v.request_sha256))return fail();
 if(!exact(v.queue_pins,QUEUE_PIN_FIELDS_V1)||v.queue_pins.queue_task_id!==QUEUE_TASK_V1)return fail();
 for(const k of QUEUE_PIN_FIELDS_V1){const x=v.queue_pins[k];if(typeof x!=='string'||x.length<1||x.length>256||/[^\x21-\x7e]/.test(x)||k.endsWith('_sha256')&&!canonicalHash(x))return fail();}
 if(v.original_effect_deadline!==null)instant(v.original_effect_deadline);instant(v.valid_until);
 for(const k of ['pending_count','unresolved_count'])if(typeof v[k]!=='number'||!Number.isSafeInteger(v[k])||v[k]<0||v[k]>4096)return fail();
 if(v.run_id!==null&&(typeof v.run_id!=='string'||!/^[A-Za-z0-9_-]{1,256}$/.test(v.run_id)))return fail();
 if((v.state==='observed')!==(v.run_id!==null)||v.fresh_claim!==(v.state==='claimed')||v.fresh_claim!==(v.body!==null))return fail();
 if(v.claim_id!==null){if(v.ingress_event_id===null||v.request_sha256===null||v.original_effect_deadline===null)return fail();}
 else if(v.request_sha256!==null||v.original_effect_deadline!==null||!['idle','UNKNOWN'].includes(v.state))return fail();
 if(v.body!==null){
  if(!v.claim_id||typeof v.workspace_id!=='string'||typeof v.meeting_id!=='string'||typeof v.ingress_event_id!=='string'||canonicalJson(v.body)!==canonicalJson(queueBodyV1(v.workspace_id,v.meeting_id,v.ingress_event_id))||sha256(Buffer.from(canonicalJson(v.body)))!==v.request_sha256)return fail();
  Object.freeze((v.body as QueueBodyV1).payload);Object.freeze((v.body as QueueBodyV1).options);Object.freeze(v.body);
 }
 Object.freeze(v.queue_pins);return Object.freeze(v) as unknown as Readonly<MeetingQueuePacketV1>;
}
export function matchMeetingQueuePacketV1(p:Readonly<MeetingQueuePacketV1>,b:Readonly<MeetingQueueBinding>):void{
 if(p.principal_id!==b.principal_id||p.workspace_id!==b.workspace_id||p.meeting_id!==b.meeting_id||QUEUE_PIN_FIELDS_V1.some(k=>p.queue_pins[k]!==b[k]))return fail();
}
