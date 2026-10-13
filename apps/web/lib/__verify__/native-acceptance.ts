import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:https';
import { createHmac } from 'node:crypto';
import { authorizePilotRequest } from '../oracle2-pilot-auth';
import { canonical, parseSettings, protectedBytes, checkCertificate, opaqueRequest, signature,
  nativeRequestOrigin, nativeTransport, nativeHandlers, sha, type NativeSettings, type NativeDependencies } from '../native-acceptance';

const scratch=mkdtempSync(join(tmpdir(),'oracle-native-browser-invented-'));
const H='a'.repeat(64),actor='00000000-0000-4000-8000-000000000001',workspace='00000000-0000-4000-8000-000000000002';
const worker='spiffe://oracle/invented-native-browser/worker';let now=Math.floor(Date.now()/1000);
let checks=0;
function check(fn:()=>void){fn();checks++;}
function file(name:string,raw:Buffer|string){const path=join(scratch,name);writeFileSync(path,raw,{mode:0o600});return {path,sha256:sha(readFileSync(path))};}
function openssl(args:string[]){execFileSync('openssl',args,{cwd:scratch,stdio:'ignore'});}
try{
  openssl(['req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem','-days','1','-subj','/CN=Invented local CA',
    '-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign']);
  for(const kind of ['server','client']){
    openssl(['req','-newkey','rsa:2048','-nodes','-keyout',kind+'.key','-out',kind+'.csr','-subj','/CN=Invented '+kind]);
    file(kind+'.ext',`subjectAltName=${kind==='server'?'DNS:localhost':`URI:${worker}`}\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=${kind==='server'?'serverAuth':'clientAuth'}\n`);
    openssl(['x509','-req','-in',kind+'.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-out',kind+'.pem','-days','1','-extfile',kind+'.ext']);
    chmodSync(join(scratch,kind+'.key'),0o600);chmodSync(join(scratch,kind+'.pem'),0o600);
  }
  chmodSync(join(scratch,'ca.pem'),0o600);
  now=Math.floor(Date.now()/1000);
  const pin=(name:string)=>({path:join(scratch,name),sha256:sha(readFileSync(join(scratch,name)))});
  const key=Buffer.alloc(32,7),hmac=file('hmac',key),db=file('database','postgres://not-a-live-credential');
  const c:NativeSettings={schema_version:1,purpose:'public-invented-native-browser',namespace:'invented-native-browser',hostname:'localhost',origin:'https://localhost',public_page_origin:'https://native.example.test',
    actor_id:actor,workspace_id:workspace,job_id:'00000000-0000-4000-8000-000000000003',runtime_hash:H,admission_hash:H,release_hash:H,permission_hash:H,
    worker_uri:worker,source_authority_expires_at:now+600,worker_permit_expires_at:now+600,job_expires_at:now+600,
    source_refs:[{schema_version:1,workspace_id:workspace,source_id:'00000000-0000-4000-8000-000000000004',revision:1,original_sha256:H,reading_sha256:H,parser_id:H}],
    metadata_login:'oracle_synthetic_gateway',metadata_role:'oracle2_gateway_metadata',database_url:db,database_ca:pin('ca.pem'),client_cert:pin('client.pem'),client_key:pin('client.key'),server_ca:pin('ca.pem'),hmac_key:hmac};
  const raw=Buffer.from(canonical(c)),seal=sha(raw);
  check(()=>assert.deepEqual(parseSettings(raw,seal,now),c));
  const envKeys=['ORACLE2_NATIVE_BROWSER_ONLY','ORACLE2_NATIVE_BROWSER_PUBLIC_HOST','ORACLE2_NATIVE_ACCEPTANCE_SETTINGS','ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256'];
  const old=envKeys.map(k=>process.env[k]);
  try{
    process.env.ORACLE2_NATIVE_BROWSER_ONLY='1';process.env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST='native.example.test';
    process.env.ORACLE2_NATIVE_ACCEPTANCE_SETTINGS=file('sealed-settings',raw).path;process.env.ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256=seal;
    const headers={'host':'native.example.test','x-forwarded-proto':'https','origin':c.public_page_origin};
    const request=(h:Record<string,string>)=>new Request('http://0.0.0.0:3000/api/consultant/native-acceptance',{method:'POST',headers:h});
    check(()=>assert(nativeRequestOrigin(request(headers))));
    check(()=>assert(nativeRequestOrigin(request({...headers,'x-forwarded-host':'native.example.test'}))));
    for(const bad of ([{'host':'foreign.test'},{'x-forwarded-proto':'https, https'},{'origin':'https://foreign.test'},{'x-forwarded-host':'native.example.test, native.example.test'},{'forwarded':'host=native.example.test'},{'sec-fetch-site':'cross-site'}] as Record<string,string>[]))check(()=>assert(!nativeRequestOrigin(request({...headers,...bad}))));
    delete process.env.ORACLE2_NATIVE_BROWSER_ONLY;
    check(()=>assert(nativeRequestOrigin(new Request(c.public_page_origin,{headers:{origin:c.public_page_origin}}))));
  }finally{envKeys.forEach((k,i)=>{if(old[i]===undefined)delete process.env[k];else process.env[k]=old[i];});}

  for(const change of ['seal','duplicate','expiry','foreign_sources','hostname','legacy_hostname','http'])check(()=>{
    let altered=structuredClone(c),bytes=raw,hash=seal;
    if(change==='seal')hash='b'.repeat(64);
    else if(change==='duplicate')bytes=Buffer.from(raw.toString().replace('"schema_version":1','"schema_version":1,"schema_version":1'));
    else if(change==='expiry')altered.source_authority_expires_at=now;
    else if(change==='foreign_sources')altered.source_refs[0]!.workspace_id=actor;
    else if(change==='hostname')altered.hostname='other.invalid';
    else if(change==='legacy_hostname'){altered.hostname='oracle.designflow.app';altered.origin='https://oracle.designflow.app';}
    else altered.origin='http://localhost';
    if(change!=='seal'){if(change!=='duplicate')bytes=Buffer.from(canonical(altered));hash=sha(bytes);}
    assert.throws(()=>parseSettings(bytes,hash,now));
  });
  check(()=>assert.deepEqual(protectedBytes(hmac.path),key));
  chmodSync(hmac.path,0o644);check(()=>assert.throws(()=>protectedBytes(hmac.path)));chmodSync(hmac.path,0o600);
  const cert=readFileSync(c.client_cert.path),clientKey=readFileSync(c.client_key.path);
  check(()=>checkCertificate(cert,clientKey,worker,now));
  check(()=>assert.throws(()=>checkCertificate(cert,clientKey,worker,now+172800)));
  check(()=>assert.throws(()=>checkCertificate(cert,clientKey,'spiffe://oracle/foreign',now)));
  check(()=>assert.throws(()=>checkCertificate(cert,readFileSync(join(scratch,'server.key')),worker,now)));
  const envelope=opaqueRequest(c,'result',now),another=opaqueRequest(c,'result',now);
  check(()=>assert.notEqual(envelope.body.toString(),another.body.toString()));
  check(()=>assert.equal(signature(envelope.path,envelope.body,key),createHmac('sha256',key).update(Buffer.concat([Buffer.from('POST\n/v1/jobs/result\n'),envelope.body])).digest('hex')));
  check(()=>assert.notEqual(signature('/v1/jobs/admit',envelope.body,key),signature('/v1/jobs/result',envelope.body,key)));
  check(()=>assert.throws(()=>opaqueRequest({...c,worker_permit_expires_at:now},'result',now)));
  check(()=>assert.throws(()=>opaqueRequest(c,'result',now,'not-a-uuid')));

  const canonicalResult=Buffer.from('{"artifact_hash":"'+H+'","value":1.2300,"unicode":"☃"}');
  let transportCalls=0,currentCalls=0;
  const deps:NativeDependencies={authorize:async()=>({ok:true,actorId:actor,sessionId:'invented'}),workspace:()=>workspace,
    settings:()=>c,current:async()=>{currentCalls++;return {status:'completed',canonical:canonicalResult,expiresAt:now+600};},
    transport:async()=>{transportCalls++;return {status:200,body:canonicalResult};},clock:()=>now};
  const get=()=>new Request('https://preview.invalid/api/consultant/native-acceptance');
  let response=await nativeHandlers(deps)(get(),'result');assert.equal(response.status,200);assert.deepEqual(Buffer.from(await response.arrayBuffer()),canonicalResult);checks++;
  response=await nativeHandlers({...deps,authorize:authorizePilotRequest})(get(),'result');assert.equal(response.status,401);checks++;
  const noNative=transportCalls;
  for(const delta of [
    {authorize:async()=>({ok:true as const,actorId:workspace,sessionId:'invented'})},
    {workspace:()=>actor},
    {current:async()=>{throw Error('current original withdrawn');}},
    {settings:()=>({...c,worker_permit_expires_at:now})},
  ]){response=await nativeHandlers({...deps,...delta})(get(),'result');assert.notEqual(response.status,200);checks++;}
  assert.equal(transportCalls,noNative);checks++;
  response=await nativeHandlers(deps)(new Request('https://preview.invalid/api/consultant/native-acceptance?job_id=foreign'),'result');assert.equal(response.status,400);checks++;
  response=await nativeHandlers(deps)(new Request('https://preview.invalid/api/consultant/native-acceptance',{method:'POST',headers:{Origin:'https://foreign.invalid'}}),'admit');assert.equal(response.status,400);checks++;
  response=await nativeHandlers({...deps,transport:async()=>({status:200,body:Buffer.from('{"value":1.23}')})})(get(),'result');assert.equal(response.status,409);checks++;
  let reads=0;
  response=await nativeHandlers({...deps,current:async()=>{if(++reads>1)throw Error('revoked during transport');return {status:'completed',canonical:canonicalResult,expiresAt:now+600};}})(get(),'result');assert.equal(response.status,409);checks++;
  response=await nativeHandlers({...deps,transport:async()=>{throw Error('ambiguous timeout');}})(get(),'result');assert.equal(response.status,409);checks++;
  let settingsReads=0;
  response=await nativeHandlers({...deps,settings:()=>++settingsReads===1?c:{...c,runtime_hash:'b'.repeat(64)}})(get(),'result');assert.equal(response.status,409);checks++;
  let authReads=0;
  response=await nativeHandlers({...deps,authorize:async()=>++authReads===1?{ok:true,actorId:actor,sessionId:'invented'}:{ok:false,status:403,error:'revoked'}})(get(),'result');assert.equal(response.status,403);checks++;
  response=await nativeHandlers(deps)(new Request('https://preview.invalid/api/consultant/native-acceptance',{method:'POST',headers:{Origin:'https://preview.invalid'},body:'{"job_id":"foreign"}'}),'admit');assert.equal(response.status,400);checks++;
  let clockReads=0;
  response=await nativeHandlers({...deps,clock:()=>++clockReads===1?now:now+600})(get(),'result');assert.equal(response.status,409);checks++;
  for(const path of ['components/consultant/native-acceptance-workspace.tsx','app/consultant/native-acceptance/page.tsx']){
    const source=readFileSync(path,'utf8');assert(!/ORACLE2_|client_cert|client_key|hmac_key|nativeTransport/.test(source));checks++;
  }

  const nonces=new Set<string>();let received=0;
  const server=createServer({key:readFileSync(join(scratch,'server.key')),cert:readFileSync(join(scratch,'server.pem')),ca:readFileSync(join(scratch,'ca.pem')),
    requestCert:true,rejectUnauthorized:true,minVersion:'TLSv1.3'},(req,res)=>{
    const chunks:Buffer[]=[];req.on('data',(chunk:Buffer)=>chunks.push(chunk));req.on('end',()=>{
      const bytes=Buffer.concat(chunks),packet=JSON.parse(bytes.toString());received++;
      if(req.headers['x-oracle-job-signature']!==signature(req.url!,bytes,key)||nonces.has(packet.nonce)){res.writeHead(403);res.end();return;}
      nonces.add(packet.nonce);
      const result=req.url==='/v1/jobs/admit'?Buffer.from(JSON.stringify({job_id:c.job_id,request_hash:sha(bytes),state:'accepted'})):canonicalResult;
      res.writeHead(req.url==='/v1/jobs/admit'?202:200,{'Content-Type':'application/json','Content-Length':result.length,'Cache-Control':'no-store'});res.end(result);
    });
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address();assert(address&&typeof address!=='string');const connected={...c,origin:`https://localhost:${address.port}`};
  try{
    const actual=await nativeTransport(connected,'result',Math.floor(Date.now()/1000));assert.equal(actual.status,200);assert.deepEqual(actual.body,canonicalResult);checks++;
    const accepted=await nativeTransport(connected,'admit',Math.floor(Date.now()/1000));assert.equal(accepted.status,202);checks++;
    assert.equal(nonces.size,2);checks++;
    await assert.rejects(()=>nativeTransport({...connected,hostname:'127.0.0.1',origin:`https://127.0.0.1:${address.port}`},'result',Math.floor(Date.now()/1000)));checks++;
    const before=received;
    await assert.rejects(()=>nativeTransport({...connected,worker_uri:'spiffe://oracle/foreign'},'result',Math.floor(Date.now()/1000)));assert.equal(received,before);checks++;
    writeFileSync(hmac.path,Buffer.alloc(32,8));
    await assert.rejects(()=>nativeTransport(connected,'result',Math.floor(Date.now()/1000)));assert.equal(received,before);checks++;
    const mismatched={...connected,hmac_key:{path:hmac.path,sha256:sha(readFileSync(hmac.path))}};
    await assert.rejects(()=>nativeTransport(mismatched,'result',Math.floor(Date.now()/1000)));assert.equal(received,before+1);checks++;
  }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));}
  console.log(`native browser source verification: ${checks} passed; invented local TLS only; live acceptance false`);
}finally{rmSync(scratch,{recursive:true,force:true});}
