import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {NodeNextRequest} from 'next/dist/server/base-http/node';
import {NextRequestAdapter} from 'next/dist/server/web/spec-extension/adapters/next-request';
import {triggerV2Settings,createTriggerNativeV2Session,authorizeTriggerNativeV2Request,triggerNativeV2Handler,nativeTriggerV2CompletionMatches,nativeTriggerV2HasEmptyBody,nativeTriggerV2Handlers} from './native-trigger-v2';
const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
const enc=(s:string)=>Buffer.from(s).toString('base64');
function install(patch:Record<string,unknown>={}){
 const now=Math.floor(Date.now()/1000);
 const body={schema_version:1,purpose:'public-invented-trigger-v2',issued_at:now-1,expires_at:now+3599,runtime_hash:'a'.repeat(64),review_hash:'b'.repeat(64),release_hash:'c'.repeat(64),admission_hash:hash('oracle-public-invented-trigger-fixture/v2'),files:{database_url:enc('postgresql://oracle_native_v2_gateway.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v2'),database_ca:enc('invented unit CA only')},...patch};
 const raw=JSON.stringify(body);process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE=raw;process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE_SHA256=hash(raw);return body;
}
test('new native web bundle keeps exact isolated SQL target and verify-full',()=>{install();const s=triggerV2Settings();assert.match(s.url,/sslmode=verify-full/);assert.match(s.url,/oracle_native_proof_v2/);});
test('expired, foreign or extended authority is rejected without a connection',()=>{
 for(const patch of [{purpose:'public-invented-v1'},{expires_at:1},{issued_at:1,expires_at:9999999999},{runtime_hash:'bad'}]){install(patch);assert.throws(()=>triggerV2Settings());}
});
test('missing/tampered bundle cannot grant native permission',()=>{install();process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE_SHA256='0'.repeat(64);assert.throws(()=>triggerV2Settings());delete process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE;assert.throws(()=>triggerV2Settings());});
test('retained pilot DB and SSL override cannot become native SQL target',()=>{
 for(const url of ['postgresql://oracle_native_v2_gateway.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres','postgresql://oracle_native_v2_gateway.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v2?sslmode=disable']){install({files:{database_url:enc(url),database_ca:enc('invented')}});assert.throws(()=>triggerV2Settings());}
});
test('Vercel access and wrong native token do not grant native session',async()=>{
 install();process.env.ORACLE2_NATIVE_TRIGGER_TOKEN='invented-native-token';assert.equal((await createTriggerNativeV2Session('wrong')).ok,false);assert.equal((await authorizeTriggerNativeV2Request(new Headers())).ok,false);
 const response=await triggerNativeV2Handler(new Request('https://oracle.designflow.app/api/consultant/native-acceptance'),'result');assert.equal(response.status,401);assert.deepEqual(await response.json(),{error:'Hosted invented-data test unavailable'});
});

test('Trigger completion must bind actual artifact and canonical result, not just a successful job',()=>{
 const expected={runtimeHash:'a'.repeat(64),releaseHash:'b'.repeat(64),artifactHash:'c'.repeat(64),resultSha256:'d'.repeat(64),expiresAt:1234};
 const output={schema_version:1,state:'completed',job_id:'6714d4ed-51df-4c38-9155-c456edf7b727',workspace_id:'cc904285-f213-4a57-9cdb-06f8c278d3ec',runtime_hash:expected.runtimeHash,release_hash:expected.releaseHash,artifact_hash:expected.artifactHash,result_sha256:expected.resultSha256,sdk_version:'1.4.0',graph_name:'oracle_operating_model_v1_cc904285f2134a579cdb06f8c278d3ec_62ec10d787254fb89668035dd89c9acd_1_5c56ede7638c4f51bd98d9e6cad3a8d0',expires_at:1234};
 assert.equal(nativeTriggerV2CompletionMatches(output,expected),true);
 for(const patch of [{artifact_hash:'e'.repeat(64)},{result_sha256:'f'.repeat(64)},{job_id:'77777777-7777-4777-8777-777777777777'},{expires_at:1235},{private_text:'forbidden'}])assert.equal(nativeTriggerV2CompletionMatches({...output,...patch},expected),false);
});


test('installed Next adapter accepts an ordinary browser empty POST and rejects a one-byte POST',async()=>{
 const server=createServer(async(incoming,response)=>{
  try{
   const request=NextRequestAdapter.fromNodeNextRequest(new NodeNextRequest(incoming),new AbortController().signal);
   const bodyIsNull=request.body===null;
   const accepted=await nativeTriggerV2HasEmptyBody(request);
   response.setHeader('Connection','close');response.end(JSON.stringify({bodyIsNull,accepted}));
  }catch{response.statusCode=500;response.end('adapter-test-failed');}
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 try{
  const address=server.address();assert.ok(address&&typeof address!=='string');
  const url=`http://127.0.0.1:${address.port}/invented-adapter-only`;
  const empty=await fetch(url,{method:'POST'});assert.equal(empty.status,200);assert.deepEqual(await empty.json(),{bodyIsNull:false,accepted:true});
  const oneByte=await fetch(url,{method:'POST',body:'x'});assert.equal(oneByte.status,200);assert.deepEqual(await oneByte.json(),{bodyIsNull:false,accepted:false});
 }finally{server.close();await once(server,'close');}
});

test('zero-length framed stream with one unexpected byte is cancelled without JSON parsing',async()=>{
 let cancelled=false;
 const body=new ReadableStream<Uint8Array>({start(controller){controller.enqueue(new Uint8Array([123]));},cancel(){cancelled=true;}});
 const request=new Request('https://invented.invalid',{method:'POST',headers:{'content-length':'0'},body,duplex:'half'} as RequestInit);
 assert.equal(await nativeTriggerV2HasEmptyBody(request),false);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(cancelled,true);
});

test('unfinished empty POST reaches a bounded timeout and cancels its reader',async()=>{
 let cancelled=false;
 const body=new ReadableStream<Uint8Array>({cancel(){cancelled=true;}});
 const request=new Request('https://invented.invalid',{method:'POST',headers:{'content-length':'0'},body,duplex:'half'} as RequestInit);
 assert.equal(await nativeTriggerV2HasEmptyBody(request,20),false);
 await new Promise(resolve=>setImmediate(resolve));assert.equal(cancelled,true);
});

test('framing and GET-body refusals happen before any native metadata or dispatch',async()=>{
 const framingHeaders:Array<Record<string,string>>=[{'transfer-encoding':'chunked'},{'content-length':'1'},{'content-length':'00'}];
 for(const headers of framingHeaders){
  const request=new Request('https://oracle.designflow.app/api/consultant/native-acceptance',{method:'POST',headers:{origin:'https://oracle.designflow.app',...headers}});
  assert.equal(await nativeTriggerV2HasEmptyBody(request),false);
  assert.equal((await triggerNativeV2Handler(request,'admit')).status,400);
 }
 assert.equal(await nativeTriggerV2HasEmptyBody({method:'GET',headers:new Headers(),body:new ReadableStream()} as Request),false);
 assert.equal(await nativeTriggerV2HasEmptyBody(new Request('https://invented.invalid')),true);
});

test('v2 refuses old v1 bundles and every privileged/provider environment before metadata',()=>{
 install({purpose:'public-invented-trigger-v1'});assert.throws(()=>triggerV2Settings());
 for(const name of ['DATABASE_URL','ORACLE2_DATABASE_URL','TRIGGER_ACCESS_TOKEN','ORACLE2_PROJECTOR_GRAPH_URL','ORACLE_NATIVE_GRAPH_PROJECTOR_PASSWORD','ORACLE_NATIVE_PROJECTOR_DATABASE_URL','ORACLE2_PROJECTOR_DATABASE_URL','TRIGGER_PAT','ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY','ZHIPU_API_KEY','AZURE_OPENAI_API_KEY','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','ORACLE2_PREVIEW_ADMIN_URL','ORACLE_NATIVE_ADMIN_URL','ORACLE2_NATIVE_TRIGGER_BUNDLE','ORACLE2_NATIVE_TRIGGER_BUNDLE_SHA256']){
  install();const before=process.env[name];process.env[name]='';
  try{assert.throws(()=>triggerV2Settings());}finally{if(before===undefined)delete process.env[name];else process.env[name]=before;}
 }
});

test('v2 refuses v1 SQL namespace and login even with a correctly sealed bundle',()=>{
 for(const url of ['postgresql://oracle_synthetic_gateway.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v1','postgresql://oracle_native_v2_projector.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.co:5432/oracle_native_proof_v2']){
  install({files:{database_url:enc(url),database_ca:enc('invented')}});assert.throws(()=>triggerV2Settings());
 }
});

test('v2 refuses changed complete attestations and historical v1 job identity',()=>{
 const expected={runtimeHash:'a'.repeat(64),releaseHash:'b'.repeat(64),artifactHash:'c'.repeat(64),resultSha256:'d'.repeat(64),expiresAt:1234};
 const output={schema_version:1,state:'completed',job_id:'6714d4ed-51df-4c38-9155-c456edf7b727',workspace_id:'cc904285-f213-4a57-9cdb-06f8c278d3ec',runtime_hash:expected.runtimeHash,release_hash:expected.releaseHash,artifact_hash:expected.artifactHash,result_sha256:expected.resultSha256,sdk_version:'1.4.0',graph_name:'oracle_operating_model_v1_cc904285f2134a579cdb06f8c278d3ec_62ec10d787254fb89668035dd89c9acd_1_5c56ede7638c4f51bd98d9e6cad3a8d0',expires_at:1234};
 for(const key of Object.keys(output)){
  const absent={...output};delete absent[key as keyof typeof absent];assert.equal(nativeTriggerV2CompletionMatches(absent,expected),false);
  assert.equal(nativeTriggerV2CompletionMatches({...output,[key]:'foreign'},expected),false);
 }
 assert.equal(nativeTriggerV2CompletionMatches({...output,job_id:'9c9c7424-8e16-4f71-be10-c935160e16c7'},expected),false);
});


test('v2 one-use admission and exact canonical result survive real handler flow',async()=>{
 const c=install();let dispatches=0;let triggerId:string|null=null;let completed=false;
 process.env.ORACLE2_NATIVE_TRIGGER_SECRET_KEY='invented-test-key';
 const bytes=Buffer.from('{"invented":"canonical bytes"}');
 const output={schema_version:1,state:'completed',job_id:'6714d4ed-51df-4c38-9155-c456edf7b727',workspace_id:'cc904285-f213-4a57-9cdb-06f8c278d3ec',runtime_hash:c.runtime_hash,release_hash:c.release_hash,artifact_hash:'e'.repeat(64),result_sha256:hash(bytes.toString()),sdk_version:'1.4.0',graph_name:'oracle_operating_model_v1_cc904285f2134a579cdb06f8c278d3ec_62ec10d787254fb89668035dd89c9acd_1_5c56ede7638c4f51bd98d9e6cad3a8d0',expires_at:c.expires_at};
 let counterfeit=false;
 const handler=nativeTriggerV2Handlers({
  authorize:async()=>({ok:true,actorId:'invented',sessionId:'invented'}),
  metadata:async()=>({c:c as ReturnType<typeof triggerV2Settings>['c'],url:'unused',seal:'f'.repeat(64),artifactHash:'e'.repeat(64),status:completed?'completed':'pending',bytes:completed?bytes:null,triggerId}),
  dispatch:async()=>{if(dispatches)throw Error('spent');dispatches++;},trigger:async()=>({id:'run_invented_v2'}),bind:async id=>{triggerId=id;},
  retrieve:async()=>({status:'COMPLETED',output:counterfeit?{...output,result_sha256:'0'.repeat(64)}:output}),
 });
 const admit=()=>new Request('https://oracle.designflow.app/api/consultant/native-acceptance',{method:'POST',headers:{origin:'https://oracle.designflow.app'}});
 assert.equal((await handler(admit(),'admit')).status,202);
 assert.equal((await handler(admit(),'admit')).status,409);assert.equal(dispatches,1);
 const get=()=>new Request('https://oracle.designflow.app/api/consultant/native-acceptance');
 assert.equal((await handler(get(),'result')).status,202);completed=true;
 counterfeit=true;assert.equal((await handler(get(),'result')).status,403);counterfeit=false;
 const result=await handler(get(),'result');assert.equal(result.status,200);assert.equal(Buffer.compare(Buffer.from(await result.arrayBuffer()),bytes),0);
 assert.equal(result.headers.get('X-Oracle-Native-Result-Sha256'),hash(bytes.toString()));
});

test('v2 framing refusal precedes every metadata or dispatch dependency',async()=>{
 const forbidden=async():Promise<never>=>{throw Error('metadata must not run');};let calls=0;
 const handler=nativeTriggerV2Handlers({authorize:async()=>{calls++;return forbidden();},metadata:forbidden,dispatch:forbidden,trigger:forbidden,bind:forbidden,retrieve:forbidden});
 const bad=new Request('https://oracle.designflow.app/api/consultant/native-acceptance',{method:'POST',headers:{origin:'https://oracle.designflow.app','content-length':'1'},body:'x'});
 assert.equal((await handler(bad,'admit')).status,400);assert.equal(calls,0);
});

test('real Next adapter unfinished body times out before authority lookup',async()=>{
 const {PassThrough}=await import('node:stream');
 const incoming=Object.assign(new PassThrough(),{method:'POST',url:'/invented',headers:{'content-length':'0'},rawHeaders:['content-length','0']});
 const request=NextRequestAdapter.fromNodeNextRequest(new NodeNextRequest(incoming as never),new AbortController().signal);
 assert.notEqual(request.body,null);
 assert.equal(await nativeTriggerV2HasEmptyBody(request,20),false);
 incoming.destroy();
});

test('only explicit v2 mode selects the new adapter; v1 and default retain their selectors',async()=>{
 const {nativeTriggerV2Enabled}=await import('./native-trigger-v2');
 const {nativeTriggerEnabled}=await import('./native-trigger');
 const previous=process.env.ORACLE2_NATIVE_TRIGGER_MODE;
 try{
  for(const [mode,v1,v2] of [['v1',true,false],['v2',false,true],['',false,false]] as const){process.env.ORACLE2_NATIVE_TRIGGER_MODE=mode;assert.equal(nativeTriggerEnabled(),v1);assert.equal(nativeTriggerV2Enabled(),v2);}
  delete process.env.ORACLE2_NATIVE_TRIGGER_MODE;assert.equal(nativeTriggerEnabled(),false);assert.equal(nativeTriggerV2Enabled(),false);
 }finally{if(previous===undefined)delete process.env.ORACLE2_NATIVE_TRIGGER_MODE;else process.env.ORACLE2_NATIVE_TRIGGER_MODE=previous;}
});


test('v2 rejects shortened and extended authority instead of accepting a resealed lifetime',()=>{
 const now=Math.floor(Date.now()/1000);
 for(const expires_at of [now+99,now+3598,now+3600]){install({issued_at:now-1,expires_at});assert.throws(()=>triggerV2Settings());}
 install({issued_at:now-1,expires_at:now+3599});assert.doesNotThrow(()=>triggerV2Settings());
});
