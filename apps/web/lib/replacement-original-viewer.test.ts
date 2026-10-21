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
import { canonicalJson, sha256, type ViewerBinding, validateViewerBinding, MAX_ORIGINAL_BYTES } from './replacement-server-binding';
import { validateOriginalViewRequest } from './replacement-protected-client';
import * as route from '../app/api/consultant/replacement/v1/protected/original/route';

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
let dir:string, backend:tls.Server, web:https.Server, binding:ViewerBinding;
let proxyModule:typeof import('../proxy');
let peerRequests=0, peerMode='valid', lastBodyReads=0;
const pdf=Buffer.from('%PDF-1.7\nInvented original only\n%%EOF');
const large=Buffer.alloc(MAX_ORIGINAL_BYTES,32);pdf.copy(large);
let reply=pdf, leaseDelay=0, replyMedia='application/pdf';
const textOriginals=[Buffer.from('<script>original only</script>\n员工：先检查，再交接。\n'),Buffer.from([255]),Buffer.from('valid\0hidden')];
const textIds=['77777777-7777-4777-8777-777777777777','88888888-8888-4888-8888-888888888888','99999999-9999-4999-8999-999999999999'];
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
      assert.match(header,/^POST \/v1\/replacement\/original HTTP\/1.1/);
      assert.doesNotMatch(header,/authorization:|cookie:|x-actor:|x-role:/i);
      if(peerMode==='uncertain'){socket.destroy();return;}
      const deadline=JSON.parse(data.subarray(split+4).toString()).caller_deadline;
      let lease=deadline;
      if(peerMode==='expired')lease=new Date(Date.now()-1000).toISOString().replace(/([0-9]{3})Z$/,'$1000Z');
      if(peerMode==='excessive')lease=new Date(Date.now()+60000).toISOString().replace(/([0-9]{3})Z$/,'$1000Z');
      if(peerMode==='short')lease=new Date(Date.now()+100).toISOString().replace(/([0-9]{3})Z$/,'$1000Z');
      if(peerMode==='malformed')lease=new Date().toISOString();
      const bytes=peerMode==='wronghash'?Buffer.from(reply.map(b=>b^1)):reply;
      let headers='HTTP/1.1 '+(peerMode==='partial'?'206 Partial Content':'200 OK')+'\r\nContent-Type: '+replyMedia+'\r\nContent-Length: '+(peerMode==='overlarge'?MAX_ORIGINAL_BYTES+1:bytes.length)+'\r\nConnection: close\r\nCache-Control: no-store, private\r\nX-Content-Type-Options: nosniff\r\n';
      if(peerMode!=='missing')headers+='X-Oracle-Original-Valid-Until: '+lease+'\r\n';
      if(peerMode==='duplicate')headers+='X-Oracle-Original-Valid-Until: '+lease+'\r\n';
      if(peerMode==='encoding')headers+='Content-Encoding: gzip\r\n';
      socket.write(headers+'\r\n');
      setTimeout(()=>socket.end(peerMode==='truncated'?bytes.subarray(0,bytes.length-1):bytes),leaseDelay);

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
  binding={schema_version:1,purpose:'replacement-original-web-binding-v1',project_url:identity.project,auth_issuer:identity.project+'/auth/v1',auth_user_id:id,employee_id:employee,principal_id:'33333333-3333-4333-8333-333333333333',workspace_id:'44444444-4444-4444-8444-444444444444',runtime_hash:hash,registry_hash:hash,viewer_config_sha256:hash,viewer_appointment_sha256:hash,viewer_peer_profile_sha256:hash,storage_profile_hash:hash,web_origin:'https://localhost.localdomain:'+port(web),backend_origin:'https://localhost.localdomain:'+port(backend),original_path:'/v1/replacement/original',sources:[...([pdf,large].map((bytes,i)=>({schema_version:1 as const,source_id:i?employee:id,revision:1,original_sha256:sha256(bytes),byte_count:bytes.length,media_type:'application/pdf' as const,reservation_id:id,custody_seal_sha256:hash}))),...textOriginals.map((bytes,i)=>({schema_version:1 as const,source_id:textIds[i]!,revision:1,original_sha256:sha256(bytes),byte_count:bytes.length,media_type:'text/plain' as const,reservation_id:id,custody_seal_sha256:hash}))],server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(read('server.crt')).raw),server_ca_file:f('ca.crt'),server_ca_sha256:pin('ca.crt'),client_certificate_file:f('client.crt'),client_certificate_sha256:pin('client.crt'),client_certificate_der_sha256:sha256(new X509Certificate(read('client.crt')).raw),client_uri:'spiffe://oracle/invented-web',client_key_file:f('client.key'),client_key_sha256:pin('client.key'),issuer_actor:'independent-route-issuer',reviewer_actor:'independent-route-reviewer',valid_from:new Date(Date.now()-10000).toISOString(),expires_at:new Date(Date.now()+180000).toISOString(),original_horizon:new Date(Date.now()+180000).toISOString()};
  writeFileSync(f('binding.json'),canonicalJson(binding),{mode:0o600});
  process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_FILE=f('binding.json');process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_SHA256=pin('binding.json');process.env.NEXT_PUBLIC_SUPABASE_URL=identity.project;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-anon-key';
});
after(async()=>{
  hooks.deregister();await Promise.all([new Promise<void>(resolve=>web.close(()=>resolve())),new Promise<void>(resolve=>backend.close(()=>resolve()))]);
  rmSync(dir,{recursive:true,force:true});delete (globalThis as unknown as Record<string,unknown>).__routeAuthFixture;
});
const requestBody=(extra:Record<string,unknown>={})=>Buffer.from(canonicalJson({schema_version:1,source_id:id,revision:1,caller_deadline:new Date(Date.now()+5000).toISOString().replace('.000Z','Z').replace(/([0-9]{3})Z$/,'$1000Z'),...extra}));
interface HttpResult{status:number;headers:Readonly<Record<string,string|string[]|undefined>>;body:Buffer;}
const invoke=(bytes=requestBody(),headers:Record<string,string>={},method='POST')=>new Promise<HttpResult>((resolve,reject)=>{
  const req=https.request(binding.web_origin+'/api/consultant/replacement/v1/protected/original',{method,ca:read('ca.crt'),agent:false,headers:{origin:binding.web_origin,'Content-Type':'application/json','Content-Length':String(bytes.length),...headers}},res=>{
    const chunks:Buffer[]=[];res.on('data',(chunk:Buffer)=>chunks.push(chunk));res.on('end',()=>resolve({status:res.statusCode??0,headers:res.headers,body:Buffer.concat(chunks)}));res.on('error',reject);
  });req.on('error',reject);req.end(bytes);
});
const unavailable=(result:HttpResult)=>{
  assert.equal(result.status,503);assert.deepEqual(JSON.parse(result.body.toString()),{error:'Replacement control unavailable'});
  assert.equal(result.headers['cache-control'],'private, no-store, max-age=0');assert.equal(result.headers['x-content-type-options'],'nosniff');assert.equal(result.headers.pragma,'no-cache');assert.equal(result.headers.location,undefined);
  assert.doesNotMatch(result.body.toString(),/private identity|binding|certificate|\.key|password|supabase|stack|ready|resultAvailable/i);
};


test('actual route is POST-only dynamic Node and actual mTLS returns hash-verified original bytes',async()=>{
 assert.deepEqual(Object.keys(route).sort(),['POST','dynamic','runtime']);assert.equal(route.runtime,'nodejs');
 const bytes=requestBody(),r=await invoke(bytes);assert.equal(r.status,200);assert.deepEqual(r.body,pdf);assert.deepEqual(seenBodies.at(-1),bytes);assert.equal(r.headers['content-type'],'application/pdf');assert.equal(r.headers['cache-control'],'private, no-store, max-age=0');assert.equal(r.headers['x-oracle-original-valid-until'],undefined);assert.equal(r.headers[CONTROL_WINDOW_HEADER],undefined);assert.match(String(r.headers['set-cookie']),/invented-refresh=retained/);
});
test('independently pinned exact25MiB original passes full verification before release',async()=>{
 reply=large;try{const r=await invoke(requestBody({source_id:employee}));assert.equal(r.status,200);assert.equal(r.body.length,MAX_ORIGINAL_BYTES);assert.equal(sha256(r.body),sha256(large));}finally{reply=pdf;}
});
test('mandatory lease refuses missing duplicate malformed expired and excessive dates',async()=>{
 for(peerMode of ['missing','duplicate','malformed','expired','excessive'])unavailable(await invoke());peerMode='valid';
});
test('expiry during buffering cannot release any original byte',async()=>{
 peerMode='short';leaseDelay=180;try{unavailable(await invoke());}finally{peerMode='valid';leaseDelay=0;}
});
test('hash count truncation encoding uncertain close and partial response refuse',async()=>{
 for(peerMode of ['wronghash','overlarge','truncated','encoding','uncertain','partial'])unavailable(await invoke());peerMode='valid';
});
test('source revision and authority selectors never escape closed source wire',async()=>{
 const n=peerRequests;for(const patch of [{revision:2},{source_id:'66666666-6666-4666-8666-666666666666'},{actor:id},{role:'admin'},{url:binding.backend_origin},{resultAvailable:true},{schema_version:true}])unavailable(await invoke(requestBody(patch)));assert.equal(peerRequests,n);
});
test('original conditional and Next bypass headers refuse before auth body or peer',async()=>{
 for(const header of [...CONTROL_BYPASS_HEADERS,'range','if-range','if-match','if-none-match','if-modified-since','if-unmodified-since','content-encoding']){const n=peerRequests,calls=identity.proxyCalls;unavailable(await invoke(requestBody(),{[header]:'invented'}));assert.equal(lastBodyReads,0);assert.equal(peerRequests,n);assert.equal(identity.proxyCalls,calls);}
});
test('verified identity project disabled employee and origin refuse before body and peer',async()=>{
 for(const patch of [{user:employee},{employee:id},{project:'https://foreign.example.test'},{disabledAt:new Date()},{error:true}]){const saved={...identity},n=peerRequests;Object.assign(identity,patch);try{unavailable(await invoke());assert.equal(lastBodyReads,0);assert.equal(peerRequests,n);}finally{Object.assign(identity,saved);}}
 const n=peerRequests;unavailable(await invoke(requestBody(),{origin:'https://foreign.example.test'}));assert.equal(peerRequests,n);assert.equal(lastBodyReads,0);
});
test('missing separate viewer installation never falls back to control or fixture',async()=>{
 const saved=process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_FILE,n=peerRequests;delete process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_FILE;try{unavailable(await invoke());assert.equal(lastBodyReads,0);assert.equal(peerRequests,n);}finally{process.env.ORACLE2_REPLACEMENT_VIEWER_BINDING_FILE=saved;}
});
test('methods and native-first path refuse with no authentication or body effect',async()=>{
 const n=peerRequests,calls=identity.proxyCalls;for(const method of ['GET','PUT','DELETE'])assert.equal((await invoke(Buffer.alloc(0),{},method)).status,405);process.env.ORACLE2_NATIVE_BROWSER_ONLY='1';try{assert.equal((await invoke(requestBody(),{'x-middleware-subrequest':'forged'})).status,404);}finally{delete process.env.ORACLE2_NATIVE_BROWSER_ONLY;}assert.equal(peerRequests,n);assert.equal(identity.proxyCalls,calls);
});
test('pinned actual peer mismatch refuses before any HTTP request',async()=>{
 const n=peerRequests;backend.setSecureContext({key:read('alternate.key'),cert:read('alternate.crt'),ca:read('ca.crt')});try{unavailable(await invoke());assert.equal(peerRequests,n);}finally{backend.setSecureContext({key:read('server.key'),cert:read('server.crt'),ca:read('ca.crt')});}
});
test('strict profile pins deny duplicate swapped invalid bounds and competing authority fields',()=>{
 for(const patch of [{sources:[binding.sources[0],binding.sources[0]]},{sources:[{...binding.sources[0],byte_count:MAX_ORIGINAL_BYTES+1}]},{sources:[{...binding.sources[0],revision:true}]},{sources:[{...binding.sources[0],media_type:'text/html'}]},{sources:[{...binding.sources[0],media_type:['text/plain']}]},{purpose:'replacement-web-binding-v1'},{control_path:'/v1/replacement/control'},{sources:[]}])assert.throws(()=>validateViewerBinding({...binding,...patch}));
});
test('identical explicit replay retains exact original deadline and sends only once per invocation',async()=>{
 const bytes=requestBody(),n=peerRequests;assert.equal((await invoke(bytes)).status,200);assert.equal((await invoke(bytes)).status,200);assert.equal(peerRequests,n+2);assert.deepEqual(seenBodies.at(-1),seenBodies.at(-2));
});

test('Expect header refusal executes before auth at the actual proxy boundary',async()=>{const n=identity.proxyCalls;const r=await proxyModule.proxy(new NextRequest(binding.web_origin+'/api/consultant/replacement/v1/protected/original',{method:'POST',headers:{origin:binding.web_origin,expect:'invented'}}));assert.equal(r.status,503);assert.equal(identity.proxyCalls,n);});

test('canonical request refuses duplicate names noncanonical datetime unknown fields and booleans',()=>{
 const good=requestBody();assert.doesNotThrow(()=>validateOriginalViewRequest(good));
 for(const bytes of [Buffer.from(good.toString().replace('"revision":1','"revision":1,"revision":1')),requestBody({revision:true}),requestBody({caller_deadline:new Date(Date.now()+3000).toISOString()}),requestBody({caller_deadline:'2026-02-30T12:00:00Z'}),requestBody({actor:id}),Buffer.concat([good,Buffer.from(' ')])])assert.throws(()=>validateOriginalViewRequest(bytes));
});
test('lease expiry during independent final identity recheck cannot release PDF',async()=>{
 peerMode='short';identity.delayAt=identity.calls+4;identity.delay=160;try{unavailable(await invoke());}finally{identity.delay=0;identity.delayAt=0;peerMode='valid';}
});
async function directOriginal(){
 const bytes=requestBody();const incoming=new NextRequest(binding.web_origin+'/api/consultant/replacement/v1/protected/original',{method:'POST',headers:{origin:binding.web_origin,'content-type':'application/json'},body:bytes});
 const forward=await proxyModule.proxy(incoming);assert.equal(forward.headers.get('x-middleware-next'),'1');const headers=new Headers();for(const k of (forward.headers.get('x-middleware-override-headers')??'').split(','))if(k)headers.set(k,forward.headers.get('x-middleware-request-'+k)??'');
 return route.POST(new Request(incoming.url,{method:'POST',headers,body:bytes}));
}
test('verified browser stream stops at exact lease and cannot admit queued concurrent viewer',async()=>{
 peerMode='short';try{const response=await directOriginal();assert.equal(response.status,200);unavailable(await invoke());await new Promise(r=>setTimeout(r,150));await assert.rejects(response.arrayBuffer());}finally{peerMode='valid';}
});
test('direct handler refuses absent or foreign clock-domain propagation',async()=>{
 for(const header of [undefined,'foreign-domain']){const headers:Record<string,string>={origin:binding.web_origin,'content-type':'application/json'};if(header)headers[CONTROL_WINDOW_HEADER]=header;const r=await route.POST(new Request(binding.web_origin+'/api/consultant/replacement/v1/protected/original',{method:'POST',headers,body:requestBody()}));assert.equal(r.status,503);}
});
test('narrowing deadline cannot renew server window and invalid canonical selectors have no peer effect',async()=>{
 const n=peerRequests;for(const patch of [{caller_deadline:new Date(Date.now()+31000).toISOString().replace(/([0-9]{3})Z$/,'$1000Z')},{caller_deadline:new Date(Date.now()-1000).toISOString().replace(/([0-9]{3})Z$/,'$1000Z')},{source_id:'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'}])unavailable(await invoke(requestBody(patch)));assert.equal(peerRequests,n);
});
test('actual route preserves independently pinned UTF8 original as nosniff text and refuses invalid text or wrong media',async()=>{
  try{
    replyMedia='text/plain; charset=utf-8';reply=textOriginals[0]!;
    const good=await invoke(requestBody({source_id:textIds[0]}));
    assert.equal(good.status,200);assert.deepEqual(good.body,reply);
    assert.equal(good.headers['content-type'],'text/plain; charset=utf-8');
    assert.equal(good.headers['content-disposition'],'inline; filename="original.txt"');
    assert.equal(good.headers['x-content-type-options'],'nosniff');
    for(const i of [1,2]){reply=textOriginals[i]!;unavailable(await invoke(requestBody({source_id:textIds[i]})));}
    reply=textOriginals[0]!;replyMedia='application/pdf';unavailable(await invoke(requestBody({source_id:textIds[0]})));
  }finally{reply=pdf;replyMedia='application/pdf';}
});

test('viewer binding drift after verification stops browser stream and releases bounded slot',async()=>{
 const response=await directOriginal();assert.equal(response.status,200);const original=read('binding.json');writeFileSync(f('binding.json'),canonicalJson({...binding,registry_hash:'b'.repeat(64)}));try{await assert.rejects(response.arrayBuffer());}finally{writeFileSync(f('binding.json'),original);}unavailable(await invoke());
});
