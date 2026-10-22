/** Opaque durable-ingress wake only; source processing remains backend-owned. */
import {task} from '@trigger.dev/sdk/v3';
import {parseMeetingNormalizationWakeV1} from '@oracle/shared/protected-worker-contract';
import {runInstalledMeetingNormalizationV1} from '../lib/meeting-normalization';
export const oracle2MeetingIngressNormalizeV1=task({
 id:'oracle2-meeting-ingress-normalize-v1',maxDuration:30,retry:{maxAttempts:1},
 run:async(raw:unknown)=>{
  const wake=parseMeetingNormalizationWakeV1(raw);
  return runInstalledMeetingNormalizationV1(wake);
 },
});
