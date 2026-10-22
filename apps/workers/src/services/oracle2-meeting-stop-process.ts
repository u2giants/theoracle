/** Separately installed Linux STOP service; never a Trigger task or issuer.
 * Actual independent observer verifies this process/loop and its current queue.
 * No environment/profile is created, installed, renewed or borrowed here.
 */
import * as net from 'node:net';
import {lstatSync,chmodSync,unlinkSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {performance} from 'node:perf_hooks';
import {canonicalJson,parseClosedJson,instant,readInstalledMeetingStopProcessConfigV1,currentInstalledMeetingStopProcessRuntimeV1,readInstalledMeetingStopSupervisionBinding} from '@oracle/shared/protected-server-binding';
import {installedLocalMeetingStopSupervisionV1,installedLocalMeetingStopSequenceV1,installedLocalMeetingStopCycleV1} from '@oracle/shared/protected-meeting-worker';
import {interpretRecallCaptureResponseV1} from '@oracle/shared/recall-capture-contract';
import {RecallWireUncertaintyV1} from '@oracle/shared/protected-node-https';
import type {MeetingWorkerPacketV1,MeetingSupervisionPacketV1} from '@oracle/shared/protected-worker-contract';
const fail=():never=>{throw new Error('Meeting STOP unavailable');};
if(process.platform!=='linux'||typeof window!=='undefined')fail();
type Sequence=ReturnType<typeof installedLocalMeetingStopSequenceV1>;
type Worker=Sequence['leave'];
class InstalledStopProcessV1{
 private readonly config=readInstalledMeetingStopProcessConfigV1();
 private stopped=false;private busy=false;private failed=true;private uncertain=false;private attempted=false;
 private lastSuccess=0;private nextPoll=0;private timer:ReturnType<typeof setTimeout>|undefined;
 private readonly sockets=new Set<net.Socket>();private readonly server:net.Server;
 private socketIdentity:string|undefined;private parentIdentity:string|undefined;private active:Promise<void>|undefined;
 constructor(){currentInstalledMeetingStopProcessRuntimeV1(this.config);this.server=net.createServer({allowHalfOpen:true},socket=>this.observe(socket));this.server.maxConnections=1;}
 private current():void{currentInstalledMeetingStopProcessRuntimeV1(this.config);if(this.stopped||Date.now()>=Math.min(instant(this.config.expires_at),instant(this.config.stop_until)))fail();}
 private matchQueue(packet:Readonly<MeetingSupervisionPacketV1>):void{
  const p=readInstalledMeetingStopSupervisionBinding().profile;
  if(packet.workspace_id!==this.config.workspace_id||packet.meeting_id!==this.config.meeting_id||packet.process_purpose!=='meeting-stop-worker-process-v1'||packet.scope_sha256!==p.scope_sha256||packet.runtime_sha256!==p.process_runtime_sha256||packet.config_sha256!==p.process_config_sha256||instant(packet.capture_until)!==instant(this.config.capture_until)||instant(packet.stop_until)!==instant(this.config.stop_until)||instant(packet.due_at)!==instant(this.config.capture_until)-this.config.stop_margin_seconds*1000)fail();
 }
 private async stage(worker:Worker,sequence:Sequence):Promise<Readonly<MeetingWorkerPacketV1>>{
  const effect=worker.effect_purpose;if(effect!=='capture-leave'&&effect!=='capture-retrieve')return fail();
  sequence.current_v1();this.current();const prepared=await worker.prepare_v1();
  if(prepared.state!=='prepared')return prepared;
  const claim=await worker.claim_v1();if(!claim.executable)return claim;
  let wire:Uint8Array,error:'transport_uncertain'|'invalid_response'|null;
  try{const response=await worker.exchange_provider_v1(claim);wire=response.wire;error=interpretRecallCaptureResponseV1(effect,response,claim.bot_id).state==='UNKNOWN'?'invalid_response':null;}
  catch(failure){wire=failure instanceof RecallWireUncertaintyV1?failure.wire:Buffer.alloc(0);error='transport_uncertain';}
  // Exact raw wire is handed to the SAME backend once before interpretation
  // may become an operational receipt. No observation/retry from this process.
  return await worker.observe_v1(claim,wire,error);
 }
 private async execute(sequence:Sequence):Promise<void>{
  // SAME original operation already includes the preceding current queue read.
  this.current();const pre=await this.stage(sequence.pre_stop,sequence);
  if(pre.state!=='observed')fail();
  let ready=false;
  for(let n=0;n<this.config.readonly_wait_count;n++){
   sequence.current_v1();this.current();
   let status:Readonly<MeetingWorkerPacketV1>|undefined;
   try{status=await sequence.leave.status_v1();}catch{sequence.current_v1();}
   if(status?.state==='UNKNOWN'||status?.state==='inflight'||status?.state==='observed')fail();if(status?.state==='prepared'){ready=true;break;}
   if(n+1<this.config.readonly_wait_count){if(this.config.readonly_wait_milliseconds>=sequence.current_v1())fail();await new Promise<void>(r=>setTimeout(r,this.config.readonly_wait_milliseconds));}
  }
  if(!ready)fail();const leave=await this.stage(sequence.leave,sequence);if(leave.state!=='observed')fail();
  if(this.config.post_stop_delay_milliseconds>=sequence.current_v1())fail();
  await new Promise<void>(r=>setTimeout(r,this.config.post_stop_delay_milliseconds));sequence.current_v1();this.current();
  const post=await this.stage(sequence.post_stop,sequence);if(post.state!=='observed')fail();
  // No remote-stop output. Only the existing actual backend interprets a
  // complete current terminal receipt; HTTP200 or this process is not proof.
 }
 private poll():void{
  if(this.stopped)return;this.busy=true;this.timer=undefined;this.nextPoll=performance.now()+this.config.scheduler_poll_seconds*1000;
  this.active=(async()=>{
   // No SQL/effect lies outside an actual freshly captured fixed client window.
   const cycle=installedLocalMeetingStopCycleV1();this.current();const packet=await cycle.current_queue_v1();this.matchQueue(packet);
   if(Date.now()>=instant(packet.due_at)&&!this.attempted){this.attempted=true;this.uncertain=true;await this.execute(cycle.sequence);this.uncertain=false;}
   this.current();this.lastSuccess=performance.now();this.failed=false;
  })().catch(()=>{this.failed=true;}).finally(()=>{
   this.busy=false;
   if(Date.now()>=Math.min(instant(this.config.expires_at),instant(this.config.stop_until))){void this.close();return;}
   if(!this.stopped)this.timer=setTimeout(()=>this.poll(),Math.max(0,this.nextPoll-performance.now()));
  });
 }
 private observe(socket:net.Socket):void{
  // Original start exists BEFORE profile/config/body reads. This ONE fixed
  // queue client preserves the original window through a delayed IPC body.
  const wall=Date.now(),mono=performance.now();let end=wall+30000,monoEnd=mono+30000;
  let client:ReturnType<typeof installedLocalMeetingStopSupervisionV1>;
  try{client=installedLocalMeetingStopSupervisionV1();this.current();end=Math.min(end,instant(client.original_deadline_v1),instant(this.config.expires_at));monoEnd=mono+(end-wall);}catch{socket.destroy();return;}
  this.sockets.add(socket);socket.on('close',()=>this.sockets.delete(socket));socket.on('error',()=>undefined);let bytes=Buffer.alloc(0),running=false;
  const remaining=()=>{const ms=Math.min(end-Date.now(),monoEnd-performance.now());if(ms<=0||this.stopped)fail();return Math.floor(ms);};
  const expire=()=>socket.destroy();let timer=setTimeout(expire,remaining());
  socket.on('close',()=>clearTimeout(timer));socket.on('data',(part:Buffer)=>{
   if(running){socket.destroy();return;}bytes=Buffer.concat([bytes,part]);if(bytes.length>4100){socket.destroy();return;}if(bytes.length<4)return;const count=bytes.readUInt32BE(0);if(count<1||count>4096||bytes.length>count+4){socket.destroy();return;}if(bytes.length<count+4)return;running=true;
   void(async()=>{
    remaining();const raw=bytes.subarray(4),v=parseClosedJson(raw,4096) as Record<string,unknown>;
    if(!v||typeof v!=='object'||Array.isArray(v)||canonicalJson(v)!==raw.toString('utf8')||Object.keys(v).sort().join(',')!=='caller_deadline,challenge,purpose,schema_version,scope_sha256'||v.schema_version!==2||v.purpose!=='meeting-process-currentness-v2'||typeof v.challenge!=='string'||!/^[a-f0-9]{64}$/.test(v.challenge)||typeof v.scope_sha256!=='string'||!/^[a-f0-9]{64}$/.test(v.scope_sha256))fail();
    const deadline=instant(v.caller_deadline);if(!(wall<deadline&&deadline<=Math.min(wall+30000,instant(this.config.expires_at))))fail();const chosenDeadline=deadline<=instant(client.original_deadline_v1)?v.caller_deadline as string:client.original_deadline_v1;end=Math.min(end,deadline);monoEnd=Math.min(monoEnd,mono+(deadline-wall));clearTimeout(timer);timer=setTimeout(expire,remaining());
    if(this.busy||this.failed||this.uncertain||!this.timer?.hasRef()||this.lastSuccess<=0||performance.now()-this.lastSuccess>(this.config.scheduler_poll_seconds+2)*1000||performance.now()>this.nextPoll+1000)fail();
    this.current();const packet=await client.current_queue_v1(chosenDeadline);this.matchQueue(packet);remaining();this.current();
    if(packet.scope_sha256!==v.scope_sha256||this.busy||this.failed||this.uncertain||!this.timer?.hasRef())fail();
    const now=Date.now(),until=Math.min(now+2000,end,instant(packet.valid_until),instant(this.config.stop_until));if(until<=now)fail();
    const value={schema_version:2,purpose:'meeting-process-currentness-v2',process_purpose:'meeting-stop-worker-process-v1',challenge:v.challenge,scope_sha256:packet.scope_sha256,runtime_sha256:packet.runtime_sha256,config_sha256:packet.config_sha256,queue_observation_sha256:packet.queue_observation_sha256,sequence:packet.version,checked_at:new Date(now).toISOString(),expires_at:new Date(until).toISOString()};
    const body=Buffer.from(canonicalJson(value)),prefix=Buffer.alloc(4);prefix.writeUInt32BE(body.length);remaining();socket.end(Buffer.concat([prefix,body]));
   })().catch(()=>socket.destroy());
  });
 }
 async run():Promise<void>{
  const path=this.config.socket_file,parent=dirname(path);if(resolve(path)!==path)fail();const p=lstatSync(parent);if(!p.isDirectory()||p.isSymbolicLink()||(p.mode&0o077)!==0||p.uid!==process.getuid!())fail();this.parentIdentity=[p.dev,p.ino,p.mode,p.uid].join(':');
  try{lstatSync(path);fail();}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
  await new Promise<void>((yes,no)=>{this.server.once('error',no);this.server.listen(path,()=>{this.server.removeListener('error',no);yes();});});chmodSync(path,0o600);const s=lstatSync(path),after=lstatSync(parent);if(this.parentIdentity!==[after.dev,after.ino,after.mode,after.uid].join(':')||!s.isSocket())fail();this.socketIdentity=[s.dev,s.ino].join(':');this.poll();
 }
 async close():Promise<void>{
  if(this.stopped)return;this.stopped=true;if(this.timer)clearTimeout(this.timer);for(const s of this.sockets)s.destroy();
  await new Promise<void>(r=>this.server.close(()=>r()));await this.active;
  const path=this.config.socket_file;
  // Node removes its own listened Unix path on close. Never unlink a foreign
  // replacement/stale path or create a directory as a recovery shortcut.
  try{const s=lstatSync(path);if(this.socketIdentity!==[s.dev,s.ino].join(':'))fail();unlinkSync(path);}catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;}
 }
}
const processOwner=new InstalledStopProcessV1();
process.once('SIGTERM',()=>{void processOwner.close().catch(()=>{process.exitCode=1;});});process.once('SIGINT',()=>{void processOwner.close().catch(()=>{process.exitCode=1;});});
await processOwner.run();
