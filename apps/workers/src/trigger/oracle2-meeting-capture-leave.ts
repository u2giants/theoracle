import {task} from '@trigger.dev/sdk/v3';
import {parseMeetingCaptureWakeV1,runInstalledMeetingCaptureLeaveV1} from '../lib/meeting-capture';
// Isolated meetings configuration only. No schedule, activation or legacy fallback.
export const oracle2MeetingCaptureLeaveV1=task({
 id:'oracle2-meeting-capture-leave-v1',maxDuration:30,retry:{maxAttempts:1},
 run:async(raw:unknown)=>{parseMeetingCaptureWakeV1(raw);return runInstalledMeetingCaptureLeaveV1();},
});
