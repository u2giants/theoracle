import {task} from '@trigger.dev/sdk/v3';
import {parseMeetingCaptureWakeV1,runInstalledMeetingCaptureCreateV1} from '../lib/meeting-capture';
// Isolated meetings configuration only. No schedule, activation or legacy fallback.
export const oracle2MeetingCaptureCreateV1=task({
 id:'oracle2-meeting-capture-create-v1',maxDuration:30,retry:{maxAttempts:1},
 run:async(raw:unknown)=>{parseMeetingCaptureWakeV1(raw);return runInstalledMeetingCaptureCreateV1();},
});
