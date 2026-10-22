import {task} from '@trigger.dev/sdk/v3';
import {parseMeetingCaptureWakeV1,runInstalledMeetingCapturePreStopRetrieveV1} from '../lib/meeting-capture';
export const oracle2MeetingCapturePreStopRetrieveV1=task({id:'oracle2-meeting-capture-retrieve-pre-stop-v1',maxDuration:30,retry:{maxAttempts:1},run:async(raw:unknown)=>{parseMeetingCaptureWakeV1(raw);return runInstalledMeetingCapturePreStopRetrieveV1();}});
