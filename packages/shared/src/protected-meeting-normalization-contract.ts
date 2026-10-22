/** Closed pending-source observations; never reading or qualification authority. */
import {canonicalJson,canonicalUuid,canonicalHash,instant,parseClosedJson,type MeetingNormalizationBinding} from './protected-server-binding';
const fail=():never=>{throw new Error('Meeting normalization unavailable');};
export type MeetingNormalizationStateV1='final_artifact_pending'|'intake_claimed'|'UNKNOWN'|'awaiting_independently_installed_exact_reading_review'|'source_unavailable';
export interface MeetingNormalizationPacketV1 {
 readonly schema_version:1;readonly principal_id:string;readonly workspace_id:string;readonly meeting_id:string;
 readonly ingress_event_id:string;readonly state:MeetingNormalizationStateV1;readonly valid_until:string;
 readonly source_binding:Readonly<{source_id:string;revision:number;original_sha256:string;byte_count:number}>|null;
 readonly qualification:false;readonly source_read_permission:false;readonly observation_only:true;
}
const keys=['schema_version','principal_id','workspace_id','meeting_id','ingress_event_id','state','valid_until','source_binding','qualification','source_read_permission','observation_only'];
export function parseMeetingNormalizationPacketV1(bytes:Uint8Array):Readonly<MeetingNormalizationPacketV1>{
 const raw=parseClosedJson(bytes,4096);
 if(!raw||typeof raw!=='object'||Array.isArray(raw)||Object.keys(raw).length!==keys.length||!keys.every(k=>Object.hasOwn(raw,k))||canonicalJson(raw)!==new TextDecoder('utf-8',{fatal:true}).decode(bytes))return fail();
 const v=raw as Record<string,unknown>;
 if(v.schema_version!==1||typeof v.state!=='string'||!['final_artifact_pending','intake_claimed','UNKNOWN','awaiting_independently_installed_exact_reading_review','source_unavailable'].includes(v.state)||v.qualification!==false||v.source_read_permission!==false||v.observation_only!==true)return fail();
 for(const key of ['principal_id','workspace_id','meeting_id','ingress_event_id'])if(!canonicalUuid(v[key]))return fail();
 instant(v.valid_until);
 if(v.source_binding!==null){
  const r=v.source_binding;
  if(!r||typeof r!=='object'||Array.isArray(r)||Object.keys(r).length!==4||!['source_id','revision','original_sha256','byte_count'].every(k=>Object.hasOwn(r,k)))return fail();
  const s=r as Record<string,unknown>;
  if(!canonicalUuid(s.source_id)||!canonicalHash(s.original_sha256)||typeof s.revision!=='number'||!Number.isSafeInteger(s.revision)||s.revision<1||typeof s.byte_count!=='number'||!Number.isSafeInteger(s.byte_count)||s.byte_count<1||s.byte_count>1048576)return fail();
  if(v.state!=='awaiting_independently_installed_exact_reading_review')return fail();
  Object.freeze(r);
 }else if(v.state==='awaiting_independently_installed_exact_reading_review')return fail();
 return Object.freeze(v) as unknown as Readonly<MeetingNormalizationPacketV1>;
}
export function matchMeetingNormalizationPacketV1(packet:Readonly<MeetingNormalizationPacketV1>,profile:Readonly<MeetingNormalizationBinding>,ingress:string):void{
 if(packet.principal_id!==profile.principal_id||packet.workspace_id!==profile.workspace_id||packet.meeting_id!==profile.meeting_id||packet.ingress_event_id!==ingress)return fail();
}
export function parseMeetingNormalizationWakeV1(value:unknown):Readonly<{ingress_event_id:string}>{
 if(!value||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value))||Object.getOwnPropertySymbols(value).length||Object.getOwnPropertyNames(value).length!==1||!Object.hasOwn(value,'ingress_event_id'))return fail();
 const descriptor=Object.getOwnPropertyDescriptor(value,'ingress_event_id');
 if(!descriptor||!Object.hasOwn(descriptor,'value')||!canonicalUuid(descriptor.value))return fail();
 return Object.freeze({ingress_event_id:descriptor.value});
}
