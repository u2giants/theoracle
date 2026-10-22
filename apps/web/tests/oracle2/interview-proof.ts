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
import { canonicalJson,sha256,readInstalledConversationBinding,type ConversationBinding } from '../../lib/replacement-server-binding';
const file=process.argv[2];assert.ok(file,'fixture metadata path required');
const meta=JSON.parse(readFileSync(file,'utf8'));
const identity={user:meta.auth_user_id,employee:meta.employee_id,project:meta.project_url,disabledAt:null as unknown,calls:0};
(globalThis as unknown as Record<string,unknown>).__conversationProofIdentity=identity;
(globalThis as unknown as Record<string,unknown>).React=React;
const hook=registerHooks({
 resolve(specifier,ctx,next){
  if(ctx.parentURL?.endsWith('/proxy.ts')&&specifier==='@supabase/ssr')return {url:'conversation-proof:refresh',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'conversation-proof:auth',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'conversation-proof:employee',shortCircuit:true};
  if(ctx.parentURL?.includes('/consultant/interviews/')&&specifier==='@/lib/auth-guard')return {url:'conversation-proof:page',shortCircuit:true};
  return next(specifier,ctx);
 },
 load(url,ctx,next){
  if(url==='conversation-proof:refresh')return {format:'module',shortCircuit:true,source:`export function createServerClient(url,key,options){return {supabaseUrl:url,auth:{async getUser(){const f=globalThis.__conversationProofIdentity;options.cookies.setAll([{name:'invented-refresh',value:'retained',options:{secure:true,httpOnly:true,path:'/'}}]);return {data:{user:{id:f.user}},error:null}}}}}`};
  if(url==='conversation-proof:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__conversationProofIdentity;return {supabaseUrl:f.project,auth:{async getUser(){f.calls++;return {data:{user:{id:f.user}},error:null}}}}}`};
  if(url==='conversation-proof:employee')return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(){const f=globalThis.__conversationProofIdentity;return {id:f.employee,disabledAt:f.disabledAt}}`};
  if(url==='conversation-proof:page')return {format:'module',shortCircuit:true,source:`export async function requireEmployee(){const f=globalThis.__conversationProofIdentity;if(f.disabledAt)throw new Error('Unavailable');return {id:f.employee}}`};
  if(url.startsWith("file:")&&ctx.format==="commonjs")return {format:"commonjs",source:readFileSync(new URL(url),"utf8"),shortCircuit:true};
  return next(url,ctx);
 },
});

const proxy=await import('../../proxy');const route=await import('../../app/api/consultant/interviews/route');
const detailRoute=await import('../../app/api/consultant/interviews/[id]/turns/route');
const indexPage=await import('../../app/consultant/interviews/page');const detailPage=await import('../../app/consultant/interviews/[id]/page');
const req=createRequire(import.meta.url),tsxReq=createRequire(req.resolve('tsx/package.json'));const esbuild=tsxReq('esbuild') as typeof import('esbuild');
const built=await esbuild.build({stdin:{contents:`import React from 'react';import {hydrateRoot} from 'react-dom/client';import {InterviewPanel} from './components/consultant/interview-panel';const match=location.pathname.match(/interviews\\/([0-9a-f-]+)$/);hydrateRoot(document.getElementById('root'),React.createElement(InterviewPanel,{threadId:match?.[1]}));`,resolveDir:resolve('.'),loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:resolve('tsconfig.json'),define:{'process.env.NODE_ENV':'"production"'}});
const javascript=built.outputFiles[0]!.contents;let binding:ConversationBinding;const operations:string[]=[];const statuses:number[]=[];let lastPacket:Record<string,unknown>|undefined;
const server=https.createServer({key:readFileSync(meta.server_key_file),cert:readFileSync(meta.server_certificate_file)},async(incoming,outgoing)=>{
 try{
  if(incoming.method==='GET'&&incoming.url==='/conversation.js'){outgoing.writeHead(200,{'Content-Type':'text/javascript'});outgoing.end(javascript);return;}
  if(incoming.method==='GET'&&incoming.url?.startsWith('/consultant/interviews')){
   const match=incoming.url.match(/interviews\/([0-9a-f-]+)$/);const rendered=renderToString(match?await detailPage.default({params:Promise.resolve({id:match[1]!})}):await indexPage.default());
   outgoing.writeHead(200,{'Content-Type':'text/html','Cache-Control':'no-store'});outgoing.end('<!doctype html><html><body>'+rendered.replace(/<section[\s\S]*<\/section>/,section=>'<div id="root">'+section+'</div>')+'<script src="/conversation.js"></script></body></html>');return;
  }
  const headers=new Headers();for(const [k,v]of Object.entries(incoming.headers))if(v!==undefined)headers.set(k,Array.isArray(v)?v.join(', '):v);
  const request=new NextRequest(binding.web_origin+incoming.url,{method:incoming.method,headers,body:Readable.toWeb(incoming),duplex:'half'} as NonNullable<ConstructorParameters<typeof NextRequest>[1]>&{duplex:'half'});
  const forward=await proxy.proxy(request);let response:Response;
  if(forward.headers.get('x-middleware-next')==='1'){
   const h=new Headers();for(const k of(forward.headers.get('x-middleware-override-headers')??'').split(','))if(k)h.set(k,forward.headers.get('x-middleware-request-'+k)??'');
   const bytes=Buffer.from(await request.arrayBuffer());const q=JSON.parse(bytes.toString());operations.push(q.operation??'create');
   response=await (new URL(request.url).pathname==='/api/consultant/interviews'?route:detailRoute).POST(new Request(request.url,{method:'POST',headers:h,body:bytes}));
  }else response=forward;
  const bytes=Buffer.from(await response.arrayBuffer());if(response.status===200)lastPacket=JSON.parse(bytes.toString());
  statuses.push(response.status);outgoing.writeHead(response.status,Object.fromEntries(response.headers));outgoing.end(bytes);
 }catch{outgoing.writeHead(503,{'Cache-Control':'no-store'});outgoing.end();}
});
await new Promise<void>(r=>server.listen(0,'::1',r));const address=server.address();assert.ok(address&&typeof address!=='string');
const origin='https://localhost.localdomain:'+address.port;const hashFile=(p:string)=>sha256(readFileSync(p));
binding={schema_version:1,purpose:'employee-conversation-web-binding-v1',project_url:identity.project,auth_issuer:identity.project+'/auth/v1',auth_user_id:identity.user,employee_id:identity.employee,principal_id:meta.principal_id,workspace_id:meta.workspace_id,runtime_hash:meta.runtime_hash,registry_hash:meta.registry_hash,conversation_config_sha256:meta.conversation_config_sha256,conversation_appointment_sha256:meta.conversation_appointment_sha256,conversation_peer_profile_sha256:meta.conversation_peer_profile_sha256,web_origin:origin,backend_origin:meta.backend_origin,conversation_path:'/v1/employee/conversation',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.server_certificate_file)).raw),server_ca_file:meta.client_ca_file,server_ca_sha256:hashFile(meta.client_ca_file),client_certificate_file:meta.client_certificate_file,client_certificate_sha256:hashFile(meta.client_certificate_file),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.client_certificate_file)).raw),client_uri:meta.client_uri,client_key_file:meta.client_key_file,client_key_sha256:hashFile(meta.client_key_file),issuer_actor:meta.issuer_actor,reviewer_actor:meta.reviewer_actor,valid_from:meta.valid_from,expires_at:meta.expires_at,original_horizon:meta.original_horizon};
const path=join(meta.scratch,'conversation-web-binding.json');writeFileSync(path,canonicalJson(binding),{mode:0o600});
process.env.ORACLE2_CONVERSATION_BINDING_FILE=path;process.env.ORACLE2_CONVERSATION_BINDING_SHA256=hashFile(path);process.env.NEXT_PUBLIC_SUPABASE_URL=identity.project;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-browser-only';readInstalledConversationBinding();
const browser=await chromium.launch({headless:true});const errors:string[]=[];
const page=await browser.newPage({ignoreHTTPSErrors:true});
try{
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(origin+'/consultant/interviews');await page.getByLabel('Topic',{exact:true}).fill('Invented packing process');
 await page.getByLabel('Original language',{exact:true}).fill('zh-Hans');await page.getByRole('button',{name:'Start an interview (up to 8 questions)',exact:true}).click();
 await page.waitForURL(/\/consultant\/interviews\/[0-9a-f-]+$/);await page.getByTestId('interview-question').waitFor();
 const first=lastPacket as unknown as {thread_id:string;pending_question_id:string;question_count:number};assert.equal(first.question_count,1);
 await page.getByLabel('Original language',{exact:true}).fill('zh-Hans');await page.getByLabel('Your response or direct question',{exact:true}).fill('不允许未经复核就发货。仅限样品。');await page.getByRole('button',{name:'Send response',exact:true}).click();
 await page.locator('ol').getByText('不允许未经复核就发货。仅限样品。',{exact:true}).waitFor();const afterAnswer=lastPacket as unknown as typeof first;assert.equal(afterAnswer.question_count,2);const pending=afterAnswer.pending_question_id;
 await page.getByRole('button',{name:'Pause',exact:true}).click();await page.getByRole('button',{name:'Resume',exact:true}).waitFor();await page.reload();await page.getByRole('button',{name:'Resume',exact:true}).waitFor();
 assert.equal((lastPacket as unknown as typeof first).question_count,2);await page.getByRole('button',{name:'Resume',exact:true}).click();await page.getByTestId('interview-question').waitFor();assert.equal((lastPacket as unknown as typeof first).pending_question_id,pending);
 await page.getByRole('button',{name:'Correct this response',exact:true}).click();await page.getByRole('textbox',{name:/Your corrected original response/}).fill('样品也必须复核。');await page.getByRole('button',{name:'Save correction',exact:true}).click();await page.locator('ol').getByText('样品也必须复核。',{exact:true}).waitFor();
 assert.equal((lastPacket as unknown as typeof first).question_count,2);assert.equal(await page.locator('ol').getByText('不允许未经复核就发货。仅限样品。',{exact:true}).count(),1);
 await page.getByRole('button',{name:'Review recap',exact:true}).click();await page.getByRole('button',{name:'I reviewed this exact account',exact:true}).click();await page.getByText('Your earlier account review is retained. It does not approve company policy.',{exact:true}).waitFor();
 await page.screenshot({path:join(meta.scratch,'interview-browser.png'),fullPage:true});
 assert.equal(errors.length,0);assert.ok(identity.calls>=30);assert.ok(statuses.every(s=>s===200));
 // Actual production identity adapter must still deny a disabled employee.
 identity.disabledAt='invented-disabled';const denied=await page.evaluate(async()=>{const r=await fetch('/api/consultant/interviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({schema_version:1,operation:'list',caller_deadline:new Date(Date.now()+15000).toISOString()})});return {status:r.status,body:await r.text()};});assert.equal(denied.status,503);assert.ok(!denied.body.includes('不允许'));
 await page.getByRole('button',{name:'Refresh saved history',exact:true}).click();
 await page.getByText('This conversation is unavailable. Saved history remains on the server; its contents are withheld until access is verified.',{exact:true}).waitFor();
 assert.equal(await page.locator('ol').getByText('不允许未经复核就发货。仅限样品。',{exact:true}).count(),0);
 assert.equal(await page.locator('ol').getByText('样品也必须复核。',{exact:true}).count(),0);
 assert.equal(await page.getByRole('button',{name:'Correct this response',exact:true}).count(),0);
 assert.equal(await page.getByRole('textbox',{name:/Your corrected original response/}).count(),0);
 writeFileSync(join(meta.scratch,'interview-browser-receipt.json'),JSON.stringify({actual_browser:true,auth:'invented existing-import hooks',framework:'actual pages/component + explicit production proxy/route HTTPS harness; not deployed Next routing',thread_id:first.thread_id,operations,question_count:2,pause_refresh_resume_same_question:true,exact_original_and_correction:true,company_policy_confirmed:false,identity_calls:identity.calls,disabled_employee_status:denied.status,denied_visible_history_withheld:true,page_errors:errors})+'\n');
}catch(error){await page.screenshot({path:join(meta.scratch,'interview-browser-failure.png'),fullPage:true});writeFileSync(join(meta.scratch,'interview-browser-diagnostic.json'),JSON.stringify({statuses,operations,lastPacket,errors})+'\n');throw error;}
finally{await browser.close();server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));hook.deregister();}
