/** Actual owned synthetic TLS provider only. No provider account/installation proof. */
import assert from 'node:assert/strict';
import {after,before,test} from 'node:test';
import {mkdtempSync,readFileSync,writeFileSync,chmodSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import * as tls from 'node:tls';
import {createRequire,syncBuiltinESMExports} from 'node:module';
import {X509Certificate,createHash} from 'node:crypto';
import {RecallWireUncertaintyV1,inventedLoopbackRecallHTTPSV1,installedRecallHTTPSV1,publicRecallAddressV1,type OriginalWireWindowV1} from '@oracle/shared/protected-node-https';
const sha=(bytes:Uint8Array)=>createHash('sha256').update(bytes).digest('hex');
let directory:string,server:tls.Server,port:number,client:ReturnType<typeof inventedLoopbackRecallHTTPSV1>,mode='valid',requests=0,guardCalls=0;const sockets=new Set<tls.TLSSocket>(),seen:Array<{header:string,body:Buffer}>=[];
const f=(name:string)=>join(directory,name),read=(name:string)=>readFileSync(f(name));
const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:directory,stdio:'pipe'});
before(async()=>{
 directory=mkdtempSync(join(tmpdir(),'oracle-recall-wire-'));chmodSync(directory,0o700);
 openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented Provider CA');
 openssl('req','-newkey','rsa:2048','-nodes','-keyout','server.key','-out','server.csr','-subj','/CN=Invented Provider');
 writeFileSync(f('server.ext'),'subjectAltName=DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\n');openssl('x509','-req','-in','server.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out','server.crt','-days','1','-extfile','server.ext');
 server=tls.createServer({key:read('server.key'),cert:read('server.crt'),allowHalfOpen:true},socket=>{
  sockets.add(socket);socket.on('close',()=>sockets.delete(socket));socket.on('error',()=>undefined);let data=Buffer.alloc(0),answered=false;
  socket.on('data',(chunk:Buffer)=>{data=Buffer.concat([data,chunk]);const split=data.indexOf('\r\n\r\n');if(split<0||answered)return;const header=data.subarray(0,split).toString('ascii'),length=/content-length: ([0-9]+)/i.exec(header)?.[1];if(length===undefined||data.length<split+4+Number(length))return;answered=true;requests++;seen.push({header,body:data.subarray(split+4)});
   const body=mode==='empty'?Buffer.alloc(0):Buffer.from('{"id":"11111111-1111-4111-8111-111111111111"}');
   const status=mode==='redirect'?302:header.startsWith('POST /api/v1/bot/ HTTP')?201:200;
   const reply=Buffer.concat([Buffer.from('HTTP/1.1 '+status+' '+(status===201?'Created':'OK')+'\r\nContent-Type: application/json\r\n'+(mode==='duplicate'?'Content-Type: application/json\r\n':'')+(mode==='chunked'?'Transfer-Encoding: chunked\r\n':'')+'Content-Length: '+body.length+'\r\nConnection: close\r\n\r\n'),body]);
   if(mode==='partial'){socket.write(reply.subarray(0,reply.length-3));socket.destroy();}
   else if(mode==='retained-partial')socket.end(reply.subarray(0,reply.length-3));
   else if(mode==='wire-overflow')socket.end(Buffer.concat([Buffer.from('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 1048576\r\nConnection: close\r\n\r\n'),Buffer.alloc(1064961,120)]));
   else if(mode==='extra')socket.end(Buffer.concat([reply,Buffer.from('extra')]));
   else if(mode==='delayed-extra'){socket.write(reply);setTimeout(()=>socket.end('extra'),30);}
   else if(mode==='double'){socket.write(reply);setTimeout(()=>socket.end(reply),30);}
   else if(mode==='no-eof')socket.write(reply);
   else if(mode==='header-limit')socket.end('HTTP/1.1 200 OK\r\nX-Extra: '+'x'.repeat(17000)+'\r\n\r\n');
   else if(mode==='slow')setTimeout(()=>socket.end(reply),150);
   else socket.end(reply);
  });
 });server.on('tlsClientError',()=>undefined);await new Promise<void>(resolve=>server.listen(0,'::1',resolve));const address=server.address();assert.ok(address&&typeof address!=='string');port=address.port;
 client=inventedLoopbackRecallHTTPSV1({hostname:'localhost.localdomain',ca:read('ca.crt'),serverDerSha256:sha(new X509Certificate(read('server.crt')).raw),authorization:'invented-fixed-account-key'},port);
});
after(async()=>{for(const socket of sockets)socket.destroy();await new Promise<void>(resolve=>server.close(()=>resolve()));rmSync(directory,{recursive:true,force:true});});
const window=(ms=3000):OriginalWireWindowV1=>({wallDeadline:Date.now()+ms,monotonicDeadline:process.hrtime.bigint()+BigInt(ms)*1000000n,signal:new AbortController().signal,current:()=>{guardCalls++;}});
const create=()=>client.exchange({kind:'create',body:Buffer.from('{"meeting_url":"https://teams.example.test/invented"}')},window(),async()=>{});
test('production destination policy denies private mapped transition reserved and mixed answer candidates',()=>{
 for(const address of JSON.parse(readFileSync(new URL('../../../tests/fixtures/recall-denied-addresses.json',import.meta.url),'utf8')) as string[])assert.equal(publicRecallAddressV1(address),false,address);
 for(const address of ['8.8.8.8','1.1.1.1','2001:4860:4860::8888','2606:4700:4700::1111'])assert.equal(publicRecallAddressV1(address),true,address);
 assert.throws(()=>installedRecallHTTPSV1({hostname:'localhost.localdomain',ca:read('ca.crt'),serverDerSha256:'a'.repeat(64),authorization:'invented-key'}));
 assert.throws(()=>inventedLoopbackRecallHTTPSV1({hostname:'localhost.localdomain',ca:read('ca.crt'),serverDerSha256:'a'.repeat(64),authorization:'not-an-invented-fixture-key'},port));
});
test('actual synthetic TLS returns exact full raw201 wire and fixed account header only once',async()=>{
 mode='valid';const count=requests,result=await create();assert.equal(result.status,201);assert.equal(requests,count+1);assert.equal(result.wireSha256,sha(result.wire));assert.ok(result.wire.subarray(result.wire.length-result.body.length).equals(result.body));assert.match(seen.at(-1)!.header,/^POST \/api\/v1\/bot\/ HTTP\/1.1/);assert.match(seen.at(-1)!.header,/Authorization: invented-fixed-account-key/i);assert.ok(guardCalls>0);
});
test('closed leave retrieve and send paths preserve exact body and literal statuses without interpreting stop',async()=>{
 const id='11111111-1111-4111-8111-111111111111';mode='empty';const left=await client.exchange({kind:'leave',botId:id},window(),async()=>{});assert.equal(left.status,200);assert.equal(left.body.length,0);assert.match(seen.at(-1)!.header,/leave_call\//);
 mode='valid';assert.equal((await client.exchange({kind:'retrieve',botId:id},window(),async()=>{})).status,200);assert.match(seen.at(-1)!.header,/^GET \/api\/v1\/bot\//);
 const bytes=Buffer.from('{"to":"everyone","message":"原话"}');assert.equal((await client.exchange({kind:'send-chat',botId:id,body:bytes},window(),async()=>{})).status,200);assert.deepEqual(seen.at(-1)!.body,bytes);
});
test('redirect is observed once never followed or retried',async()=>{mode='redirect';const count=requests,result=await create();assert.equal(result.status,302);assert.equal(requests,count+1);mode='valid';});
test('unknown bot and invalid fixed target cannot send any request bytes',async()=>{const count=requests;await assert.rejects(client.exchange({kind:'leave',botId:'../other'},window(),async()=>{}));assert.equal(requests,count);});
for(const state of ['partial','extra','delayed-extra','double','duplicate','chunked','header-limit'])test('actual '+state+' wire refuses without a retry',async()=>{mode=state;const count=requests;await assert.rejects(create());assert.equal(requests,count+1);mode='valid';});
test('actual missing EOF and delay expire at original window without claiming stop',async()=>{for(mode of ['no-eof','slow']){const count=requests;await assert.rejects(client.exchange({kind:'create',body:Buffer.from('{}')},window(80),async()=>{}));assert.equal(requests,count+1);for(const socket of sockets)socket.destroy();}mode='valid';});
test('currentness refusal after TLS prevents all HTTP bytes and late guard cannot dispatch',async()=>{
 const count=requests;await assert.rejects(client.exchange({kind:'create',body:Buffer.from('{}')},window(),async()=>{throw new Error('private currentness refusal');}));assert.equal(requests,count);
 await assert.rejects(client.exchange({kind:'create',body:Buffer.from('{}')},window(50),async()=>{await new Promise(resolve=>setTimeout(resolve,100));}));assert.equal(requests,count);await new Promise(resolve=>setTimeout(resolve,110));assert.equal(requests,count);
});

test('production all-address DNS policy rejects mixed answers before any TLS or request',async()=>{
 const mutable=createRequire(import.meta.url)('node:dns') as {lookup:(...args:unknown[])=>unknown},original=mutable.lookup;
 const count=requests;
 try{mutable.lookup=(...args:unknown[])=>{const cb=args.at(-1) as(error:Error|null,addresses:Array<{address:string,family:number}>)=>void;cb(null,[{address:'8.8.8.8',family:4},{address:'127.0.0.1',family:4}]);};syncBuiltinESMExports();
 const production=installedRecallHTTPSV1({hostname:'us-east-1.recall.ai',ca:read('ca.crt'),serverDerSha256:'a'.repeat(64),authorization:'invented-key'});await assert.rejects(production.exchange({kind:'create',body:Buffer.from('{}')},window(100),async()=>{}));assert.equal(requests,count);
 }finally{mutable.lookup=original;syncBuiltinESMExports();}
});
test('one persistent resolver bounds original wait and late DNS never connects or queues',async()=>{
 const mutable=createRequire(import.meta.url)('node:dns') as {lookup:(...args:unknown[])=>unknown},original=mutable.lookup;let lookups=0;const count=requests;
 try{mutable.lookup=(...args:unknown[])=>{lookups++;const cb=args.at(-1) as(error:Error|null,addresses:Array<{address:string,family:number}>)=>void;setTimeout(()=>cb(null,[{address:'127.0.0.1',family:4}]),80);};syncBuiltinESMExports();
 const production=installedRecallHTTPSV1({hostname:'us-east-1.recall.ai',ca:read('ca.crt'),serverDerSha256:'a'.repeat(64),authorization:'invented-key'});await assert.rejects(production.exchange({kind:'create',body:Buffer.from('{}')},window(20),async()=>{}));await assert.rejects(production.exchange({kind:'create',body:Buffer.from('{}')},window(100),async()=>{}));assert.equal(lookups,1);await new Promise(resolve=>setTimeout(resolve,100));assert.equal(requests,count);assert.equal(lookups,1);
 }finally{mutable.lookup=original;syncBuiltinESMExports();}
});
test('actual TLS leaf pin mismatch refuses before HTTP and currentness cannot open a revoked window',async()=>{
 const count=requests;const wrong=inventedLoopbackRecallHTTPSV1({hostname:'localhost.localdomain',ca:read('ca.crt'),serverDerSha256:'0'.repeat(64),authorization:'invented-key'},port);let guard=0;
 await assert.rejects(wrong.exchange({kind:'create',body:Buffer.from('{}')},window(),async()=>{guard++;}));assert.equal(guard,0);assert.equal(requests,count);
 let revoked=false;const fence={...window(),current:()=>{if(revoked)throw new Error('revoked');}};
 await assert.rejects(client.exchange({kind:'create',body:Buffer.from('{}')},fence,async()=>{revoked=true;}));assert.equal(requests,count);
});
test('already expired aborted nonfinite or oversized request has zero outbound effects',async()=>{
 const count=requests;const aborted=new AbortController();aborted.abort();
 for(const fence of [{...window(),wallDeadline:NaN},{...window(),monotonicDeadline:0n},{...window(),signal:aborted.signal}])await assert.rejects(client.exchange({kind:'create',body:Buffer.from('{}')},fence,async()=>{}));
 await assert.rejects(client.exchange({kind:'create',body:Buffer.alloc(65537)},window(),async()=>{}));assert.equal(requests,count);
});

for(const state of ['retained-partial','delayed-extra','double','no-eof','wire-overflow'])test('uncertain '+state+' retains bounded observed response bytes without authority or request secrets',async()=>{
 mode=state;const count=requests;let error:unknown;
 try{await client.exchange({kind:'create',body:Buffer.from('{}')},window(120),async()=>{});}catch(value){error=value;}
 assert.ok(error instanceof RecallWireUncertaintyV1);assert.equal(requests,count+1);
 const raw=error.wire;assert.ok(raw.length>0&&raw.length<=1064960);assert.ok(error.observedBytes>=raw.length);assert.equal(error.wireTruncated,error.observedBytes>raw.length);
 if(state==='wire-overflow'){assert.ok(raw.length>1048576);}else{assert.match(raw.toString('ascii'),/^HTTP\/1\.1/);assert.equal(error.wireTruncated,false);}
 assert.doesNotMatch(raw.toString('ascii'),/Authorization:|invented-fixed-account-key|meeting_url/i);
 raw.fill(0);assert.notDeepEqual(error.wire,raw);for(const socket of sockets)socket.destroy();mode='valid';
});
