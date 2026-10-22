/** Closed descriptive Recall capture subset, shared by existing semantic owners.
 * No URL fetch, admission, transport, employee identity or remote-stop issuer.
 * Official sources: https://docs.recall.ai/reference/bot_create and
 * https://docs.recall.ai/docs/bot-real-time-transcription . Dashboard lifecycle
 * webhooks are separate; realtime endpoints never subscribe to done/failed/bot.*.
 */
import {canonicalJson,parseClosedJson,canonicalUuid,instant} from './protected-server-binding';
import type {RecallWireObservationV1} from './protected-node-https';
const fail=():never=>{throw new Error('Installed Recall capture unavailable');};
const exact=(v:unknown,keys:readonly string[]):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const text=(v:unknown,max:number):v is string=>typeof v==='string'&&v.length>0&&[...v].length<=max&&v.trim()===v&&!/[\x00-\x1f\x7f]/.test(v);
function httpsLabel(value:unknown):boolean{
 if(!text(value,4096))return false;
 try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password&&!url.hash&&url.href===value;}catch{return false;}
}
/** Validates only the independently admitted exact-body subset; a URL is data,
 * never a destination selector or permission to join. Full SHA/scope stays in
 * the installed worker and actual durable owner, independent of this codec.
 */
export function validateRecallCaptureCreateBodyV1(bytes:Uint8Array):Readonly<Record<string,unknown>>{
 const v=parseClosedJson(bytes,65536);if(canonicalJson(v)!==Buffer.from(bytes).toString('utf8'))return fail();
 const keys=['meeting_url','bot_name','recording_config'];if(v&&typeof v==='object'&&Object.hasOwn(v,'metadata'))keys.push('metadata');
 if(!exact(v,keys)||!httpsLabel(v.meeting_url)||!text(v.bot_name,100)||!exact(v.recording_config,['transcript','realtime_endpoints']))return fail();
 const transcript=v.recording_config.transcript;if(!transcript||typeof transcript!=='object'||Array.isArray(transcript))return fail();
 const transcriptKeys=['provider'];if(Object.hasOwn(transcript,'diarization'))transcriptKeys.push('diarization');
 if(!exact(transcript,transcriptKeys)||!transcript.provider||typeof transcript.provider!=='object'||Array.isArray(transcript.provider))return fail();
 const provider=transcript.provider as Record<string,unknown>,names=Object.keys(provider);
 if(names.length!==1||!['elevenlabs_streaming','assembly_ai_v3_streaming'].includes(names[0]!)||!exact(provider[names[0]!],[]))return fail();
 if('diarization'in transcript&&(!exact(transcript.diarization,['use_separate_streams_when_available'])||typeof transcript.diarization.use_separate_streams_when_available!=='boolean'))return fail();
 const endpoints=v.recording_config.realtime_endpoints;
 if(!Array.isArray(endpoints)||endpoints.length!==1)return fail();
 const endpoint=endpoints[0];if(!exact(endpoint,['type','url','events'])||endpoint.type!=='webhook'||!httpsLabel(endpoint.url)||!Array.isArray(endpoint.events)||canonicalJson(endpoint.events)!=='["transcript.data"]')return fail();
 if('metadata'in v){const metadata=v.metadata;if(!metadata||typeof metadata!=='object'||Array.isArray(metadata)||Object.keys(metadata).length>32||Object.entries(metadata).some(([k,value])=>!text(k,64)||!text(value,256)))return fail();}
 return Object.freeze(v);
}
export interface RecallCaptureObservationV1 {
 readonly state:'create-observed'|'leave-observed'|'metadata-observed'|'UNKNOWN';readonly bot_id:string|null;
 readonly latest_status:Readonly<{code:string;created_at:string}>|null;
 readonly observation_only:true;readonly remote_stop_proven:false;readonly source_qualified:false;
}
/** Literal complete protocol observations only. The backend retains raw wire;
 * independently current mapping/capture/STOP admission remains decisive. No
 * lifecycle polling, media URL fetching, auto retries or stopped=true output.
 */
export function interpretRecallCaptureResponseV1(purpose:'capture-create'|'capture-leave'|'capture-retrieve',response:Readonly<RecallWireObservationV1>,expectedBot:string|null):Readonly<RecallCaptureObservationV1>{
 const result=(state:RecallCaptureObservationV1['state'],bot_id:string|null=null,latest_status:RecallCaptureObservationV1['latest_status']=null)=>Object.freeze({state,bot_id,latest_status,observation_only:true as const,remote_stop_proven:false as const,source_qualified:false as const});
 try{
  if(purpose==='capture-leave')return canonicalUuid(expectedBot)&&response.status===200&&response.body.length===0?result('leave-observed',expectedBot):result('UNKNOWN');
  if((purpose==='capture-create'&&response.status!==201)||(purpose==='capture-retrieve'&&(response.status!==200||!canonicalUuid(expectedBot))))return result('UNKNOWN');
  if(!response.headers.some(([name,value])=>name==='content-type'&&['application/json','application/json; charset=utf-8'].includes(value)))return result('UNKNOWN');
  const v=parseClosedJson(response.body,1048576);if(!v||typeof v!=='object'||Array.isArray(v)||!canonicalUuid((v as Record<string,unknown>).id))return result('UNKNOWN');
  const object=v as Record<string,unknown>;if(purpose==='capture-create')return expectedBot===null?result('create-observed',object.id as string):result('UNKNOWN');
  if(object.id!==expectedBot||!Array.isArray(object.status_changes)||object.status_changes.length>2048)return result('UNKNOWN');
  let latest:RecallCaptureObservationV1['latest_status']=null,last=-Infinity;
  for(const status of object.status_changes){if(!status||typeof status!=='object'||Array.isArray(status))return result('UNKNOWN');const s=status as Record<string,unknown>;if(!text(s.code,128)||typeof s.created_at!=='string')return result('UNKNOWN');const at=instant(s.created_at);if(at>last){last=at;latest=Object.freeze({code:s.code,created_at:s.created_at});}else if(at===last&&(latest?.code!==s.code||latest?.created_at!==s.created_at))return result('UNKNOWN');}
  return result('metadata-observed',expectedBot,latest);
 }catch{return result('UNKNOWN');}
}
