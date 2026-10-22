import {validateRecallCaptureCreateBodyV1} from './recall-capture-contract';
/** Fixed installed service worker. Never employee auth, profile issuance or retry.
 * The sole backend operational owner creates/claims/records actual effects.
 */
import {performance} from 'node:perf_hooks';
import {readInstalledMeetingWorkerBinding,readInstalledMeetingCaptureCreateWorkerBinding,readInstalledMeetingCaptureLeaveWorkerBinding,readInstalledMeetingCapturePreStopRetrieveWorkerBinding,readInstalledMeetingCapturePostStopRetrieveWorkerBinding,readInstalledMeetingParticipationWorkerBinding,rereadInstalledMeetingWorkerBinding,readInstalledMeetingStopProcessConfigV1,currentInstalledMeetingStopProcessConfigV1,type MeetingStopProcessConfigV1,canonicalJson,instant,parseClosedJson,canonicalUuid,type MeetingWorkerBinding,type MeetingWorkerPurposeV1,type InstalledBinding} from './protected-server-binding';
import {protectedRead,sha256,type PinnedFile} from './_protected-file';
import {remaining,canonicalInstantV1,_captureLocalStopOperationV1,_currentLocalStopOperationV1,_narrowLocalStopOperationV1,type Window} from './protected-control-window';
import {openProtectedChannelV1,current} from './protected-service-channel';
import {parseMeetingWorkerPacketV1,matchMeetingWorkerPacketV1,type MeetingWorkerPacketV1} from './protected-worker-contract';
import {installedRecallHTTPSV1,type RecallWireObservationV1,type RecallWireOperationV1} from './protected-node-https';
import {beginWorkerReceiptV1,currentWorkerReceiptV1} from './_worker-receipt';
if(typeof window!=='undefined')throw new Error('Meeting worker unavailable');
const fail=():never=>{throw new Error('Meeting worker unavailable');};
export type WorkerUncertaintyV1='transport_uncertain'|'invalid_response'|'expired'|'cancelled'|'local_failure';
import {_meetingStopSupervisionForOperationV1} from './protected-meeting-supervision';
type LocalSequenceV1=Readonly<{operation:object;wall:number;mono:number;tick:bigint;end:number;config:Readonly<MeetingStopProcessConfigV1>;profiles:readonly InstalledBinding<MeetingWorkerBinding>[]} >;
const localSequenceEnds=new WeakMap<LocalSequenceV1,number>();
const localSequenceOwners=new WeakMap<object,LocalSequenceV1>();
function sequenceCurrent(cap:LocalSequenceV1,window:Window):void{
 const end=localSequenceEnds.get(cap);if(end===undefined)return fail();const original=_currentLocalStopOperationV1(cap.operation);window.end=Math.min(window.end,end,original.window.end);window.proxyMonoEnd=window.proxyMonoEnd<original.window.proxyMonoEnd?window.proxyMonoEnd:original.window.proxyMonoEnd;currentInstalledMeetingStopProcessConfigV1(cap.config);
 for(const installed of cap.profiles)current(installed,window);remaining(window);
}
class InstalledMeetingWorkerV1 {
 private readonly installed:InstalledBinding<MeetingWorkerBinding>;private readonly window:Window;
 private readonly provider:ReturnType<typeof installedRecallHTTPSV1>;private readonly providerFiles:readonly PinnedFile[];
 private prepared:Readonly<MeetingWorkerPacketV1>|undefined;private claimed:Readonly<MeetingWorkerPacketV1>|undefined;
 private readonly localProcess:Readonly<MeetingStopProcessConfigV1>|undefined;
 private prepareUsed=false;private claimUsed=false;private exchangeUsed=false;private observeUsed=false;private receipt:PinnedFile|undefined;
 readonly effect_purpose:MeetingWorkerPurposeV1;readonly original_deadline_v1:string;
 constructor(kind:'legacy'|'create'|'leave'|'pre-stop-retrieve'|'post-stop-retrieve'|'participation'|'local-leave'|'local-pre-stop-retrieve'|'local-post-stop-retrieve'='legacy',sequence?:LocalSequenceV1){
  // One original wall/monotonic window exists before any profile/key/body read.
  const capturedWall=Date.now(),capturedMono=performance.now(),capturedTick=process.hrtime.bigint();
  if(sequence&&!localSequenceEnds.has(sequence))throw new Error('Meeting worker unavailable');
  if(sequence)localSequenceOwners.set(this,sequence);
  const wall=sequence?.wall??capturedWall,mono=sequence?.mono??capturedMono,originalMono=sequence?.tick??capturedTick;
  this.window={wall,mono,end:wall+30000,signal:AbortSignal.timeout(30000),proxyMonoEnd:originalMono+30000000000n};
  const local=kind==='local-leave'||kind==='local-pre-stop-retrieve'||kind==='local-post-stop-retrieve';
  if(sequence&&!local)throw new Error('Meeting worker unavailable');
  this.localProcess=sequence?.config??(local?readInstalledMeetingStopProcessConfigV1():undefined);
  if(this.localProcess){const c=this.localProcess;currentInstalledMeetingStopProcessConfigV1(c);this.window.end=Math.min(this.window.end,wall+c.stop_request_seconds*1000,instant(c.expires_at),instant(c.stop_until),instant(c.original_horizon));remaining(this.window);}
  const installed=sequence?rereadInstalledMeetingWorkerBinding(sequence.profiles[kind==='local-pre-stop-retrieve'?0:kind==='local-leave'?1:2]!):kind==='create'?readInstalledMeetingCaptureCreateWorkerBinding():(kind==='leave'||kind==='local-leave')?readInstalledMeetingCaptureLeaveWorkerBinding():(kind==='pre-stop-retrieve'||kind==='local-pre-stop-retrieve')?readInstalledMeetingCapturePreStopRetrieveWorkerBinding():(kind==='post-stop-retrieve'||kind==='local-post-stop-retrieve')?readInstalledMeetingCapturePostStopRetrieveWorkerBinding():kind==='participation'?readInstalledMeetingParticipationWorkerBinding():readInstalledMeetingWorkerBinding(),p=installed.profile;this.installed=installed;this.effect_purpose=p.effect_purpose;
  if(sequence)this.window.end=Math.min(this.window.end,localSequenceEnds.get(sequence)!);
  this.window.end=Math.min(this.window.end,instant(p.expires_at),instant(p.original_horizon),instant(['capture-create','participation-send'].includes(p.effect_purpose)?p.capture_until:p.stop_until));remaining(this.window);
  this.original_deadline_v1=canonicalInstantV1(Math.floor(this.window.end));
  this.window.end=instant(this.original_deadline_v1);
  if(this.localProcess)this.window.proxyMonoEnd=originalMono+BigInt(Math.max(0,Math.floor(this.window.end-wall)))*1000000n;
  if(this.localProcess){const c=this.localProcess;if(p.workspace_id!==c.workspace_id||p.meeting_id!==c.meeting_id||p.provider_account!==c.provider_account||instant(p.capture_until)!==instant(c.capture_until)||instant(p.stop_until)!==instant(c.stop_until)||instant(p.original_horizon)>instant(c.original_horizon))throw new Error('Meeting worker unavailable');currentInstalledMeetingStopProcessConfigV1(c);remaining(this.window);}
  this.providerFiles=[protectedRead(p.provider_ca_file,p.provider_ca_sha256),protectedRead(p.provider_key_file,p.provider_key_sha256)];
  const authorization=new TextDecoder('utf-8',{fatal:true}).decode(this.providerFiles[1]!.bytes);
  this.provider=installedRecallHTTPSV1({hostname:p.provider_region+'.recall.ai',ca:this.providerFiles[0]!.bytes,serverDerSha256:p.provider_server_der_sha256,authorization});
  this.check();
 }
 private check():void{
  const sequence=localSequenceOwners.get(this);if(sequence)sequenceCurrent(sequence,this.window);
  current(this.installed,this.window);if(this.localProcess)currentInstalledMeetingStopProcessConfigV1(this.localProcess);const p=this.installed.profile;
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
   const lease=instant(packet.valid_until);if(lease<=Date.now()||lease>this.window.end)return fail();this.window.end=Math.min(this.window.end,lease);const sequence=localSequenceOwners.get(this);if(sequence){localSequenceEnds.set(sequence,Math.min(localSequenceEnds.get(sequence)!,this.window.end));_narrowLocalStopOperationV1(sequence.operation,this.window.end);}
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
  if(p.effect_purpose==='capture-create'){validateRecallCaptureCreateBodyV1(body);operation={kind:'create',body};}
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

export function installedMeetingCaptureCreateWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('create');}
export function installedMeetingCaptureLeaveWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('leave');}
export function installedMeetingCapturePreStopRetrieveWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('pre-stop-retrieve');}
export function installedMeetingCapturePostStopRetrieveWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('post-stop-retrieve');}
export function installedMeetingParticipationWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('participation');}

export {installedMeetingNormalizationWorkerV1} from './protected-meeting-normalization';

export {installedMeetingSchedulerSupervisionV1,installedMeetingStopSupervisionV1,installedLocalMeetingStopSupervisionV1} from './protected-meeting-supervision';

/** Local persistent STOP owner: fixed configuration narrows BEFORE key reads. */
export function installedLocalMeetingCaptureLeaveWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('local-leave');}
export function installedLocalMeetingCapturePreStopRetrieveWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('local-pre-stop-retrieve');}
export function installedLocalMeetingCapturePostStopRetrieveWorkerV1():InstalledMeetingWorkerV1{return new InstalledMeetingWorkerV1('local-post-stop-retrieve');}

/** All three independently installed stages spend ONE original local window.
 * The only constructor of this private capability captures clocks before pins;
 * neither caller objects nor later configuration can manufacture/renew it.
 */
export function installedLocalMeetingStopSequenceV1(){return buildLocalMeetingStopSequenceV1(_captureLocalStopOperationV1());}
function buildLocalMeetingStopSequenceV1(operation:object){
 const original=_currentLocalStopOperationV1(operation),{wall,mono,tick,config}=original;
 const profiles=[readInstalledMeetingCapturePreStopRetrieveWorkerBinding(),readInstalledMeetingCaptureLeaveWorkerBinding(),readInstalledMeetingCapturePostStopRetrieveWorkerBinding()] as const;
 const end=Math.floor(Math.min(original.window.end,wall+config.stop_request_seconds*1000,instant(config.expires_at),instant(config.stop_until),instant(config.original_horizon),...profiles.flatMap(p=>[instant(p.profile.expires_at),instant(p.profile.original_horizon),instant(p.profile.stop_until)])));
  _narrowLocalStopOperationV1(operation,end);
 const cap:LocalSequenceV1=Object.freeze({operation,wall,mono,tick,end,config,profiles:Object.freeze(profiles)});localSequenceEnds.set(cap,end);
 const window:Window={wall,mono,end,signal:AbortSignal.timeout(30000),proxyMonoEnd:tick+BigInt(Math.max(0,end-wall))*1000000n};sequenceCurrent(cap,window);
 const pre_stop=new InstalledMeetingWorkerV1('local-pre-stop-retrieve',cap),leave=new InstalledMeetingWorkerV1('local-leave',cap),post_stop=new InstalledMeetingWorkerV1('local-post-stop-retrieve',cap);
 const original_deadline_v1=canonicalInstantV1(end);
 if([pre_stop,leave,post_stop].some(w=>w.original_deadline_v1!==original_deadline_v1))throw new Error('Meeting worker unavailable');
 return Object.freeze({pre_stop,leave,post_stop,original_deadline_v1,current_v1:()=>{sequenceCurrent(cap,window);return remaining(window);}});
}

/** Current due-queue and all stages spend the SAME original local operation. */
export function installedLocalMeetingStopCycleV1(){
 const operation=_captureLocalStopOperationV1(),sequence=buildLocalMeetingStopSequenceV1(operation),queue=_meetingStopSupervisionForOperationV1(operation);
 return Object.freeze({sequence,original_deadline_v1:sequence.original_deadline_v1,current_queue_v1:()=>queue.current_queue_v1(sequence.original_deadline_v1)});
}

export {installedMeetingQueueWorkerV1} from './protected-meeting-queue';
