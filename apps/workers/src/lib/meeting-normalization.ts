/** Fixed opaque-ingress consumer. Durable backend claim is decisive across jobs. */
import {installedMeetingNormalizationWorkerV1} from '@oracle/shared/protected-meeting-worker';
import {parseMeetingNormalizationWakeV1,type MeetingNormalizationPacketV1} from '@oracle/shared/protected-worker-contract';
export interface MeetingNormalizationAttemptV1 {
 readonly outcome:'response-observed'|'UNKNOWN';readonly receipt:Readonly<MeetingNormalizationPacketV1>|null;
 readonly qualification:false;readonly source_read_permission:false;readonly observation_only:true;
}
export async function runInstalledMeetingNormalizationV1(raw:unknown):Promise<Readonly<MeetingNormalizationAttemptV1>>{
 const wake=parseMeetingNormalizationWakeV1(raw);
 try{
  const worker=installedMeetingNormalizationWorkerV1();
  const receipt=await worker.normalize_v1(wake.ingress_event_id);
  return Object.freeze({outcome:'response-observed',receipt,qualification:false,source_read_permission:false,observation_only:true});
 }catch{
  // A failed handoff is never safe redispatch. Trigger retry is disabled; own
  // durable outbox/normalization status remains the explicit recovery owner.
  return Object.freeze({outcome:'UNKNOWN',receipt:null,qualification:false,source_read_permission:false,observation_only:true});
 }
}
