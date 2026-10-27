/** Invented auth-import snapshots + actual mTLS. NOT real Auth/SQL acceptance. */
import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
import {mkdtempSync,writeFileSync,readFileSync,chmodSync,rmSync,renameSync} from 'node:fs';
import {tmpdir} from 'node:os';import {join} from 'node:path';
import {execFileSync} from 'node:child_process';import * as tls from 'node:tls';
import {X509Certificate} from 'node:crypto';
import {canonicalJson,sha256,readInstalledEmployeeBindingV1,rereadInstalledEmployeeBindingV1,type ServerBinding} from '../../lib/replacement-server-binding';
import {captureControlWindow,CONTROL_WINDOW_HEADER} from '../../lib/replacement-control-window';
const directory=mkdtempSync(join(tmpdir(),'oracle-recipient-'));chmodSync(directory,0o700);
const path=(name:string)=>join(directory,name),hash=(name:string)=>sha256(readFileSync(path(name)));
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const project='https://recipient-auth.example.test',origin='https://recipient-web.example.test';
const fixture={user:id(1),employee:id(11),disabledAt:null as null|string,ambiguous:false};
(globalThis as unknown as Record<string,unknown>).__recipientFixture=fixture;
const hooks=registerHooks({
 resolve(specifier,context,next){if(context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'oracle-recipient:auth',shortCircuit:true};if(context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'oracle-recipient:employee',shortCircuit:true};return next(specifier,context);},
 load(url,context,next){if(url==='oracle-recipient:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__recipientFixture;return {supabaseUrl:'${project}',auth:{async getUser(){return {data:{user:{id:f.user}},error:null}}}}}`};if(url==='oracle-recipient:employee')return {format:'module',shortCircuit:true,source:'export async function getUniqueEmployeeForAuthUserV1(){const f=globalThis.__recipientFixture;return f.ambiguous?null:{id:f.employee,disabledAt:f.disabledAt}};export const getEmployeeForAuthUser=getUniqueEmployeeForAuthUserV1;'};return next(url,context);}
});
let server:tls.Server|undefined;const sockets=new Set<tls.TLSSocket>();let requests=0;
const previous={...process.env};
try{
 const openssl=(...args:string[])=>execFileSync('openssl',args,{cwd:directory,stdio:'pipe'});
 openssl('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.crt','-days','1','-subj','/CN=Invented Recipient CA');
 for(const name of ['server','a','b','c','aw','bw','am','bm','ar','br','sr']){
  openssl('req','-newkey','rsa:2048','-nodes','-keyout',name+'.key','-out',name+'.csr','-subj','/CN=Invented '+name);
  writeFileSync(path(name+'.ext'),name==='server'?'subjectAltName=DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\n':'subjectAltName=URI:spiffe://oracle/recipient-'+name+'\nextendedKeyUsage=clientAuth\n');
  openssl('x509','-req','-in',name+'.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial','-out',name+'.crt','-days','1','-extfile',name+'.ext');
  chmodSync(path(name+'.key'),0o600);chmodSync(path(name+'.crt'),0o600);
 }
 chmodSync(path('ca.crt'),0o600);
 server=tls.createServer({key:readFileSync(path('server.key')),cert:readFileSync(path('server.crt')),ca:readFileSync(path('ca.crt')),requestCert:true,rejectUnauthorized:true,allowHalfOpen:true},socket=>{
  sockets.add(socket);socket.once('close',()=>sockets.delete(socket));socket.on('error',()=>undefined);
  const uri=socket.getPeerCertificate().subjectaltname,advice=uri==='URI:spiffe://oracle/recipient-ar'||uri==='URI:spiffe://oracle/recipient-br'||uri==='URI:spiffe://oracle/recipient-sr',n=uri==='URI:spiffe://oracle/recipient-a'||uri==='URI:spiffe://oracle/recipient-ar'||uri==='URI:spiffe://oracle/recipient-sr'?1:uri==='URI:spiffe://oracle/recipient-b'||uri==='URI:spiffe://oracle/recipient-br'?2:0;
  if(!socket.authorized||!n){socket.destroy();return;}let data=Buffer.alloc(0),done=false;
  socket.on('data',(part:Buffer)=>{data=Buffer.concat([data,part]);const i=data.indexOf('\r\n\r\n');if(i<0||done)return;const header=data.subarray(0,i).toString('ascii'),len=Number(/content-length: ([0-9]+)/i.exec(header)?.[1]);if(!len||data.length<i+4+len)return;done=true;requests++;
   assert.match(header,advice?/^POST \/v1\/replacement\/recommendation-actions HTTP\/1.1/:/^POST \/v1\/replacement\/control HTTP\/1.1/);assert.doesNotMatch(header,/authorization:|cookie:|actor:/i);
   const body=JSON.parse(data.subarray(i+4,i+4+len).toString('utf8'));
   if(advice){
    assert.equal(body.operation,'list');const result={schema_version:1,kind:'recommendation-index-v1',entries:[],coverage_gap:false,list_complete:true,scope:'current-permitted-model-advice',valid_until:body.caller_deadline,policy_accepted:false,effect_executed:false,business_acceptance:false};
    const raw=Buffer.from(canonicalJson({schema_version:1,principal_id:id(n+20),workspace_id:id(n+30),model_id:id(n+80),request_sha256:sha256(data.subarray(i+4,i+4+len)),operation:'list',command_id:null,expected_head:null,result}));socket.end(Buffer.concat([Buffer.from('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+raw.length+'\r\nConnection: close\r\n\r\n'),raw]));return;
   }
   if(body.run_id!==id(n+100)){socket.end('HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n');return;}
   const raw=Buffer.from(canonicalJson({runId:id(n+100),journeyRevision:n,controlState:'processing',populationSha256:String(n).repeat(64),cancelRequested:false,remoteStopProven:false,resultAvailable:false}));socket.end(Buffer.concat([Buffer.from('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+raw.length+'\r\nConnection: close\r\n\r\n'),raw]));
  });
 });server.on('tlsClientError',()=>undefined);await new Promise<void>(yes=>server!.listen(0,'::1',yes));const address=server.address();assert.ok(address&&typeof address!=='string');
 const end=new Date(Date.now()+180000).toISOString(),from=new Date(Date.now()-1000).toISOString();
 const recipients=[1,2,3].map(n=>{const name=n===1?'a':n===2?'b':'c';const binding:ServerBinding={schema_version:1,purpose:'replacement-web-binding-v1',project_url:project,auth_issuer:project+'/auth/v1',auth_user_id:id(n),employee_id:id(n+10),principal_id:id(n+20),workspace_id:id(n+30),runtime_hash:'a'.repeat(64),registry_hash:'b'.repeat(64),intake_appointment_sha256:'c'.repeat(64),peer_profile_sha256:'d'.repeat(64),web_origin:origin,backend_origin:'https://localhost.localdomain:'+address.port,control_path:'/v1/replacement/control',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(path('server.crt'))).raw),server_ca_file:path('ca.crt'),server_ca_sha256:hash('ca.crt'),client_certificate_file:path(name+'.crt'),client_certificate_sha256:hash(name+'.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(path(name+'.crt'))).raw),client_uri:'spiffe://oracle/recipient-'+name,client_key_file:path(name+'.key'),client_key_sha256:hash(name+'.key'),issuer_actor:id(501),reviewer_actor:id(502),valid_from:from,expires_at:end,original_horizon:end};writeFileSync(path(name+'.json'),canonicalJson(binding),{mode:0o600});const bindings:Record<string,{path:string;sha256:string}>={control:{path:path(name+'.json'),sha256:hash(name+'.json')}};
  if(n===3)return {project_url:project,auth_issuer:project+'/auth/v1',auth_user_id:id(n),employee_id:id(n+10),bindings};
  const adviceClient=name+'r',advice:Record<string,unknown>={...binding,purpose:'replacement-recommendation-actions-web-binding-v1',recommendation_path:'/v1/replacement/recommendation-actions',model_id:id(n+80),recommendation_config_sha256:'e'.repeat(64),recommendation_peer_profile_sha256:'f'.repeat(64),client_certificate_file:path(adviceClient+'.crt'),client_certificate_sha256:hash(adviceClient+'.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(path(adviceClient+'.crt'))).raw),client_uri:'spiffe://oracle/recipient-'+adviceClient,client_key_file:path(adviceClient+'.key'),client_key_sha256:hash(adviceClient+'.key')};for(const key of ['intake_appointment_sha256','peer_profile_sha256','control_path'])Reflect.deleteProperty(advice,key);writeFileSync(path(adviceClient+'.json'),canonicalJson(advice),{mode:0o600});bindings.recommendation={path:path(adviceClient+'.json'),sha256:hash(adviceClient+'.json')};
  for(const channel of ['web','mcp'] as const){const client=name+(channel==='web'?'w':'m'),record={...binding,purpose:channel==='web'?'qualified-connected-answer-web-binding-v1':'qualified-connected-answer-mcp-binding-v1',answer_path:channel==='web'?'/v1/employee/answer':'/v1/employee/mcp-answer',answer_config_sha256:'e'.repeat(64),answer_peer_sha256:'f'.repeat(64),model_id:id(n+70),client_certificate_file:path(client+'.crt'),client_certificate_sha256:hash(client+'.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(path(client+'.crt'))).raw),client_uri:'spiffe://oracle/recipient-'+client,client_key_file:path(client+'.key'),client_key_sha256:hash(client+'.key')};for(const key of ['intake_appointment_sha256','peer_profile_sha256','control_path'])Reflect.deleteProperty(record,key);writeFileSync(path(client+'.json'),canonicalJson(record),{mode:0o600});bindings[channel==='web'?'answer':'mcp-answer']={path:path(client+'.json'),sha256:hash(client+'.json')};}
  return {project_url:project,auth_issuer:project+'/auth/v1',auth_user_id:id(n),employee_id:id(n+10),bindings};});
 const index=canonicalJson({schema_version:1,purpose:'replacement-employee-recipient-index-v1',issuer_actor:id(601),reviewer_actor:id(602),valid_from:from,expires_at:end,original_horizon:end,recipients});writeFileSync(path('index.json'),index,{mode:0o600});
 process.env.NEXT_PUBLIC_SUPABASE_URL=project;
 const singleton={...JSON.parse(readFileSync(path('ar.json'),'utf8')),client_certificate_file:path('sr.crt'),client_certificate_sha256:hash('sr.crt'),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(path('sr.crt'))).raw),client_uri:'spiffe://oracle/recipient-sr',client_key_file:path('sr.key'),client_key_sha256:hash('sr.key')};writeFileSync(path('singleton.json'),canonicalJson(singleton),{mode:0o600});process.env.ORACLE2_RECOMMENDATION_ACTIONS_BINDING_FILE=path('singleton.json');process.env.ORACLE2_RECOMMENDATION_ACTIONS_BINDING_SHA256=hash('singleton.json');
 const {requestReplacementControl,authenticatedConnectedAnswerChannel,requestRecommendationActionsV1,authenticatedRecommendationPageAvailableV1}=await import('../../lib/replacement-protected-client');
 assert.equal(await authenticatedRecommendationPageAvailableV1(),true); // Truly valid retained singleton, not a vacuous missing-config fallback.
 process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE=path('index.json');process.env.ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256=hash('index.json');
 const installed=readInstalledEmployeeBindingV1('control',{configuredProjectUrl:project,actualProjectUrl:project,verifiedUserId:id(1),employeeId:id(11),disabledAt:null});assert.throws(()=>rereadInstalledEmployeeBindingV1({...installed}));
 async function ask(n:number,extra:Record<string,unknown>={}){const bytes=canonicalJson({schema_version:1,operation:'status',run_id:id(n+100),caller_deadline:new Date(Date.now()+5000).toISOString(),...extra});return requestReplacementControl(new Request(origin+'/api/control',{method:'POST',headers:{origin,'Content-Type':'application/json',[CONTROL_WINDOW_HEADER]:canonicalJson(captureControlWindow())},body:bytes}));}
 async function adviceAsk(extra:Record<string,unknown>={},webOrigin=origin){const bytes=canonicalJson({schema_version:1,operation:'list',caller_deadline:new Date(Date.now()+5000).toISOString().replace('.000Z','Z').replace(/\.(\d{3})Z$/,'.$1000Z'),...extra});return requestRecommendationActionsV1(new Request(origin+'/api/consultant/replacement/v1/protected/recommendation-actions',{method:'POST',headers:{origin:webOrigin,'Content-Type':'application/json',[CONTROL_WINDOW_HEADER]:canonicalJson(captureControlWindow())},body:bytes}));}
 for(const n of [1,2,1]){fixture.user=id(n);fixture.employee=id(n+10);const value=await ask(n);assert.equal(value.available,true);if(value.available)assert.equal(value.metadata.journeyRevision,n);
  assert.equal(await authenticatedRecommendationPageAvailableV1(),true);const advice=await adviceAsk();assert.equal(advice.status,200);assert.equal((await advice.json()).kind,'recommendation-index-v1');
  for(const channel of ['web','mcp'] as const){const request=new Request(origin+'/api/mcp',{method:'POST',headers:{origin,'Content-Type':'application/json',[CONTROL_WINDOW_HEADER]:canonicalJson(captureControlWindow())}});assert.equal(await authenticatedConnectedAnswerChannel(request,channel),true);}}

 fixture.user=id(3);fixture.employee=id(13);let before=requests;assert.equal((await adviceAsk()).status,503);assert.equal(await authenticatedRecommendationPageAvailableV1(),false);assert.equal(requests,before);
 fixture.user=id(4);fixture.employee=id(14);assert.deepEqual(await ask(1),{available:false});assert.equal(requests,before);
 fixture.user=id(1);fixture.employee=id(11);fixture.disabledAt='disabled';assert.equal((await adviceAsk()).status,503);assert.equal(await authenticatedRecommendationPageAvailableV1(),false);assert.deepEqual(await ask(1),{available:false});assert.equal(requests,before);fixture.disabledAt=null;
 fixture.ambiguous=true;assert.equal((await adviceAsk()).status,503);assert.deepEqual(await ask(1),{available:false});assert.equal(requests,before);fixture.ambiguous=false;
 assert.deepEqual(await ask(2),{available:false});assert.equal(requests,before+1);
 before=requests;assert.deepEqual(await ask(1,{actor:id(2)}),{available:false});assert.equal(requests,before);
 before=requests;assert.equal((await adviceAsk({actor:id(2)})).status,503);assert.equal((await adviceAsk({},'https://foreign.example.test')).status,503);assert.equal(requests,before);
 // Current protected profile/key drift cannot borrow a valid singleton or another employee.
 writeFileSync(path('ar.key'),'changed invented key');assert.equal((await adviceAsk()).status,503);assert.equal(await authenticatedRecommendationPageAvailableV1(),false);assert.equal(requests,before);
 fixture.user=id(2);fixture.employee=id(12);assert.equal((await adviceAsk()).status,200);before=requests;fixture.user=id(1);fixture.employee=id(11);
 renameSync(path('index.json'),path('index-old.json'));writeFileSync(path('index.json'),index,{mode:0o600});assert.deepEqual(await ask(1),{available:false});assert.equal(requests,before);assert.equal((await adviceAsk()).status,503);assert.equal(requests,before);
 console.log('INVENTED_RECIPIENT_WIRE_PROOF_PASS two distinct own control+recommendation TLS profiles; A/B/A isolation; ninth-purpose selected model/page isolation; missing-purpose/foreign/disabled/ambiguous/origin/key/index drift zero effects; foreign/disabled/ambiguous/payload actor/index replacement refuse; no real Auth/SQL acceptance');
}finally{
 hooks.deregister();for(const socket of sockets)socket.destroy();if(server)await new Promise<void>(yes=>server!.close(()=>yes()));
 for(const key of Object.keys(process.env))if(!(key in previous))delete process.env[key];Object.assign(process.env,previous);
 delete (globalThis as unknown as Record<string,unknown>).__recipientFixture;rmSync(directory,{recursive:true,force:true});
}
