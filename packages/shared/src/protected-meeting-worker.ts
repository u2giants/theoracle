/** Fixed installed service worker. Never employee auth, profile issuance or retry.
 * The sole backend operational owner creates/claims/records actual effects.
 */
import {performance} from 'node:perf_hooks';
import {readInstalledMeetingWorkerBinding,canonicalJson,instant,parseClosedJson,canonicalUuid,type MeetingWorkerBinding,type MeetingWorkerPurposeV1,type InstalledBinding} from './protected-server-binding';
import {protectedRead,sha256,type PinnedFile} from './_protected-file';
import {remaining,canonicalInstantV1,type Window} from './protected-control-window';
import {openProtectedChannelV1,current} from './protected-service-channel';
import {parseMeetingWorkerPacketV1,matchMeetingWorkerPacketV1,type MeetingWorkerPacketV1} from './protected-worker-contract';
import {installedRecallHTTPSV1,type RecallWireObservationV1,type RecallWireOperationV1} from './protected-node-https';
import {beginWorkerReceiptV1,currentWorkerReceiptV1} from './_worker-receipt';
if(typeof window!=='undefined')throw new Error('Meeting worker unavailable');
const fail=():never=>{throw new Error('Meeting worker unavailable');};
export type WorkerUncertaintyV1='transport_uncertain'|'invalid_response'|'expired'|'cancelled'|'local_failure';
class InstalledMeetingWorkerV1 {
 private readonly installed:InstalledBinding<MeetingWorkerBinding>;private readonly window:Window;
 private readonly provider:ReturnType<typeof installedRecallHTTPSV1>;private readonly providerFiles:readonly PinnedFile[];
 private prepared:Readonly<MeetingWorkerPacketV1>|undefined;private claimed:Readonly<MeetingWorkerPacketV1>|undefined;
 private prepareUsed=false;private claimUsed=false;private exchangeUsed=false;private observeUsed=false;private receipt:PinnedFile|undefined;
 readonly effect_purpose:MeetingWorkerPurposeV1;readonly original_deadline_v1:string;
 constructor(){
  // One original wall/monotonic window exists before any profile/key/body read.
  const wall=Date.now(),mono=performance.now(),originalMono=process.hrtime.bigint();
  this.window={wall,mono,end:wall+30000,signal:AbortSignal.timeout(30000),proxyMonoEnd:originalMono+30000000000n};
  const installed=readInstalledMeetingWorkerBinding(),p=installed.profile;this.installed=installed;this.effect_purpose=p.effect_purpose;
  this.window.end=Math.min(this.window.end,instant(p.expires_at),instant(p.original_horizon),instant(['capture-create','participation-send'].includes(p.effect_purpose)?p.capture_until:p.stop_until));remaining(this.window);
  this.original_deadline_v1=canonicalInstantV1(Math.floor(this.window.end));
  this.window.end=instant(this.original_deadline_v1);
  this.providerFiles=[protectedRead(p.provider_ca_file,p.provider_ca_sha256),protectedRead(p.provider_key_file,p.provider_key_sha256)];
  const authorization=new TextDecoder('utf-8',{fatal:true}).decode(this.providerFiles[1]!.bytes);
  this.provider=installedRecallHTTPSV1({hostname:p.provider_region+'.recall.ai',ca:this.providerFiles[0]!.bytes,serverDerSha256:p.provider_server_der_sha256,authorization});
  this.check();
 }
 private check():void{
  current(this.installed,this.window);const p=this.installed.profile;
  for(const file of this.providerFiles){const actual=protectedRead(file.path,file.digest);if(actual.identity!==file.identity)return fail();}
  if(this.receipt)currentWorkerReceiptV1(p,this.receipt);remaining(this.window);
 }
 private exactClaim(claim:Readonly<MeetingWorkerPacketV1>):void{
  if(!this.claimed||claim!==this.claimed||claim.state!=='claimed'||!claim.executable)return fail();this.check();
 }
 private async control(operation:'prepare'|'claim'|'current'|'observe'|'status',claim?:Readonly<MeetingWorkerPacketV1>,wire?:Uint8Array,error:WorkerUncertaintyV1|null=null):Promise<Readonly<MeetingWorkerPacketV1>>{
  this.check();
  if(wire!==undefined&&(!(wire instanceof Uint8Array)||wire.length>1064960))return fail();
  if(error!==null&&!['transport_uncertain','invalid_response','expired','cancelled','local_failure'].includes(error))return fail();
  const q={schema_version:1,operation,operation_id:claim?.operation_id??this.prepared?.operation_id??null,claim_event_id:claim?.claim_event_id??null,wire_base64:operation==='observe'?Buffer.from(wire??[]).toString('base64'):null,error:operation==='observe'?error:null,caller_deadline:this.original_deadline_v1};
  const channel=await openProtectedChannelV1(this.installed,this.window);
  let packet:Readonly<MeetingWorkerPacketV1>;
  try{
   this.check();const response=await channel.send(Buffer.from(canonicalJson(q)));
   packet=parseMeetingWorkerPacketV1(Buffer.from(canonicalJson(response)));matchMeetingWorkerPacketV1(packet,this.installed.profile);
   const lease=instant(packet.valid_until);if(lease<=Date.now()||lease>this.window.end)return fail();this.window.end=Math.min(this.window.end,lease);
   if(claim&&(packet.operation_id!==claim.operation_id||packet.claim_event_id!==claim.claim_event_id||packet.request_sha256!==claim.request_sha256||packet.bot_id!==claim.bot_id))return fail();
  }finally{channel.close();}
  this.check();return packet!;
 }
 async prepare_v1():Promise<Readonly<MeetingWorkerPacketV1>>{
  if(this.prepareUsed)return fail();this.prepareUsed=true;
  const packet=await this.control('prepare');if(packet.executable||packet.body_base64!==null)return fail();this.prepared=packet;return packet;
 }
 async claim_v1():Promise<Readonly<MeetingWorkerPacketV1>>{
  if(this.claimUsed||!this.prepared||this.prepared.state!=='prepared'||!canonicalUuid(this.prepared.operation_id))return fail();this.claimUsed=true;
  const packet=await this.control('claim');if(packet.operation_id!==this.prepared.operation_id)return fail();
  if(packet.state==='claimed')this.claimed=packet;return packet;
 }
 async current_v1(claim:Readonly<MeetingWorkerPacketV1>):Promise<Readonly<MeetingWorkerPacketV1>>{
  this.exactClaim(claim);const packet=await this.control('current',claim);
  if(packet.executable||packet.body_base64!==null||packet.state!=='inflight')return fail();return packet;
 }
 async exchange_provider_v1(claim:Readonly<MeetingWorkerPacketV1>):Promise<Readonly<RecallWireObservationV1>>{
  this.exactClaim(claim);if(this.exchangeUsed)return fail();this.exchangeUsed=true;
  const p=this.installed.profile;this.receipt=beginWorkerReceiptV1(p,claim);this.check();
  const body=Buffer.from(claim.body_base64!,'base64');if(sha256(body)!==claim.request_sha256)return fail();
  let operation:RecallWireOperationV1;
  if(p.effect_purpose==='capture-create')operation={kind:'create',body};
  else{
   if(!claim.bot_id)return fail();
   operation=p.effect_purpose==='capture-leave'?{kind:'leave',botId:claim.bot_id}:p.effect_purpose==='capture-retrieve'?{kind:'retrieve',botId:claim.bot_id}:{kind:'send-chat',botId:claim.bot_id,body};
  }
  return await this.provider.exchange(operation,{wallDeadline:this.window.end,monotonicDeadline:this.window.proxyMonoEnd,signal:this.window.signal,current:()=>this.check()},async()=>{await this.current_v1(claim);this.check();});
 }
 async observe_v1(claim:Readonly<MeetingWorkerPacketV1>,wire:Uint8Array,error:WorkerUncertaintyV1|null=null):Promise<Readonly<MeetingWorkerPacketV1>>{
  this.exactClaim(claim);if(this.observeUsed||!this.exchangeUsed)return fail();this.observeUsed=true;
  return await this.control('observe',claim,wire,error);
 }
 async status_v1():Promise<Readonly<MeetingWorkerPacketV1>>{
  const packet=await this.control('status',this.claimed);if(packet.executable||packet.body_base64!==null)return fail();return packet;
 }
}
/** One fixed server configuration, captured once; no caller selectors. */
export function installedMeetingWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1();}
