/** Invented identity module snapshots + actual loopback mTLS only.
 * These tests do NOT establish an actual Supabase session or installation. */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { registerHooks } from 'node:module';
import { mkdtempSync, readFileSync, writeFileSync, chmodSync, rmSync, renameSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync,execFile } from 'node:child_process';
import { X509Certificate } from 'node:crypto';
import * as tls from 'node:tls';
import { captureControlWindow, CONTROL_WINDOW_HEADER } from './replacement-control-window';
import { validateEmployeeRecipientIndexV1,canonicalJson, instant, matchesIdentity, parseClosedJson, sha256, validateBinding, type ServerBinding } from './replacement-server-binding';
import { parseControlMetadata, requestReplacementControl, validateControlRequest } from './replacement-protected-client';

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
let dir: string, server: tls.Server, binding: ServerBinding;
const peerSockets=new Set<tls.TLSSocket>();
let mode = 'valid', requests = 0, acceptedClients = 0;
const received: Buffer[] = [];
const metadata = {runId:id,journeyRevision:1,controlState:'processing',populationSha256:h,cancelRequested:false,remoteStopProven:false,resultAvailable:false};
const responseBytes = () => Buffer.from(canonicalJson(metadata));
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
      assert.match(header,/^POST \/v1\/replacement\/control HTTP\/1.1/);
      let bytes = responseBytes();
      if (mode === 'unknown') bytes = Buffer.from(canonicalJson({...metadata,ready:true}));
      if (mode === 'duplicate') bytes = Buffer.from('{"runId":"'+id+'","runId":"'+id+'"}');
      if (mode === 'noncanonical') bytes = Buffer.from(JSON.stringify(metadata));
      if (mode === 'wrong-run') bytes = Buffer.from(canonicalJson({...metadata,runId:employee}));
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
  binding = {
    schema_version:1,purpose:'replacement-web-binding-v1',project_url:fixture.project,auth_issuer:fixture.project+'/auth/v1',auth_user_id:id,employee_id:employee,principal_id:'33333333-3333-4333-8333-333333333333',workspace_id:'44444444-4444-4444-8444-444444444444',runtime_hash:h,registry_hash:h,intake_appointment_sha256:h,peer_profile_sha256:h,web_origin:'https://web.example.test',backend_origin:'https://localhost.localdomain:'+address.port,control_path:'/v1/replacement/control',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('server.crt'))).raw),server_ca_file:file('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:file('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(file('client.crt'))).raw),client_uri:'spiffe://oracle/invented-web',client_key_file:file('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-issuer',reviewer_actor:'independent-reviewer',valid_from:new Date(Date.now()-10000).toISOString(),expires_at:new Date(Date.now()+350000).toISOString(),original_horizon:new Date(Date.now()+350000).toISOString(),
  };
  writeFileSync(file('binding.json'),canonicalJson(binding),{mode:0o600});
  process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE = file('binding.json');
  process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256 = pin('binding.json');
  process.env.NEXT_PUBLIC_SUPABASE_URL = fixture.project;
});
after(async () => { hooks.deregister(); await new Promise<void>(resolve => server.close(() => resolve())); rmSync(dir,{recursive:true,force:true}); delete (globalThis as unknown as Record<string,unknown>).__replacementIdentityFixture; });
const body = (extra: Record<string,unknown> = {}) => Buffer.from(canonicalJson({schema_version:1,operation:'status',run_id:id,caller_deadline:new Date(Date.now()+5000).toISOString(),...extra}));
const request = (bytes = body(), headers: Record<string,string> = {}, signal?: AbortSignal) => new Request('https://web.example.test/api/control',{method:'POST',headers:{origin:'https://web.example.test','content-type':'application/json',[CONTROL_WINDOW_HEADER]:canonicalJson(captureControlWindow()),...headers},body:bytes,signal});
const refused = async (req: Request) => assert.deepEqual(await requestReplacementControl(req),{available:false});

test('strict canonical JSON refuses duplicate, nonfinite, extra bytes, malformed UTF8 and surrogates',() => {
  for (const raw of ['{"x":1,"x":2}','NaN','Infinity','1e999','1.1','{}{}','{"a":"\\ud800"}','{"a":-0}']) assert.throws(() => parseClosedJson(Buffer.from(raw),100));
  assert.throws(() => parseClosedJson(Buffer.from([0xc0,0xaf]),100));
  assert.deepEqual(JSON.parse(canonicalJson(parseClosedJson(Buffer.from('{"中文":"原因"}'),100))),{'中文':'原因'});
});
test('exact seven-field metadata recognizes all eleven states but never available result or proven stop',() => {
  for (const controlState of ['pending','processing','delivered','revision_pending','cancelled','error','awaiting-external-authority','missing-evidence','cancel-requested','failed','UNKNOWN']) assert.equal(parseControlMetadata(Buffer.from(canonicalJson({...metadata,controlState}))).controlState,controlState);
  for (const patch of [{schema_version:1},{remoteStopProven:true},{resultAvailable:true},{cancelRequested:1},{journeyRevision:true},{journeyRevision:0},{populationSha256:'A'.repeat(64)},{runId:'bad'},{controlState:'ready'}]) assert.throws(() => parseControlMetadata(Buffer.from(canonicalJson({...metadata,...patch}))));
});
test('wire exact schema, population, selectors, bounds and Chinese reason survive canonical validation',() => {
  assert.equal(validateControlRequest(body()).operation,'status');
  const reserve = {schema_version:1,operation:'reserve',source_selectors:[{source_id:id,revision:1}],population_sha256:h,idempotency_key:employee,caller_deadline:new Date(Date.now()+5000).toISOString()};
  assert.equal(validateControlRequest(Buffer.from(canonicalJson(reserve))).operation,'reserve');
  assert.equal(validateControlRequest(body({operation:'cancel',expected_revision:1,reason:'中文拒絕原因',idempotency_key:employee})).reason,'中文拒絕原因');
  for (const patch of [{actor:id},{schema_version:true},{run_id:'BAD'},{operation:'query'},{caller_deadline:'2026-02-30T00:00:00Z'}]) assert.throws(() => validateControlRequest(body(patch)));
  for (const patch of [{source_selectors:[{source_id:id,revision:true}]},{source_selectors:[{source_id:id,revision:1},{source_id:id,revision:2}]},{source_selectors:[]},{population_sha256:'bad'}]) assert.throws(() => validateControlRequest(Buffer.from(canonicalJson({...reserve,...patch}))));
  assert.throws(() => validateControlRequest(Buffer.concat([Buffer.from(' '),body()])));
  assert.throws(() => instant('2026-13-01T00:00:00Z'));
});
test('descriptive binding rejects unknowns, foreign authority, unsafe endpoints and invalid windows',() => {
  assert.equal(validateBinding({...binding}).purpose,'replacement-web-binding-v1');
  for (const patch of [{authority:true},{schema_version:true},{auth_issuer:'https://other.test/auth/v1'},{web_origin:'http://web.example.test'},{backend_origin:binding.backend_origin+'/path'},{control_path:'/other'},{server_dns:'wrong.example.test'},{client_uri:'https://wrong.test'},{issuer_actor:binding.reviewer_actor},{client_key_file:binding.client_certificate_file},{expires_at:binding.valid_from},{runtime_hash:'bad'}]) assert.throws(() => validateBinding({...binding,...patch}));
  const snapshot = {configuredProjectUrl:binding.project_url,actualProjectUrl:binding.project_url,verifiedUserId:id,employeeId:employee,disabledAt:null};
  assert.equal(matchesIdentity(binding,snapshot),true);
  for (const patch of [{configuredProjectUrl:'https://foreign.test'},{actualProjectUrl:'https://foreign.test'},{verifiedUserId:employee},{employeeId:id},{disabledAt:new Date()},{disabledAt:undefined}]) assert.equal(matchesIdentity(binding,{...snapshot,...patch}),false);
});
test('actual loopback mTLS validates client URI and exact unchanged request, with injected identity only',async () => {
  mode = 'valid'; const bytes = body(); const result = await requestReplacementControl(request(bytes));
  assert.equal(result.available,true); if (result.available) assert.equal(result.metadata.resultAvailable,false);
  assert.deepEqual(received.at(-1),bytes); assert.ok(acceptedClients > 0); assert.ok(fixture.calls >= 4);
});
test('explicit identical replay preserves exact deadline and bytes, with no automatic retry',async () => {
  mode = 'valid'; const bytes = body(); const count = requests;
  assert.equal((await requestReplacementControl(request(bytes))).available,true);
  assert.equal((await requestReplacementControl(request(bytes))).available,true);
  assert.equal(requests,count+2); assert.deepEqual(received.at(-1),received.at(-2));
});
test('actual leaf DER and hostname mismatch refuse before any HTTP bytes',async () => {
  for (const name of ['alternate','wronghost','untrusted']) {
    server.setSecureContext({key:readFileSync(file(name+'.key')),cert:readFileSync(file(name+'.crt')),ca:readFileSync(file('ca.crt'))});
    const count=requests; await refused(request()); assert.equal(requests,count,name);
  }
  server.setSecureContext({key:readFileSync(file('server.key')),cert:readFileSync(file('server.crt')),ca:readFileSync(file('ca.crt'))});
});
test('independently selected invented profile pin, file modes, URI, key, missing and expiry refuse',() => {
  const script = `import {readInstalledBinding} from ${JSON.stringify(new URL('./replacement-server-binding.ts',import.meta.url).href)};try{readInstalledBinding();process.exitCode=12}catch{process.exitCode=0}`;
  const check = (value: Record<string,unknown>, expected?:string) => {
    const target=file('variant.json'); writeFileSync(target,canonicalJson(value),{mode:0o600});
    execFileSync(process.execPath,[...process.execArgv,'--input-type=module','-e',script],{cwd:process.cwd(),stdio:'pipe',env:{...process.env,ORACLE2_REPLACEMENT_SERVER_BINDING_FILE:target,ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256:expected??sha256(readFileSync(target))}});
  };
  for (const patch of [{client_uri:'spiffe://oracle/foreign'},{client_certificate_der_sha256:'b'.repeat(64)},{client_key_file:file('server.key'),client_key_sha256:pin('server.key')},{server_ca_file:file('missing.crt')},{expires_at:new Date(Date.now()-1000).toISOString()},{valid_from:new Date(Date.now()+60000).toISOString()}]) check({...binding,...patch});
  check({...binding},'b'.repeat(64));
  writeFileSync(file('unsafe.key'),readFileSync(file('client.key')),{mode:0o644}); chmodSync(file('unsafe.key'),0o644); check({...binding,client_key_file:file('unsafe.key')});
});
test('verified identity, employee, actual project, configured project, disabled/error all refuse before HTTP',async () => {
  const count = requests;
  for (const patch of [{user:employee},{employee:id},{disabledAt:new Date()},{project:'https://foreign.test'},{error:true}]) {
    const saved = {...fixture}; Object.assign(fixture,patch); await refused(request()); Object.assign(fixture,saved);
  }
  const saved = process.env.NEXT_PUBLIC_SUPABASE_URL; process.env.NEXT_PUBLIC_SUPABASE_URL='https://foreign.test'; await refused(request()); process.env.NEXT_PUBLIC_SUPABASE_URL=saved;
  assert.equal(requests,count);
});
test('same-origin refusal occurs before body and auth, without forwarded-host selectors',async () => {
  const calls = fixture.calls;
  await refused(request(body(),{origin:'https://foreign.test','x-forwarded-host':'web.example.test'}));
  await refused(new Request('https://foreign.test/api/control',{method:'POST',headers:{origin:binding.web_origin,'content-type':'application/json'},body:body()}));
  assert.equal(fixture.calls,calls);
});
test('caller window strictly narrows original start; expired/excess deadlines never dispatch',async () => {
  const count = requests;
  for (const deadline of [Date.now()-1,Date.now()+31000,instant(binding.original_horizon)+1]) await refused(request(body({caller_deadline:new Date(deadline).toISOString()})));
  fixture.delay = 60; await refused(request(body({caller_deadline:new Date(Date.now()+20).toISOString()}))); fixture.delay=0;
  assert.equal(requests,count);
});
test('malformed canonical response, headers, false stop and uncertain close refuse without retry',async () => {
  for (mode of ['unknown','duplicate','noncanonical','false-stop','duplicate-header','uncertain','extra','wrong-run']) {
    const count = requests; await refused(request()); assert.equal(requests,count+1,mode);
  }
  mode='valid';
});
test('slow response and client abort never prove remote stop or available result',async () => {
  mode='slow'; await refused(request(body({caller_deadline:new Date(Date.now()+50).toISOString()})));
  const controller = new AbortController(); controller.abort(); await refused(request(body(),{},controller.signal)); mode='valid';
});
test('post-transport current identity drift refuses a previously valid reply',async () => {
  mode='slow'; const promise = requestReplacementControl(request()); setTimeout(() => { fixture.disabledAt = new Date(); },40);
  assert.deepEqual(await promise,{available:false}); fixture.disabledAt=null; mode='valid';
});
test('missing selector and changed selector refuse; original immutable file remains selected',async () => {
  const saved=process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE;
  delete process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE; await refused(request());
  process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE=file('other.json'); await refused(request());
  process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE=saved;
});
test('valid complete body with delayed peer EOF remains supported inside original lease',async()=>{
 mode='delayed-end';const before=Date.now(),count=requests;const result=await requestReplacementControl(request(body({caller_deadline:new Date(Date.now()+1000).toISOString()})));assert.equal(result.available,true);assert.equal(requests,count+1);assert.ok(Date.now()-before>=40);mode='valid';
});
test('half-close ownership still refuses delayed extra response bytes double responses and missing peer EOF',async()=>{
 for(mode of ['late-extra','double-response','no-eof','header-overflow']){const count=requests;await refused(request(body({caller_deadline:new Date(Date.now()+350).toISOString()})));assert.equal(requests,count+1,mode);for(const socket of peerSockets)socket.destroy();}mode='valid';
});

// Actual channel lifecycle proof only. Production user identity remains solely
// in the web wrapper above and is independently checked by retained negatives.
test('shared staged channel sends no HTTP before explicit send and close refuses later send',async()=>{
 const {openProtectedChannelV1}=await import('@oracle/shared/protected-service-channel');
 const {readInstalledBinding}=await import('./replacement-server-binding');
 const {performance}=await import('node:perf_hooks');
 const wall=Date.now(),mono=performance.now(),count=requests;
 const window={wall,mono,end:wall+2000,signal:new AbortController().signal,proxyMonoEnd:process.hrtime.bigint()+2000000000n};
 const channel=await openProtectedChannelV1(readInstalledBinding(),window);
 await new Promise(r=>setTimeout(r,20));assert.equal(requests,count);
 channel.close();await assert.rejects(channel.send(body()));assert.equal(requests,count);
});
test('shared verified channel is single use and cannot renew original expiry',async()=>{
 const {openProtectedChannelV1}=await import('@oracle/shared/protected-service-channel');
 const {readInstalledBinding}=await import('./replacement-server-binding');
 const {performance}=await import('node:perf_hooks');
 let wall=Date.now(),mono=performance.now();mode='valid';
 let window={wall,mono,end:wall+2000,signal:new AbortController().signal,proxyMonoEnd:process.hrtime.bigint()+2000000000n};
 const channel=await openProtectedChannelV1(readInstalledBinding(),window);const count=requests;
 assert.equal((await channel.send(body()) as {runId:string}).runId,id);assert.equal(requests,count+1);
 await assert.rejects(channel.send(body()));channel.close();assert.equal(requests,count+1);
 wall=Date.now();mono=performance.now();window={wall,mono,end:wall+2000,signal:new AbortController().signal,proxyMonoEnd:process.hrtime.bigint()+2000000000n};
 const expired=await openProtectedChannelV1(readInstalledBinding(),window);window.end=Date.now()-1;
 await assert.rejects(expired.send(body()));expired.close();assert.equal(requests,count+1);
});

test('mid-transport identical file replacement refuses reply and later entry (last: installation poisoned)',async () => {
  mode='slow'; const count=requests; const pending=requestReplacementControl(request());
  await new Promise<void>((resolve,reject) => { const started=Date.now(); const tick=()=>{if(requests>count)return resolve();if(Date.now()-started>1000)return reject(new Error('invented request did not reach peer'));setTimeout(tick,2)};tick(); });
  renameSync(file('binding.json'),file('old-binding.json')); writeFileSync(file('binding.json'),canonicalJson(binding),{mode:0o600});
  assert.deepEqual(await pending,{available:false}); assert.equal(requests,count+1);
  await refused(request()); assert.equal(requests,count+1);
});


test('finite independently installed recipient index is closed and never a grant',()=>{
 const index={schema_version:1,purpose:'replacement-employee-recipient-index-v1',issuer_actor:id,reviewer_actor:employee,valid_from:binding.valid_from,expires_at:binding.expires_at,original_horizon:binding.original_horizon,
  recipients:[{project_url:binding.project_url,auth_issuer:binding.auth_issuer,auth_user_id:id,employee_id:employee,bindings:{control:{path:file('recipient.json'),sha256:h}}}]};
 assert.equal(validateEmployeeRecipientIndexV1(JSON.parse(canonicalJson(index))).recipients.length,1);
 const variants=[{...index,schema_version:true},{...index,issuer_actor:employee},{...index,grant:true},{...index,recipients:[]},{...index,recipients:[...index.recipients,...index.recipients]},
  {...index,recipients:[{...index.recipients[0],actor:id}]},{...index,recipients:[{...index.recipients[0],auth_issuer:'https://foreign.test/auth/v1'}]},
  {...index,recipients:[{...index.recipients[0],bindings:{worker:index.recipients[0]!.bindings.control}}]},
  {...index,recipients:[{...index.recipients[0],bindings:{control:{path:'relative',sha256:h}}}]},
  {...index,recipients:[{...index.recipients[0],bindings:{control:{path:file('recipient.json'),sha256:'A'.repeat(64)}}}]},
  {...index,recipients:[{...index.recipients[0],bindings:{control:index.recipients[0]!.bindings.control,answer:index.recipients[0]!.bindings.control}}]}];
 for(const value of variants)assert.throws(()=>validateEmployeeRecipientIndexV1(JSON.parse(canonicalJson(value))));
});
test('two recipient profiles remain isolated through actual TLS and invented identity adapter',async()=>{
 const environment={...process.env};delete environment.NODE_TEST_CONTEXT;
 const result=await new Promise<{stdout:string;stderr:string}>((resolve,reject)=>execFile('pnpm',['--filter','@oracle/web','exec','tsx','tests/oracle2/employee-recipient-wire-proof.ts'],{cwd:new URL('../',import.meta.url),env:environment,timeout:15000},(error,stdout,stderr)=>error?reject(new Error(stdout+'\n'+stderr)):resolve({stdout,stderr})));
 assert.match(result.stdout,/INVENTED_RECIPIENT_WIRE_PROOF_PASS/);
});
