/** Actual Python+SQL peers. Auth imports are invented test-process hooks only. */
import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import {X509Certificate,createHmac} from 'node:crypto';
import {join} from 'node:path';
import {canonicalJson,sha256} from '../../lib/replacement-server-binding';
import {captureControlWindow,CONTROL_WINDOW_HEADER,canonicalInstantV1} from '../../lib/replacement-control-window';
const input=process.argv[2];if(!input)throw new Error('Owned fixture metadata required');
const meta=JSON.parse(readFileSync(input,'utf8'));
(globalThis as unknown as Record<string,unknown>).__meetingPeerMeta=meta;
const hooks=registerHooks({
 resolve(specifier,context,next){
  if(context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'meeting-proof:auth',shortCircuit:true};
  if(context.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'meeting-proof:employee',shortCircuit:true};
  return next(specifier,context);
 },load(url,context,next){
  if(url==='meeting-proof:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const m=globalThis.__meetingPeerMeta;return {supabaseUrl:m.project_url,auth:{async getUser(){return {data:{user:{id:m.auth_user_id}},error:null}}}}}`};
  if(url==='meeting-proof:employee')return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(){return {id:globalThis.__meetingPeerMeta.employee_id,disabledAt:null}}`};
  return next(url,context);
 }});
const filePin=(file:string)=>sha256(readFileSync(file));
const binding=(p:Record<string,unknown>,service:boolean)=>({schema_version:1,purpose:service?'replacement-meeting-ingress-web-binding-v1':'replacement-meeting-control-web-binding-v1',principal_id:p.principal_id,workspace_id:p.workspace_id,runtime_hash:p.runtime_hash,registry_hash:p.registry_hash,meeting_id:meta.meeting_id,meeting_config_sha256:p.meeting_config_sha256,meeting_peer_profile_sha256:p.profile_sha256,backend_origin:p.backend_origin,server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(p.server_certificate_file as string)).raw),server_ca_file:p.client_ca_file,server_ca_sha256:filePin(p.client_ca_file as string),client_certificate_file:p.client_certificate_file,client_certificate_sha256:filePin(p.client_certificate_file as string),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(p.client_certificate_file as string)).raw),client_uri:p.client_uri,client_key_file:p.client_key_file,client_key_sha256:filePin(p.client_key_file as string),issuer_actor:p.issuer_actor,reviewer_actor:p.reviewer_actor,valid_from:p.valid_from,expires_at:p.expires_at,original_horizon:p.original_horizon,...(service?{ingress_path:'/v1/replacement/meetings/ingress',provider_account:meta.provider_account,verifier_secret_file:meta.verifier_secret_file,verifier_secret_sha256:filePin(meta.verifier_secret_file)}:{meeting_path:'/v1/replacement/meetings/control',project_url:meta.project_url,auth_issuer:meta.project_url+'/auth/v1',auth_user_id:meta.auth_user_id,employee_id:meta.employee_id,web_origin:'https://invented-web.example.test'})});
for(const [name,service]of [['control',false],['ingress',true]]as const){const path=join(meta.scratch,name+'-binding.json');writeFileSync(path,canonicalJson(binding(meta[name],service)),{mode:0o600});process.env[service?'ORACLE2_MEETING_INGRESS_BINDING_FILE':'ORACLE2_MEETING_CONTROL_BINDING_FILE']=path;process.env[service?'ORACLE2_MEETING_INGRESS_BINDING_SHA256':'ORACLE2_MEETING_CONTROL_BINDING_SHA256']=filePin(path);}
process.env.NEXT_PUBLIC_SUPABASE_URL=meta.project_url;
try{
 const control=await import('../../app/api/consultant/replacement/v1/protected/meetings/control/route');
 const {requestReplacementMeetingIngress}=await import('../../lib/replacement-protected-client');
 const deadline=canonicalInstantV1(Date.now()+8000);
 const wire=canonicalJson({schema_version:1,operation:'invite',meeting_id:meta.meeting_id,expected_head:0,operation_id:meta.operation_id,payload:{explicit_invitation:true,consent_observed:true},caller_deadline:deadline});
 const response=await control.POST(new Request('https://invented-web.example.test/api/consultant/replacement/v1/protected/meetings/control',{method:'POST',headers:{origin:'https://invented-web.example.test','content-type':'application/json',[CONTROL_WINDOW_HEADER]:canonicalJson(captureControlWindow())},body:wire}));
 assert.equal(response.status,200);const invited=await response.json();assert.equal(invited.state,'invited');assert.equal(invited.qualification,false);
 const raw=Buffer.from(JSON.stringify({event:'transcript.data',data:{bot:{id:'bot1'},data:{words:[{text:'原话',start_timestamp:{relative:0},end_timestamp:null}],participant:{id:7,name:'Untrusted label'},language_code:'zh'}}}));
 const id='actual-python-peer-message',stamp=String(Math.floor(Date.now()/1000)),secret=readFileSync(meta.verifier_secret_file,'utf8'),signature=createHmac('sha256',Buffer.from(secret.slice(6),'base64')).update(id+'.'+stamp+'.').update(raw).digest('base64');
 const ingress=await requestReplacementMeetingIngress(new Request('https://invented-web.example.test/api/teams/live/recall',{method:'POST',headers:{'content-type':'application/json','webhook-id':id,'webhook-timestamp':stamp,'webhook-signature':'v1,'+signature,[CONTROL_WINDOW_HEADER]:canonicalJson(captureControlWindow())},body:raw}));
 assert.equal(ingress.status,202);assert.equal(await ingress.text(),'');const retained={status:202,opaque_acknowledgement:true};
 writeFileSync(join(meta.scratch,'meeting-conformance.json'),JSON.stringify({invited,retained,raw_sha256:sha256(raw),auth_proof:'invented module hooks; no actual employee session'}));
}finally{hooks.deregister();}
