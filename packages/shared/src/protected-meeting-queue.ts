/** Fixed installed queue worker, one original fence, no legacy key/SDK/retry.
 * https://trigger.dev/docs/management/tasks/trigger
 * Response x-trigger-jwt can be a run capability: raw wire stays private custody.
 */
import {performance} from 'node:perf_hooks';
import {readInstalledMeetingQueueBinding,canonicalJson,instant,parseClosedJson,type InstalledBinding,type MeetingQueueBinding} from './protected-server-binding';
import {protectedRead,sha256,type PinnedFile} from './_protected-file';
import {remaining,canonicalInstantV1,type Window} from './protected-control-window';
import {current,openProtectedChannelV1} from './protected-service-channel';
import {parseMeetingQueuePacketV1,matchMeetingQueuePacketV1,MAX_QUEUE_WIRE_V1,QUEUE_PIN_FIELDS_V1,type MeetingQueuePacketV1} from './protected-meeting-queue-contract';
import {installedTriggerQueueHTTPSV1,type RecallWireObservationV1} from './protected-node-https';
import {beginQueueReceiptV1,currentQueueReceiptV1} from './_worker-receipt';
if(typeof window!=='undefined')throw new Error('Meeting queue unavailable');
const fail=():never=>{throw new Error('Meeting queue unavailable');};
type QueueErrorV1='network'|'timeout'|'framing'|'expired'|'unknown';
class InstalledMeetingQueueWorkerV1 {
 private readonly installed:InstalledBinding<MeetingQueueBinding>;private readonly window:Window;private readonly originTick:bigint;
 private readonly provider:ReturnType<typeof installedTriggerQueueHTTPSV1>;private readonly files:readonly PinnedFile[];
 private pending:Readonly<MeetingQueuePacketV1>|undefined;private claimed:Readonly<MeetingQueuePacketV1>|undefined;
 private pendingUsed=false;private claimUsed=false;private exchangeUsed=false;private observeUsed=false;private receipt:PinnedFile|undefined;
 readonly original_deadline_v1:string;
 constructor(){
  const wall=Date.now(),mono=performance.now(),tick=process.hrtime.bigint();this.originTick=tick;
  this.window={wall,mono,end:wall+30000,signal:AbortSignal.timeout(30000),proxyMonoEnd:tick+30000000000n};
  this.installed=readInstalledMeetingQueueBinding();const p=this.installed.profile;
  this.window.end=Math.min(this.window.end,instant(p.expires_at),instant(p.original_horizon),instant(p.original_processing_horizon));remaining(this.window);
  this.original_deadline_v1=canonicalInstantV1(Math.floor(this.window.end));this.window.end=instant(this.original_deadline_v1);this.window.proxyMonoEnd=tick+BigInt(Math.max(0,this.window.end-wall))*1000000n;
  this.files=[protectedRead(p.queue_key_file,p.queue_credential_sha256),protectedRead(p.queue_ca_file,p.queue_ca_sha256),protectedRead(p.queue_installation_receipt_file,p.queue_installation_receipt_sha256),protectedRead(p.queue_target_descriptor_file,p.queue_target_descriptor_sha256)];
  this.checkInstallation();
  const key=new TextDecoder('utf-8',{fatal:true}).decode(this.files[0]!.bytes);
  if(!/^[\x21-\x7e]{1,4089}$/.test(key))fail();
  this.provider=installedTriggerQueueHTTPSV1({hostname:'api.trigger.dev',ca:this.files[1]!.bytes,serverDerSha256:p.queue_server_der_sha256,authorization:'Bearer '+key});
  this.check();
 }
 private checkInstallation():void{
  const p=this.installed.profile;
  const pins=Object.fromEntries(QUEUE_PIN_FIELDS_V1.filter(k=>k!=='queue_installation_receipt_sha256').map(k=>[k,p[k]]));
  // These exact independently installed files are prerequisites, never issued
  // from runtime observations, token prefixes or a self-described target.
  const target={schema_version:1,purpose:'meeting-queue-target-v1',origin:'https://api.trigger.dev',path:'/api/v1/tasks/oracle2-meeting-ingress-normalize-v1/trigger',queue_project_ref:p.queue_project_ref,queue_environment_id:p.queue_environment_id,queue_account_id:p.queue_account_id,queue_task_id:p.queue_task_id,issuer_actor:p.issuer_actor,reviewer_actor:p.reviewer_actor,valid_from:p.valid_from,expires_at:p.expires_at,original_horizon:p.original_processing_horizon};
  const receipt={schema_version:1,purpose:'meeting-queue-key-installation-v1',worker_id:p.worker_id,principal_id:p.principal_id,workspace_id:p.workspace_id,meeting_id:p.meeting_id,...pins,issuer_actor:p.issuer_actor,reviewer_actor:p.reviewer_actor,valid_from:p.valid_from,expires_at:p.expires_at,original_horizon:p.original_processing_horizon};
  // Avoid circular self-hash: the receipt does not contain its own digest.
  for(const [file,expected] of [[this.files[2]!,receipt],[this.files[3]!,target]] as const){
   if(canonicalJson(parseClosedJson(file.bytes,16384))!==canonicalJson(expected)||file.bytes.toString('utf8')!==canonicalJson(expected))return fail();
  }
 }
 private check():void{
  current(this.installed,this.window);remaining(this.window);
  for(const f of this.files){const now=protectedRead(f.path,f.digest);if(now.identity!==f.identity)return fail();}
  this.checkInstallation();if(this.receipt)currentQueueReceiptV1(this.installed.profile,this.receipt);
 }
 private exact(claim:Readonly<MeetingQueuePacketV1>):void{if(!this.claimed||claim!==this.claimed||!claim.fresh_claim||!claim.body||!claim.claim_id||!claim.ingress_event_id||!claim.request_sha256)return fail();this.check();}
 private async control(operation:'pending'|'claim'|'current'|'observe'|'status',claim?:Readonly<MeetingQueuePacketV1>,wire?:Uint8Array,error:QueueErrorV1|null=null):Promise<Readonly<MeetingQueuePacketV1>>{
  this.check();if(wire!==undefined&&(!(wire instanceof Uint8Array)||wire.length>MAX_QUEUE_WIRE_V1))return fail();
  const ingress=claim?.ingress_event_id??this.pending?.ingress_event_id??null;
  if(operation!=='pending'&&!ingress)return fail();
  const q={schema_version:1,operation,ingress_event_id:operation==='pending'?null:ingress,claim_id:['current','observe'].includes(operation)?claim?.claim_id??null:null,request_sha256:['current','observe'].includes(operation)?claim?.request_sha256??null:null,raw_wire_hex:operation==='observe'?Buffer.from(wire??[]).toString('hex'):null,error:operation==='observe'?error:null,caller_deadline:this.original_deadline_v1};
  const channel=await openProtectedChannelV1(this.installed,this.window);
  try{
   this.check();const response=await channel.send(Buffer.from(canonicalJson(q))),packet=parseMeetingQueuePacketV1(Buffer.from(canonicalJson(response)));matchMeetingQueuePacketV1(packet,this.installed.profile);
   if(operation!=='pending'&&packet.ingress_event_id!==ingress||claim&&(packet.claim_id!==claim.claim_id||packet.request_sha256!==claim.request_sha256))return fail();
   const end=instant(packet.valid_until);if(end<=Date.now()||end>this.window.end)return fail();this.window.end=Math.min(this.window.end,end);const clipped=this.originTick+BigInt(Math.max(0,Math.floor(this.window.end-this.window.wall)))*1000000n;this.window.proxyMonoEnd=this.window.proxyMonoEnd<clipped?this.window.proxyMonoEnd:clipped;
   if(packet.original_effect_deadline!==null&&instant(packet.original_effect_deadline)>instant(this.original_deadline_v1))return fail();
   this.check();return packet;
  }finally{channel.close();}
 }
 async pending_v1():Promise<Readonly<MeetingQueuePacketV1>>{if(this.pendingUsed)return fail();this.pendingUsed=true;const p=await this.control('pending');if(p.body!==null||p.fresh_claim)return fail();this.pending=p;return p;}
 async claim_v1():Promise<Readonly<MeetingQueuePacketV1>>{if(this.claimUsed||!this.pending?.ingress_event_id)return fail();this.claimUsed=true;const p=await this.control('claim');if(p.fresh_claim)this.claimed=p;return p;}
 async current_v1(claim:Readonly<MeetingQueuePacketV1>):Promise<Readonly<MeetingQueuePacketV1>>{this.exact(claim);const p=await this.control('current',claim);if(p.state!=='inflight'||p.body!==null||p.fresh_claim)return fail();return p;}
 async exchange_provider_v1(claim:Readonly<MeetingQueuePacketV1>):Promise<Readonly<RecallWireObservationV1>>{
  this.exact(claim);if(this.exchangeUsed)return fail();this.exchangeUsed=true;
  this.receipt=beginQueueReceiptV1(this.installed.profile,claim);this.check();
  return await this.provider.exchange({kind:'queue-enqueue',body:Buffer.from(canonicalJson(claim.body))},{wallDeadline:this.window.end,monotonicDeadline:this.window.proxyMonoEnd,signal:this.window.signal,current:()=>this.check()},async()=>{await this.current_v1(claim);this.check();});
 }
 async observe_v1(claim:Readonly<MeetingQueuePacketV1>,wire:Uint8Array,error:QueueErrorV1|null=null):Promise<Readonly<MeetingQueuePacketV1>>{this.exact(claim);if(!this.exchangeUsed||this.observeUsed)return fail();this.observeUsed=true;return await this.control('observe',claim,wire,error);}
 async status_v1():Promise<Readonly<MeetingQueuePacketV1>>{const p=await this.control('status',this.claimed);if(p.fresh_claim||p.body!==null)return fail();return p;}
}
/** The sole queue profile is selected by fixed protected server configuration. */
export function installedMeetingQueueWorkerV1():InstalledMeetingQueueWorkerV1{return new InstalledMeetingQueueWorkerV1();}
