/** Source only: separately installed meeting target; never legacy runtime. */
import {task} from '@trigger.dev/sdk/v3';
import {parseMeetingParticipationWakeV1,runInstalledMeetingParticipationV1} from '../lib/meeting-participation';

export const oracle2MeetingParticipationV1=task({
 id:'oracle2-meeting-participation-v1',
 maxDuration:30,
 retry:{maxAttempts:1},
 run:async(raw:unknown)=>{
  parseMeetingParticipationWakeV1(raw);
  return runInstalledMeetingParticipationV1();
 },
});
