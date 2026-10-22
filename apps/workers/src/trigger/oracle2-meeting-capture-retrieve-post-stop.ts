import {task} from '@trigger.dev/sdk/v3';
import {parseMeetingCaptureWakeV1,runInstalledMeetingCapturePostStopRetrieveV1} from '../lib/meeting-capture';
export const oracle2MeetingCapturePostStopRetrieveV1=task({id:'oracle2-meeting-capture-retrieve-post-stop-v1',maxDuration:30,retry:{maxAttempts:1},run:async(raw:unknown)=>{parseMeetingCaptureWakeV1(raw);return runInstalledMeetingCapturePostStopRetrieveV1();}});
