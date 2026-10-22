/** Read-only source-fixed local-loop channel. No liveness/effect/employee grant. */
import {performance} from 'node:perf_hooks';
import {readInstalledMeetingSchedulerSupervisionBinding,readInstalledMeetingStopSupervisionBinding,canonicalJson,instant,type InstalledBinding,type MeetingSupervisionBinding} from './protected-server-binding';
import {remaining,canonicalInstantV1,_captureLocalStopOperationV1,_currentLocalStopOperationV1,_narrowLocalStopOperationV1,type Window} from './protected-control-window';
import {current,openProtectedChannelV1} from './protected-service-channel';
import {parseMeetingSupervisionPacketV1,matchMeetingSupervisionPacketV1,type MeetingSupervisionPacketV1} from './protected-meeting-supervision-contract';
if(typeof window!=='undefined')throw new Error('Meeting supervision unavailable');
const fail=():never=>{throw new Error('Meeting supervision unavailable');};
const queueOperationOwnersV1=new WeakMap<object,object>();
class InstalledMeetingSupervisionV1 {
 private readonly installed:InstalledBinding<MeetingSupervisionBinding>;private readonly window:Window;private sent=false;
 readonly original_deadline_v1:string;
 constructor(kind:'scheduler'|'stop',operation?:object){
  const wall=Date.now(),mono=performance.now(),tick=process.hrtime.bigint();
  if(operation){const v=_currentLocalStopOperationV1(operation);if(kind!=='stop')throw new Error('Meeting supervision unavailable');queueOperationOwnersV1.set(this,operation);this.window=v.window;}
  else this.window={wall,mono,end:wall+30000,signal:AbortSignal.timeout(30000),proxyMonoEnd:tick+30000000000n};
  this.installed=kind==='scheduler'?readInstalledMeetingSchedulerSupervisionBinding():readInstalledMeetingStopSupervisionBinding();const p=this.installed.profile;
  this.window.end=Math.min(this.window.end,instant(p.expires_at),instant(p.original_horizon),instant(p.process_purpose==='meeting-scheduler-process-v1'?p.capture_until:p.stop_until));remaining(this.window);
  this.original_deadline_v1=canonicalInstantV1(Math.floor(this.window.end));this.window.end=instant(this.original_deadline_v1);current(this.installed,this.window);
 }
 async current_queue_v1(caller_deadline:string=this.original_deadline_v1):Promise<Readonly<MeetingSupervisionPacketV1>>{
  if(this.sent)return fail();this.sent=true;
  // Forward original supplied deadline unchanged as narrowing only. Construct
  // this fixed client before IPC body reading, never after a delayed request.
  const operation=queueOperationOwnersV1.get(this);if(operation)_currentLocalStopOperationV1(operation);
  const end=instant(caller_deadline);if(end<=Date.now()||end>this.window.end)return fail();this.window.end=Math.min(this.window.end,end);if(operation)_narrowLocalStopOperationV1(operation,this.window.end);current(this.installed,this.window);
  const channel=await openProtectedChannelV1(this.installed,this.window);
  try{
   current(this.installed,this.window);const response=await channel.send(Buffer.from(canonicalJson({schema_version:1,caller_deadline})));
   const packet=parseMeetingSupervisionPacketV1(Buffer.from(canonicalJson(response)));matchMeetingSupervisionPacketV1(packet,this.installed.profile);
   const until=instant(packet.valid_until);if(until<=Date.now()||until>this.window.end)return fail();this.window.end=Math.min(this.window.end,until);if(operation)_narrowLocalStopOperationV1(operation,this.window.end);current(this.installed,this.window);return packet;
  }finally{channel.close();}
 }
}
export function installedMeetingSchedulerSupervisionV1():InstalledMeetingSupervisionV1{return new InstalledMeetingSupervisionV1('scheduler');}
export function installedMeetingStopSupervisionV1():InstalledMeetingSupervisionV1{return new InstalledMeetingSupervisionV1('stop');}

/** Internal same-owner bridge accepts only genuine private original provenance. */
export function _meetingStopSupervisionForOperationV1(operation:object):InstalledMeetingSupervisionV1{_currentLocalStopOperationV1(operation);return new InstalledMeetingSupervisionV1('stop',operation);}
export function installedLocalMeetingStopSupervisionV1():InstalledMeetingSupervisionV1{return _meetingStopSupervisionForOperationV1(_captureLocalStopOperationV1());}
