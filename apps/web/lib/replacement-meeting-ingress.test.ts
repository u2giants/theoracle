/** Invented identity module snapshots + actual loopback mTLS only.
 * These tests do NOT establish an actual Supabase session or installation. */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { registerHooks } from 'node:module';
import { mkdtempSync, readFileSync, writeFileSync, chmodSync, rmSync, renameSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { X509Certificate,createHmac } from 'node:crypto';
import * as tls from 'node:tls';
import { captureControlWindow, CONTROL_WINDOW_HEADER } from './replacement-control-window';
import { canonicalJson, sha256, validateMeetingBinding, type MeetingIngressBinding } from './replacement-server-binding';
import { requestReplacementMeetingIngress } from './replacement-protected-client';

const id = '11111111-1111-4111-8111-111111111111', employee = '22222222-2222-4222-8222-222222222222';
const h = 'a'.repeat(64);
const fixture = {user:id,employee,disabledAt:null as unknown,project:'https://auth.example.test',error:false,delay:0,calls:0};
(globalThis as unknown as Record<string,unknown>).__replacementIdentityFixture = fixture;
// Test-process loader only. No production injection parameter or fallback exists.
const hooks = registerHooks({
  resolve(specifier,context,next) {
    if (context.parentURL?.includes('replacement-protected-client.ts') && specifier === './supabase/server') return {url:'oracle-test:auth',shortCircuit:true};
    if (context.parentURL?.includes('replacement-protected-client.ts') && specifier === './auth-guard') return {url:'oracle-test:employee',shortCircuit:true};
    return next(specifier,context);
  },
  load(url,context,next) {
    if (url === 'oracle-test:auth') return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__replacementIdentityFixture;return {supabaseUrl:f.project,auth:{async getUser(){f.calls++;if(f.delay)await new Promise(r=>setTimeout(r,f.delay));return {data:{user:{id:f.user}},error:f.error?new Error('invented'):null}}}}}`};
    if (url === 'oracle-test:employee') return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(id){const f=globalThis.__replacementIdentityFixture;return {id:f.employee,disabledAt:f.disabledAt}}`};
    return next(url,context);
  },
});
let dir: string, server: tls.Server, binding: MeetingIngressBinding;
const peerSockets=new Set<tls.TLSSocket>();
let mode = 'valid', requests = 0, acceptedClients = 0;
const received: Buffer[] = [];
const metadata={schema_version:1,meeting_id:id,version:1,state:'invited',event_id:employee,ingress_id:employee,pending_count:0,valid_until:new Date().toISOString(),qualification:false,remote_stop_proven:false,observation_only:true};
const responseBytes=()=>Buffer.from(canonicalJson({...metadata,valid_until:JSON.parse(received.at(-1)!.toString()).caller_deadline}));
const openssl = (...args: string[]) => execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
const file = (name: string) => join(dir,name);
const pin = (name: string) => sha256(readFileSync(file(name)));

before(async () => {
  dir = mkdtempSync(join(tmpdir(),'oracle-web-control-')); chmodSync(dir,0o700);
  openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented Oracle Test CA');
  for (const name of ['server','client','alternate','wronghost']) {
    openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented '+name);
    writeFileSync(file(name+'.ext'), name !== 'client' ? 'subjectAltName=DNS:'+(name === 'wronghost' ? 'wrong.example.test' : 'localhost.localdomain')+'\nextendedKeyUsage=serverAuth\n' : 'subjectAltName=URI:spiffe://oracle/invented-web\nextendedKeyUsage=clientAuth\n');
    openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');
  }
  openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','untrusted.key','-out','untrusted.crt','-days','1','-subj','/CN=Invented Untrusted','-addext','subjectAltName=DNS:localhost.localdomain');
  for (const name of ['ca.crt','server.crt','server.key','client.crt','client.key','alternate.crt','alternate.key','wronghost.crt','wronghost.key']) chmodSync(file(name),0o600);
  server = tls.createServer({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),ca:readFileSync(file('ca.crt')),requestCert:true,rejectUnauthorized:true,allowHalfOpen:true}, socket => {
    peerSockets.add(socket);socket.on('close',()=>peerSockets.delete(socket));
    socket.on('error',() => undefined);
    if (!socket.authorized || !socket.getPeerCertificate().subjectaltname?.includes('URI:spiffe://oracle/invented-web')) { socket.destroy(); return; }
    acceptedClients++; let data = Buffer.alloc(0); let answered = false;
    socket.on('data',(chunk:Buffer) => {
      data = Buffer.concat([data,chunk]); const split = data.indexOf('\r\n\r\n'); if (split < 0 || answered) return;
      const header = data.subarray(0,split).toString('ascii'); const length = /content-length: ([0-9]+)/i.exec(header)?.[1];
      if (!length || data.length < split + 4 + Number(length)) return;
      answered = true; requests++; received.push(data.subarray(split + 4));
      assert.match(header,/^POST \/v1\/replacement\/meetings\/ingress HTTP\/1.1/);
      let bytes = responseBytes();
      if(mode==='unknown')bytes=Buffer.from(canonicalJson({...metadata,ready:true}));
      if (mode === 'duplicate') bytes = Buffer.from('{"runId":"'+id+'","runId":"'+id+'"}');
      if (mode === 'noncanonical') bytes = Buffer.from(JSON.stringify(metadata));
      if(mode==='wrong-run')bytes=Buffer.from(canonicalJson({...metadata,meeting_id:employee}));
      if (mode === 'false-stop') bytes = Buffer.from(canonicalJson({...metadata,remoteStopProven:true}));
      const duplicate = mode === 'duplicate-header' ? 'Content-Type: application/json\r\n' : '';
      const reply = Buffer.concat([Buffer.from('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'+duplicate+'Content-Length: '+bytes.length+'\r\nConnection: close\r\n\r\n'),bytes]);
      if (mode === 'uncertain') { socket.write(reply.subarray(0,reply.length - 5)); socket.destroy(); }
      else if (mode === 'extra') socket.end(Buffer.concat([reply,Buffer.from('extra')]));
      else if (mode === 'delayed-end') {socket.write(reply);setTimeout(()=>socket.end(),60);}
      else if (mode === 'header-overflow') socket.end(Buffer.concat([Buffer.from('HTTP/1.1 200 OK\r\nX-Oversized: '+ 'a'.repeat(17000)+'\r\n\r\n'),bytes]));
      else if (mode === 'no-eof') socket.write(reply);
      else if (mode === 'late-extra') {socket.write(reply);setTimeout(()=>socket.end('extra'),40);}
      else if (mode === 'double-response') {socket.write(reply);setTimeout(()=>socket.end(reply),40);}
      else if (mode === 'slow') setTimeout(() => socket.end(reply),100);
      else socket.end(reply);
    });
  });
  server.on('tlsClientError',() => undefined);
  await new Promise<void>(resolve => server.listen(0,'::1',resolve));
  const address = server.address(); assert.ok(address && typeof address !== 'string');
  writeFileSync(file('verifier.secret'),'whsec_'+Buffer.alloc(32,7).toString('base64'),{mode:0o600});
  binding = {
    schema_version:1,purpose:'replacement-meeting-ingress-web-binding-v1',principal_id:'33333333-3333-4333-8333-333333333333',workspace_id:'44444444-4444-4444-8444-444444444444',runtime_hash:h,registry_hash:h,meeting_id:id,meeting_config_sha256:h,meeting_peer_profile_sha256:h,backend_origin:'https://localhost.localdomain:'+address.port,ingress_path:'/v1/replacement/meetings/ingress',provider_account:'independent-recall-account',verifier_secret_file:file('verifier.secret'),verifier_secret_sha256:pin('verifier.secret'),server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),server_ca_file:file('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:file('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('client.crt'))).raw),client_uri:'spiffe://oracle/invented-web',client_key_file:file('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-issuer',reviewer_actor:'independent-reviewer',valid_from:new Date(Date.now()-10000).toISOString(),expires_at:new Date(Date.now()+350000).toISOString(),original_horizon:new Date(Date.now()+350000).toISOString(),
  };
  writeFileSync(file('binding.json'),canonicalJson(binding),{mode:0o600});
  process.env.ORACLE2_MEETING_INGRESS_BINDING_FILE = file('binding.json');
  process.env.ORACLE2_MEETING_INGRESS_BINDING_SHA256 = pin('binding.json');
  process.env.NEXT_PUBLIC_SUPABASE_URL = fixture.project;
});
after(async () => { hooks.deregister(); await new Promise<void>(resolve => server.close(() => resolve())); rmSync(dir,{recursive:true,force:true}); delete (globalThis as unknown as Record<string,unknown>).__replacementIdentityFixture; });
const raw=(extra:Record<string,unknown>={})=>Buffer.from(JSON.stringify({event:'transcript.data',data:{bot:{id:'actual-provider-bot'},data:{words:[{text:'原话'}]}},...extra}));
const request=(bytes=raw(),headers:Record<string,string>={},signal?:AbortSignal)=>{
 const timestamp=String(Math.floor(Date.now()/1000)),message='invented-provider-message';
 const signature=createHmac('sha256',Buffer.alloc(32,7)).update(message+'.'+timestamp+'.').update(bytes).digest('base64');
 return new Request('https://web.example.test/api/teams/live/recall',{method:'POST',headers:{'content-type':'application/json','webhook-id':message,'webhook-timestamp':timestamp,'webhook-signature':'v1,'+signature,[CONTROL_WINDOW_HEADER]:canonicalJson(captureControlWindow()),...headers},body:bytes,signal});
};
const refused=async(req:Request)=>{const response=await requestReplacementMeetingIngress(req);assert.equal(response.status,503);assert.deepEqual(await response.json(),{error:'Replacement control unavailable'});assert.equal(response.headers.get('cache-control'),'private, no-store, max-age=0');};
test('installed provider purpose has no employee project cookie or source grant',()=>{
 assert.equal(validateMeetingBinding(binding,true).provider_account,'independent-recall-account');
 for(const patch of [{auth_user_id:id},{employee_id:employee},{project_url:fixture.project},{web_origin:'https://web.example.test'},{ingress_path:'/arbitrary'},{role:'admin'}])assert.throws(()=>validateMeetingBinding({...binding,...patch},true));
});
test('actual mTLS preserves exact signed bytes and durable opaque receipt with zero employee auth',async()=>{
 const bytes=raw(),response=await requestReplacementMeetingIngress(request(bytes));assert.equal(response.status,202);const result=await response.json();assert.equal(result.ingress_id,employee);assert.equal(result.qualification,false);assert.equal(result.remote_stop_proven,false);assert.equal(Object.keys(result).length,11);assert.equal(fixture.calls,0);
 const wire=JSON.parse(received.at(-1)!.toString());assert.deepEqual(Buffer.from(wire.raw_base64,'base64'),bytes);assert.equal(wire.verifier_secret_sha256,binding.verifier_secret_sha256);assert.equal(wire.operation,'ingress');assert.match(wire.caller_deadline,/\.\d{6}Z$/);assert.equal(Object.keys(wire).length,8);
});
test('bad signatures timestamp families and canonical provider identity deny before outbound',async()=>{
 const count=requests;
 for(const headers of ([{'webhook-signature':'v1,'+Buffer.alloc(32).toString('base64')},{'webhook-timestamp':String(Math.floor(Date.now()/1000)-301)},{'svix-id':'wrong-family'},{'webhook-id':'non ascii é'}] as Record<string,string>[]))await refused(request(raw(),headers));
 assert.equal(requests,count);assert.equal(fixture.calls,0);
});
test('strict bounded raw UTF8 and word populations reject before outbound',async()=>{
 const count=requests;
 for(const bytes of [raw({data:{bot:{id:'actual-provider-bot'},data:{words:Array.from({length:4097},()=>({text:'x'}))}}}),Buffer.alloc(1024*1024+1,65),Buffer.from([0xc0,0xaf]),raw({event:'arbitrary'})])await refused(request(bytes));
 assert.equal(requests,count);assert.equal(fixture.calls,0);
});
test('missing protected verifier or binding never falls back to employee or legacy handler',async()=>{
 const saved=process.env.ORACLE2_MEETING_INGRESS_BINDING_FILE,count=requests;delete process.env.ORACLE2_MEETING_INGRESS_BINDING_FILE;await refused(request());process.env.ORACLE2_MEETING_INGRESS_BINDING_FILE=saved;assert.equal(requests,count);assert.equal(fixture.calls,0);
});
test('uncertain peer does not acknowledge or retry and changed verifier pin refuses',async()=>{
 const count=requests;mode='uncertain';await refused(request());assert.equal(requests,count+1);mode='valid';writeFileSync(file('verifier.secret'),'whsec_'+Buffer.alloc(32,8).toString('base64'));await refused(request());assert.equal(requests,count+1);assert.equal(fixture.calls,0);
});
