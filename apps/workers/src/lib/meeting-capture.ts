import {installedMeetingCaptureCreateWorkerV1,installedMeetingCaptureLeaveWorkerV1,installedMeetingCapturePreStopRetrieveWorkerV1,installedMeetingCapturePostStopRetrieveWorkerV1} from '@oracle/shared/protected-meeting-worker';
import {RecallWireUncertaintyV1} from '@oracle/shared/protected-node-https';
import {interpretRecallCaptureResponseV1} from '@oracle/shared/recall-capture-contract';
import type {MeetingWorkerPacketV1} from '@oracle/shared/protected-worker-contract';
export function parseMeetingCaptureWakeV1(value:unknown):void{
 if(!value||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value))||Reflect.ownKeys(value).length!==0)throw new Error('Meeting capture unavailable');
}
type Purpose='capture-create'|'capture-leave'|'capture-retrieve';
function metadata(packet:Readonly<MeetingWorkerPacketV1>){return Object.freeze({state:packet.state,effect_purpose:packet.effect_purpose,operation_id:packet.operation_id,observation_only:true,remote_stop_proven:false,source_qualified:false});}
/** Same installed worker, one original deadline and no automatic redispatch.
 * A Trigger wake carries no body, URL, actor, account or operation selector.
 */
async function execute(kind:'create'|'leave'|'pre-stop'|'post-stop'){
 const purpose:Purpose=kind==='create'?'capture-create':kind==='leave'?'capture-leave':'capture-retrieve';
 let worker:ReturnType<typeof installedMeetingCaptureCreateWorkerV1>|undefined;
 let claim:Readonly<MeetingWorkerPacketV1>|undefined;
 try{
  worker=kind==='create'?installedMeetingCaptureCreateWorkerV1():kind==='leave'?installedMeetingCaptureLeaveWorkerV1():kind==='pre-stop'?installedMeetingCapturePreStopRetrieveWorkerV1():installedMeetingCapturePostStopRetrieveWorkerV1();
  if(worker.effect_purpose!==purpose)throw new Error('Meeting capture unavailable');
  const prepared=await worker.prepare_v1();if(prepared.state!=='prepared')return metadata(prepared);
  claim=await worker.claim_v1();if(!claim.executable)return metadata(claim);
  let wire:Uint8Array,error:'invalid_response'|'transport_uncertain'|null;
  try{
   const response=await worker.exchange_provider_v1(claim);
   const interpreted=interpretRecallCaptureResponseV1(purpose,response,claim.bot_id);
   wire=response.wire;error=interpreted.state==='UNKNOWN'?'invalid_response':null;
  }catch(failure){
   wire=failure instanceof RecallWireUncertaintyV1?failure.wire:Buffer.alloc(0);error='transport_uncertain';
  }
  // Exactly one observation attempt; a lost handoff is never re-submitted.
  return metadata(await worker.observe_v1(claim,wire,error));
 }catch{
  // No effect replay. Reconciliation is read-only and can itself be unavailable.
  try{if(worker)return metadata(await worker.status_v1());}catch{/* Retain UNKNOWN below. */}
  return Object.freeze({state:'UNKNOWN' as const,effect_purpose:purpose,operation_id:claim?.operation_id??null,observation_only:true,remote_stop_proven:false,source_qualified:false});
 }
}
export const runInstalledMeetingCaptureCreateV1=()=>execute('create');
export const runInstalledMeetingCaptureLeaveV1=()=>execute('leave');
export const runInstalledMeetingCapturePreStopRetrieveV1=()=>execute('pre-stop');
export const runInstalledMeetingCapturePostStopRetrieveV1=()=>execute('post-stop');
