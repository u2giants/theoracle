/** Fixed installed participation execution. No supplied text, identity or retry. */
import {installedMeetingParticipationWorkerV1} from '@oracle/shared/protected-meeting-worker';
import {RecallWireUncertaintyV1} from '@oracle/shared/protected-node-https';
import type {MeetingWorkerPacketV1} from '@oracle/shared/protected-worker-contract';
import {protectedParticipationChatBodyV1} from './recall';

/** Queue wake only. Meeting, account, actor, turn and text are not payload. */
export function parseMeetingParticipationWakeV1(value:unknown):Readonly<Record<string,never>>{
 if(!value||typeof value!=='object'||Array.isArray(value)
  ||![Object.prototype,null].includes(Object.getPrototypeOf(value))||Reflect.ownKeys(value).length!==0){
  throw new Error('Meeting participation wake unavailable');
 }
 return Object.freeze({});
}

export interface MeetingParticipationAttemptV1 {
 readonly outcome:'provider-response-observed'|'not-dispatched'|'UNKNOWN';
 readonly receipt:Readonly<MeetingWorkerPacketV1>|null;
 readonly qualification:false;readonly visible_message_proven:false;
 readonly remote_stop_proven:false;readonly resend_authorized:false;
}
function result(outcome:MeetingParticipationAttemptV1['outcome'],receipt:Readonly<MeetingWorkerPacketV1>|null):Readonly<MeetingParticipationAttemptV1>{
 return Object.freeze({outcome,receipt,qualification:false,visible_message_proven:false,remote_stop_proven:false,resend_authorized:false});
}

/** One fixed installed service profile and one original deadline, captured by
 * the shared owner. Uncertainty resolves as data so task retries cannot resend.
 * This function never installs or schedules itself and never calls legacy send.
 */
export async function runInstalledMeetingParticipationV1():Promise<Readonly<MeetingParticipationAttemptV1>>{
 try{
  const worker=installedMeetingParticipationWorkerV1();
  if(worker.effect_purpose!=='participation-send')return result('not-dispatched',null);
  const prepared=await worker.prepare_v1();
  if(prepared.state!=='prepared')return result(prepared.state==='UNKNOWN'||prepared.state==='inflight'?'UNKNOWN':'not-dispatched',prepared);
  const claim=await worker.claim_v1();
  if(claim.state!=='claimed'||!claim.executable||claim.body_base64===null||claim.request_sha256===null){
   return result(claim.state==='UNKNOWN'||claim.state==='inflight'?'UNKNOWN':'not-dispatched',claim);
  }
  // Integrity is checked against actual immutable SQL commitment. This does
  // not replace the shared owner's fresh currentness after provider TLS.
  protectedParticipationChatBodyV1(Buffer.from(claim.body_base64,'base64'),claim.request_sha256);
  let wire:Uint8Array;let error:'transport_uncertain'|null=null;
  try{wire=(await worker.exchange_provider_v1(claim)).wire;}
  catch(cause){
   wire=cause instanceof RecallWireUncertaintyV1?cause.wire:new Uint8Array();
   error='transport_uncertain';
  }
  // Exact already-inflight claim only. If the original window has ended,
  // refusal leaves its durable UNKNOWN and any observed private orphan intact.
  const receipt=await worker.observe_v1(claim,wire,error);
  return result(error===null&&receipt.state==='observed'?'provider-response-observed':'UNKNOWN',receipt);
 }catch{
  // Never reconstruct a worker, renew a window, repeat a claim or send again.
  // This is not rollback, delivery, receipt-ACK or remote-stop proof.
  return result('UNKNOWN',null);
 }
}
