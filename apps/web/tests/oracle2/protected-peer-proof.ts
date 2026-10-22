/** Actual Python peer conformance, invented existing-auth imports only. */
import assert from 'node:assert/strict';
import { readFileSync,writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { registerHooks } from 'node:module';
import { X509Certificate } from 'node:crypto';
import { canonicalJson,sha256 } from '../../lib/replacement-server-binding';
import { captureControlWindow,CONTROL_WINDOW_HEADER } from '../../lib/replacement-control-window';
const meta=JSON.parse(readFileSync(process.argv[2]!,'utf8'));
(globalThis as unknown as Record<string,unknown>).__peerProofIdentity=meta;
const hook=registerHooks({
 resolve(specifier,ctx,next){if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'peer-proof:auth',shortCircuit:true};if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'peer-proof:employee',shortCircuit:true};return next(specifier,ctx);},
 load(url,ctx,next){if(url==='peer-proof:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__peerProofIdentity;return {supabaseUrl:f.project_url,auth:{async getUser(){return {data:{user:{id:f.auth_user_id}},error:null}}}}}`};if(url==='peer-proof:employee')return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(){return {id:globalThis.__peerProofIdentity.employee_id,disabledAt:null}}`};return next(url,ctx);},
});
const hashFile=(p:string)=>sha256(readFileSync(p));const c=meta.common;
const common={schema_version:1,project_url:meta.project_url,auth_issuer:meta.project_url+'/auth/v1',auth_user_id:meta.auth_user_id,employee_id:meta.employee_id,principal_id:c.principal_id,workspace_id:c.workspace_id,runtime_hash:c.runtime_hash,registry_hash:c.registry_hash,web_origin:'https://invented-web.example.test',backend_origin:meta.backend_origin,server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.server_certificate_file)).raw),server_ca_file:meta.client_ca_file,server_ca_sha256:hashFile(meta.client_ca_file),client_certificate_file:meta.client_certificate_file,client_certificate_sha256:hashFile(meta.client_certificate_file),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.client_certificate_file)).raw),client_uri:meta.client_uri,client_key_file:meta.client_key_file,client_key_sha256:hashFile(meta.client_key_file),issuer_actor:meta.issuer_actor,reviewer_actor:meta.reviewer_actor,valid_from:meta.valid_from,expires_at:meta.expires_at,original_horizon:meta.original_horizon};
const profile=meta.kind==='control'?{...common,purpose:'replacement-web-binding-v1',control_path:'/v1/replacement/control',intake_appointment_sha256:meta.intake_appointment_sha256,peer_profile_sha256:meta.peer_profile_sha256}:{...common,purpose:'replacement-original-web-binding-v1',original_path:'/v1/replacement/original',viewer_config_sha256:meta.viewer_config_sha256,viewer_appointment_sha256:meta.viewer_appointment_sha256,viewer_peer_profile_sha256:meta.peer_profile_sha256,storage_profile_hash:meta.storage_profile_hash,sources:meta.sources};
const path=join(meta.scratch,'peer-web-binding.json');writeFileSync(path,canonicalJson(profile),{mode:0o600});const selector=meta.kind==='control'?'SERVER':'VIEWER';process.env['ORACLE2_REPLACEMENT_'+selector+'_BINDING_FILE']=path;process.env['ORACLE2_REPLACEMENT_'+selector+'_BINDING_SHA256']=hashFile(path);
process.env.NEXT_PUBLIC_SUPABASE_URL=meta.project_url;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-peer-proof';
const client=await import('../../lib/replacement-protected-client');
try{
 const capture=captureControlWindow();const wire=Buffer.from(meta.request_wire_base64,'base64');const request=new Request(common.web_origin+'/api/consultant/replacement/v1/protected/'+(meta.kind==='control'?'control':'original'),{method:'POST',headers:{origin:common.web_origin,'content-type':'application/json',[CONTROL_WINDOW_HEADER]:canonicalJson(capture)},body:wire});
 if(meta.kind==='control'){const result=await client.requestReplacementControl(request);assert.equal(result.available,true);if(result.available){assert.equal(result.metadata.resultAvailable,false);assert.equal(result.metadata.remoteStopProven,false);assert.equal(Object.keys(result.metadata).length,7);}}
 else{const result=await client.requestReplacementOriginal(request);assert.equal(result.status,200);assert.equal(result.headers.get('content-type'),'application/pdf');const data=Buffer.from(await result.arrayBuffer());assert.equal(data.length,meta.expected_byte_count);assert.equal(sha256(data),meta.expected_sha256);}
 writeFileSync(join(meta.scratch,'peer-conformance.json'),JSON.stringify({kind:meta.kind,actual_python_backend:true,actual_mtls:true,shared_typescript_client:true,auth:'invented existing-import hooks',source_qualification:false})+'\n');
}finally{hook.deregister();}
