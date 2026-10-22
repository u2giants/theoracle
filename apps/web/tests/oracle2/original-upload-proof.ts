/** Test-only actual browser→production proxy/API→Python mTLS/store/SQL bridge.
 * Existing auth imports are explicit invented hooks, never real employee proof.
 * Invoked by the Python integration fixture with its protected metadata file.
 */
import assert from 'node:assert/strict';
import { readFileSync,writeFileSync } from 'node:fs';
import { resolve,join } from 'node:path';
import { registerHooks,createRequire } from 'node:module';
import { X509Certificate } from 'node:crypto';
import * as https from 'node:https';
import { Readable } from 'node:stream';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { chromium } from '@playwright/test';
import { NextRequest } from 'next/server';
import { canonicalJson,sha256,readInstalledUploadBinding,type UploadBinding } from '../../lib/replacement-server-binding';
const file=process.argv[2];assert.ok(file,'fixture metadata path required');
const meta=JSON.parse(readFileSync(file,'utf8'));
const identity={user:meta.auth_user_id,employee:meta.employee_id,project:meta.project_url,disabledAt:null,calls:0};
(globalThis as unknown as Record<string,unknown>).__uploadProofIdentity=identity;
(globalThis as unknown as Record<string,unknown>).React=React;
const hook=registerHooks({
 resolve(specifier,ctx,next){
  if(ctx.parentURL?.endsWith('/proxy.ts')&&specifier==='@supabase/ssr')return {url:'upload-proof:refresh',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'upload-proof:auth',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'upload-proof:employee',shortCircuit:true};
  if(ctx.parentURL?.includes('/replacement/upload/page.tsx')&&specifier==='@/lib/auth-guard')return {url:'upload-proof:page',shortCircuit:true};
  return next(specifier,ctx);
 },
 load(url,ctx,next){
  if(url==='upload-proof:refresh')return {format:'module',shortCircuit:true,source:`export function createServerClient(url,key,options){return {supabaseUrl:url,auth:{async getUser(){const f=globalThis.__uploadProofIdentity;options.cookies.setAll([{name:'invented-refresh',value:'retained',options:{secure:true,httpOnly:true,path:'/'}}]);return {data:{user:{id:f.user}},error:null}}}}}`};
  if(url==='upload-proof:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__uploadProofIdentity;return {supabaseUrl:f.project,auth:{async getUser(){f.calls++;return {data:{user:{id:f.user}},error:null}}}}}`};
  if(url==='upload-proof:employee')return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(){const f=globalThis.__uploadProofIdentity;return {id:f.employee,disabledAt:f.disabledAt}}`};
  if(url==='upload-proof:page')return {format:'module',shortCircuit:true,source:`export async function requireEmployee(){const f=globalThis.__uploadProofIdentity;if(f.disabledAt)throw new Error('Unavailable');return {id:f.employee}}`};
  return next(url,ctx);
 },
});
const {parseUploadResponse}=await import('../../lib/replacement-protected-client');
const proxy=await import('../../proxy');const route=await import('../../app/api/consultant/replacement/v1/protected/upload/route');const pageModule=await import('../../app/consultant/replacement/upload/page');
const req=createRequire(import.meta.url),tsxReq=createRequire(req.resolve('tsx/package.json'));const esbuild=tsxReq('esbuild') as typeof import('esbuild');
const built=await esbuild.build({stdin:{contents:`import React from 'react';import {hydrateRoot} from 'react-dom/client';import Form from './app/consultant/replacement/upload/upload-form';hydrateRoot(document.getElementById('root'),React.createElement(Form));`,resolveDir:resolve('.'),loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:resolve('tsconfig.json'),define:{'process.env.NODE_ENV':'"production"'}});
const javascript=built.outputFiles[0]!.contents;let binding:UploadBinding;const operations:string[]=[];const statuses:number[]=[];const sizes:number[]=[];const deadlines=new Set<string>();
const server=https.createServer({key:readFileSync(meta.server_key_file),cert:readFileSync(meta.server_certificate_file)},async(incoming,outgoing)=>{
 try{
  if(incoming.method==='GET'&&incoming.url==='/upload.js'){outgoing.writeHead(200,{'Content-Type':'text/javascript'});outgoing.end(javascript);return;}
  if(incoming.method==='GET'&&incoming.url==='/consultant/replacement/upload'){
   const rendered=renderToString(await pageModule.default());outgoing.writeHead(200,{'Content-Type':'text/html','Cache-Control':'no-store'});outgoing.end('<!doctype html><html><body>'+rendered.replace(/<form[\s\S]*?<\/form>/,form=>'<div id="root">'+form+'</div>')+'<script src="/upload.js"></script></body></html>');return;
  }
  const headers=new Headers();for(const [k,v]of Object.entries(incoming.headers))if(v!==undefined)headers.set(k,Array.isArray(v)?v.join(', '):v);
  const request=new NextRequest(binding.web_origin+incoming.url,{method:incoming.method,headers,body:Readable.toWeb(incoming),duplex:'half'} as NonNullable<ConstructorParameters<typeof NextRequest>[1]> & {duplex:'half'});
  writeFileSync(join(meta.scratch,'request-boundary.json'),JSON.stringify({origin:request.headers.get('origin'),url:request.url,method:request.method,content_type:request.headers.get('content-type'),headers:[...request.headers.keys()]})+'\n');
  const forward=await proxy.proxy(request);let response:Response;
  if(forward.headers.get('x-middleware-next')==='1'){
   const h=new Headers();for(const k of (forward.headers.get('x-middleware-override-headers')??'').split(','))if(k)h.set(k,forward.headers.get('x-middleware-request-'+k)??'');
   const bytes=Buffer.from(await request.arrayBuffer());const body=JSON.parse(bytes.toString());operations.push(body.operation);sizes.push(bytes.length);deadlines.add(body.caller_deadline);
   response=await route.POST(new Request(request.url,{method:'POST',headers:h,body:bytes}));
  }else response=forward;
  statuses.push(response.status);outgoing.writeHead(response.status,Object.fromEntries(response.headers));outgoing.end(Buffer.from(await response.arrayBuffer()));
 }catch{outgoing.writeHead(503,{'Cache-Control':'no-store'});outgoing.end();}
});
await new Promise<void>(r=>server.listen(0,'::1',r));const address=server.address();assert.ok(address&&typeof address!=='string');
const origin='https://localhost.localdomain:'+address.port;
const hashFile=(p:string)=>sha256(readFileSync(p));
binding={schema_version:1,purpose:'replacement-upload-web-binding-v1',project_url:identity.project,auth_issuer:identity.project+'/auth/v1',auth_user_id:identity.user,employee_id:identity.employee,principal_id:meta.principal_id,workspace_id:meta.workspace_id,runtime_hash:meta.runtime_hash,registry_hash:meta.registry_hash,intake_config_sha256:meta.intake_config_sha256,intake_appointment_sha256:meta.intake_appointment_sha256,upload_peer_profile_sha256:meta.upload_peer_profile_sha256,upload_spool_initialization_sha256:meta.upload_spool_initialization_sha256,storage_profile_hash:meta.storage_profile_hash,web_origin:origin,backend_origin:meta.backend_origin,upload_path:'/v1/replacement/upload/chunks',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.server_certificate_file)).raw),server_ca_file:meta.client_ca_file,server_ca_sha256:hashFile(meta.client_ca_file),client_certificate_file:meta.client_certificate_file,client_certificate_sha256:hashFile(meta.client_certificate_file),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.client_certificate_file)).raw),client_uri:meta.client_uri,client_key_file:meta.client_key_file,client_key_sha256:hashFile(meta.client_key_file),issuer_actor:meta.issuer_actor,reviewer_actor:meta.reviewer_actor,valid_from:meta.valid_from,expires_at:meta.expires_at,original_horizon:meta.original_horizon};
const bindingPath=join(meta.scratch,'web-binding.json');writeFileSync(bindingPath,canonicalJson(binding),{mode:0o600});process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_FILE=bindingPath;process.env.ORACLE2_REPLACEMENT_UPLOAD_BINDING_SHA256=hashFile(bindingPath);process.env.NEXT_PUBLIC_SUPABASE_URL=identity.project;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-browser-only';
writeFileSync(join(meta.scratch,'binding-startup.json'),JSON.stringify({loaded:!!readInstalledUploadBinding()})+'\n');
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({ignoreHTTPSErrors:true});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin+'/consultant/replacement/upload');
 // SSR page executes its existing guard import; the actual client form is
 // separately hydrated by this explicit fixture bundle, not a deployed Next build.
 const form=page.locator('#root');await form.getByLabel('Original PDF').waitFor();
 const data=Buffer.alloc(25*1024*1024,32);data.write('%PDF-1.7\nInvented actual browser full-stack custody only\n');
 await form.getByLabel('Original PDF').setInputFiles({name:'invented-browser.pdf',mimeType:'application/pdf',buffer:data});
 await form.getByRole('button',{name:'Upload original',exact:true}).click();try{await form.getByRole('status').filter({hasText:'Original uploaded. Reading and review are still required.'}).waitFor({timeout:30000});}catch(error){let parseResult='no backend result';try{parseUploadResponse(readFileSync(join(meta.scratch,'last-result.json')));parseResult='valid exact DTO';}catch(e){parseResult=e instanceof Error?e.stack??e.message:String(e);}
writeFileSync(join(meta.scratch,'browser-diagnostic.json'),JSON.stringify({statuses,operations,sizes,parseResult,identity_calls:identity.calls,message:await form.getByRole('status').textContent(),errors})+'\n');throw error;}
 assert.equal(operations.length,15);assert.deepEqual(operations,['begin',...Array(13).fill('chunk'),'finalize']);assert.equal(deadlines.size,1);assert.ok(sizes.every(n=>n<=2850000));assert.equal(errors.length,0);assert.ok(identity.calls>=60);
 await page.screenshot({path:join(meta.scratch,'browser-upload.png')});
 writeFileSync(join(meta.scratch,'browser-receipt.json'),JSON.stringify({actual_browser:true,auth:'invented existing-import hooks',framework:'actual page/form + explicit proxy/route HTTPS harness; not deployed Next routing',operations,sizes,deadline_count:deadlines.size,original_sha256:sha256(data),byte_count:data.length,identity_calls:identity.calls,page_errors:errors})+'\n');
}finally{await browser.close();server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));hook.deregister();}
