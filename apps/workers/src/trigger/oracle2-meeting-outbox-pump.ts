/** Fixed installed outbox owner; a wake carries no destination or authority. */
import {task} from '@trigger.dev/sdk/v3';
import {parseMeetingCaptureWakeV1} from '../lib/meeting-capture';
import {runInstalledMeetingQueueV1} from '../lib/meeting-queue';
export const oracle2MeetingOutboxPumpV1=task({
 id:'oracle2-meeting-outbox-pump-v1',maxDuration:30,retry:{maxAttempts:1},
 run:async(raw:unknown)=>{
  parseMeetingCaptureWakeV1(raw);
  return runInstalledMeetingQueueV1();
 },
});
