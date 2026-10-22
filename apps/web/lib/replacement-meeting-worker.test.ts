/** Actual owned loopback mTLS + provider TLS, invented backend state only.
 * Not actual SQL, installed service, provider account or employee proof. */
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {registerHooks,syncBuiltinESMExports} from 'node:module';
import nodeFs from 'node:fs';
import nodeDns from 'node:dns';import nodeTls from 'node:tls';
import {mkdtempSync,chmodSync,writeFileSync,readFileSync,lstatSync,rmSync} from 'node:fs';
import {join} from 'node:path';import {tmpdir} from 'node:os';import {execFileSync} from 'node:child_process';
import {X509Certificate} from 'node:crypto';import * as tls from 'node:tls';
import {canonicalJson,sha256,validateMeetingWorkerBinding,type MeetingWorkerBinding} from '@oracle/shared/protected-server-binding';
import {parseMeetingWorkerPacketV1,type MeetingWorkerPacketV1} from '@oracle/shared/protected-worker-contract';
let installedMeetingWorkerV1:typeof import('@oracle/shared/protected-meeting-worker')['installedMeetingWorkerV1'];
const id='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222',hash='a'.repeat(64);
let dir:string,backend:tls.Server,provider:tls.Server,profile:MeetingWorkerBinding,backendCount=0,providerCount=0;
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
 const record=(globalThis as unknown as Record<string,{client:unknown;port:number}>).__meetingConstructedFixtureClient;
 assert.ok(record);assert.equal(Reflect.get(worker as object,'provider'),record.client);
 assert.equal(Reflect.get(record.client as object,'fixture'),true);assert.equal(Reflect.get(record.client as object,'hostname'),'localhost.localdomain');
 assert.equal(Reflect.get(record.client as object,'port'),record.port);
}

const body=Buffer.from(canonicalJson({meeting_url:'https://teams.microsoft.com/l/meetup-join/invented',bot_name:'Oracle',recording_config:{transcript:{provider:{elevenlabs_streaming:{}}},realtime_endpoints:[{type:'webhook',url:'https://web.example.test/api/teams/live/recall',events:['transcript.data']}]}}));
const bodySHA=sha256(body),file=(name:string)=>join(dir,name),pin=(name:string)=>sha256(readFileSync(file(name)));
const primitiveURL=new URL('../../../packages/shared/src/protected-node-https.ts',import.meta.url).href.replace('/apps/packages/','/packages/');
// Explicit test-only loopback profile keeps production all-public DNS untouched.
const hooks=registerHooks({resolve(specifier,context,next){if(context.parentURL?.includes('protected-meeting-worker.ts')&&specifier==='./protected-node-https')return {url:'oracle-test:meeting-provider',shortCircuit:true};return next(specifier,context);},load(url,context,next){if(url==='oracle-test:meeting-provider')return {format:'module',shortCircuit:true,source:`import {inventedLoopbackRecallHTTPSV1} from ${JSON.stringify(primitiveURL)};export function installedRecallHTTPSV1(target){globalThis.__meetingFixtureProviderHookCalls=(globalThis.__meetingFixtureProviderHookCalls??0)+1;if(!Number.isSafeInteger(globalThis.__meetingProviderPort))throw new Error('fixture target absent');const client=inventedLoopbackRecallHTTPSV1({...target,hostname:'localhost.localdomain'},globalThis.__meetingProviderPort);globalThis.__meetingConstructedFixtureClient={client,port:globalThis.__meetingProviderPort};return client}`};return next(url,context);}});
function packet(state:MeetingWorkerPacketV1['state'],deadline:string):MeetingWorkerPacketV1{return {schema_version:1,state,effect_purpose:'capture-create',principal_id:id,worker_id:other,workspace_id:id,meeting_id:id,provider_account:'invented-account',operation_id:id,claim_event_id:state==='prepared'?null:other,request_sha256:bodySHA,bot_id:null,body_base64:state==='claimed'?body.toString('base64'):null,operation_policy_sha256:hash,composer_program_sha256:null,valid_until:deadline,executable:state==='claimed',qualification:false,remote_stop_proven:false,observation_only:true,resend_authorized:false};}
function serve(socket:tls.TLSSocket,callback:(q:Record<string,unknown>)=>void){sockets.add(socket);socket.on('close',()=>sockets.delete(socket));socket.on('error',()=>undefined);let raw=Buffer.alloc(0),done=false;socket.on('data',(part:Buffer)=>{raw=Buffer.concat([raw,part]);const split=raw.indexOf('\r\n\r\n');if(done||split<0)return;const size=Number(/content-length: (\d+)/i.exec(raw.subarray(0,split).toString())?.[1]);if(raw.length<split+4+size)return;done=true;callback({header:raw.subarray(0,split).toString(),body:raw.subarray(split+4)});});}
function reply(socket:tls.TLSSocket,status:number,bytes:Buffer){socket.end(Buffer.concat([Buffer.from(`HTTP/1.1 ${status} OK\r\nContent-Type: application/json\r\nContent-Length: ${bytes.length}\r\nConnection: close\r\n\r\n`),bytes]));}
before(async()=>{
 ({installedMeetingWorkerV1}=await import('@oracle/shared/protected-meeting-worker'));
 dir=mkdtempSync(join(tmpdir(),'oracle-worker-wire-'));chmodSync(dir,0o700);const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented Worker CA');
 for(const name of ['server','client']){openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented '+name);writeFileSync(file(name+'.ext'),name==='server'?'subjectAltName=DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\n':'subjectAltName=URI:spiffe://oracle/invented-worker\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');}
 for(const name of ['ca.crt','client.crt','client.key','server.crt','server.key'])chmodSync(file(name),0o600);
 provider=tls.createServer({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),allowHalfOpen:true},socket=>serve(socket,q=>{providerCount++;assert.match(String(q.header),/^POST \/api\/v1\/bot\/ HTTP\/1.1/);assert.match(String(q.header),/Authorization: invented-provider-key/);assert.deepEqual(q.body,body);reply(socket,201,Buffer.from(canonicalJson({id:other})));}));
 await new Promise<void>(r=>provider.listen(0,'::1',r));const pa=provider.address();assert.ok(pa&&typeof pa!=='string');(globalThis as unknown as Record<string,unknown>).__meetingProviderPort=pa.port;
 backend=tls.createServer({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),ca:readFileSync(file('ca.crt')),requestCert:true,rejectUnauthorized:true,allowHalfOpen:true},socket=>serve(socket,q=>{
  backendCount++;assert.equal(socket.authorized,true);assert.match(socket.getPeerCertificate().subjectaltname!,/spiffe:\/\/oracle\/invented-worker/);assert.match(String(q.header),/^POST \/v1\/replacement\/meetings\/worker HTTP\/1.1/);
  const request=JSON.parse((q.body as Buffer).toString());let state:MeetingWorkerPacketV1['state']=request.operation==='prepare'?'prepared':request.operation==='claim'?'claimed':request.operation==='observe'?'observed':'inflight';if(mode==='repeated'&&request.operation==='claim')state='UNKNOWN';
  const response=packet(state,request.caller_deadline);if(request.operation==='observe'){observedWire=Buffer.from(request.wire_base64,'base64');assert.match(observedWire.toString(),/^HTTP\/1.1 201/);}
  if(mode==='foreign')Object.assign(response,{workspace_id:other});if(mode==='unknown-field')Object.assign(response,{role:'admin'});if(mode==='altered-body'&&state==='claimed')Object.assign(response,{body_base64:Buffer.from('{}').toString('base64')});reply(socket,200,Buffer.from(canonicalJson(response)));
 }));backend.on('tlsClientError',()=>undefined);await new Promise<void>(r=>backend.listen(0,'::1',r));const ba=backend.address();assert.ok(ba&&typeof ba!=='string');
 const receipt=file('receipts');__importMkdir(receipt,{mode:0o700});const stat=lstatSync(receipt);const initialization={schema_version:1,purpose:'meeting-worker-receipt-root-v1',worker_id:other,receipt_root:receipt,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer'};writeFileSync(join(receipt,'initialization.json'),canonicalJson(initialization),{mode:0o600});writeFileSync(file('provider.key'),'invented-provider-key',{mode:0o600});
 const now=Date.now();profile={schema_version:1,purpose:'replacement-meeting-worker-binding-v1',principal_id:id,workspace_id:id,runtime_hash:hash,registry_hash:hash,backend_origin:'https://localhost.localdomain:'+ba.port,server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),server_ca_file:file('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:file('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('client.crt'))).raw),client_uri:'spiffe://oracle/invented-worker',client_key_file:file('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer',valid_from:new Date(now-1000).toISOString(),expires_at:new Date(now+180000).toISOString(),original_horizon:new Date(now+240000).toISOString(),worker_path:'/v1/replacement/meetings/worker',worker_id:other,meeting_id:id,effect_purpose:'capture-create',worker_config_sha256:hash,worker_peer_profile_sha256:hash,worker_admission_sha256:hash,provider_account:'invented-account',provider_region:'us-east-1',provider_ca_file:file('ca.crt'),provider_ca_sha256:pin('ca.crt'),provider_server_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),provider_key_file:file('provider.key'),provider_key_sha256:pin('provider.key'),operation_policy_sha256:hash,composer_program_sha256:null,create_operation_id:id,create_request_sha256:bodySHA,stop_mapping_sha256:null,capture_until:new Date(now+180000).toISOString(),stop_until:new Date(now+240000).toISOString(),receipt_root:receipt,receipt_device:stat.dev,receipt_inode:stat.ino,receipt_uid:stat.uid,receipt_initialization_file:join(receipt,'initialization.json'),receipt_initialization_sha256:sha256(canonicalJson(initialization))};writeFileSync(file('binding.json'),canonicalJson(profile),{mode:0o600});process.env.ORACLE2_MEETING_WORKER_BINDING_FILE=file('binding.json');process.env.ORACLE2_MEETING_WORKER_BINDING_SHA256=pin('binding.json');
});
import {mkdirSync as __importMkdir} from 'node:fs';
after(async()=>{hooks.deregister();Object.defineProperty(nodeDns,'lookup',{value:realLookup});Object.defineProperty(nodeTls,'connect',{value:realConnect});syncBuiltinESMExports();for(const socket of sockets)socket.destroy();await Promise.all([new Promise<void>(r=>backend?backend.close(()=>r()):r()),new Promise<void>(r=>provider?provider.close(()=>r()):r())]);rmSync(dir,{recursive:true,force:true});delete (globalThis as unknown as Record<string,unknown>).__meetingProviderPort;});

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
test('provider key drift refuses current worker before any further HTTP',async()=>{
 const worker=installedMeetingWorkerV1(),count=backendCount;writeFileSync(file('provider.key'),'altered-provider-key');await assert.rejects(worker.prepare_v1());assert.equal(backendCount,count);assert.equal(providerCount,1);
});
