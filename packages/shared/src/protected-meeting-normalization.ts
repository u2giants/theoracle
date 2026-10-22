/** One fixed installed processing service. No employee/provider key or retry. */
import {performance} from 'node:perf_hooks';
import {readInstalledMeetingNormalizationBinding,canonicalJson,canonicalUuid,instant,type InstalledBinding,type MeetingNormalizationBinding} from './protected-server-binding';
import {remaining,canonicalInstantV1,type Window} from './protected-control-window';
import {current,openProtectedChannelV1} from './protected-service-channel';
import {parseMeetingNormalizationPacketV1,matchMeetingNormalizationPacketV1,type MeetingNormalizationPacketV1} from './protected-meeting-normalization-contract';
if(typeof window!=='undefined')throw new Error('Meeting normalization unavailable');
const fail=():never=>{throw new Error('Meeting normalization unavailable');};
class InstalledMeetingNormalizationWorkerV1 {
 private readonly installed:InstalledBinding<MeetingNormalizationBinding>;private readonly window:Window;
 private used=false;readonly original_deadline_v1:string;
 constructor(){
  const wall=Date.now(),mono=performance.now(),originalMono=process.hrtime.bigint();
  this.window={wall,mono,end:wall+30000,signal:AbortSignal.timeout(30000),proxyMonoEnd:originalMono+30000000000n};
  this.installed=readInstalledMeetingNormalizationBinding();const p=this.installed.profile;
  this.window.end=Math.min(this.window.end,instant(p.expires_at),instant(p.original_horizon),instant(p.original_processing_horizon));
  remaining(this.window);this.original_deadline_v1=canonicalInstantV1(Math.floor(this.window.end));this.window.end=instant(this.original_deadline_v1);this.check();
 }
 private check():void{current(this.installed,this.window);remaining(this.window);}
 async normalize_v1(ingress_event_id:string):Promise<Readonly<MeetingNormalizationPacketV1>>{
  if(this.used||!canonicalUuid(ingress_event_id))return fail();this.used=true;this.check();
  const channel=await openProtectedChannelV1(this.installed,this.window);
  try{
   this.check();const response=await channel.send(Buffer.from(canonicalJson({schema_version:1,ingress_event_id,caller_deadline:this.original_deadline_v1})));
   const packet=parseMeetingNormalizationPacketV1(Buffer.from(canonicalJson(response)));
   matchMeetingNormalizationPacketV1(packet,this.installed.profile,ingress_event_id);
   const end=instant(packet.valid_until);if(end<=Date.now()||end>this.window.end)return fail();this.window.end=Math.min(this.window.end,end);this.check();return packet;
  }finally{channel.close();}
 }
}
export function installedMeetingNormalizationWorkerV1():InstalledMeetingNormalizationWorkerV1{return new InstalledMeetingNormalizationWorkerV1();}
