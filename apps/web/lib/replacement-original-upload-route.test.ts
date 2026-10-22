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
import { CONTROL_WINDOW_HEADER, CONTROL_BYPASS_HEADERS } from './replacement-control-window';
import { Readable } from 'node:stream';
import { canonicalJson, sha256, type UploadBinding, validateUploadBinding } from './replacement-server-binding';
import { validateUploadRequest, parseUploadResponse } from './replacement-protected-client';
import * as route from '../app/api/consultant/replacement/v1/protected/upload/route';

const id='11111111-1111-4111-8111-111111111111', employee='22222222-2222-4222-8222-222222222222', hash='a'.repeat(64);
const identity={user:id,employee,disabledAt:null as unknown,project:'https://invented-auth.example.test',error:false,calls:0,proxyCalls:0,lateCookie:false,refreshFailure:false,authFetchUrl:'',refreshDelay:0,lateDenied:false,multipleCookies:false,delay:0,delayAt:0};
(globalThis as unknown as Record<string,unknown>).__routeAuthFixture=identity;
const hooks=registerHooks({
  resolve(specifier,context,next){
    if(context.parentURL?.endsWith('/proxy.ts')&&specifier==='@supabase/ssr')return {url:'oracle-route-test:refresh',shortCircuit:true};
    if(context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'oracle-route-test:auth',shortCircuit:true};
    if(context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'oracle-route-test:employee',shortCircuit:true};
    return next(specifier,context);
  },
  load(url,context,next){
    if(url==='oracle-route-test:refresh')return {format:'module',shortCircuit:true,source:`export function createServerClient(url,key,options){const f=globalThis.__routeAuthFixture;return {supabaseUrl:url,auth:{async getUser(){f.proxyCalls++;if(f.refreshDelay)await new Promise(r=>setTimeout(r,f.refreshDelay));if(f.authFetchUrl)await options.global.fetch(f.authFetchUrl);if(f.lateCookie){setTimeout(()=>{try{options.cookies.setAll([{name:'late',value:'never'}])}catch{f.lateDenied=true}},30);throw new Error('private refresh failure')}if(f.refreshFailure)throw new Error('private refresh failure');if(f.multipleCookies)options.cookies.setAll([{name:'first-refresh',value:'retained-first',options:{httpOnly:true,secure:true,sameSite:'strict',path:'/'}}]);options.cookies.setAll([{name:'invented-refresh',value:'retained',options:{httpOnly:true,secure:true,sameSite:'lax',path:'/'}}]);return {data:{user:{id:f.user}},error:f.error?new Error('private refresh error'):null}}}}}`};
    if(url==='oracle-route-test:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__routeAuthFixture;return {supabaseUrl:f.project,auth:{async getUser(){f.calls++;if(f.delay&&f.calls===f.delayAt)await new Promise(r=>setTimeout(r,f.delay));return {data:{user:{id:f.user}},error:f.error?new Error('private identity detail never returned'):null}}}}}`};
    if(url==='oracle-route-test:employee')return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(){const f=globalThis.__routeAuthFixture;return {id:f.employee,disabledAt:f.disabledAt}}`};
    return next(url,context);
  },
});
let dir:string, backend:tls.Server, web:https.Server, binding:UploadBinding;
let proxyModule:typeof import('../proxy');
let peerRequests=0, peerMode='valid', lastBodyReads=0;
const pdf=Buffer.from('%PDF-1.7\nInvented original only\n%%EOF');


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
      assert.match(header,/^POST \/v1\/replacement\/upload\/chunks HTTP\/1.1/);
      assert.doesNotMatch(header,/authorization:|cookie:|x-actor:|x-role:/i);
      if(peerMode==='uncertain'){socket.destroy();return;}
      const request=JSON.parse(data.subarray(split+4).toString());
      const value={schema_version:1,state:'reserved',reservation_id:id,source_id:employee,revision:1,begin_sha256:sha256(data.subarray(split+4)),received_bytes:0,next_chunk_index:0,valid_until:request.caller_deadline,qualification:false,remote_stop_proven:false,observation_only:true,source_snapshot:null};
      if(peerMode==='qualified')value.qualification=true;
      const bytes=Buffer.from(canonicalJson(value));
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
    try{res.end(Buffer.from(await result.arrayBuffer()));}catch{res.destroy();}
  });await listen(web);
  binding={schema_version:1,purpose:'replacement-upload-web-binding-v1',project_url:identity.project,auth_issuer:identity.project+'/auth/v1',auth_user_id:id,employee_id:employee,principal_id:'33333333-3333-4333-8333-333333333333',workspace_id:'44444444-4444-4444-8444-444444444444',runtime_hash:hash,registry_hash:hash,intake_config_sha256:hash,intake_appointment_sha256:hash,upload_peer_profile_sha256:hash,upload_spool_initialization_sha256:hash,storage_profile_hash:hash,web_origin:'https://localhost.localdomain:'+port(web),backend_origin:'https://localhost.localdomain:'+port(backend),upload_path:'/v1/replacement/upload/chunks',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(read('server.crt')).raw),server_ca_file:f('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:f('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(read('client.crt')).raw),client_uri:'spiffe://oracle/invented-web',client_key_file:f('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-route-issuer',reviewer_actor:'independent-route-reviewer',valid_from:new Date(Date.now()-10000).toISOString(),expires_at:new Date(Date.now()+180000).toISOString(),original_horizon:new Date(Date.now()+180000).toISOString()};
  writeFileSync(f('binding.json'),canonicalJson(binding),{mode:0o600});
  process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_FILE=f('binding.json');process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_SHA256=pin('binding.json');process.env.NEXT_PUBLIC_SUPABASE_URL=identity.project;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-anon-key';
});
after(async()=>{
  hooks.deregister();await Promise.all([new Promise<void>(resolve=>web.close(()=>resolve())),new Promise<void>(resolve=>backend.close(()=>resolve()))]);
  rmSync(dir,{recursive:true,force:true});delete (globalThis as unknown as Record<string,unknown>).__routeAuthFixture;
});
const requestBody=(extra:Record<string,unknown>={})=>Buffer.from(canonicalJson({schema_version:1,operation:'begin',source_id:null,expected_head:0,idempotency_key:id,filename:'invented.pdf',original_sha256:sha256(pdf),byte_count:pdf.length,caller_deadline:new Date(Date.now()+5000).toISOString().replace(/([0-9]{3})Z$/,'$1000Z'),...extra}));
interface HttpResult{status:number;headers:Readonly<Record<string,string|string[]|undefined>>;body:Buffer;}
const invoke=(bytes=requestBody(),headers:Record<string,string>={},method='POST')=>new Promise<HttpResult>((resolve,reject)=>{
  const req=https.request(binding.web_origin+'/api/consultant/replacement/v1/protected/upload',{method,ca:read('ca.crt'),agent:false,headers:{origin:binding.web_origin,'Content-Type':'application/json','Content-Length':String(bytes.length),...headers}},res=>{
    const chunks:Buffer[]=[];res.on('data',(chunk:Buffer)=>chunks.push(chunk));res.on('end',()=>resolve({status:res.statusCode??0,headers:res.headers,body:Buffer.concat(chunks)}));res.on('error',reject);
  });req.on('error',reject);req.end(bytes);
});
const unavailable=(result:HttpResult)=>{
  assert.equal(result.status,503);assert.deepEqual(JSON.parse(result.body.toString()),{error:'Replacement control unavailable'});
  assert.equal(result.headers['cache-control'],'private, no-store, max-age=0');assert.equal(result.headers['x-content-type-options'],'nosniff');assert.equal(result.headers.pragma,'no-cache');assert.equal(result.headers.location,undefined);
  assert.doesNotMatch(result.body.toString(),/private identity|binding|certificate|\.key|password|supabase|stack|ready|resultAvailable/i);
};



test('actual POST route and independent mTLS accept closed begin without source qualification',async()=>{
 const bytes=requestBody(),r=await invoke(bytes);assert.equal(r.status,200);const value=parseUploadResponse(r.body);assert.equal(value.qualification,false);assert.equal(value.source_snapshot,null);assert.equal(value.begin_sha256,sha256(bytes));assert.deepEqual(seenBodies.at(-1),bytes);assert.equal(route.runtime,'nodejs');assert.deepEqual(Object.keys(route).sort(),['POST','dynamic','runtime']);assert.match(String(r.headers['set-cookie']),/invented-refresh=retained/);
});
test('auth issuer project employee origin and missing upload purpose refuse before body peer',async()=>{
 for(const patch of [{user:employee},{employee:id},{disabledAt:new Date()},{error:true},{project:'https://foreign.example.test'}]){const saved={...identity},n=peerRequests;Object.assign(identity,patch);try{unavailable(await invoke());assert.equal(lastBodyReads,0);assert.equal(peerRequests,n);}finally{Object.assign(identity,saved);}}
 const n=peerRequests;unavailable(await invoke(requestBody(),{origin:'https://foreign.example.test'}));assert.equal(peerRequests,n);
 const saved=process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_FILE;delete process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_FILE;try{unavailable(await invoke());assert.equal(peerRequests,n);}finally{process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_FILE=saved;}
});
test('identity URL grants unknown selectors and oversized requests never dispatch',async()=>{
 const n=peerRequests;for(const patch of [{actor:id},{role:'admin'},{url:binding.backend_origin},{byte_count:26*1024*1024},{schema_version:true},{caller_deadline:new Date(Date.now()+31000).toISOString().replace(/([0-9]{3})Z$/,'$1000Z')}])unavailable(await invoke(requestBody(patch)));
 unavailable(await invoke(Buffer.alloc(2850001,32)));assert.equal(peerRequests,n);
});
test('closed wire chunk canonical base64 hash offsets and metadata bounds are exact',()=>{
 const base={schema_version:1,operation:'chunk',reservation_id:id,source_id:employee,revision:1,begin_sha256:hash,caller_deadline:new Date(Date.now()+5000).toISOString().replace(/([0-9]{3})Z$/,'$1000Z'),chunk_index:0,offset:0,chunk_sha256:sha256(pdf),data_base64:pdf.toString('base64')};
 assert.doesNotThrow(()=>validateUploadRequest(Buffer.from(canonicalJson(base))));
 for(const patch of [{offset:1},{chunk_index:true},{data_base64:base.data_base64+'='},{chunk_sha256:hash},{remote_stop_proven:true},{revision:0}])assert.throws(()=>validateUploadRequest(Buffer.from(canonicalJson({...base,...patch}))));
});
test('peer attempted qualification and wrong certificate never escape',async()=>{
 peerMode='qualified';try{unavailable(await invoke());}finally{peerMode='valid';}
 const n=peerRequests;backend.setSecureContext({key:read('alternate.key'),cert:read('alternate.crt'),ca:read('ca.crt')});try{unavailable(await invoke());assert.equal(peerRequests,n);}finally{backend.setSecureContext({key:read('server.key'),cert:read('server.crt'),ca:read('ca.crt')});}
});
test('method bypass native-first and direct foreign clock refusal retain no effects',async()=>{
 const n=peerRequests,calls=identity.proxyCalls;for(const method of ['GET','PUT','DELETE'])assert.equal((await invoke(Buffer.alloc(0),{},method)).status,405);
 for(const h of CONTROL_BYPASS_HEADERS)unavailable(await invoke(requestBody(),{[h]:'forged'}));
 process.env.ORACLE2_NATIVE_BROWSER_ONLY='1';try{assert.equal((await invoke(requestBody(),{'x-middleware-subrequest':'forged'})).status,404);}finally{delete process.env.ORACLE2_NATIVE_BROWSER_ONLY;}
 assert.equal(peerRequests,n);assert.equal(identity.proxyCalls,calls);
 const r=await route.POST(new Request(binding.web_origin+'/api/consultant/replacement/v1/protected/upload',{method:'POST',headers:{origin:binding.web_origin,'content-type':'application/json'},body:requestBody()}));assert.equal(r.status,503);
});
test('upload profile refuses viewer/control path inheritance and missing independent spool pins',()=>{
 for(const patch of [{purpose:'replacement-web-binding-v1'},{upload_path:'/v1/replacement/upload'},{upload_spool_initialization_sha256:''},{control_path:'/v1/replacement/control'}])assert.throws(()=>validateUploadBinding({...binding,...patch}));
});
