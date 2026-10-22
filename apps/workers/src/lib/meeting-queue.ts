/** One fixed installed queue attempt. No automatic dispatch after uncertainty. */
import {installedMeetingQueueWorkerV1} from '@oracle/shared/protected-meeting-worker';
import {RecallWireUncertaintyV1} from '@oracle/shared/protected-node-https';
import type {MeetingQueuePacketV1} from '@oracle/shared/protected-worker-contract';
export interface MeetingQueueAttemptV1 {
 readonly outcome:'idle'|'enqueue-observed'|'UNKNOWN';readonly receipt:Readonly<MeetingQueuePacketV1>|null;
 readonly task_completed_proven:false;readonly remote_stop_proven:false;readonly observation_only:true;
}
export async function runInstalledMeetingQueueV1():Promise<Readonly<MeetingQueueAttemptV1>>{
 const result=(outcome:MeetingQueueAttemptV1['outcome'],receipt:Readonly<MeetingQueuePacketV1>|null):Readonly<MeetingQueueAttemptV1>=>Object.freeze({outcome,receipt,task_completed_proven:false,remote_stop_proven:false,observation_only:true});
 try{
  const worker=installedMeetingQueueWorkerV1(),pending=await worker.pending_v1();
  if(!pending.ingress_event_id)return result(pending.unresolved_count?'UNKNOWN':'idle',pending);
  const claim=await worker.claim_v1();if(!claim.fresh_claim||!claim.body)return result('UNKNOWN',claim);
  let wire:Uint8Array,error:'framing'|null=null;
  try{wire=(await worker.exchange_provider_v1(claim)).wire;}
  catch(cause){if(!(cause instanceof RecallWireUncertaintyV1))return result('UNKNOWN',null);wire=cause.wire;error='framing';}
  const receipt=await worker.observe_v1(claim,wire,error);
  return result(receipt.state==='observed'?'enqueue-observed':'UNKNOWN',receipt);
 }catch{return result('UNKNOWN',null);}
}
