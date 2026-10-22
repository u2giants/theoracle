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
import { canonicalJson,sha256,readInstalledModelReviewBinding,type ModelReviewBinding } from '../../lib/replacement-server-binding';
const file=process.argv[2];assert.ok(file,'fixture metadata path required');
const meta=JSON.parse(readFileSync(file,'utf8'));
const identity={user:meta.auth_user_id,employee:meta.employee_id,project:meta.project_url,disabledAt:null as string|null,calls:0};
(globalThis as unknown as Record<string,unknown>).__uploadProofIdentity=identity;
(globalThis as unknown as Record<string,unknown>).React=React;
const hook=registerHooks({
 resolve(specifier,ctx,next){
  if(ctx.parentURL?.endsWith('/proxy.ts')&&specifier==='@supabase/ssr')return {url:'upload-proof:refresh',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'upload-proof:auth',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'upload-proof:employee',shortCircuit:true};
  if(ctx.parentURL?.includes('/replacement/review/page.tsx')&&specifier==='../../../../lib/auth-guard')return {url:'upload-proof:page',shortCircuit:true};
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
const proxy=await import('../../proxy');const route=await import('../../app/api/consultant/replacement/v1/protected/model-review/route');const pageModule=await import('../../app/consultant/replacement/review/page');
const req=createRequire(import.meta.url),tsxReq=createRequire(req.resolve('tsx/package.json'));const esbuild=tsxReq('esbuild') as typeof import('esbuild');
const built=await esbuild.build({stdin:{contents:`import React from 'react';import {hydrateRoot} from 'react-dom/client';import Form from './app/consultant/replacement/review/review';hydrateRoot(document.getElementById('root'),React.createElement(Form,{modelId:${JSON.stringify(meta.model_id)}}));`,resolveDir:resolve('.'),loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:resolve('tsconfig.json'),define:{'process.env.NODE_ENV':'"production"'}});
const javascript=built.outputFiles[0]!.contents;let binding:ModelReviewBinding;const operations:string[]=[];const statuses:number[]=[];
const server=https.createServer({key:readFileSync(meta.server_key_file),cert:readFileSync(meta.server_certificate_file)},async(incoming,outgoing)=>{
 try{
  if(incoming.method==='GET'&&incoming.url==='/review.js'){outgoing.writeHead(200,{'Content-Type':'text/javascript'});outgoing.end(javascript);return;}
  if(incoming.method==='GET'&&incoming.url==='/consultant/replacement/review'){
   const rendered=renderToString(await pageModule.default());outgoing.writeHead(200,{'Content-Type':'text/html','Cache-Control':'no-store'});outgoing.end('<!doctype html><html><body><div id="root">'+rendered+'</div><script src="/review.js"></script></body></html>');return;
  }
  const headers=new Headers();for(const [k,v]of Object.entries(incoming.headers))if(v!==undefined)headers.set(k,Array.isArray(v)?v.join(', '):v);
  const request=new NextRequest(binding.web_origin+incoming.url,{method:incoming.method,headers,body:Readable.toWeb(incoming),duplex:'half'} as NonNullable<ConstructorParameters<typeof NextRequest>[1]> & {duplex:'half'});
  const forward=await proxy.proxy(request);let response:Response;
  if(forward.headers.get('x-middleware-next')==='1'){
   const h=new Headers();for(const k of (forward.headers.get('x-middleware-override-headers')??'').split(','))if(k)h.set(k,forward.headers.get('x-middleware-request-'+k)??'');
   const bytes=Buffer.from(await request.arrayBuffer());operations.push(JSON.parse(bytes.toString()).operation);
   response=await route.POST(new Request(request.url,{method:'POST',headers:h,body:bytes}));
  }else response=forward;
  statuses.push(response.status);outgoing.writeHead(response.status,Object.fromEntries(response.headers));outgoing.end(Buffer.from(await response.arrayBuffer()));
 }catch(error){writeFileSync(join(meta.scratch,'web-error.txt'),String(error));outgoing.writeHead(503,{'Cache-Control':'no-store'});outgoing.end();}
});
await new Promise<void>(r=>server.listen(0,'::1',r));const address=server.address();assert.ok(address&&typeof address!=='string');
const origin='https://localhost.localdomain:'+address.port;
const hashFile=(p:string)=>sha256(readFileSync(p));
binding={schema_version:1,purpose:'replacement-model-review-web-binding-v1',project_url:identity.project,auth_issuer:identity.project+'/auth/v1',auth_user_id:identity.user,employee_id:identity.employee,principal_id:meta.principal_id,workspace_id:meta.workspace_id,runtime_hash:meta.runtime_hash,registry_hash:meta.registry_hash,model_id:meta.model_id,review_config_sha256:meta.review_config_sha256,review_peer_profile_sha256:meta.review_peer_profile_sha256,web_origin:origin,backend_origin:meta.backend_origin,review_path:'/v1/replacement/model-review',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.server_certificate_file)).raw),server_ca_file:meta.client_ca_file,server_ca_sha256:hashFile(meta.client_ca_file),client_certificate_file:meta.client_certificate_file,client_certificate_sha256:hashFile(meta.client_certificate_file),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.client_certificate_file)).raw),client_uri:meta.client_uri,client_key_file:meta.client_key_file,client_key_sha256:hashFile(meta.client_key_file),issuer_actor:meta.issuer_actor,reviewer_actor:meta.reviewer_actor,valid_from:meta.valid_from,expires_at:meta.expires_at,original_horizon:meta.original_horizon};
const bindingPath=join(meta.scratch,'web-binding.json');writeFileSync(bindingPath,canonicalJson(binding),{mode:0o600});process.env.ORACLE2_REPLACEMENT_REVIEW_BINDING_FILE=bindingPath;process.env.ORACLE2_REPLACEMENT_REVIEW_BINDING_SHA256=hashFile(bindingPath);process.env.NEXT_PUBLIC_SUPABASE_URL=identity.project;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-browser-only';
assert.ok(readInstalledModelReviewBinding());const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({ignoreHTTPSErrors:true});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin+'/consultant/replacement/review');await page.getByRole('button',{name:'Load review',exact:true}).click();
 try{await page.getByRole('radio').first().waitFor({timeout:20000});}catch(error){let parseResult='no factory result';try{const {parseModelReviewResponse}=await import('../../lib/replacement-protected-client');parseModelReviewResponse(readFileSync(join(meta.scratch,'factory-result.json')));parseResult='valid DTO';}catch(e){parseResult=String(e);}writeFileSync(join(meta.scratch,'browser-diagnostic.json'),JSON.stringify({statuses,operations,message:await page.locator('body').textContent(),errors,parseResult}));throw error;}
 await page.getByText('Changed account',{exact:true}).waitFor();await page.getByText('Earlier: documentary fixture',{exact:true}).waitFor();await page.getByText('Current: documentary correction fixture',{exact:true}).waitFor();await page.screenshot({path:join(meta.scratch,'browser-stale-diff.png')});
 await page.getByRole('button',{name:'Reload current version for a new decision',exact:true}).click();await page.getByRole('radio').first().waitFor();
 await page.getByRole('radio').first().check();await page.getByRole('button',{name:'Accept my reported account',exact:true}).click();
 await page.getByRole('status').filter({hasText:'Your account decision was recorded. Company policy remains unconfirmed.'}).waitFor({timeout:10000});
 await page.getByLabel('Version last reviewed').fill('1');await page.getByRole('button',{name:'Load review',exact:true}).click();await page.getByText('Your earlier version is unavailable. Its contents have been withheld.',{exact:true}).waitFor();assert.equal(await page.getByRole('radio').count(),0);
 assert.deepEqual(operations,['inspect','inspect','decide','inspect']);assert.deepEqual(statuses,[200,200,200,200]);assert.equal(errors.length,0);assert.ok(identity.calls>=8);
 // Actual existing identity owner refuses changed/disabled employee before peer.
 identity.disabledAt='invented-disabled';const denied=await page.evaluate(async()=>{const r=await fetch('/api/consultant/replacement/v1/protected/model-review',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return r.status;});assert.equal(denied,503);
 await page.screenshot({path:join(meta.scratch,'browser-review.png')});
 writeFileSync(join(meta.scratch,'browser-receipt.json'),JSON.stringify({actual_browser:true,auth:'invented existing-import hooks',framework:'actual page/component + explicit proxy/API HTTPS harness; not deployed Next routing',operations,statuses,identity_calls:identity.calls,page_errors:errors})+'\n');
}finally{await browser.close();server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));hook.deregister();}
