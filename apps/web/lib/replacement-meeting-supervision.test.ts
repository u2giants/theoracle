/** Actual owned mTLS only; invented backend state, not SQL/employee/installation. */
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {mkdtempSync,chmodSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {execFileSync} from 'node:child_process';
import {X509Certificate} from 'node:crypto';import * as tls from 'node:tls';
import nodeDns from 'node:dns';import nodeTls from 'node:tls';import {syncBuiltinESMExports} from 'node:module';
import {canonicalJson,sha256,validateMeetingSupervisionBinding,readInstalledMeetingSchedulerSupervisionBinding,rereadInstalledMeetingSupervisionBinding,type MeetingSupervisionBinding} from '@oracle/shared/protected-server-binding';
import {installedMeetingSchedulerSupervisionV1} from '@oracle/shared/protected-meeting-worker';
import {parseMeetingSupervisionPacketV1,type MeetingSupervisionPacketV1} from '@oracle/shared/protected-worker-contract';
const id='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222',hash='a'.repeat(64);
let dir:string,server:tls.Server,profile:MeetingSupervisionBinding,count=0,mode='valid';const sockets=new Set<tls.TLSSocket>();
const lookup=nodeDns.lookup,connect=nodeTls.connect;
Object.defineProperty(nodeDns,'lookup',{configurable:true,writable:true,value:(...args:unknown[])=>{if(!['localhost.localdomain','::1','127.0.0.1'].includes(String(args[0])))throw new Error('fixture external DNS refused');return Reflect.apply(lookup,nodeDns,args);}});
Object.defineProperty(nodeTls,'connect',{configurable:true,writable:true,value:(...args:unknown[])=>{const v=args[0];if(!v||typeof v!=='object'||Reflect.get(v,'host')!=='localhost.localdomain'||Reflect.get(v,'servername')!=='localhost.localdomain')throw new Error('fixture external TLS refused');return Reflect.apply(connect,nodeTls,args);}});syncBuiltinESMExports();
const file=(name:string)=>join(dir,name),pin=(name:string)=>sha256(readFileSync(file(name)));
function packet(deadline:string):MeetingSupervisionPacketV1{return {schema_version:1,purpose:'meeting-supervision-current-queue-v1',principal_id:id,workspace_id:id,meeting_id:id,process_purpose:'meeting-scheduler-process-v1',scope_sha256:hash,runtime_sha256:hash,config_sha256:hash,queue_observation_sha256:hash,version:1,capture_until:profile.capture_until,stop_until:profile.stop_until,due_at:new Date(Date.parse(profile.capture_until)-5000).toISOString(),valid_until:deadline,observation_only:true,remote_stop_proven:false};}
before(async()=>{
 dir=mkdtempSync(join(tmpdir(),'oracle-supervision-wire-'));chmodSync(dir,0o700);
 const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented supervision CA');
 for(const name of ['server','client']){openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented '+name);writeFileSync(file(name+'.ext'),name==='server'?'subjectAltName=DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\n':'subjectAltName=URI:spiffe://oracle/invented-supervisor\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');}
 for(const name of ['ca.crt','client.crt','client.key','server.crt','server.key'])chmodSync(file(name),0o600);
 server=tls.createServer({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),ca:readFileSync(file('ca.crt')),requestCert:true,rejectUnauthorized:true,allowHalfOpen:true},socket=>{
  sockets.add(socket);socket.on('close',()=>sockets.delete(socket));socket.on('error',()=>undefined);let bytes=Buffer.alloc(0),done=false;
  socket.on('data',(part:Buffer)=>{bytes=Buffer.concat([bytes,part]);const split=bytes.indexOf('\r\n\r\n');if(done||split<0)return;const length=Number(/content-length: (\d+)/i.exec(bytes.subarray(0,split).toString())?.[1]);if(bytes.length<split+4+length)return;done=true;count++;
   assert.equal(socket.authorized,true);assert.match(socket.getPeerCertificate().subjectaltname!,/spiffe:\/\/oracle\/invented-supervisor/);
   const header=bytes.subarray(0,split).toString();assert.match(header,/^POST \/v1\/replacement\/meetings\/supervision HTTP\/1.1/);assert.doesNotMatch(header,/authorization:|cookie:|actor:/i);
   const raw=bytes.subarray(split+4);const q=JSON.parse(raw.toString());assert.equal(raw.toString(),canonicalJson(q));assert.deepEqual(Object.keys(q).sort(),['caller_deadline','schema_version']);
   const response={...packet(q.caller_deadline)};if(mode==='foreign')response.workspace_id=other;if(mode==='excessive')response.valid_until=new Date(Date.parse(q.caller_deadline)+1000).toISOString();if(mode==='expired')response.valid_until=new Date(Date.now()-1).toISOString();
   let body=canonicalJson(response);if(mode==='unknown')body=canonicalJson({...response,result_available:true});if(mode==='duplicate')body=body.replace('"schema_version":1','"schema_version":1,"schema_version":1');
   const wire=Buffer.concat([Buffer.from(`HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${Buffer.byteLength(body)}\r\nConnection: close\r\n\r\n`),Buffer.from(body)]);
   if(mode==='extra'){socket.write(wire);setTimeout(()=>socket.end('extra'),15);}else if(mode==='noEOF')socket.write(wire);else socket.end(wire);
  });
 });await new Promise<void>(resolve=>server.listen(0,'::1',resolve));const address=server.address();assert.ok(address&&typeof address!=='string');const now=Date.now();
 profile={schema_version:1,purpose:'meeting-supervision-service-binding-v1',principal_id:id,workspace_id:id,runtime_hash:hash,registry_hash:hash,backend_origin:'https://localhost.localdomain:'+address.port,server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),server_ca_file:file('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:file('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('client.crt'))).raw),client_uri:'spiffe://oracle/invented-supervisor',client_key_file:file('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer',valid_from:new Date(now-1000).toISOString(),expires_at:new Date(now+12000).toISOString(),original_horizon:new Date(now+20000).toISOString(),supervision_path:'/v1/replacement/meetings/supervision',meeting_id:id,supervision_config_sha256:hash,supervision_peer_profile_sha256:hash,process_purpose:'meeting-scheduler-process-v1',scope_sha256:hash,process_runtime_sha256:hash,process_config_sha256:hash,capture_until:new Date(now+12000).toISOString(),stop_until:new Date(now+18000).toISOString()};
 writeFileSync(file('binding.json'),canonicalJson(profile),{mode:0o600});process.env.ORACLE2_MEETING_SCHEDULER_SUPERVISION_BINDING_FILE=file('binding.json');process.env.ORACLE2_MEETING_SCHEDULER_SUPERVISION_BINDING_SHA256=pin('binding.json');
});
after(async()=>{for(const socket of sockets)socket.destroy();await new Promise<void>(resolve=>server.close(()=>resolve()));rmSync(dir,{recursive:true,force:true});Object.defineProperty(nodeDns,'lookup',{value:lookup});Object.defineProperty(nodeTls,'connect',{value:connect});syncBuiltinESMExports();delete process.env.ORACLE2_MEETING_SCHEDULER_SUPERVISION_BINDING_FILE;delete process.env.ORACLE2_MEETING_SCHEDULER_SUPERVISION_BINDING_SHA256;});

test('source-fixed supervisor profile cannot borrow employee/provider/other path',()=>{
 assert.equal(validateMeetingSupervisionBinding(profile).purpose,'meeting-supervision-service-binding-v1');
 for(const change of [{auth_user_id:id},{provider_key_file:'/secret'},{supervision_path:'/arbitrary'},{purpose:'meeting-normalization-worker-v1'},{process_runtime_sha256:'bad'}])assert.throws(()=>validateMeetingSupervisionBinding({...profile,...change}));
});
test('actual owned mTLS reads exact queue with unchanged original narrowing deadline once',async()=>{
 const worker=installedMeetingSchedulerSupervisionV1();const end=new Date(Date.now()+1000).toISOString(),original=worker.original_deadline_v1;
 const result=await worker.current_queue_v1(end);assert.equal(result.valid_until,end);assert.equal(result.queue_observation_sha256,hash);assert.equal(result.remote_stop_proven,false);assert.equal(worker.original_deadline_v1,original);
 await assert.rejects(worker.current_queue_v1(end));assert.equal(count,1);
});
test('deadline extension refuses before HTTP bytes',async()=>{const before=count,worker=installedMeetingSchedulerSupervisionV1();await assert.rejects(worker.current_queue_v1(new Date(Date.parse(worker.original_deadline_v1)+1).toISOString()));assert.equal(count,before);});
test('copied loader provenance cannot become installed process profile',()=>{const binding=readInstalledMeetingSchedulerSupervisionBinding();assert.equal(rereadInstalledMeetingSupervisionBinding(binding).profile.process_purpose,'meeting-scheduler-process-v1');assert.throws(()=>rereadInstalledMeetingSupervisionBinding({...binding}));});
for(const value of ['foreign','unknown','duplicate','excessive','expired','extra'])test('actual strict queue transport refuses '+value,async()=>{mode=value;try{await assert.rejects(installedMeetingSchedulerSupervisionV1().current_queue_v1());}finally{mode='valid';}});
test('queue metadata never grants liveness or remote-stop proof',()=>{const p=packet(new Date(Date.now()+1000).toISOString());for(const change of [{remote_stop_proven:true},{observation_only:1},{active:true},{process_purpose:'capture-create'},{version:0}])assert.throws(()=>parseMeetingSupervisionPacketV1(Buffer.from(canonicalJson({...p,...change}))));});
test('complete bytes without actual peer EOF expire inside original process window',async()=>{mode='noEOF';const start=Date.now();await assert.rejects(installedMeetingSchedulerSupervisionV1().current_queue_v1());assert.ok(Date.now()-start<14000);});
