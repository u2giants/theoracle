import test from 'node:test';
import assert from 'node:assert/strict';
import {validateRecallCaptureCreateBodyV1,interpretRecallCaptureResponseV1} from '@oracle/shared/recall-capture-contract';
import {canonicalJson} from '@oracle/shared/protected-server-binding';
const bot='01000000-0000-4000-8000-000000000001';
const body=()=>({meeting_url:'https://teams.microsoft.com/l/meetup-join/invented',bot_name:'Invented capture',recording_config:{transcript:{provider:{elevenlabs_streaming:{}},diarization:{use_separate_streams_when_available:true}},realtime_endpoints:[{type:'webhook',url:'https://ingress.example.test/recall',events:['transcript.data']}]}});
const bytes=(v:unknown)=>Buffer.from(canonicalJson(v));
test('documented closed create admits exact transcript-only body, never dashboard subscriptions',()=>{
 assert.equal(validateRecallCaptureCreateBodyV1(bytes(body())).bot_name,'Invented capture');
 for(const event of ['bot.done','transcript.done','transcript.failed','transcript.partial_data']){const b=body();b.recording_config.realtime_endpoints[0]!.events=[event];assert.throws(()=>validateRecallCaptureCreateBodyV1(bytes(b)));}
});
test('unknown, chat, duplicate, malformed nested provider and boolean bodies refuse',()=>{
 for(const change of [{chat:{message:'hello'}},{metadata:{x:1}},{recording_config:{...body().recording_config,transcript:{provider:{unknown:{}}}}},{recording_config:{...body().recording_config,transcript:{provider:{elevenlabs_streaming:{}},diarization:{use_separate_streams_when_available:1}}}}])assert.throws(()=>validateRecallCaptureCreateBodyV1(bytes({...body(),...change})));
 const raw=canonicalJson(body());assert.throws(()=>validateRecallCaptureCreateBodyV1(Buffer.from(raw.replace('"bot_name":','"bot_name":"duplicate","bot_name":'))));assert.throws(()=>validateRecallCaptureCreateBodyV1(Buffer.from(' '+raw)));
});
const response=(status:number,value:unknown)=>({status,headers:[['content-type','application/json']] as const,body:bytes(value),wire:Buffer.alloc(0),wireSha256:'a'.repeat(64)});
test('literal create201 records only observed bot, never stop/source qualification',()=>{
 const result=interpretRecallCaptureResponseV1('capture-create',response(201,{id:bot}),null);assert.equal(result.state,'create-observed');assert.equal(result.remote_stop_proven,false);assert.equal(result.source_qualified,false);assert.equal(interpretRecallCaptureResponseV1('capture-create',response(200,{id:bot}),null).state,'UNKNOWN');assert.equal(interpretRecallCaptureResponseV1('capture-create',response(201,{id:bot}),bot).state,'UNKNOWN');
});
test('leave200 empty is observation only and every other status/body refuses',()=>{
 const empty={...response(200,{}),body:Buffer.alloc(0)};assert.equal(interpretRecallCaptureResponseV1('capture-leave',empty,bot).state,'leave-observed');assert.equal(interpretRecallCaptureResponseV1('capture-leave',response(200,{}),bot).state,'UNKNOWN');assert.equal(interpretRecallCaptureResponseV1('capture-leave',{...empty,status:204},bot).state,'UNKNOWN');
});
test('bounded recovery metadata requires exact bot and unambiguous last status, never a stop proof',()=>{
 const v={id:bot,status_changes:[{code:'done',created_at:'2026-10-21T20:00:00Z'}]};const r=interpretRecallCaptureResponseV1('capture-retrieve',response(200,v),bot);assert.equal(r.latest_status?.code,'done');assert.equal(r.remote_stop_proven,false);assert.equal(interpretRecallCaptureResponseV1('capture-retrieve',response(200,{...v,id:'02000000-0000-4000-8000-000000000001'}),bot).state,'UNKNOWN');assert.equal(interpretRecallCaptureResponseV1('capture-retrieve',response(200,{...v,status_changes:[...v.status_changes,{code:'failed',created_at:'2026-10-21T20:00:00Z'}]}),bot).state,'UNKNOWN');
});

test('future provider status metadata never becomes a terminal observation',()=>{
 const v={id:bot,status_changes:[{code:'done',created_at:new Date(Date.now()+60000).toISOString()}]};
 const result=interpretRecallCaptureResponseV1('capture-retrieve',response(200,v),bot);
 assert.equal(result.state,'UNKNOWN');assert.equal(result.latest_status,null);assert.equal(result.remote_stop_proven,false);
});
