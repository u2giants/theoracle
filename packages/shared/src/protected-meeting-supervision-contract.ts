/** Current installed queue metadata alone never proves process liveness/STOP. */
import {canonicalJson,canonicalUuid,canonicalHash,instant,parseClosedJson,type MeetingSupervisionBinding,type MeetingSupervisionPurposeV1} from './protected-server-binding';
const fail=():never=>{throw new Error('Meeting supervision unavailable');};
export interface MeetingSupervisionPacketV1 {
 readonly schema_version:1;readonly purpose:'meeting-supervision-current-queue-v1';
 readonly principal_id:string;readonly workspace_id:string;readonly meeting_id:string;readonly process_purpose:MeetingSupervisionPurposeV1;
 readonly scope_sha256:string;readonly runtime_sha256:string;readonly config_sha256:string;readonly queue_observation_sha256:string;
 readonly version:number;readonly capture_until:string;readonly stop_until:string;readonly due_at:string;readonly valid_until:string;
 readonly observation_only:true;readonly remote_stop_proven:false;
}
const keys=['schema_version','purpose','principal_id','workspace_id','meeting_id','process_purpose','scope_sha256','runtime_sha256','config_sha256','queue_observation_sha256','version','capture_until','stop_until','due_at','valid_until','observation_only','remote_stop_proven'];
export function parseMeetingSupervisionPacketV1(bytes:Uint8Array):Readonly<MeetingSupervisionPacketV1>{
 const raw=parseClosedJson(bytes,4096);
 if(!raw||typeof raw!=='object'||Array.isArray(raw)||Object.keys(raw).length!==keys.length||!keys.every(k=>Object.hasOwn(raw,k))||canonicalJson(raw)!==new TextDecoder('utf-8',{fatal:true}).decode(bytes))return fail();
 const v=raw as Record<string,unknown>;
 if(v.schema_version!==1||v.purpose!=='meeting-supervision-current-queue-v1'||typeof v.process_purpose!=='string'||!['meeting-scheduler-process-v1','meeting-stop-worker-process-v1'].includes(v.process_purpose)||v.observation_only!==true||v.remote_stop_proven!==false||typeof v.version!=='number'||!Number.isSafeInteger(v.version)||v.version<1||v.version>16384)return fail();
 for(const k of ['principal_id','workspace_id','meeting_id'])if(!canonicalUuid(v[k]))return fail();
 for(const k of ['scope_sha256','runtime_sha256','config_sha256','queue_observation_sha256'])if(!canonicalHash(v[k]))return fail();
 const capture=instant(v.capture_until),stop=instant(v.stop_until),due=instant(v.due_at),until=instant(v.valid_until);
 if(!(due<capture&&capture<=stop&&until<=(v.process_purpose==='meeting-scheduler-process-v1'?capture:stop)))return fail();
 return Object.freeze(v) as unknown as Readonly<MeetingSupervisionPacketV1>;
}
export function matchMeetingSupervisionPacketV1(packet:Readonly<MeetingSupervisionPacketV1>,profile:Readonly<MeetingSupervisionBinding>):void{
 if(packet.principal_id!==profile.principal_id||packet.workspace_id!==profile.workspace_id||packet.meeting_id!==profile.meeting_id||packet.process_purpose!==profile.process_purpose||packet.scope_sha256!==profile.scope_sha256||packet.runtime_sha256!==profile.process_runtime_sha256||packet.config_sha256!==profile.process_config_sha256||instant(packet.capture_until)!==instant(profile.capture_until)||instant(packet.stop_until)!==instant(profile.stop_until))return fail();
}
