import test from 'node:test';
import assert from 'node:assert/strict';
import {unclaimedMeetingStopReadyV1} from './meeting-stop-readiness';
import type {MeetingWorkerPacketV1} from '@oracle/shared/protected-worker-contract';
const identity='12345678-1234-4234-8234-123456789012';
const base={effect_purpose:'capture-leave',state:'idle',operation_id:identity,bot_id:identity,request_sha256:'a'.repeat(64),claim_event_id:null,executable:false,body_base64:null} as MeetingWorkerPacketV1;
test('unclaimed idle status is only ready for the existing prepare step',()=>{
 assert.equal(unclaimedMeetingStopReadyV1(base),true);
 assert.equal(unclaimedMeetingStopReadyV1({...base,state:'prepared'}),true);
});
test('missing descriptors and claimed/uncertain observations cannot become STOP readiness',()=>{
 for(const change of [{operation_id:null},{bot_id:null},{request_sha256:null},{claim_event_id:identity},{executable:true},{body_base64:''},{effect_purpose:'capture-create'},...(['UNKNOWN','claimed','inflight','observed','terminal_observed','DENIED'] as const).map(state=>({state}))]){
  assert.equal(unclaimedMeetingStopReadyV1({...base,...change} as MeetingWorkerPacketV1),false);
 }
});
