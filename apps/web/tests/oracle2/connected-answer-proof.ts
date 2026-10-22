/** Source-only invented auth hooks, actual browser/proxy/API/mTLS/SQL/SDK graph. */
import assert from 'node:assert/strict';
import {Session} from 'node:inspector';
// Native package loading precedes the test-only web auth import hooks.
import 'mcp-handler';
import 'zod';
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
import { canonicalJson,sha256,readInstalledConnectedAnswerBinding,readInstalledMcpAnswerBinding,type ConnectedAnswerBinding } from '../../lib/replacement-server-binding';
const meta=JSON.parse(readFileSync(process.argv[2]!,'utf8'));
// Invented-fixture diagnostic only. Exception behavior and every access guard remain unchanged.
const inspector=new Session();inspector.connect();inspector.post('Debugger.enable');inspector.post('Debugger.setPauseOnExceptions',{state:'all'});
const exceptions:unknown[]=[];inspector.on('Debugger.paused',event=>{try{const data=event.params;if(data.callFrames.some(f=>f.url.includes('replacement-protected-client')||f.url.includes('protected-control-window'))){exceptions.push({reason:data.reason,data:data.data,frames:data.callFrames.map(f=>({function:f.functionName,url:f.url,line:f.location.lineNumber}))});writeFileSync(join(meta.scratch,'client-exceptions.json'),JSON.stringify(exceptions),{mode:0o600});}}finally{inspector.post('Debugger.resume');}});
const identity={user:meta.auth_user_id,employee:meta.employee_id,project:meta.project_url,disabledAt:null as string|null,calls:0};
(globalThis as unknown as Record<string,unknown>).__connectedProofIdentity=identity;
(globalThis as unknown as Record<string,unknown>).React=React;
const hook=registerHooks({
 resolve(specifier,ctx,next){
  if(ctx.parentURL?.endsWith('/proxy.ts')&&specifier==='@supabase/ssr')return {url:'connected-proof:refresh',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./supabase/server')return {url:'connected-proof:auth',shortCircuit:true};
  if(ctx.parentURL?.includes('replacement-protected-client.ts')&&specifier==='./auth-guard')return {url:'connected-proof:employee',shortCircuit:true};
  if(ctx.parentURL?.includes('/consultant/ask/page.tsx')&&specifier==='@/lib/auth-guard')return {url:'connected-proof:page',shortCircuit:true};
  return next(specifier,ctx);
 },
 load(url,ctx,next){
  if(url==='connected-proof:refresh')return {format:'module',shortCircuit:true,source:`export function createServerClient(url,key,options){return {supabaseUrl:url,auth:{async getUser(){const f=globalThis.__connectedProofIdentity;options.cookies.setAll([{name:'invented-refresh',value:'retained',options:{secure:true,httpOnly:true,path:'/'}}]);return {data:{user:{id:f.user}},error:null}}}}}`};
  if(url==='connected-proof:auth')return {format:'module',shortCircuit:true,source:`export async function getServerSupabase(){const f=globalThis.__connectedProofIdentity;return {supabaseUrl:f.project,auth:{async getUser(){f.calls++;return {data:{user:{id:f.user}},error:null}}}}}`};
  if(url==='connected-proof:employee')return {format:'module',shortCircuit:true,source:`export async function getEmployeeForAuthUser(){const f=globalThis.__connectedProofIdentity;return {id:f.employee,disabledAt:f.disabledAt}}`};
  if(url==='connected-proof:page')return {format:'module',shortCircuit:true,source:`export async function requireEmployee(){const f=globalThis.__connectedProofIdentity;if(f.disabledAt)throw new Error('Unavailable');return {id:f.employee}}`};
  return next(url,ctx);
 },
});
const proxy=await import('../../proxy');const route=await import('../../app/api/consultant/replacement/v1/protected/answer/route');const mcp=await import('../../app/api/consultant/mcp/[transport]/route');const pageModule=await import('../../app/consultant/ask/page');
const req=createRequire(import.meta.url),tsxReq=createRequire(req.resolve('tsx/package.json'));const esbuild=tsxReq('esbuild') as typeof import('esbuild');
const built=await esbuild.build({stdin:{contents:`import React from 'react';import {hydrateRoot} from 'react-dom/client';import {ConnectedAnswerPanel} from './components/consultant/connected-answer-panel';hydrateRoot(document.getElementById('qualified-answer-client'),React.createElement(ConnectedAnswerPanel));`,resolveDir:resolve('.'),loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:resolve('tsconfig.json'),define:{'process.env.NODE_ENV':'"production"'}});
const javascript=built.outputFiles[0]!.contents;let binding:ConnectedAnswerBinding;const statuses:number[]=[];const operations:string[]=[];
const server=https.createServer({key:readFileSync(meta.server_key_file),cert:readFileSync(meta.server_certificate_file)},async(incoming,outgoing)=>{
 try{
  if(incoming.method==='GET'&&incoming.url==='/answer.js'){outgoing.writeHead(200,{'Content-Type':'text/javascript'});outgoing.end(javascript);return;}
  if(incoming.method==='GET'&&incoming.url==='/consultant/ask'){
   const rendered=renderToString(await pageModule.default());outgoing.writeHead(200,{'Content-Type':'text/html','Cache-Control':'no-store'});outgoing.end('<!doctype html><html><body><div id="root">'+rendered+'</div><script src="/answer.js"></script></body></html>');return;
  }
  const headers=new Headers();for(const [k,v]of Object.entries(incoming.headers))if(v!==undefined)headers.set(k,Array.isArray(v)?v.join(', '):v);
  const request=new NextRequest(binding.web_origin+incoming.url,{method:incoming.method,headers,body:Readable.toWeb(incoming),duplex:'half'} as NonNullable<ConstructorParameters<typeof NextRequest>[1]> & {duplex:'half'});
  const forward=await proxy.proxy(request);let response:Response;
  if(forward.headers.get('x-middleware-next')==='1'){
   const h=new Headers();for(const k of (forward.headers.get('x-middleware-override-headers')??'').split(','))if(k)h.set(k,forward.headers.get('x-middleware-request-'+k)??'');
   const bytes=Buffer.from(await request.arrayBuffer());const json=JSON.parse(bytes.toString());operations.push(json.method??json.query?.mode??'unknown');
   const rewritten=new Request(request.url,{method:'POST',headers:h,body:bytes});response=incoming.url==='/api/consultant/mcp/mcp'?await mcp.POST(rewritten):await route.POST(rewritten);
  }else response=forward;
  statuses.push(response.status);outgoing.writeHead(response.status,Object.fromEntries(response.headers));outgoing.end(Buffer.from(await response.arrayBuffer()));
 }catch(error){writeFileSync(join(meta.scratch,'web-error.txt'),String(error));outgoing.writeHead(503,{'Cache-Control':'no-store'});outgoing.end();}
});
await new Promise<void>(r=>server.listen(0,'::1',r));const address=server.address();assert.ok(address&&typeof address!=='string');const origin='https://localhost.localdomain:'+address.port;
const hashFile=(p:string)=>sha256(readFileSync(p));
function install(channel:'web'|'mcp',p:Record<'answer_config_sha256'|'answer_peer_sha256'|'backend_origin'|'client_certificate_file'|'client_key_file'|'client_uri',string>){
 const b={schema_version:1,purpose:channel==='web'?'qualified-connected-answer-web-binding-v1':'qualified-connected-answer-mcp-binding-v1',project_url:identity.project,auth_issuer:identity.project+'/auth/v1',auth_user_id:identity.user,employee_id:identity.employee,principal_id:meta.principal_id,workspace_id:meta.workspace_id,runtime_hash:meta.runtime_hash,registry_hash:meta.registry_hash,model_id:meta.model_id,answer_config_sha256:p.answer_config_sha256,answer_peer_sha256:p.answer_peer_sha256,web_origin:origin,backend_origin:p.backend_origin,answer_path:channel==='web'?'/v1/employee/answer':'/v1/employee/mcp-answer',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.server_certificate_file)).raw),server_ca_file:meta.client_ca_file,server_ca_sha256:hashFile(meta.client_ca_file),client_certificate_file:p.client_certificate_file,client_certificate_sha256:hashFile(p.client_certificate_file),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(p.client_certificate_file)).raw),client_uri:p.client_uri,client_key_file:p.client_key_file,client_key_sha256:hashFile(p.client_key_file),issuer_actor:meta.issuer_actor,reviewer_actor:meta.reviewer_actor,valid_from:meta.valid_from,expires_at:meta.expires_at,original_horizon:meta.original_horizon};
 const path=join(meta.scratch,channel+'-binding.json');writeFileSync(path,canonicalJson(b),{mode:0o600});const prefix=channel==='web'?'ORACLE2_CONNECTED_ANSWER':'ORACLE2_MCP_ANSWER';process.env[prefix+'_BINDING_FILE']=path;process.env[prefix+'_BINDING_SHA256']=hashFile(path);return b as ConnectedAnswerBinding;
}
binding=install('web',meta.web);install('mcp',meta.mcp);process.env.NEXT_PUBLIC_SUPABASE_URL=identity.project;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY='invented-browser-only';
assert.ok(readInstalledConnectedAnswerBinding());assert.ok(readInstalledMcpAnswerBinding());const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({ignoreHTTPSErrors:true});const errors:string[]=[];page.on('pageerror',e=>{errors.push(e.message);writeFileSync(join(meta.scratch,'page-errors.json'),JSON.stringify(errors));});
 await page.goto(origin+'/consultant/ask');
 await page.getByLabel('Your question').fill('What is reported across all processes?');await page.getByRole('button',{name:'Ask',exact:true}).click();
 try{await page.getByText('Reported account',{exact:false}).first().waitFor({timeout:20000});}catch(error){writeFileSync(join(meta.scratch,'browser-diagnostic.json'),JSON.stringify({statuses,operations,body:await page.locator('body').textContent(),errors}));await page.screenshot({path:join(meta.scratch,'browser-diagnostic.png')});throw error;}
 assert.ok(await page.getByRole('link',{name:'Open original under current access'}).count());
 await page.getByText('Coverage and limits',{exact:true}).click();await page.getByText('Dates and retained history',{exact:true}).click();
 const processes=meta.process_expectations as {label:string;process_id:string;assertion_ids:string[]}[];assert.ok(processes.length>=2);
 for(const process of processes.slice(0,2)){
  const question='What is reported in '+process.label+'?';await page.getByLabel('Your question').fill(question);
  const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/consultant/replacement/v1/protected/answer'&&r.request().postDataJSON().question===question,{timeout:20000});
  await page.getByRole('button',{name:'Ask',exact:true}).click();const observed=await response;assert.equal(observed.status(),200);
  const body=await observed.json();assert.equal(body.resolved_mode,'local');
  assert.deepEqual(body.answer.coverage.represented_process_ids,[process.process_id]);
  assert.deepEqual(body.answer.records.map((r:{assertion:{assertion_id:string}})=>r.assertion.assertion_id).sort(),process.assertion_ids);
  await page.getByText('Reported account',{exact:false}).first().waitFor({timeout:20000});
 }
 await page.getByLabel('Your question').fill('What happens to it next?');await page.getByRole('button',{name:'Ask',exact:true}).click();await page.getByText('Which process or reported action do you mean in this question?',{exact:true}).waitFor();assert.equal(await page.getByRole('link',{name:'Open original under current access'}).count(),0);
 await page.getByLabel('Your question').fill('What is reported across all processes?');
 const finalResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/consultant/replacement/v1/protected/answer'&&r.request().postDataJSON().question==='What is reported across all processes?',{timeout:20000});
 await page.getByRole('button',{name:'Ask',exact:true}).click();const finalObserved=await finalResponse;writeFileSync(join(meta.scratch,'final-global-response.json'),JSON.stringify({status:finalObserved.status(),body:await finalObserved.text()}),{mode:0o600});assert.equal(finalObserved.status(),200);await page.getByRole('link',{name:'Open original under current access'}).first().waitFor();
 const rpc=await page.evaluate<Record<'initialize'|'list'|'answer',{status:number;text:string}>>(`(async()=>{
  async function call(method,params,id){const r=await fetch('/api/consultant/mcp/mcp',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'},body:JSON.stringify({jsonrpc:'2.0',id,method,params})});const text=await r.text();return {status:r.status,text};}
  const initialize=await call('initialize',{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'invented-employee-browser-MCP',version:'1'}},1);
  const list=await call('tools/list',{},2);
  const answer=await call('tools/call',{name:'oracle_ask_question',arguments:{question:'What is reported across all processes?'}},3);
  return {initialize,list,answer};
 })()`);
 writeFileSync(join(meta.scratch,'mcp-protocol.json'),JSON.stringify(rpc));
 for(const result of Object.values(rpc))assert.equal(result.status,200);
 const parseRpc=(raw:string)=>JSON.parse(raw.startsWith('event:')||raw.startsWith('data:')?raw.split('\n').find(l=>l.startsWith('data:'))!.slice(5).trim():raw);
 assert.equal(parseRpc(rpc.initialize.text).result.serverInfo.name,'oracle-employee-qualified-records');
 assert.deepEqual(parseRpc(rpc.list.text).result.tools.map((t:{name:string})=>t.name),['oracle_ask_question','oracle_connected_answer']);
 const tool=parseRpc(rpc.answer.text);assert.ok(!tool.result.isError,JSON.stringify(tool));assert.ok(JSON.parse(tool.result.content[0].text).answer.records.length);
 identity.disabledAt='invented-disabled';await page.getByRole('button',{name:'Ask',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.getByRole('link',{name:'Open original under current access'}).count(),0);
 const denied=await page.evaluate(async()=>{const r=await fetch('/api/consultant/mcp/mcp',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return r.status;});assert.equal(denied,503);
 identity.disabledAt=null;identity.user='00000000-0000-0000-0000-000000000001';const foreign=await page.evaluate(async()=>{const r=await fetch('/api/consultant/replacement/v1/protected/answer',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return r.status;});assert.equal(foreign,503);
 assert.equal(errors.length,0,JSON.stringify(errors));await page.screenshot({path:join(meta.scratch,'browser-answer-access-denied.png')});
 writeFileSync(join(meta.scratch,'browser-receipt.json'),JSON.stringify({actual_browser:true,auth:'explicit invented existing import hooks',framework:'actual page/component+proxy/API/mcp-handler in explicit HTTPS harness; not deployed Next routing',operations,statuses,identity_calls:identity.calls,page_errors:errors})+'\n');
}finally{await browser.close();server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));hook.deregister();inspector.disconnect();}
