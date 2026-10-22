/** Actual owned loopback mTLS + provider TLS, invented backend state only.
 * Not actual SQL, installed service, provider account or employee proof. */
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {registerHooks,syncBuiltinESMExports} from 'node:module';
import nodeFs from 'node:fs';
import nodeDns from 'node:dns';import nodeTls from 'node:tls';
import {mkdtempSync,chmodSync,writeFileSync,readFileSync,lstatSync,existsSync,rmSync} from 'node:fs';
import {join} from 'node:path';import {tmpdir} from 'node:os';import {execFileSync,execFile,spawn} from 'node:child_process';
import {X509Certificate} from 'node:crypto';import * as tls from 'node:tls';
import {canonicalJson,sha256,validateMeetingWorkerBinding,type MeetingWorkerBinding,type MeetingSupervisionBinding} from '@oracle/shared/protected-server-binding';
import {parseMeetingWorkerPacketV1,type MeetingWorkerPacketV1} from '@oracle/shared/protected-worker-contract';
let installedMeetingWorkerV1:typeof import('@oracle/shared/protected-meeting-worker')['installedMeetingWorkerV1'];
const id='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222',hash='a'.repeat(64);
let dir:string,backend:tls.Server,provider:tls.Server,profile:MeetingWorkerBinding,backendCount=0,providerCount=0;
let localProfile:MeetingWorkerBinding|undefined,providerTLSCount=0;let localSelected:MeetingWorkerBinding|undefined;const localStages=new Map<string,MeetingWorkerBinding>();const localDeadlines:string[]=[];
let queueProfile:MeetingSupervisionBinding|undefined;let queueCount=0;
let mode='valid',observedWire:Buffer|undefined;const sockets=new Set<tls.TLSSocket>();
// Test-child-only tripwires. Even a broken constructor hook cannot resolve or
// connect to a production peer. The actual production guard is unchanged.
const realLookup=nodeDns.lookup,realConnect=nodeTls.connect;
Object.defineProperty(nodeDns,'lookup',{configurable:true,writable:true,value:(...args:unknown[])=>{
 if(!['localhost.localdomain','::1','127.0.0.1'].includes(String(args[0])))throw new Error('synthetic test refused external DNS');
 return Reflect.apply(realLookup,nodeDns,args);
}});
Object.defineProperty(nodeTls,'connect',{configurable:true,writable:true,value:(...args:unknown[])=>{
 const options=args[0];if(!options||typeof options!=='object'||!['localhost.localdomain','::1','127.0.0.1'].includes(String(Reflect.get(options,'host')))||Reflect.get(options,'servername')!=='localhost.localdomain')throw new Error('synthetic test refused external TLS');
 return Reflect.apply(realConnect,nodeTls,args);
}});syncBuiltinESMExports();
function assertInventedClient(worker:unknown):void{
 const records=(globalThis as unknown as Record<string,{client:unknown;port:number}[]>).__meetingConstructedFixtureClients;
 const record=records?.find(value=>value.client===Reflect.get(worker as object,'provider'));
 assert.ok(record);assert.equal(Reflect.get(worker as object,'provider'),record.client);
 assert.equal(Reflect.get(record.client as object,'fixture'),true);assert.equal(Reflect.get(record.client as object,'hostname'),'localhost.localdomain');
 assert.equal(Reflect.get(record.client as object,'port'),record.port);
}

const body=Buffer.from(canonicalJson({meeting_url:'https://teams.microsoft.com/l/meetup-join/invented',bot_name:'Oracle',recording_config:{transcript:{provider:{elevenlabs_streaming:{}}},realtime_endpoints:[{type:'webhook',url:'https://web.example.test/api/teams/live/recall',events:['transcript.data']}]}}));
const bodySHA=sha256(body),file=(name:string)=>join(dir,name),pin=(name:string)=>sha256(readFileSync(file(name)));
const primitiveURL=new URL('../../../packages/shared/src/protected-node-https.ts',import.meta.url).href.replace('/apps/packages/','/packages/');
// Explicit test-only loopback profile keeps production all-public DNS untouched.
const hooks=registerHooks({resolve(specifier,context,next){if(context.parentURL?.includes('protected-meeting-worker.ts')&&specifier==='./protected-node-https')return {url:'oracle-test:meeting-provider',shortCircuit:true};return next(specifier,context);},load(url,context,next){if(url==='oracle-test:meeting-provider')return {format:'module',shortCircuit:true,source:`import {inventedLoopbackRecallHTTPSV1} from ${JSON.stringify(primitiveURL)};export function installedRecallHTTPSV1(target){globalThis.__meetingFixtureProviderHookCalls=(globalThis.__meetingFixtureProviderHookCalls??0)+1;if(!Number.isSafeInteger(globalThis.__meetingProviderPort))throw new Error('fixture target absent');const client=inventedLoopbackRecallHTTPSV1({...target,hostname:'localhost.localdomain'},globalThis.__meetingProviderPort);globalThis.__meetingConstructedFixtureClient={client,port:globalThis.__meetingProviderPort};(globalThis.__meetingConstructedFixtureClients??=[]).push(globalThis.__meetingConstructedFixtureClient);return client}`};return next(url,context);}});
function packet(state:MeetingWorkerPacketV1['state'],deadline:string):MeetingWorkerPacketV1{if(mode.startsWith('local')){localDeadlines.push(deadline);return {schema_version:1,state,effect_purpose:(localSelected??localProfile)!.effect_purpose,principal_id:id,worker_id:(localSelected??localProfile)!.worker_id,workspace_id:id,meeting_id:id,provider_account:'invented-account',operation_id:(localSelected??localProfile)!.retrieve_operation_id??'55555555-5555-4555-8555-555555555555',claim_event_id:state==='prepared'?null:'44444444-4444-4444-8444-444444444444',request_sha256:sha256(Buffer.alloc(0)),bot_id:other,body_base64:state==='claimed'?'':null,operation_policy_sha256:hash,composer_program_sha256:null,valid_until:deadline,executable:state==='claimed',qualification:false,remote_stop_proven:false,observation_only:true,resend_authorized:false};}return {schema_version:1,state,effect_purpose:'capture-create',principal_id:id,worker_id:other,workspace_id:id,meeting_id:id,provider_account:'invented-account',operation_id:id,claim_event_id:state==='prepared'?null:other,request_sha256:bodySHA,bot_id:null,body_base64:state==='claimed'?body.toString('base64'):null,operation_policy_sha256:hash,composer_program_sha256:null,valid_until:deadline,executable:state==='claimed',qualification:false,remote_stop_proven:false,observation_only:true,resend_authorized:false};}
function serve(socket:tls.TLSSocket,callback:(q:Record<string,unknown>)=>void){sockets.add(socket);socket.on('close',()=>sockets.delete(socket));socket.on('error',()=>undefined);let raw=Buffer.alloc(0),done=false;socket.on('data',(part:Buffer)=>{raw=Buffer.concat([raw,part]);const split=raw.indexOf('\r\n\r\n');if(done||split<0)return;const size=Number(/content-length: (\d+)/i.exec(raw.subarray(0,split).toString())?.[1]);if(raw.length<split+4+size)return;done=true;callback({header:raw.subarray(0,split).toString(),body:raw.subarray(split+4)});});}
function reply(socket:tls.TLSSocket,status:number,bytes:Buffer){socket.end(Buffer.concat([Buffer.from(`HTTP/1.1 ${status} OK\r\nContent-Type: application/json\r\nContent-Length: ${bytes.length}\r\nConnection: close\r\n\r\n`),bytes]));}
before(async()=>{
 ({installedMeetingWorkerV1}=await import('@oracle/shared/protected-meeting-worker'));
 dir=mkdtempSync(join(tmpdir(),'oracle-worker-wire-'));chmodSync(dir,0o700);const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented Worker CA');
 for(const name of ['server','client']){openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented '+name);writeFileSync(file(name+'.ext'),name==='server'?'subjectAltName=DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\n':'subjectAltName=URI:spiffe://oracle/invented-worker\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');}
 for(const name of ['ca.crt','client.crt','client.key','server.crt','server.key'])chmodSync(file(name),0o600);
 provider=tls.createServer({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),allowHalfOpen:true},socket=>{providerTLSCount++;serve(socket,q=>{providerCount++;if(mode.startsWith('local')){assert.match(String(q.header),new RegExp('^GET /api/v1/bot/'+other+'/ HTTP/1.1'));assert.match(String(q.header),/Authorization: invented-provider-key/);assert.equal((q.body as Buffer).length,0);reply(socket,200,Buffer.from(canonicalJson({id:other,status_changes:[{code:'in_call_recording',created_at:new Date(Date.now()-1000).toISOString()}]})));return;}assert.match(String(q.header),/^POST \/api\/v1\/bot\/ HTTP\/1.1/);assert.match(String(q.header),/Authorization: invented-provider-key/);assert.deepEqual(q.body,body);reply(socket,201,Buffer.from(canonicalJson({id:other})));});});
 await new Promise<void>(r=>provider.listen(0,'::1',r));const pa=provider.address();assert.ok(pa&&typeof pa!=='string');(globalThis as unknown as Record<string,unknown>).__meetingProviderPort=pa.port;
 backend=tls.createServer({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),ca:readFileSync(file('ca.crt')),requestCert:true,rejectUnauthorized:true,allowHalfOpen:true},socket=>serve(socket,q=>{
  backendCount++;assert.equal(socket.authorized,true);
  if((mode==='local-cycle'||mode==='local-process')&&String(q.header).startsWith('POST /v1/replacement/meetings/supervision ')){
   assert.match(socket.getPeerCertificate().subjectaltname!,/spiffe:\/\/oracle\/invented-local-queue/);assert.ok(queueProfile);const request=JSON.parse((q.body as Buffer).toString());assert.deepEqual(Object.keys(request).sort(),['caller_deadline','schema_version']);localDeadlines.push(request.caller_deadline);queueCount++;
   const packet={schema_version:1,purpose:'meeting-supervision-current-queue-v1',principal_id:id,workspace_id:id,meeting_id:id,process_purpose:'meeting-stop-worker-process-v1',scope_sha256:hash,runtime_sha256:queueProfile.process_runtime_sha256,config_sha256:queueProfile.process_config_sha256,queue_observation_sha256:hash,version:1,capture_until:profile.capture_until,stop_until:profile.stop_until,due_at:new Date(Date.parse(profile.capture_until)-5000).toISOString(),valid_until:request.caller_deadline,observation_only:true,remote_stop_proven:false};setTimeout(()=>reply(socket,200,Buffer.from(canonicalJson(packet))),mode==='local-cycle'?1600:0);return;
  }assert.match(socket.getPeerCertificate().subjectaltname!,mode.startsWith('local')?/spiffe:\/\/oracle\/invented-local-/:/spiffe:\/\/oracle\/invented-worker/);if(mode.startsWith('local')){const uri=socket.getPeerCertificate().subjectaltname!.replace('URI:','');localSelected=localStages.get(uri);assert.ok(localSelected);}assert.match(String(q.header),/^POST \/v1\/replacement\/meetings\/worker HTTP\/1.1/);
  const request=JSON.parse((q.body as Buffer).toString());let state:MeetingWorkerPacketV1['state']=request.operation==='prepare'?'prepared':request.operation==='claim'?'claimed':request.operation==='observe'?'observed':'inflight';if(mode==='repeated'&&request.operation==='claim')state='UNKNOWN';
  const response=packet(state,request.caller_deadline);if(request.operation==='observe'){observedWire=Buffer.from(request.wire_base64,'base64');assert.match(observedWire.toString(),mode.startsWith('local')?/^HTTP\/1.1 200/:/^HTTP\/1.1 201/);}
  if(mode==='foreign')Object.assign(response,{workspace_id:other});if(mode==='unknown-field')Object.assign(response,{role:'admin'});if(mode==='altered-body'&&state==='claimed')Object.assign(response,{body_base64:Buffer.from('{}').toString('base64')});if((mode==='local-slow-current'||(mode==='local-sequence'||mode==='local-cycle')&&localSelected?.effect_purpose==='capture-leave')&&request.operation==='current')setTimeout(()=>reply(socket,200,Buffer.from(canonicalJson(response))),mode==='local-sequence'||mode==='local-cycle'?1800:3400);else if(mode==='local-slow-status'||mode==='local-sequence'&&request.operation==='status')setTimeout(()=>reply(socket,200,Buffer.from(canonicalJson(response))),800);else reply(socket,200,Buffer.from(canonicalJson(response)));
 }));backend.on('tlsClientError',()=>undefined);await new Promise<void>(r=>backend.listen(0,'::1',r));const ba=backend.address();assert.ok(ba&&typeof ba!=='string');
 const receipt=file('receipts');__importMkdir(receipt,{mode:0o700});const stat=lstatSync(receipt);const initialization={schema_version:1,purpose:'meeting-worker-receipt-root-v1',worker_id:other,receipt_root:receipt,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer'};writeFileSync(join(receipt,'initialization.json'),canonicalJson(initialization),{mode:0o600});writeFileSync(file('provider.key'),'invented-provider-key',{mode:0o600});
 const now=Date.now();profile={schema_version:1,purpose:'replacement-meeting-worker-binding-v1',principal_id:id,workspace_id:id,runtime_hash:hash,registry_hash:hash,backend_origin:'https://localhost.localdomain:'+ba.port,server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),server_ca_file:file('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:file('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('client.crt'))).raw),client_uri:'spiffe://oracle/invented-worker',client_key_file:file('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer',valid_from:new Date(now-1000).toISOString(),expires_at:new Date(now+180000).toISOString(),original_horizon:new Date(now+240000).toISOString(),worker_path:'/v1/replacement/meetings/worker',worker_id:other,meeting_id:id,effect_purpose:'capture-create',worker_config_sha256:hash,worker_peer_profile_sha256:hash,worker_admission_sha256:hash,provider_account:'invented-account',provider_region:'us-east-1',provider_ca_file:file('ca.crt'),provider_ca_sha256:pin('ca.crt'),provider_server_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),provider_key_file:file('provider.key'),provider_key_sha256:pin('provider.key'),operation_policy_sha256:hash,composer_program_sha256:null,create_operation_id:id,create_request_sha256:bodySHA,stop_mapping_sha256:null,capture_until:new Date(now+180000).toISOString(),stop_until:new Date(now+240000).toISOString(),receipt_root:receipt,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,receipt_initialization_file:join(receipt,'initialization.json'),receipt_initialization_sha256:sha256(canonicalJson(initialization))};writeFileSync(file('binding.json'),canonicalJson(profile),{mode:0o600});process.env.ORACLE2_MEETING_WORKER_BINDING_FILE=file('binding.json');process.env.ORACLE2_MEETING_WORKER_BINDING_SHA256=pin('binding.json');
});
import {mkdirSync as __importMkdir} from 'node:fs';
after(async()=>{hooks.deregister();Object.defineProperty(nodeDns,'lookup',{value:realLookup});Object.defineProperty(nodeTls,'connect',{value:realConnect});syncBuiltinESMExports();for(const socket of sockets)socket.destroy();await Promise.all([new Promise<void>(r=>backend?backend.close(()=>r()):r()),new Promise<void>(r=>provider?provider.close(()=>r()):r())]);rmSync(dir,{recursive:true,force:true});delete (globalThis as unknown as Record<string,unknown>).__meetingProviderPort;});

async function localInstallation(){
 const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 openssl('req','-newkey','rsa:2048','-nodes','-keyout','local.key','-out','local.csr','-subj','/CN=Invented local STOP');writeFileSync(file('local.ext'),'subjectAltName=URI:spiffe://oracle/invented-local-leave\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in','local.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out','local.crt','-days','1','-extfile','local.ext');chmodSync(file('local.key'),0o600);chmodSync(file('local.crt'),0o600);
 const root=file('local-receipts');__importMkdir(root,{mode:0o700});const stat=lstatSync(root),worker='33333333-3333-4333-8333-333333333333';const initialization={schema_version:1,purpose:'meeting-worker-receipt-root-v1',worker_id:worker,receipt_root:root,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer'};writeFileSync(join(root,'initialization.json'),canonicalJson(initialization),{mode:0o600});
 localProfile={...profile,worker_id:worker,effect_purpose:'capture-leave',create_operation_id:null,create_request_sha256:null,stop_mapping_sha256:hash,client_uri:'spiffe://oracle/invented-local-leave',client_certificate_file:file('local.crt'),client_certificate_sha256:pin('local.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('local.crt'))).raw),client_key_file:file('local.key'),client_key_sha256:pin('local.key'),receipt_root:root,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,receipt_initialization_file:join(root,'initialization.json'),receipt_initialization_sha256:sha256(canonicalJson(initialization))};
 localStages.set(localProfile.client_uri,localProfile); writeFileSync(file('local-binding.json'),canonicalJson(localProfile),{mode:0o600});process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_FILE=file('local-binding.json');process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_SHA256=pin('local-binding.json');
 const now=Date.now(),config={schema_version:1,purpose:'meeting-stop-process-runtime-v1',workspace_id:id,meeting_id:id,provider_account:'invented-account',create_operation_id:id,create_request_sha256:bodySHA,capture_until:profile.capture_until,stop_valid_from:new Date(now-2000).toISOString(),stop_until:profile.stop_until,original_horizon:profile.original_horizon,scheduler_poll_seconds:1,stop_request_seconds:3,safety_allowance_seconds:1,stop_margin_seconds:5,socket_file:file('stop.sock'),observer_uid:process.getuid!(),valid_from:new Date(now-1000).toISOString(),expires_at:profile.stop_until,readonly_wait_count:4,readonly_wait_milliseconds:100,post_stop_delay_milliseconds:100,issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer'};
 writeFileSync(file('local-process.json'),canonicalJson(config),{mode:0o600});process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_FILE=file('local-process.json');process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_SHA256=pin('local-process.json');
}
const isolatedMode=process.env.ORACLE2_TEST_LOCAL_SEQUENCE_ONLY;const sequenceOnly=isolatedMode==='1',cycleOnly=isolatedMode==='cycle',processOnly=isolatedMode==='process';
if(!sequenceOnly&&!cycleOnly&&!processOnly){
test('synthetic child tripwires refuse production DNS and public TLS before network',()=>{
 assert.throws(()=>Reflect.apply(nodeDns.lookup,nodeDns,['us-east-1.recall.ai',()=>undefined]),/refused external DNS/);
 assert.throws(()=>Reflect.apply(nodeTls.connect,nodeTls,[{host:'8.8.8.8',port:443,servername:'us-east-1.recall.ai'}]),/refused external TLS/);
});
test('strict service profile never admits employee selectors or broad provider/action authority',()=>{
 assert.equal(validateMeetingWorkerBinding(profile).effect_purpose,'capture-create');for(const changed of [{auth_user_id:id},{effect_purpose:'anything'},{provider_region:['us-east-1']},{worker_path:'/arbitrary'},{create_request_sha256:null},{receipt_inode:true}])assert.throws(()=>validateMeetingWorkerBinding({...profile,...changed}));
});
test('actual onceclaim mTLS to fixed provider TLS retains exact full wire and same original deadline',async()=>{
 const worker=installedMeetingWorkerV1();assert.equal((globalThis as unknown as Record<string,unknown>).__meetingFixtureProviderHookCalls,1);assert.equal(worker.effect_purpose,'capture-create');assert.match(worker.original_deadline_v1,/\d{2}(?:\.(?!000000)\d{6})?Z$/);const original=worker.original_deadline_v1;
 assert.equal((await worker.prepare_v1()).state,'prepared');const claim=await worker.claim_v1();assert.equal(claim.executable,true);assertInventedClient(worker);const response=await worker.exchange_provider_v1(claim);assert.equal(response.status,201);assert.equal(providerCount,1);
 assert.equal((await worker.observe_v1(claim,response.wire)).state,'observed');assert.equal(sha256(observedWire!),response.wireSha256);assert.equal(worker.original_deadline_v1,original);
 assertInventedClient(worker);await assert.rejects(worker.exchange_provider_v1(claim));await assert.rejects(worker.claim_v1());assert.equal(providerCount,1);
});
test('prior local immutable receipt prevents redispatch even if a bad backend repeats executable body',async()=>{
 mode='valid';const worker=installedMeetingWorkerV1();await worker.prepare_v1();const claim=await worker.claim_v1();assertInventedClient(worker);await assert.rejects(worker.exchange_provider_v1(claim));assert.equal(providerCount,1);
});
test('repeat backend claim is UNKNOWN and never a body capability',async()=>{
 mode='repeated';const worker=installedMeetingWorkerV1();await worker.prepare_v1();const claim=await worker.claim_v1();assert.equal(claim.state,'UNKNOWN');assert.equal(claim.body_base64,null);assertInventedClient(worker);await assert.rejects(worker.exchange_provider_v1(claim));assert.equal(providerCount,1);mode='valid';
});
for(const value of ['foreign','unknown-field','altered-body'])test('foreign or malformed sealed worker observation refuses '+value,async()=>{
 mode=value;const worker=installedMeetingWorkerV1();if(value==='altered-body'){await worker.prepare_v1();await assert.rejects(worker.claim_v1());}else await assert.rejects(worker.prepare_v1());assert.equal(providerCount,1);mode='valid';
});
test('closed packet rejects executable body outside first claim, booleans and duplicate JSON',()=>{
 const v=packet('prepared',new Date(Date.now()+1000).toISOString());for(const change of [{body_base64:''},{executable:1},{remote_stop_proven:true},{schema_version:true},{effect_purpose:['capture-create']}])assert.throws(()=>parseMeetingWorkerPacketV1(Buffer.from(canonicalJson({...v,...change}))));assert.throws(()=>parseMeetingWorkerPacketV1(Buffer.from(canonicalJson(v).replace('"schema_version":1','"schema_version":1,"schema_version":1'))));
});
test('exact-second original deadline uses canonical Python UTC without renewal',()=>{
 const originalNow=Date.now,captured=Math.floor(originalNow()/1000)*1000,count=providerCount;
 try{Date.now=()=>captured;const worker=installedMeetingWorkerV1();assertInventedClient(worker);assert.equal(worker.original_deadline_v1,new Date(captured+30000).toISOString().replace('.000Z','Z'));assert.doesNotMatch(worker.original_deadline_v1,/\.000000Z$/);assert.equal(providerCount,count);}finally{Date.now=originalNow;}
});
test('fixed noargs purpose refuses old/global fallback and wrong profile before provider private reads',async()=>{
 const workerModule=await import('@oracle/shared/protected-meeting-worker'),original=nodeFs.openSync;
 const constructed=(globalThis as unknown as Record<string,number>).__meetingFixtureProviderHookCalls;let providerReads=0;
 Object.defineProperty(nodeFs,'openSync',{configurable:true,writable:true,value:(...args:unknown[])=>{if(args[0]===file('provider.key')||args[0]===file('ca.crt'))providerReads++;return Reflect.apply(original,nodeFs,args as Parameters<typeof original>);}});syncBuiltinESMExports();
 try{
  assert.throws(()=>workerModule.installedMeetingCaptureLeaveWorkerV1());
  process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_FILE=file('binding.json');process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_SHA256=pin('binding.json');
  assert.throws(()=>workerModule.installedMeetingCaptureLeaveWorkerV1());assert.equal(providerReads,0);
  assert.equal((globalThis as unknown as Record<string,number>).__meetingFixtureProviderHookCalls,constructed);
 }finally{Object.defineProperty(nodeFs,'openSync',{configurable:true,writable:true,value:original});syncBuiltinESMExports();delete process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_FILE;delete process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_SHA256;}
});
test('static create consumer keeps its own loader through actual current reread and rejects forged copies',async()=>{
 const bindingModule=await import('@oracle/shared/protected-server-binding');const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 openssl('req','-newkey','rsa:2048','-nodes','-keyout','fixed.key','-out','fixed.csr','-subj','/CN=Invented fixed create');writeFileSync(file('fixed.ext'),'subjectAltName=URI:spiffe://oracle/invented-fixed-create\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in','fixed.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out','fixed.crt','-days','1','-extfile','fixed.ext');chmodSync(file('fixed.key'),0o600);chmodSync(file('fixed.crt'),0o600);
 const fixed={...profile,client_uri:'spiffe://oracle/invented-fixed-create',client_certificate_file:file('fixed.crt'),client_certificate_sha256:pin('fixed.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('fixed.crt'))).raw),client_key_file:file('fixed.key'),client_key_sha256:pin('fixed.key')};writeFileSync(file('fixed-binding.json'),canonicalJson(fixed),{mode:0o600});process.env.ORACLE2_MEETING_CREATE_WORKER_BINDING_FILE=file('fixed-binding.json');process.env.ORACLE2_MEETING_CREATE_WORKER_BINDING_SHA256=pin('fixed-binding.json');
 try{const installed=bindingModule.readInstalledMeetingCaptureCreateWorkerBinding();assert.equal(bindingModule.rereadInstalledMeetingWorkerBinding(installed).profile.client_uri,fixed.client_uri);assert.throws(()=>bindingModule.rereadInstalledMeetingWorkerBinding({...installed}));process.env.ORACLE2_MEETING_CREATE_WORKER_BINDING_FILE=file('binding.json');assert.throws(()=>bindingModule.rereadInstalledMeetingWorkerBinding(installed));}finally{delete process.env.ORACLE2_MEETING_CREATE_WORKER_BINDING_FILE;delete process.env.ORACLE2_MEETING_CREATE_WORKER_BINDING_SHA256;}
});
test('retrieve stage and operation are exact together and cannot qualify a different purpose',()=>{
 const retrieve={...profile,effect_purpose:'capture-retrieve',create_operation_id:null,create_request_sha256:null,stop_mapping_sha256:hash,retrieve_stage:'pre-stop-consistency',retrieve_operation_id:id};assert.equal(validateMeetingWorkerBinding(retrieve).retrieve_stage,'pre-stop-consistency');for(const change of [{retrieve_stage:'any'},{retrieve_operation_id:null},{effect_purpose:'capture-create'},{retrieve_stage:undefined}])assert.throws(()=>validateMeetingWorkerBinding({...retrieve,...change}));
});
test('local original3s includes actual providerTLS then slow fresh backend currentness: zero Authorization/body',async()=>{
 await localInstallation();mode='local-slow-current';localDeadlines.length=0;const moduleWorker=await import('@oracle/shared/protected-meeting-worker');const start=performance.now(),beforeHTTP=providerCount,beforeTLS=providerTLSCount,worker=moduleWorker.installedLocalMeetingCaptureLeaveWorkerV1(),original=worker.original_deadline_v1;
 try{await worker.prepare_v1();const claim=await worker.claim_v1();assertInventedClient(worker);await assert.rejects(worker.exchange_provider_v1(claim));assert.ok(performance.now()-start<4000);assert.ok(performance.now()-start>=2500);assert.equal(providerCount,beforeHTTP);assert.equal(providerTLSCount,beforeTLS+1);assert.ok(localDeadlines.length>=3);assert.ok(localDeadlines.every(d=>d===original));assert.equal(worker.original_deadline_v1,original);}finally{mode='valid';}
});
test('bounded readonly status waiting cannot reset SAME original local3s window',async()=>{
 mode='local-slow-status';localDeadlines.length=0;const moduleWorker=await import('@oracle/shared/protected-meeting-worker'),worker=moduleWorker.installedLocalMeetingCaptureLeaveWorkerV1(),original=worker.original_deadline_v1,start=performance.now(),beforeHTTP=providerCount;
 try{await worker.status_v1();await worker.status_v1();await worker.status_v1();await assert.rejects(worker.status_v1());assert.ok(performance.now()-start<4000);assert.ok(performance.now()-start>=2500);assert.equal(providerCount,beforeHTTP);assert.ok(localDeadlines.length>=3);assert.ok(localDeadlines.every(d=>d===original));assert.equal(worker.original_deadline_v1,original);}finally{mode='valid';delete process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_FILE;delete process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_SHA256;delete process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_FILE;delete process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_SHA256;}
});
test('provider key drift refuses current worker before any further HTTP',async()=>{
 const worker=installedMeetingWorkerV1(),count=backendCount;writeFileSync(file('provider.key'),'altered-provider-key');await assert.rejects(worker.prepare_v1());assert.equal(backendCount,count);assert.equal(providerCount,1);
});

test('aggregate sequence uses a fresh process and SAME fixture owner, with no reused spent state',async()=>{
 const environment:NodeJS.ProcessEnv={...process.env,ORACLE2_TEST_LOCAL_SEQUENCE_ONLY:'1'};delete environment.NODE_TEST_CONTEXT;
 const result=await new Promise<{stdout:string;stderr:string}>((resolve,reject)=>execFile('pnpm',['--filter','@oracle/web','exec','tsx','--test','lib/replacement-meeting-worker.test.ts'],{cwd:new URL('../',import.meta.url),env:environment,timeout:15000},(error,stdout,stderr)=>error?reject(new Error(stdout+'\n'+stderr)):resolve({stdout,stderr})));
 assert.match(result.stdout,/# pass 1\b/,result.stderr);assert.match(result.stdout,/# fail 0\b/);assert.match(result.stdout,/# skipped 0\b/);
});
test('queue and STOP stages share one original3s in a fresh process',async()=>{
 const environment:NodeJS.ProcessEnv={...process.env,ORACLE2_TEST_LOCAL_SEQUENCE_ONLY:'cycle'};delete environment.NODE_TEST_CONTEXT;
 const result=await new Promise<{stdout:string;stderr:string}>((resolve,reject)=>execFile('pnpm',['--filter','@oracle/web','exec','tsx','--test','lib/replacement-meeting-worker.test.ts'],{cwd:new URL('../',import.meta.url),env:environment,timeout:15000},(error,stdout,stderr)=>error?reject(new Error(stdout+'\n'+stderr)):resolve({stdout,stderr})));
 assert.match(result.stdout,/# pass 1\b/,result.stderr);assert.match(result.stdout,/# fail 0\b/);assert.match(result.stdout,/# skipped 0\b/);
});
test('concrete local STOP process proves actual armed loop and current queue without effects',async()=>{
 const environment:NodeJS.ProcessEnv={...process.env,ORACLE2_TEST_LOCAL_SEQUENCE_ONLY:'process'};delete environment.NODE_TEST_CONTEXT;
 const result=await new Promise<{stdout:string;stderr:string}>((resolve,reject)=>execFile('pnpm',['--filter','@oracle/web','exec','tsx','--test','lib/replacement-meeting-worker.test.ts'],{cwd:new URL('../',import.meta.url),env:environment,timeout:15000},(error,stdout,stderr)=>error?reject(new Error(stdout+'\n'+stderr)):resolve({stdout,stderr})));
 assert.match(result.stdout,/# pass 1\b/,result.stderr);assert.match(result.stdout,/# fail 0\b/);assert.match(result.stdout,/# skipped 0\b/);
});
}
async function localSequenceInstallation(){
 if(!localProfile)await localInstallation();
 process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_FILE=file('local-binding.json');process.env.ORACLE2_MEETING_LEAVE_WORKER_BINDING_SHA256=pin('local-binding.json');process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_FILE=file('local-process.json');process.env.ORACLE2_MEETING_STOP_PROCESS_CONFIG_SHA256=pin('local-process.json');
 const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 for(const [stage,name,worker,operation] of [['pre-stop-consistency','pre','66666666-6666-4666-8666-666666666666','88888888-8888-4888-8888-888888888888'],['post-stop-terminal','post','77777777-7777-4777-8777-777777777777','99999999-9999-4999-8999-999999999999']] as const){
  openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented local '+name);writeFileSync(file(name+'.ext'),'subjectAltName=URI:spiffe://oracle/invented-local-'+name+'\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');chmodSync(file(name+'.key'),0o600);chmodSync(file(name+'.crt'),0o600);
  const root=file(name+'-receipts');__importMkdir(root,{mode:0o700});const stat=lstatSync(root);const initialization={schema_version:1,purpose:'meeting-worker-receipt-root-v1',worker_id:worker,receipt_root:root,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer'};writeFileSync(join(root,'initialization.json'),canonicalJson(initialization),{mode:0o600});
  const p:MeetingWorkerBinding={...localProfile!,worker_id:worker,effect_purpose:'capture-retrieve',retrieve_stage:stage,retrieve_operation_id:operation,client_uri:'spiffe://oracle/invented-local-'+name,client_certificate_file:file(name+'.crt'),client_certificate_sha256:pin(name+'.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file(name+'.crt'))).raw),client_key_file:file(name+'.key'),client_key_sha256:pin(name+'.key'),receipt_root:root,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,receipt_initialization_file:join(root,'initialization.json'),receipt_initialization_sha256:sha256(canonicalJson(initialization))};
  localStages.set(p.client_uri,p);writeFileSync(file(name+'-binding.json'),canonicalJson(p),{mode:0o600});const prefix=name==='pre'?'ORACLE2_MEETING_PRE_STOP_RETRIEVE_WORKER_BINDING':'ORACLE2_MEETING_POST_STOP_RETRIEVE_WORKER_BINDING';process.env[prefix+'_FILE']=file(name+'-binding.json');process.env[prefix+'_SHA256']=pin(name+'-binding.json');
 }
}
if(sequenceOnly)test('one original3s sequence includes actual preGET, status waits and providerTLS; leave/post cannot spend later windows',async()=>{
 await localSequenceInstallation();const workerModule=await import('@oracle/shared/protected-meeting-worker');mode='local-sequence';localDeadlines.length=0;const beforeHTTP=providerCount,beforeTLS=providerTLSCount,start=performance.now(),sequence=workerModule.installedLocalMeetingStopSequenceV1();
 try{
  assert.equal(sequence.pre_stop.original_deadline_v1,sequence.original_deadline_v1);assert.equal(sequence.leave.original_deadline_v1,sequence.original_deadline_v1);assert.equal(sequence.post_stop.original_deadline_v1,sequence.original_deadline_v1);
  await sequence.pre_stop.prepare_v1();const pre=await sequence.pre_stop.claim_v1();assertInventedClient(sequence.pre_stop);const raw=await sequence.pre_stop.exchange_provider_v1(pre);assert.equal(raw.status,200);await sequence.pre_stop.observe_v1(pre,raw.wire);
  await sequence.leave.status_v1();await sequence.leave.status_v1();await sequence.leave.prepare_v1();const leave=await sequence.leave.claim_v1();assertInventedClient(sequence.leave);await assert.rejects(sequence.leave.exchange_provider_v1(leave));const beforeLate=backendCount;await assert.rejects(sequence.post_stop.prepare_v1());assert.equal(backendCount,beforeLate);assert.throws(()=>sequence.current_v1());
  assert.ok(performance.now()-start<4000);assert.ok(performance.now()-start>=2500);assert.equal(providerCount,beforeHTTP+1);assert.equal(providerTLSCount,beforeTLS+2);assert.ok(localDeadlines.every(d=>d===sequence.original_deadline_v1));assert.equal(Reflect.get(sequence.leave,'sequence'),undefined);
  const Constructor=sequence.leave.constructor as new(...args:unknown[])=>unknown;assert.throws(()=>new Constructor('local-leave',{wall:Date.now(),mono:performance.now(),tick:process.hrtime.bigint(),end:Date.now()+30000}));
 }finally{mode='valid';for(const prefix of ['ORACLE2_MEETING_LEAVE_WORKER_BINDING','ORACLE2_MEETING_PRE_STOP_RETRIEVE_WORKER_BINDING','ORACLE2_MEETING_POST_STOP_RETRIEVE_WORKER_BINDING','ORACLE2_MEETING_STOP_PROCESS_CONFIG']){delete process.env[prefix+'_FILE'];delete process.env[prefix+'_SHA256'];}}
});

async function localQueueInstallation(){
 const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 openssl('req','-newkey','rsa:2048','-nodes','-keyout','queue.key','-out','queue.csr','-subj','/CN=Invented local queue');writeFileSync(file('queue.ext'),'subjectAltName=URI:spiffe://oracle/invented-local-queue\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in','queue.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out','queue.crt','-days','1','-extfile','queue.ext');chmodSync(file('queue.key'),0o600);chmodSync(file('queue.crt'),0o600);
 const {provider_ca_file:_ca,provider_ca_sha256:_casha,provider_server_der_sha256:_der,provider_key_file:_key,provider_key_sha256:_keysha,provider_account:_account,provider_region:_region,worker_path:_path,worker_id:_worker,effect_purpose:_effect,worker_config_sha256:_config,worker_peer_profile_sha256:_peer,worker_admission_sha256:_admission,operation_policy_sha256:_policy,composer_program_sha256:_composer,create_operation_id:_create,create_request_sha256:_sha,stop_mapping_sha256:_map,receipt_root:_root,receipt_device:_device,receipt_inode:_inode,receipt_uid:_uid,receipt_initialization_file:_init,receipt_initialization_sha256:_initsha,...base}=profile;
 void [_ca,_casha,_der,_key,_keysha,_account,_region,_path,_worker,_effect,_config,_peer,_admission,_policy,_composer,_create,_sha,_map,_root,_device,_inode,_uid,_init,_initsha];
 queueProfile={...base,purpose:'meeting-supervision-service-binding-v1',client_uri:'spiffe://oracle/invented-local-queue',client_certificate_file:file('queue.crt'),client_certificate_sha256:pin('queue.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('queue.crt'))).raw),client_key_file:file('queue.key'),client_key_sha256:pin('queue.key'),supervision_path:'/v1/replacement/meetings/supervision',supervision_config_sha256:hash,supervision_peer_profile_sha256:hash,process_purpose:'meeting-stop-worker-process-v1',scope_sha256:hash,process_runtime_sha256:hash,process_config_sha256:pin('local-process.json')};
 writeFileSync(file('queue-binding.json'),canonicalJson(queueProfile),{mode:0o600});process.env.ORACLE2_MEETING_STOP_SUPERVISION_BINDING_FILE=file('queue-binding.json');process.env.ORACLE2_MEETING_STOP_SUPERVISION_BINDING_SHA256=pin('queue-binding.json');
}
if(cycleOnly)test('actual delayed queue plus providerTLS/currentness consumes SAME original3s with zero provider bytes',async()=>{
 await localSequenceInstallation();await localQueueInstallation();mode='local-cycle';localDeadlines.length=0;
 const workerModule=await import('@oracle/shared/protected-meeting-worker'),start=performance.now(),beforeHTTP=providerCount,beforeTLS=providerTLSCount,cycle=workerModule.installedLocalMeetingStopCycleV1();
 try{
  const packet=await cycle.current_queue_v1();assert.equal(packet.observation_only,true);assert.equal(queueCount,1);assert.ok(performance.now()-start>=1500);
  const pre=cycle.sequence.pre_stop;assert.equal(pre.original_deadline_v1,cycle.original_deadline_v1);assert.equal(cycle.sequence.leave.original_deadline_v1,cycle.original_deadline_v1);assert.equal(cycle.sequence.post_stop.original_deadline_v1,cycle.original_deadline_v1);
  await pre.prepare_v1();const claim=await pre.claim_v1();assertInventedClient(pre);
  // The after-provider-TLS currentness call shares the queue's original end.
  // Delay it beyond the remaining time; no Authorization/body may be written.
  mode='local-slow-current';await assert.rejects(pre.exchange_provider_v1(claim));mode='local-cycle';
  const beforeLate=backendCount;await assert.rejects(cycle.sequence.leave.prepare_v1());await assert.rejects(cycle.sequence.post_stop.prepare_v1());assert.equal(backendCount,beforeLate);assert.throws(()=>cycle.sequence.current_v1());
  assert.ok(performance.now()-start>=2500);assert.ok(performance.now()-start<4000);assert.equal(providerCount,beforeHTTP);assert.equal(providerTLSCount,beforeTLS+1);assert.ok(localDeadlines.every(d=>d===cycle.original_deadline_v1));
 }finally{mode='valid';}
});

if(processOnly)test('actual installed source process owns private socket, fresh queue, armed loop, and refuses late IPC body',async()=>{
 await localSequenceInstallation();await localQueueInstallation();mode='local-process';assert.ok(queueProfile);
 const runtime=new URL('../../workers/src/services/oracle2-meeting-stop-process.ts',import.meta.url).pathname;
 // Runtime source is the actual owned service, not a substitute child body.
 chmodSync(runtime,0o600);queueProfile={...queueProfile,process_runtime_sha256:sha256(readFileSync(runtime))};writeFileSync(file('queue-binding.json'),canonicalJson(queueProfile),{mode:0o600});process.env.ORACLE2_MEETING_STOP_SUPERVISION_BINDING_SHA256=pin('queue-binding.json');
 const preload=file('child-tripwire.mjs');writeFileSync(preload,`import dns from 'node:dns';import tls from 'node:tls';import {syncBuiltinESMExports} from 'node:module';const lookup=dns.lookup,connect=tls.connect;dns.lookup=function(...a){if(!['localhost.localdomain','::1','127.0.0.1'].includes(String(a[0])))throw Error('fixture refused external DNS');return Reflect.apply(lookup,dns,a)};tls.connect=function(...a){if(!['localhost.localdomain','::1','127.0.0.1'].includes(String(a[0]?.host))||a[0]?.servername!=='localhost.localdomain')throw Error('fixture refused external TLS');return Reflect.apply(connect,tls,a)};syncBuiltinESMExports();`,{mode:0o600});
 const child=spawn(process.execPath,['--import','tsx','--import',preload,runtime,file('local-process.json')],{cwd:new URL('../../workers/',import.meta.url),env:process.env,stdio:['ignore','pipe','pipe']});let output='';child.stdout.on('data',v=>{output+=v;});child.stderr.on('data',v=>{output+=v;});const stopped=new Promise<number|null>(resolve=>child.once('exit',resolve));
 const socketPath=file('stop.sock');
 const ask=async(late=false):Promise<Record<string,unknown>>=>{
  const net=await import('node:net');const sock=net.createConnection(socketPath),end=new Date(Date.now()+(late?100:1500)).toISOString(),value={schema_version:2,purpose:'meeting-process-currentness-v2',challenge:'b'.repeat(64),scope_sha256:hash,caller_deadline:end},body=Buffer.from(canonicalJson(value)),prefix=Buffer.alloc(4);prefix.writeUInt32BE(body.length);
  return await new Promise<Record<string,unknown>>((resolve,reject)=>{let raw=Buffer.alloc(0);const timer=setTimeout(()=>{sock.destroy();reject(new Error('fixture IPC timeout'));},2500);sock.on('error',reject);sock.on('data',v=>{raw=Buffer.concat([raw,v]);});sock.on('close',()=>{clearTimeout(timer);try{if(late){assert.equal(raw.length,0);resolve({});return;}assert.ok(raw.length>=4);assert.equal(raw.readUInt32BE(0),raw.length-4);resolve(JSON.parse(raw.subarray(4).toString()));}catch(e){reject(e);}});sock.on('connect',()=>{if(late){sock.write(Buffer.concat([prefix,body.subarray(0,-1)]));setTimeout(()=>{if(!sock.destroyed)sock.write(body.subarray(-1));},200);}else sock.write(Buffer.concat([prefix,body]));});});
 };
 try{
  const until=performance.now()+5000;let proof:Record<string,unknown>|undefined;
  while(performance.now()<until&&child.exitCode===null){if(existsSync(socketPath)){try{proof=await ask();break;}catch{}}await new Promise<void>(r=>setTimeout(r,25));}
  assert.ok(proof,output);assert.equal(proof.schema_version,2);assert.equal(proof.process_purpose,'meeting-stop-worker-process-v1');assert.equal(proof.runtime_sha256,sha256(readFileSync(runtime)));assert.equal(proof.config_sha256,pin('local-process.json'));assert.ok(queueCount>=2);assert.equal(providerCount,0);
  await ask(true);assert.equal(providerCount,0);assert.equal(child.exitCode,null);
  child.kill('SIGTERM');assert.equal(await stopped,0,output);assert.equal(existsSync(socketPath),false,'source process must remove own socket before fixture directory cleanup');assert.equal(providerCount,0);
 }finally{if(child.exitCode===null){child.kill('SIGTERM');await stopped;}}
});
