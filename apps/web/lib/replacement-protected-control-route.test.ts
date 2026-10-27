/** Real loopback HTTPS invokes the actual exported route and real protected
 * client/mTLS peer. Existing auth imports are replaced by test-process hooks;
 * this is NOT actual Supabase-session or deployed Next-server acceptance. */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { registerHooks } from 'node:module';
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { X509Certificate } from 'node:crypto';
import { createServer } from 'node:http';
import * as https from 'node:https';
import * as tls from 'node:tls';
import { NextRequest } from 'next/server';
import { controlWindowRemaining, CONTROL_WINDOW_HEADER, CONTROL_BYPASS_HEADERS } from './replacement-control-window';
import { Readable } from 'node:stream';
import { canonicalJson, sha256, type ServerBinding } from './replacement-server-binding';
import * as route from '../app/api/consultant/replacement/v1/protected/control/route';

const id='11111111-1111-4111-8111-111111111111', employee='22222222-2222-4222-8222-222222222222', hash='a'.repeat(64);
const identity={user:id,employee,disabledAt:null as unknown,project:'https://invented-auth.example.test',error:false,calls:0,proxyCalls:0,lateCookie:false,refreshFailure:false,authFetchUrl:'',refreshDelay:0,lateDenied:false,multipleCookies:false,uniqueCalls:0,disableAfterFirst:false,uniqueMissing:false,proxyProject:''};
(globalThis as unknown as Record<string,unknown>).__routeAuthFixture=identity;
const hooks=registerHooks({
  resolve(specifier,context,next){
    if(context.parentURL?.endsWith('/proxy.ts')&&specifier==='@supabase/ssr')return {url:'oracle-route-test:refresh',shortCircuit:true};
    if(context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'oracle-route-test:auth',shortCircuit:true};
    if((context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')||(context.parentURL?.endsWith('/proxy.ts')&&specifier==='./lib/auth-guard'))return {url:'oracle-route-test:employee',shortCircuit:true};
    return next(specifier,context);
  },
  load(url,context,next){
    if(url==='oracle-route-test:refresh')return {format:'module',shortCircuit:true,source:`export function createServerClient(url,key,options){const f=globalThis.__routeAuthFixture;return {supabaseUrl:f.proxyProject||url,auth:{async getUser(){f.proxyCalls++;if(f.refreshDelay)await new Promise(r=>setTimeout(r,f.refreshDelay));if(f.authFetchUrl)await options.global.fetch(f.authFetchUrl);if(f.lateCookie){setTimeout(()=>{try{options.cookies.setAll([{name:'late',value:'never'}])}catch{f.lateDenied=true}},30);throw new Error('private refresh failure')}if(f.refreshFailure)throw new Error('private refresh failure');if(f.multipleCookies)options.cookies.setAll([{name:'first-refresh',value:'retained-first',options:{httpOnly:true,secure:true,sameSite:'strict',path:'/'}}]);options.cookies.setAll([{name:'invented-refresh',value:'retained',options:{httpOnly:true,secure:true,sameSite:'lax',path:'/'}}]);return {data:{user:{id:f.user}},error:f.error?new Error('private refresh error'):null}}}}}`};
    if(url==='oracle-route-test:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__routeAuthFixture;return {supabaseUrl:f.project,auth:{async getUser(){f.calls++;return {data:{user:{id:f.user}},error:f.error?new Error('private identity detail never returned'):null}}}}}`};
    if(url==='oracle-route-test:employee')return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(){const f=globalThis.__routeAuthFixture;return {id:f.employee,disabledAt:f.disabledAt}};export async function getUniqueEmployeeForAuthUserV1(){const f=globalThis.__routeAuthFixture;f.uniqueCalls++;if(f.uniqueMissing)return null;return {id:f.employee,disabledAt:f.disableAfterFirst&&f.uniqueCalls>1?true:f.disabledAt}}`};
    return next(url,context);
  },
});
let dir:string, backend:tls.Server, web:https.Server, binding:ServerBinding;
let proxyModule:typeof import('../proxy');
let peerRequests=0, peerMode='valid', lastBodyReads=0;
const delivered={runId:id,journeyRevision:1,controlState:'delivered',populationSha256:hash,cancelRequested:false,remoteStopProven:false,resultAvailable:false};
const seenBodies:Buffer[]=[];
const f=(name:string)=>join(dir,name);
const read=(name:string)=>readFileSync(f(name));
const pin=(name:string)=>sha256(read(name));
const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:dir,stdio:'pipe'});
const listen=(server:tls.Server|https.Server)=>new Promise<void>(resolve=>server.listen(0,'::1',resolve));
const port=(server:tls.Server|https.Server)=>{const address=server.address();assert.ok(address&&typeof address!=='string');return address.port;};
before(async()=>{
  proxyModule=await import('../proxy');
  dir=mkdtempSync(join(tmpdir(),'oracle-protected-route-'));chmodSync(dir,0o700);
  openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented Route Test CA');
  for(const name of ['server','client','alternate']){
    openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented '+name);
    writeFileSync(f(name+'.ext'),name==='client'?'subjectAltName=URI:spiffe://oracle/invented-web\nextendedKeyUsage=clientAuth\n':'subjectAltName=DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\n');
    openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');
  }
  for(const name of ['ca.crt','client.crt','client.key'])chmodSync(f(name),0o600);
  backend=tls.createServer({key:read('server.key'),cert:read('server.crt'),ca:read('ca.crt'),requestCert:true,rejectUnauthorized:true},socket=>{
    socket.on('error',()=>undefined);let data=Buffer.alloc(0),answered=false;
    socket.on('data',(chunk:Buffer)=>{
      data=Buffer.concat([data,chunk]);const split=data.indexOf('\r\n\r\n');if(split<0||answered)return;
      const header=data.subarray(0,split).toString('ascii'),length=/content-length: ([0-9]+)/i.exec(header)?.[1];
      if(!length||data.length<split+4+Number(length))return;
      answered=true;peerRequests++;seenBodies.push(data.subarray(split+4));
      assert.equal(socket.authorized,true);assert.match(socket.getPeerCertificate().subjectaltname??'',/URI:spiffe:\/\/oracle\/invented-web/);
      assert.match(header,/^POST \/v1\/replacement\/control HTTP\/1.1/);
      assert.doesNotMatch(header,/authorization:|cookie:|x-actor:|x-role:/i);
      if(peerMode==='uncertain'){socket.destroy();return;}
      const bytes=Buffer.from(canonicalJson(peerMode==='result'?{...delivered,resultAvailable:true}:delivered));
      socket.end(Buffer.concat([Buffer.from('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+bytes.length+'\r\nConnection: close\r\n\r\n'),bytes]));
    });
  });backend.on('tlsClientError',()=>undefined);await listen(backend);
  web=https.createServer({key:read('server.key'),cert:read('server.crt')},async(req,res)=>{
    // Real NextRequest/NextResponse proxy + route exports mounted over loopback.
    // Header overrides/cookie merge are applied by this explicit test harness;
    // deployed Next routing and real Supabase-session proof remain separate.
    const headers=new Headers();for(const [name,value]of Object.entries(req.headers)){if(value!==undefined)headers.set(name,Array.isArray(value)?value.join(', '):value);}
    const incoming=new NextRequest(binding.web_origin+(req.url??'/'),{method:req.method,headers,...(!['GET','HEAD'].includes(req.method??'')?{body:Readable.toWeb(req) as ReadableStream<Uint8Array>,duplex:'half'}:{})} as NonNullable<ConstructorParameters<typeof NextRequest>[1]> & {duplex:'half'});
    const stream=incoming.body;lastBodyReads=0;Object.defineProperty(incoming,'body',{get(){lastBodyReads++;return stream;}});
    const forwarded=await proxyModule.proxy(incoming);
    let result:Response;
    if(forwarded.headers.get('x-middleware-next')==='1'){
      const nextHeaders=new Headers();for(const key of (forwarded.headers.get('x-middleware-override-headers')??'').split(',')){if(key)nextHeaders.set(key,forwarded.headers.get('x-middleware-request-'+key)??'');}
      const downstream=new Request(incoming.url,{method:'POST',headers:nextHeaders,body:stream,duplex:'half'} as RequestInit & {duplex:'half'});
      const downstreamBody=downstream.body;Object.defineProperty(downstream,'body',{get(){lastBodyReads++;return downstreamBody;}});
      result=await route.POST(downstream);
    }else result=forwarded;
    const cookies=forwarded.headers.getSetCookie();if(cookies.length)res.setHeader('Set-Cookie',cookies);
    res.writeHead(result.status,Object.fromEntries(result.headers));
    res.end(Buffer.from(await result.arrayBuffer()));
  });await listen(web);
  binding={schema_version:1,purpose:'replacement-web-binding-v1',project_url:identity.project,auth_issuer:identity.project+'/auth/v1',auth_user_id:id,employee_id:employee,principal_id:'33333333-3333-4333-8333-333333333333',workspace_id:'44444444-4444-4444-8444-444444444444',runtime_hash:hash,registry_hash:hash,intake_appointment_sha256:hash,peer_profile_sha256:hash,web_origin:'https://localhost.localdomain:'+port(web),backend_origin:'https://localhost.localdomain:'+port(backend),control_path:'/v1/replacement/control',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(read('server.crt')).raw),server_ca_file:f('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:f('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(read('client.crt')).raw),client_uri:'spiffe://oracle/invented-web',client_key_file:f('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-route-issuer',reviewer_actor:'independent-route-reviewer',valid_from:new Date(Date.now()-10000).toISOString(),expires_at:new Date(Date.now()+180000).toISOString(),original_horizon:new Date(Date.now()+180000).toISOString()};
  writeFileSync(f('binding.json'),canonicalJson(binding),{mode:0o600});
  process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE=f('binding.json');process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256=pin('binding.json');process.env.NEXT_PUBLIC_SUPABASE_URL=identity.project;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-anon-key';
});
after(async()=>{
  hooks.deregister();await Promise.all([new Promise<void>(resolve=>web.close(()=>resolve())),new Promise<void>(resolve=>backend.close(()=>resolve()))]);
  rmSync(dir,{recursive:true,force:true});delete (globalThis as unknown as Record<string,unknown>).__routeAuthFixture;
});
const requestBody=(extra:Record<string,unknown>={})=>Buffer.from(canonicalJson({schema_version:1,operation:'status',run_id:id,caller_deadline:new Date(Date.now()+5000).toISOString(),...extra}));
interface HttpResult{status:number;headers:Readonly<Record<string,string|string[]|undefined>>;body:Buffer;}
const invoke=(bytes=requestBody(),headers:Record<string,string>={},method='POST')=>new Promise<HttpResult>((resolve,reject)=>{
  const req=https.request(binding.web_origin+'/api/consultant/replacement/v1/protected/control',{method,ca:read('ca.crt'),agent:false,headers:{origin:binding.web_origin,'Content-Type':'application/json','Content-Length':String(bytes.length),...headers}},res=>{
    const chunks:Buffer[]=[];res.on('data',(chunk:Buffer)=>chunks.push(chunk));res.on('end',()=>resolve({status:res.statusCode??0,headers:res.headers,body:Buffer.concat(chunks)}));res.on('error',reject);
  });req.on('error',reject);req.end(bytes);
});
const unavailable=(result:HttpResult)=>{
  assert.equal(result.status,503);assert.deepEqual(JSON.parse(result.body.toString()),{error:'Replacement control unavailable'});
  assert.equal(result.headers['cache-control'],'private, no-store, max-age=0');assert.equal(result.headers['x-content-type-options'],'nosniff');assert.equal(result.headers.pragma,'no-cache');assert.equal(result.headers.location,undefined);
  assert.doesNotMatch(result.body.toString(),/private identity|binding|certificate|\.key|password|supabase|stack|ready|resultAvailable/i);
};

test('route explicitly targets dynamic Node, exports POST only and does not expose fixture methods',()=>{
  assert.equal(route.runtime,'nodejs');assert.equal(route.dynamic,'force-dynamic');assert.deepEqual(Object.keys(route).sort(),['POST','dynamic','runtime']);
});
test('actual HTTPS invokes production route/helper and mTLS, returning exactly seven private metadata fields',async()=>{
  const bytes=requestBody();const response=await invoke(bytes,{'X-Actor':'caller-ignored','X-Role':'admin','Cookie':'fixture=never-forwarded','Authorization':'Bearer invented-never-forwarded'});
  assert.equal(response.status,200);assert.deepEqual(JSON.parse(response.body.toString()),delivered);assert.equal(Object.keys(JSON.parse(response.body.toString())).length,7);
  assert.equal(response.headers['cache-control'],'private, no-store, max-age=0');assert.equal(response.headers['x-content-type-options'],'nosniff');assert.equal(response.headers.pragma,'no-cache');assert.equal(response.headers.location,undefined);assert.match(String(response.headers['set-cookie']),/invented-refresh=retained; Path=\/; Secure; HttpOnly; SameSite=lax/i);assert.equal(response.headers[CONTROL_WINDOW_HEADER],undefined);assert.equal(response.headers['x-middleware-request-'+CONTROL_WINDOW_HEADER],undefined);
  assert.deepEqual(seenBodies.at(-1),bytes);assert.ok(lastBodyReads>0);assert.ok(identity.calls>=4);
});
test('same-origin refusal precedes body and auth with zero outbound peer requests',async()=>{
  const count=peerRequests,calls=identity.calls;unavailable(await invoke(requestBody(),{Origin:'https://foreign.example.test'}));assert.equal(lastBodyReads,0);assert.equal(identity.calls,calls);assert.equal(peerRequests,count);
});
test('wrong verified user, employee, actual project, disabled identity and errors refuse before body/outbound',async()=>{
  for(const patch of [{user:employee},{employee:id},{project:'https://foreign.example.test'},{disabledAt:new Date()},{error:true}]){
    const saved={...identity},count=peerRequests;Object.assign(identity,patch);unavailable(await invoke());assert.equal(lastBodyReads,0);assert.equal(peerRequests,count);Object.assign(identity,saved);
  }
});
test('missing binding defaults unavailable before body; cannot fall back to fixture state',async()=>{
  const saved=process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE,count=peerRequests;delete process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE;
  unavailable(await invoke());assert.equal(lastBodyReads,0);assert.equal(peerRequests,count);process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE=saved;
});
test('unknown authority fields and arbitrary URL selectors fail closed without outbound',async()=>{
  const count=peerRequests;for(const patch of [{actor:id},{role:'admin'},{url:binding.backend_origin},{headers:{Authorization:'invented'}}])unavailable(await invoke(requestBody(patch)));assert.equal(peerRequests,count);
});
test('unsupported methods have no production export, body read, identity call or peer effect',async()=>{
  const count=peerRequests,calls=identity.calls;for(const method of ['GET','PUT','DELETE']){const result=await invoke(Buffer.alloc(0),{},method);assert.equal(result.status,405);assert.equal(result.headers.allow,'POST');assert.equal(result.headers['cache-control'],'private, no-store, max-age=0');assert.equal(lastBodyReads,0);}assert.equal(peerRequests,count);assert.equal(identity.calls,calls);
});
test('actual peer certificate mismatch returns constant private unavailable with no HTTP request',async()=>{
  const count=peerRequests;backend.setSecureContext({key:read('alternate.key'),cert:read('alternate.crt'),ca:read('ca.crt')});unavailable(await invoke());assert.equal(peerRequests,count);backend.setSecureContext({key:read('server.key'),cert:read('server.crt'),ca:read('ca.crt')});
});
test('uncertain reply or forged available result never escapes metadata boundary',async()=>{
  for(peerMode of ['uncertain','result'])unavailable(await invoke());peerMode='valid';
});
test('explicit identical replay preserves exact deadline/body and produces no hidden retry',async()=>{
  const bytes=requestBody(),count=peerRequests;assert.equal((await invoke(bytes)).status,200);assert.equal((await invoke(bytes)).status,200);assert.equal(peerRequests,count+2);assert.deepEqual(seenBodies.at(-1),seenBodies.at(-2));
});

test('proxy overwrites forged inbound window with actual capture and never returns it to browser',async()=>{
  const response=await invoke(requestBody(),{[CONTROL_WINDOW_HEADER]:'caller-forged-renewal'});assert.equal(response.status,200);assert.equal(response.headers[CONTROL_WINDOW_HEADER],undefined);
});
test('observed exact Next bypass headers refuse before auth, body or backend',async()=>{
  for(const header of CONTROL_BYPASS_HEADERS){const count=peerRequests,calls=identity.proxyCalls;unavailable(await invoke(requestBody(),{[header]:'forged'}));assert.equal(lastBodyReads,0);assert.equal(peerRequests,count);assert.equal(identity.proxyCalls,calls);}
});
test('refresh failure cannot leak private exception or publish late cookie mutation',async()=>{
  identity.lateCookie=true;const response=await invoke();unavailable(response);assert.equal(response.headers['set-cookie'],undefined);await new Promise(resolve=>setTimeout(resolve,50));assert.equal(response.headers['set-cookie'],undefined);assert.equal(identity.lateDenied,true);identity.lateCookie=false;
});
test('direct handler without original proxy capture refuses',async()=>{
  const response=await route.POST(new Request(binding.web_origin+'/api/consultant/replacement/v1/protected/control',{method:'POST',headers:{origin:binding.web_origin,'content-type':'application/json'},body:requestBody()}));assert.equal(response.status,503);
});

test('ordinary noncontrol requests retain real refresh and Set-Cookie capability',async()=>{
  const calls=identity.proxyCalls;const incoming=new NextRequest(binding.web_origin+'/channels',{headers:{cookie:'existing=retained'}});
  const result=await proxyModule.proxy(incoming);assert.equal(result.headers.get('x-middleware-next'),'1');assert.equal(identity.proxyCalls,calls+1);assert.match(result.headers.getSetCookie().join(';'),/invented-refresh=retained/);assert.match(incoming.headers.get('cookie')??'',/existing=retained/);assert.match(incoming.headers.get('cookie')??'',/invented-refresh=retained/);assert.equal(result.headers.get('x-middleware-request-'+CONTROL_WINDOW_HEADER),null);
});
test('ordinary static exclusions retain zero authentication work',async()=>{
  const calls=identity.proxyCalls;const result=await proxyModule.proxy(new NextRequest(binding.web_origin+'/_next/static/chunks/invented.js'));assert.equal(result.headers.get('x-middleware-next'),'1');assert.equal(identity.proxyCalls,calls);
});
test('native-only first boundary remains denial before any company authentication',async()=>{
  const calls=identity.proxyCalls;process.env.ORACLE2_NATIVE_BROWSER_ONLY='1';try{const result=await proxyModule.proxy(new NextRequest(binding.web_origin+'/api/consultant/replacement/v1/protected/control',{method:'POST',headers:{'x-middleware-subrequest':'forged'}}));assert.equal(result.status,404);assert.equal(identity.proxyCalls,calls);}finally{delete process.env.ORACLE2_NATIVE_BROWSER_ONLY;}
});
test('real scoped fetch is aborted on request cancellation without cookie or backend effect',async()=>{
  let observed!:()=>void;const seen=new Promise<void>(resolve=>{observed=resolve;});let closed=false;
  const auth=createServer(req=>{req.socket.once('close',()=>{closed=true;});observed();});await new Promise<void>(resolve=>auth.listen(0,'127.0.0.1',resolve));const address=auth.address();assert.ok(address&&typeof address!=='string');
  const controller=new AbortController();identity.authFetchUrl='http://127.0.0.1:'+address.port+'/invented-auth';const count=peerRequests;
  try{const pending=proxyModule.proxy(new NextRequest(binding.web_origin+'/api/consultant/replacement/v1/protected/control',{method:'POST',headers:{origin:binding.web_origin},signal:controller.signal}));await Promise.race([seen,new Promise<never>((_,reject)=>setTimeout(()=>reject(new Error('invented auth did not start')),1000))]);controller.abort();const response=await pending;assert.equal(response.status,503);assert.equal(response.headers.get('set-cookie'),null);await new Promise(resolve=>setTimeout(resolve,30));assert.equal(closed,true);assert.equal(peerRequests,count);}finally{identity.authFetchUrl='';auth.closeAllConnections();await new Promise<void>(resolve=>auth.close(()=>resolve()));}
});
test('proxy refresh consumes original fixed deadline; helper cannot renew it after auth',async()=>{
  identity.refreshDelay=600;const count=peerRequests;try{unavailable(await invoke(requestBody({caller_deadline:new Date(Date.now()+30500).toISOString()})));assert.equal(peerRequests,count);}finally{identity.refreshDelay=0;}
});

test('multiple successful refresh callbacks preserve all real cookie values and options',async()=>{
  identity.multipleCookies=true;try{const response=await invoke();assert.equal(response.status,200);const cookies=String(response.headers['set-cookie']);assert.match(cookies,/first-refresh=retained-first/);assert.match(cookies,/SameSite=strict/i);assert.match(cookies,/invented-refresh=retained/);}finally{identity.multipleCookies=false;}
});

/** Actual proxy code and protected file/index owners; auth and employee imports
 * are explicit invented hooks, not a real Supabase/SQL session proof. */
test('index-only proxy selects A/B after verified identity and refuses missing or changed current bindings',async()=>{
 const originalUser=identity.user,originalEmployee=identity.employee;
 const singletonFile=process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE,singletonSha=process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256;
 const secondUser='33333333-3333-4333-8333-333333333333',secondEmployee='44444444-4444-4444-8444-444444444444';
 const recipients=[];const indexedEnd=new Date(Date.now()+3000).toISOString();
 for(const [index,user,emp]of [[0,id,employee],[1,secondUser,secondEmployee]] as const){
  const name='indexed-'+index;openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented indexed recipient');
  writeFileSync(f(name+'.ext'),'subjectAltName=URI:spiffe://oracle/invented-web-'+index+'\nextendedKeyUsage=clientAuth\n');
  openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');
  chmodSync(f(name+'.key'),0o600);chmodSync(f(name+'.crt'),0o600);
  const selected={...binding,expires_at:indexedEnd,original_horizon:indexedEnd,auth_user_id:user,employee_id:emp,client_uri:'spiffe://oracle/invented-web-'+index,client_key_file:f(name+'.key'),client_key_sha256:pin(name+'.key'),client_certificate_file:f(name+'.crt'),client_certificate_sha256:pin(name+'.crt'),client_certificate_der_sha256:sha256(new X509Certificate(read(name+'.crt')).raw)};
  writeFileSync(f(name+'.json'),canonicalJson(selected),{mode:0o600});
  const adviceName=name+'-advice';openssl('req','-newkey','rsa:2048','-nodes','-keyout',adviceName+'.key','-out',adviceName+'.csr','-subj','/CN=Invented indexed advice');
  writeFileSync(f(adviceName+'.ext'),'subjectAltName=URI:spiffe://oracle/invented-advice-'+index+'\nextendedKeyUsage=clientAuth\n');openssl('x509','-req','-in',adviceName+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',adviceName+'.crt','-days','1','-extfile',adviceName+'.ext');chmodSync(f(adviceName+'.key'),0o600);chmodSync(f(adviceName+'.crt'),0o600);
  const advice:Record<string,unknown>={...selected,purpose:'replacement-recommendation-actions-web-binding-v1',recommendation_path:'/v1/replacement/recommendation-actions',model_id:id,recommendation_config_sha256:hash,recommendation_peer_profile_sha256:hash,client_uri:'spiffe://oracle/invented-advice-'+index,client_key_file:f(adviceName+'.key'),client_key_sha256:pin(adviceName+'.key'),client_certificate_file:f(adviceName+'.crt'),client_certificate_sha256:pin(adviceName+'.crt'),client_certificate_der_sha256:sha256(new X509Certificate(read(adviceName+'.crt')).raw)};for(const key of ['intake_appointment_sha256','peer_profile_sha256','control_path'])Reflect.deleteProperty(advice,key);writeFileSync(f(adviceName+'.json'),canonicalJson(advice),{mode:0o600});
  recipients.push({project_url:binding.project_url,auth_issuer:binding.auth_issuer,auth_user_id:user,employee_id:emp,bindings:{control:{path:f(name+'.json'),sha256:pin(name+'.json')},recommendation:{path:f(adviceName+'.json'),sha256:pin(adviceName+'.json')}}});
 }
 const index={schema_version:1,purpose:'replacement-employee-recipient-index-v1',issuer_actor:'55555555-5555-4555-8555-555555555555',reviewer_actor:'66666666-6666-4666-8666-666666666666',valid_from:binding.valid_from,expires_at:new Date(Date.now()+60000).toISOString(),original_horizon:new Date(Date.now()+60000).toISOString(),recipients};
 writeFileSync(f('index.json'),canonicalJson(index),{mode:0o600});
 process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE=f('index.json');process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256=pin('index.json');
 delete process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE;delete process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256;
 const incoming=(headers:Record<string,string>={},method='POST',signal?:AbortSignal,kind='control')=>new NextRequest(binding.web_origin+'/api/consultant/replacement/v1/protected/'+(kind==='recommendation'?'recommendation-actions':'control'),{method,headers:{origin:binding.web_origin,...headers},signal});
 const count=peerRequests;
 try{
  for(const [user,emp]of [[id,employee],[secondUser,secondEmployee]])for(const kind of ['control','recommendation']){identity.user=user!;identity.employee=emp!;const request=incoming({},'POST',undefined,kind);const response=await proxyModule.proxy(request);assert.equal(request.bodyUsed,false);assert.equal(response.headers.get('x-middleware-next'),'1');assert.match(response.headers.getSetCookie().join(';'),/invented-refresh=retained/);assert.ok(response.headers.get('x-middleware-request-'+CONTROL_WINDOW_HEADER));const original=JSON.parse(response.headers.get('x-middleware-request-'+CONTROL_WINDOW_HEADER)!);assert.ok(original.wall_end-original.wall_start>=29000,'forwarded window must be the original 30s, not narrowed');assert.ok(original.wall_end-original.wall_start<=31000);assert.ok(BigInt(original.mono_end)>=process.hrtime.bigint()+29000000000n);assert.ok(BigInt(original.mono_end)<=process.hrtime.bigint()+31000000000n);assert.throws(()=>controlWindowRemaining(original,{wall:original.wall_start-1000,mono:BigInt(original.mono_end)+1n,domain:original.clock_domain}));}
  identity.user=id;identity.employee=employee;
  const preauthRefusal=async(request:NextRequest)=>{const auth=identity.proxyCalls,sql=identity.uniqueCalls;assert.equal((await proxyModule.proxy(request)).status,503);assert.equal(identity.proxyCalls,auth);assert.equal(identity.uniqueCalls,sql);assert.equal(request.bodyUsed,false);};
  await preauthRefusal(incoming({origin:'https://foreign.example.test'}));await preauthRefusal(incoming({origin:'https://foreign.example.test'},'POST',undefined,'recommendation'));
  await preauthRefusal(new NextRequest('https://foreign.example.test/api/consultant/replacement/v1/protected/control',{method:'POST',headers:{origin:binding.web_origin}}));
  const missingOrigin=incoming();missingOrigin.headers.delete('origin');await preauthRefusal(missingOrigin);
  const project=process.env.NEXT_PUBLIC_SUPABASE_URL;process.env.NEXT_PUBLIC_SUPABASE_URL='https://foreign.example.test';await preauthRefusal(incoming());process.env.NEXT_PUBLIC_SUPABASE_URL=project;
  const actualNow=Date.now;Date.now=()=>actualNow()+4000;try{await preauthRefusal(incoming());await preauthRefusal(incoming({},'POST',undefined,'recommendation'));}finally{Date.now=actualNow;}
  const beforeAuth=identity.proxyCalls;assert.equal((await proxyModule.proxy(incoming({},'GET'))).status,405);assert.equal((await proxyModule.proxy(incoming({'x-middleware-subrequest':'forged'}))).status,503);assert.equal(identity.proxyCalls,beforeAuth);
  identity.disabledAt=new Date();assert.equal((await proxyModule.proxy(incoming())).status,503);identity.disabledAt=null;
  identity.uniqueCalls=0;identity.disableAfterFirst=true;assert.equal((await proxyModule.proxy(incoming())).status,503);identity.disableAfterFirst=false;
  identity.error=true;assert.equal((await proxyModule.proxy(incoming())).status,503);identity.error=false;
  identity.uniqueMissing=true;assert.equal((await proxyModule.proxy(incoming())).status,503);identity.uniqueMissing=false;
  identity.proxyProject='https://foreign.example.test';assert.equal((await proxyModule.proxy(incoming())).status,503);identity.proxyProject='';
  identity.employee=secondEmployee;assert.equal((await proxyModule.proxy(incoming())).status,503);identity.employee=employee;
  identity.user='77777777-7777-4777-8777-777777777777';assert.equal((await proxyModule.proxy(incoming())).status,503);identity.user=id;
  assert.equal((await proxyModule.proxy(incoming({origin:'https://foreign.example.test'}))).status,503);
  const saved=process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256;delete process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256;await preauthRefusal(incoming());process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256=saved;
  identity.refreshFailure=true;const refused=await proxyModule.proxy(incoming());assert.equal(refused.status,503);assert.equal(refused.headers.get('set-cookie'),null);identity.refreshFailure=false;
  const controller=new AbortController();controller.abort();assert.equal((await proxyModule.proxy(incoming({},'POST',controller.signal))).status,503);
  writeFileSync(f('indexed-1-advice.json'),'{}');await preauthRefusal(incoming({},'POST',undefined,'recommendation'));
  writeFileSync(f('indexed-1.json'),canonicalJson({...binding,auth_user_id:secondUser,employee_id:secondEmployee}));identity.user=secondUser;identity.employee=secondEmployee;await preauthRefusal(incoming());identity.user=id;identity.employee=employee;await preauthRefusal(incoming());
  writeFileSync(f('index.json'),canonicalJson({...index,extra:'never authority'}));await preauthRefusal(incoming());
  assert.equal(peerRequests,count);
 }finally{
  identity.user=originalUser;identity.employee=originalEmployee;identity.disabledAt=null;identity.refreshFailure=false;identity.error=false;identity.disableAfterFirst=false;identity.uniqueMissing=false;identity.proxyProject='';
  delete process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE;delete process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256;
  process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_FILE=singletonFile;process.env.ORACLE2_REPLACEMENT_SERVER_BINDING_SHA256=singletonSha;
 }
});
