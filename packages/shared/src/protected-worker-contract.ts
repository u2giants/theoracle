/** Closed internal worker observations. No admission or employee identity. */
import {canonicalJson,canonicalUuid,canonicalHash,instant,parseClosedJson,type MeetingWorkerBinding,type MeetingWorkerPurposeV1} from './protected-server-binding';
import {sha256} from './_protected-file';
const fail=():never=>{throw new Error('Meeting worker unavailable');};
export interface MeetingWorkerPacketV1 {
 readonly schema_version:1;readonly state:'prepared'|'claimed'|'inflight'|'observed'|'UNKNOWN'|'DENIED'|'idle'|'terminal_observed';
 readonly effect_purpose:MeetingWorkerPurposeV1;readonly principal_id:string;readonly worker_id:string;
 readonly workspace_id:string;readonly meeting_id:string;readonly provider_account:string;
 readonly operation_id:string|null;readonly claim_event_id:string|null;readonly request_sha256:string|null;readonly bot_id:string|null;
 readonly body_base64:string|null;readonly operation_policy_sha256:string;readonly composer_program_sha256:string|null;
 readonly valid_until:string;readonly executable:boolean;readonly qualification:false;readonly remote_stop_proven:false;
 readonly observation_only:true;readonly resend_authorized:false;
}
const fields=['schema_version','state','effect_purpose','principal_id','worker_id','workspace_id','meeting_id','provider_account','operation_id','claim_event_id','request_sha256','bot_id','body_base64','operation_policy_sha256','composer_program_sha256','valid_until','executable','qualification','remote_stop_proven','observation_only','resend_authorized'] as const;
export function parseMeetingWorkerPacketV1(bytes:Uint8Array):Readonly<MeetingWorkerPacketV1>{
 const raw=parseClosedJson(bytes,131072);
 if(!raw||typeof raw!=='object'||Array.isArray(raw)||Object.keys(raw).length!==fields.length||!fields.every(k=>Object.hasOwn(raw,k))||canonicalJson(raw)!==Buffer.from(bytes).toString('utf8'))return fail();
 const v=raw as Record<string,unknown>;
 if(v.schema_version!==1||typeof v.state!=='string'||!['prepared','claimed','inflight','observed','UNKNOWN','DENIED','idle','terminal_observed'].includes(v.state)||typeof v.effect_purpose!=='string'||!['capture-create','capture-leave','capture-retrieve','participation-send'].includes(v.effect_purpose))return fail();
 for(const k of ['principal_id','worker_id','workspace_id','meeting_id'])if(!canonicalUuid(v[k]))return fail();
 for(const k of ['operation_id','claim_event_id','bot_id'])if(v[k]!==null&&!canonicalUuid(v[k]))return fail();
 if(typeof v.provider_account!=='string'||!v.provider_account.length||v.provider_account.length>256||v.provider_account!==v.provider_account.trim()||/[\x00-\x1f\x7f]/.test(v.provider_account))return fail();
 if(!canonicalHash(v.operation_policy_sha256)||(v.request_sha256!==null&&!canonicalHash(v.request_sha256))||(v.composer_program_sha256!==null&&!canonicalHash(v.composer_program_sha256))||v.qualification!==false||v.remote_stop_proven!==false||v.observation_only!==true||v.resend_authorized!==false||typeof v.executable!=='boolean')return fail();
 instant(v.valid_until);
 if(v.state==='claimed'){
  if(v.executable!==true||!canonicalUuid(v.operation_id)||!canonicalUuid(v.claim_event_id)||!canonicalHash(v.request_sha256)||typeof v.body_base64!=='string'||v.body_base64.length>87384)return fail();
  const body=Buffer.from(v.body_base64,'base64');if(body.toString('base64')!==v.body_base64||sha256(body)!==v.request_sha256)return fail();
  if(v.effect_purpose==='capture-create'){if(!body.length||body.length>65536||v.bot_id!==null)return fail();}
  else if(!canonicalUuid(v.bot_id)||(['capture-leave','capture-retrieve'].includes(v.effect_purpose)?body.length!==0:body.length===0||body.length>32768))return fail();
 }else if(v.executable!==false||v.body_base64!==null)return fail();
 return Object.freeze(v) as unknown as Readonly<MeetingWorkerPacketV1>;
}
/** Exact installed scope only. Current SQL decisions remain decisive. */
export function matchMeetingWorkerPacketV1(packet:Readonly<MeetingWorkerPacketV1>,profile:Readonly<MeetingWorkerBinding>):void{
 for(const key of ['principal_id','worker_id','workspace_id','meeting_id','provider_account','effect_purpose','operation_policy_sha256','composer_program_sha256'] as const)if(packet[key]!==profile[key])return fail();
 if(profile.effect_purpose==='capture-create'&&packet.operation_id!==null&&(packet.operation_id!==profile.create_operation_id||packet.request_sha256!==profile.create_request_sha256))return fail();
}
