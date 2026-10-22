/** Actual owned mTLS only; invented backend state, not SQL/employee/installation. */
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {mkdtempSync,chmodSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {execFileSync} from 'node:child_process';
import {X509Certificate} from 'node:crypto';import * as tls from 'node:tls';
import nodeDns from 'node:dns';import nodeTls from 'node:tls';import {syncBuiltinESMExports} from 'node:module';
import {canonicalJson,sha256,validateMeetingNormalizationBinding,readInstalledMeetingNormalizationBinding,rereadInstalledMeetingNormalizationBinding,type MeetingNormalizationBinding} from '@oracle/shared/protected-server-binding';
import {installedMeetingNormalizationWorkerV1} from '@oracle/shared/protected-meeting-worker';
import {parseMeetingNormalizationPacketV1,parseMeetingNormalizationWakeV1,type MeetingNormalizationPacketV1} from '@oracle/shared/protected-worker-contract';
const id='11111111-1111-4111-8111-111111111111',other='22222222-2222-4222-8222-222222222222',hash='a'.repeat(64);
let dir:string,server:tls.Server,profile:MeetingNormalizationBinding,count=0,mode='valid';const sockets=new Set<tls.TLSSocket>();
const lookup=nodeDns.lookup,connect=nodeTls.connect;
Object.defineProperty(nodeDns,'lookup',{configurable:true,writable:true,value:(...args:unknown[])=>{if(!['localhost.localdomain','::1','127.0.0.1'].includes(String(args[0])))throw new Error('fixture external DNS refused');return Reflect.apply(lookup,nodeDns,args);}});
Object.defineProperty(nodeTls,'connect',{configurable:true,writable:true,value:(...args:unknown[])=>{const v=args[0];if(!v||typeof v!=='object'||Reflect.get(v,'host')!=='localhost.localdomain'||Reflect.get(v,'servername')!=='localhost.localdomain')throw new Error('fixture external TLS refused');return Reflect.apply(connect,nodeTls,args);}});syncBuiltinESMExports();
const file=(name:string)=>join(dir,name),pin=(name:string)=>sha256(readFileSync(file(name)));
function packet(deadline:string):MeetingNormalizationPacketV1{return {schema_version:1,principal_id:id,workspace_id:id,meeting_id:id,ingress_event_id:other,state:'awaiting_independently_installed_exact_reading_review',valid_until:deadline,source_binding:{source_id:other,revision:1,original_sha256:hash,byte_count:16},qualification:false,source_read_permission:false,observation_only:true};}
before(async()=>{
 dir=mkdtempSync(join(tmpdir(),'oracle-normalization-wire-'));chmodSync(dir,0o700);
 const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
 openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented normalization CA');
 for(const name of ['server','client']){openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented '+name);writeFileSync(file(name+'.ext'),name==='server'?'subjectAltName=DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\n':'subjectAltName=URI:spiffe://oracle/invented-normalizer\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');}
 for(const name of ['ca.crt','client.crt','client.key','server.crt','server.key'])chmodSync(file(name),0o600);
 server=tls.createServer({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),ca:readFileSync(file('ca.crt')),requestCert:true,rejectUnauthorized:true,allowHalfOpen:true},socket=>{
  sockets.add(socket);socket.on('close',()=>sockets.delete(socket));socket.on('error',()=>undefined);let bytes=Buffer.alloc(0),done=false;
  socket.on('data',(part:Buffer)=>{bytes=Buffer.concat([bytes,part]);const split=bytes.indexOf('\r\n\r\n');if(done||split<0)return;const length=Number(/content-length: (\d+)/i.exec(bytes.subarray(0,split).toString())?.[1]);if(bytes.length<split+4+length)return;done=true;count++;
   assert.equal(socket.authorized,true);assert.match(socket.getPeerCertificate().subjectaltname!,/spiffe:\/\/oracle\/invented-normalizer/);
   const header=bytes.subarray(0,split).toString();assert.match(header,/^POST \/v1\/replacement\/meetings\/normalize HTTP\/1.1/);assert.doesNotMatch(header,/authorization:|cookie:|actor:/i);
   const raw=bytes.subarray(split+4);const q=JSON.parse(raw.toString());assert.equal(raw.toString(),canonicalJson(q));assert.deepEqual(Object.keys(q).sort(),['caller_deadline','ingress_event_id','schema_version']);assert.equal(q.ingress_event_id,other);
   const response={...packet(q.caller_deadline)};if(mode==='foreign')response.workspace_id=other;if(mode==='UNKNOWN'){response.state='UNKNOWN';response.source_binding=null;}if(mode==='excessive')response.valid_until=new Date(Date.parse(q.caller_deadline)+1000).toISOString();if(mode==='expired')response.valid_until=new Date(Date.now()-1).toISOString();
   let body=canonicalJson(response);if(mode==='unknown')body=canonicalJson({...response,result_available:true});if(mode==='duplicate')body=body.replace('"schema_version":1','"schema_version":1,"schema_version":1');
   const wire=Buffer.concat([Buffer.from(`HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${Buffer.byteLength(body)}\r\nConnection: close\r\n\r\n`),Buffer.from(body)]);
   if(mode==='extra'){socket.write(wire);setTimeout(()=>socket.end('extra'),15);}else if(mode==='noEOF')socket.write(wire);else socket.end(wire);
  });
 });await new Promise<void>(resolve=>server.listen(0,'::1',resolve));const address=server.address();assert.ok(address&&typeof address!=='string');const now=Date.now();
 profile={schema_version:1,purpose:'meeting-normalization-worker-v1',principal_id:id,workspace_id:id,runtime_hash:hash,registry_hash:hash,backend_origin:'https://localhost.localdomain:'+address.port,server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),server_ca_file:file('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:file('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('client.crt'))).raw),client_uri:'spiffe://oracle/invented-normalizer',client_key_file:file('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-installer',reviewer_actor:'independent-reviewer',valid_from:new Date(now-1000).toISOString(),expires_at:new Date(now+12000).toISOString(),original_horizon:new Date(now+20000).toISOString(),original_processing_horizon:new Date(now+12000).toISOString(),normalization_path:'/v1/replacement/meetings/normalize',meeting_id:id,normalization_config_sha256:hash,normalization_peer_profile_sha256:hash,normalization_admission_sha256:hash};
 writeFileSync(file('binding.json'),canonicalJson(profile),{mode:0o600});process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_FILE=file('binding.json');process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_SHA256=pin('binding.json');
});
after(async()=>{for(const socket of sockets)socket.destroy();await new Promise<void>(resolve=>server.close(()=>resolve()));rmSync(dir,{recursive:true,force:true});Object.defineProperty(nodeDns,'lookup',{value:lookup});Object.defineProperty(nodeTls,'connect',{value:connect});syncBuiltinESMExports();delete process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_FILE;delete process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_SHA256;});
test('closed normalization profile has no employee, provider, arbitrary-path or new authority selector',()=>{
 assert.equal(validateMeetingNormalizationBinding(profile).purpose,'meeting-normalization-worker-v1');for(const change of [{auth_user_id:id},{provider_key_file:'/secret'},{normalization_path:'/arbitrary'},{purpose:'replacement-meeting-worker-binding-v1'},{normalization_config_sha256:'bad'}])assert.throws(()=>validateMeetingNormalizationBinding({...profile,...change}));
});
test('wake has only a canonical opaque ingress identity and never evaluates accessors',()=>{
 assert.equal(parseMeetingNormalizationWakeV1({ingress_event_id:other}).ingress_event_id,other);for(const value of [{},{ingress_event_id:other,actor:id},Object.create({ingress_event_id:other}),Object.defineProperty({ingress_event_id:other},'secret',{value:1}),{ingress_event_id:other,[Symbol('selector')]:1}])assert.throws(()=>parseMeetingNormalizationWakeV1(value));let called=false;assert.throws(()=>parseMeetingNormalizationWakeV1({get ingress_event_id(){called=true;return other;}}));assert.equal(called,false);
});
test('actual fixed mTLS returns only pending opaque source and cannot redispatch same instance',async()=>{
 const worker=installedMeetingNormalizationWorkerV1(),deadline=worker.original_deadline_v1;const result=await worker.normalize_v1(other);assert.equal(result.qualification,false);assert.equal(result.source_read_permission,false);assert.equal(result.source_binding?.source_id,other);assert.equal(worker.original_deadline_v1,deadline);await assert.rejects(worker.normalize_v1(other));assert.equal(count,1);
});
test('actual source executor invokes same installed client without turning missing installation into success',async()=>{
 const {runInstalledMeetingNormalizationV1}=await import('../../workers/src/lib/meeting-normalization');
 const result=await runInstalledMeetingNormalizationV1({ingress_event_id:other});assert.equal(result.outcome,'response-observed');assert.equal(result.receipt?.source_binding?.source_id,other);assert.equal(result.qualification,false);
 const before=count,saved=process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_FILE;delete process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_FILE;
 try{const denied=await runInstalledMeetingNormalizationV1({ingress_event_id:other});assert.equal(denied.outcome,'UNKNOWN');assert.equal(denied.receipt,null);assert.equal(count,before);}finally{process.env.ORACLE2_MEETING_NORMALIZATION_BINDING_FILE=saved;}
});
test('genuine loader provenance refuses a copied binding',()=>{const binding=readInstalledMeetingNormalizationBinding();assert.equal(rereadInstalledMeetingNormalizationBinding(binding).profile.meeting_id,id);assert.throws(()=>rereadInstalledMeetingNormalizationBinding({...binding}));});
for(const value of ['foreign','unknown','duplicate','excessive','expired','extra'])test('same strict transport refuses '+value,async()=>{mode=value;try{await assert.rejects(installedMeetingNormalizationWorkerV1().normalize_v1(other));}finally{mode='valid';}});
test('UNKNOWN never invents source or executable authority',async()=>{mode='UNKNOWN';try{const result=await installedMeetingNormalizationWorkerV1().normalize_v1(other);assert.equal(result.state,'UNKNOWN');assert.equal(result.source_binding,null);}finally{mode='valid';}});
test('closed response refuses boolean coercion, extra capabilities and false source state',()=>{const p=packet(new Date(Date.now()+1000).toISOString());for(const change of [{qualification:0},{source_read_permission:true},{state:'qualified'},{source_binding:null},{actor:id}])assert.throws(()=>parseMeetingNormalizationPacketV1(Buffer.from(canonicalJson({...p,...change}))));});
test('actual complete HTTP bytes without peer EOF expire inside original installed window',async()=>{mode='noEOF';const start=Date.now();await assert.rejects(installedMeetingNormalizationWorkerV1().normalize_v1(other));assert.ok(Date.now()-start<14000);});
