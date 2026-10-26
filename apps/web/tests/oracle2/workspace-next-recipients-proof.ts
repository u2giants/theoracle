/** Actual Next + SDK HTTPS auth + employee SQL + separate installed recipients.
 * All users/content/appointments are invented. No production import is replaced.
 */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {X509Certificate,randomUUID} from 'node:crypto';
import {chromium,type Page,type BrowserContext} from '@playwright/test';
import {createAuthClient,type CookieAdapter} from '../../../../packages/auth/src/server';
import {canonicalJson,sha256,type ConnectedAnswerBinding} from '../../lib/replacement-server-binding';
import {parseWorkspaceAnswerV1} from '@oracle/shared/protected-natural-question-contract';
import {canonicalInstantV1} from '@oracle/shared/protected-control-window';
import {inventedAuthService} from './invented-auth-service';
const meta=JSON.parse(readFileSync(process.argv[2]!,'utf8'));
assert.equal(meta.workflow_fixture,'workspace-artwork-rework-v1');assert.equal(typeof meta.workflow_quote,'string');
type Recipient={auth_user_id:string;employee_id:string;principal_id:string;workspace_id:string;model_id:string;runtime_hash:string;registry_hash:string;answer_config_sha256:string;answer_peer_sha256:string;backend_origin:string;client_certificate_file:string;client_key_file:string;client_uri:string;issuer_actor:string;reviewer_actor:string;valid_from:string;expires_at:string;original_horizon:string};
const recipients=meta.recipients as Recipient[];assert.equal(recipients.length,2);
const auth=await inventedAuthService({...meta,auth_user_id:recipients[0]!.auth_user_id,auth_user_ids:recipients.map(r=>r.auth_user_id)});
const allocated=createServer();await new Promise<void>(r=>allocated.listen(0,'::1',r));const address=allocated.address();assert.ok(address&&typeof address!=='string');const port=address.port;await new Promise<void>(r=>allocated.close(()=>r()));
const origin='https://localhost.localdomain:'+port,hashFile=(p:string)=>sha256(readFileSync(p));
const end=canonicalInstantV1(Math.min(Date.parse(meta.proof_valid_until),...recipients.flatMap(r=>[Date.parse(r.expires_at),Date.parse(r.original_horizon)])));
const entries=recipients.map((r,index)=>{
 const binding:ConnectedAnswerBinding={schema_version:1,purpose:'qualified-connected-answer-web-binding-v1',project_url:auth.origin,auth_issuer:auth.origin+'/auth/v1',auth_user_id:r.auth_user_id,employee_id:r.employee_id,principal_id:r.principal_id,workspace_id:r.workspace_id,runtime_hash:r.runtime_hash,registry_hash:r.registry_hash,model_id:r.model_id,answer_config_sha256:r.answer_config_sha256,answer_peer_sha256:r.answer_peer_sha256,web_origin:origin,backend_origin:r.backend_origin,answer_path:'/v1/employee/answer',server_dns:'localhost.localdomain',server_certificate_der_sha256:sha256(new X509Certificate(readFileSync(meta.server_certificate_file)).raw),server_ca_file:meta.client_ca_file,server_ca_sha256:hashFile(meta.client_ca_file),client_certificate_file:r.client_certificate_file,client_certificate_sha256:hashFile(r.client_certificate_file),client_certificate_der_sha256:sha256(new X509Certificate(readFileSync(r.client_certificate_file)).raw),client_uri:r.client_uri,client_key_file:r.client_key_file,client_key_sha256:hashFile(r.client_key_file),issuer_actor:r.issuer_actor,reviewer_actor:r.reviewer_actor,valid_from:r.valid_from,expires_at:end,original_horizon:end};
 const path=join(meta.scratch,'recipient-'+index+'.json');writeFileSync(path,canonicalJson(binding),{mode:0o600});
 return {project_url:auth.origin,auth_issuer:auth.origin+'/auth/v1',auth_user_id:r.auth_user_id,employee_id:r.employee_id,bindings:{answer:{path,sha256:hashFile(path)}}};
});
const indexPath=join(meta.scratch,'recipient-index.json');writeFileSync(indexPath,canonicalJson({schema_version:1,purpose:'replacement-employee-recipient-index-v1',issuer_actor:randomUUID(),reviewer_actor:randomUUID(),valid_from:canonicalInstantV1(Math.max(...recipients.map(r=>Date.parse(r.valid_from)))),expires_at:end,original_horizon:end,recipients:entries}),{mode:0o600});
process.env.NEXT_PUBLIC_SUPABASE_URL=auth.origin;process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY=auth.anon;
const jars=[] as ReturnType<CookieAdapter['getAll']>[];
for(const session of auth.sessions){
 const jar:ReturnType<CookieAdapter['getAll']>=[];const adapter:CookieAdapter={getAll:()=>jar,setAll:values=>{for(const cookie of values){const i=jar.findIndex(c=>c.name===cookie.name);if(i>=0)jar.splice(i,1);jar.push({name:cookie.name,value:cookie.value});}}};
 const seeded=await createAuthClient(adapter).auth.setSession({access_token:session.token,refresh_token:'invented-no-refresh'});assert.equal(seeded.error,null);assert.equal(seeded.data.user?.id,session.user);assert.ok(jar.length);jars.push(jar);
}
const allowed=['PATH','HOME','TMPDIR','LANG','SHELL','NODE_EXTRA_CA_CERTS'];const env:NodeJS.ProcessEnv={...Object.fromEntries(allowed.filter(k=>process.env[k]).map(k=>[k,process.env[k]])),NODE_ENV:'development'};
Object.assign(env,{NODE_ENV:'development',NEXT_TELEMETRY_DISABLED:'1',DATABASE_URL:meta.web_database_url,NEXT_PUBLIC_SUPABASE_URL:auth.origin,NEXT_PUBLIC_SUPABASE_ANON_KEY:auth.anon,ORACLE2_WORKSPACE_ENABLED:'true',ORACLE2_EMPLOYEE_RECIPIENT_INDEX_FILE:indexPath,ORACLE2_EMPLOYEE_RECIPIENT_INDEX_SHA256:hashFile(indexPath)});
assert.ok(!env.NODE_OPTIONS&&!env.SUPABASE_SERVICE_ROLE_KEY&&!env.ORACLE2_NATIVE_BROWSER_BUILD&&!env.ORACLE2_CONNECTED_ANSWER_BINDING_FILE);
const child=spawn('pnpm',['exec','next','dev','--turbopack','--hostname','localhost.localdomain','--port',String(port),'--experimental-https','--experimental-https-key',meta.server_key_file,'--experimental-https-cert',meta.server_certificate_file,'--experimental-https-ca',env.NODE_EXTRA_CA_CERTS!],{cwd:resolve('.'),env,stdio:['ignore','pipe','pipe']});
let output='';child.stdout.on('data',d=>{output+=d.toString();});child.stderr.on('data',d=>{output+=d.toString();});
let browser:Awaited<ReturnType<typeof chromium.launch>>|undefined;const contexts:BrowserContext[]=[],pages:Page[]=[];const pageErrors:string[]=[],downloadCounts=[0,0],statuses:Record<string,number>={},responseCounts=[0,0];const originalRequests:{remaining_ms:number}[]=[];
const start=Date.now(),endpoint='/api/consultant/replacement/v1/protected/answer';
const query=(extra:Record<string,unknown>={})=>canonicalJson({schema_version:1,protocol:'qualified-workspace-question-v1',operation:'overview',process_id:null,page:0,caller_deadline:canonicalInstantV1(Date.now()+20000),...extra});
async function action(page:Page,name:string,index:number,expected=200){
 const pending=page.waitForResponse(r=>new URL(r.url()).pathname===endpoint,{timeout:20000});await page.getByRole('button',{name,exact:true}).first().click();const response=await pending;assert.equal(response.status(),expected);statuses['action-'+Object.keys(statuses).length]=response.status();
 if(expected===200){const packet=parseWorkspaceAnswerV1(Buffer.from(await response.body()));assert.equal(packet.principal_id,recipients[index]!.principal_id);assert.equal(packet.workspace_id,recipients[index]!.workspace_id);assert.equal(packet.model_id,recipients[index]!.model_id);assert.equal(packet.company_policy,false);assert.equal(packet.automatic_action_authorized,false);responseCounts[index]!++;await page.getByLabel('Search processes and accounts',{exact:true}).waitFor();return packet;}
 await page.getByRole('status').filter({hasText:name==='Export process with evidence'?'A current export is unavailable. No earlier copy was exported.':'Current access or evidence is unavailable. Earlier records are hidden.'}).waitFor();assert.equal(await page.getByLabel('Search processes and accounts').count(),0);return undefined;
}
async function marker(name:string){writeFileSync(join(meta.scratch,name),'requested',{mode:0o600});const began=Date.now();while(!existsSync(join(meta.scratch,name+'-committed'))){assert.ok(Date.now()-began<5000,'owned fixture transition bounded');await new Promise(r=>setTimeout(r,25));}}
try{
 while(!/Ready in/.test(output)){assert.ok(child.exitCode===null);assert.ok(Date.now()-start<45000,'Next startup bounded');await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true});
 for(let i=0;i<2;i++){
  const context:BrowserContext=await browser.newContext({ignoreHTTPSErrors:true,acceptDownloads:true,viewport:{width:i===0?1280:393,height:i===0?900:852}});contexts.push(context);await context.addCookies(jars[i]!.map(c=>({...c,url:origin,httpOnly:true,secure:true,sameSite:'Lax' as const})));
  const page:Page=await context.newPage();pages.push(page);page.on('download',()=>{downloadCounts[i]!++;});page.on('pageerror',error=>pageErrors.push(error.message));page.on('request',request=>{if(new URL(request.url()).pathname===endpoint){const value=request.postDataJSON();const remaining=Date.parse(value.caller_deadline)-Date.now();assert.ok(remaining>0&&remaining<=30000);originalRequests.push({remaining_ms:remaining});}});
  assert.equal((await page.goto(origin+'/consultant/workspace'))?.status(),200);
  // Real visible language changes establish hydration; no hidden hook/sleep/API replacement.
  await page.getByLabel('Language',{exact:true}).selectOption('zh');await page.getByRole('heading',{name:'公司知识工作区',exact:true}).waitFor();await page.getByLabel('语言',{exact:true}).selectOption('en');await page.getByRole('heading',{name:'Your company knowledge',exact:true}).waitFor();
  const overview=await action(page,'Read current knowledge',i);assert.ok(overview&&typeof overview.result.process_count==='number'&&overview.result.process_count>=2);
  assert.ok(await page.getByRole('link',{name:'Compare revisions and review my account',exact:true}).count());
  await page.getByLabel('Search processes and accounts').fill(meta.processes[0].label);await page.getByText(meta.processes[0].label,{exact:true}).first().waitFor();await page.getByLabel('Search processes and accounts').fill('');
  const process=await action(page,'Reported process map',i);assert.ok(process);assert.equal(process.operation,'process');
  const workflows=process.result.workflows as Record<string,unknown>[];assert.equal(workflows.length,1,'qualified fixture must contain the actual canonical workflow');
  const workflow=workflows[0]!;assert.equal(workflow.completeness,'complete');assert.match(String(workflow.scope),/Invented ART review only/);
  const items=workflow.items as {collection:string;identity:string;value:Record<string,unknown>;evidence:{quote:string;ref:{original_sha256:string}}[]}[];
  for(const item of items){assert.ok(item.evidence.length>0);assert.ok(item.evidence.every(q=>q.quote===meta.workflow_quote&&q.ref.original_sha256===sha256(meta.workflow_quote)));}
  assert.equal(items.filter(x=>x.collection==='handoffs').length,1);assert.equal(items.filter(x=>x.collection==='roles').length,3);assert.equal(items.filter(x=>x.collection==='conditions').length,2);
  const edges=items.filter(x=>x.collection==='transitions');assert.equal(edges.length,6);assert.equal(edges.filter(x=>x.value.rework===true).length,1);assert.equal(edges.filter(x=>x.value.from_id==='art-decision').length,2);
  const map=page.getByRole('region',{name:'Reported process map',exact:true}),drawing=map.getByRole('img',{name:'Reported process map',exact:true});await drawing.waitFor();
  assert.equal(await drawing.locator('line').count(),6);assert.equal(await drawing.locator('line[stroke-dasharray="5 4"]').count(),1);
  for(const label of ['Start artwork review','Prepare ART','Review ART','Revise ART','Release ART'])assert.ok((await drawing.locator('text').allTextContents()).includes(label));
  await map.getByText('Condition: ART approved',{exact:false}).waitFor();await map.getByText('Condition: ART needs changes',{exact:false}).waitFor();await map.getByText('Revise ART → Review ART · Rework',{exact:true}).waitFor();
  await map.getByText('Read evidence',{exact:true}).first().click();await map.getByText(meta.workflow_quote,{exact:true}).first().waitFor();assert.ok(await map.getByRole('link',{name:'Open original under current access',exact:true}).count());
  assert.equal(await page.getByText('No workflow is recorded for this process.',{exact:true}).count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),true);
  await page.screenshot({path:join(meta.scratch,'workspace-'+i+'.png'),fullPage:true});
 }
 const b=pages[1]!,a=pages[0]!;
 // Exports must come from another actual current read, not the retained display packet.
 const download=b.waitForEvent('download');await action(b,'Export evidence CSV',1);const exported=await download;const file=await exported.path();assert.ok(file);const csv=readFileSync(file,'utf8');assert.match(csv,/Original link/);assert.match(csv,/Company-wide completeness unverified/);
 await exported.saveAs(join(meta.scratch,'actual-evidence.csv'));
 const htmlPending=b.waitForEvent('download');const htmlPacket=await action(b,'Export process with evidence',1);assert.equal(htmlPacket?.operation,'process');const htmlDownload=await htmlPending;await htmlDownload.saveAs(join(meta.scratch,'actual-process.html'));const html=readFileSync(join(meta.scratch,'actual-process.html'),'utf8');
 for(const literal of ['Start artwork review','Prepare ART','Review ART','Revise ART','Release ART','ART approved','ART needs changes','Rework','Handoff','Design','Supplier','Open original under current access','company-wide completeness','Invented ART review only',meta.workflow_quote])assert.ok(html.includes(literal),literal);
 assert.ok(htmlPacket&&html.includes(htmlPacket.checked_at));assert.equal(htmlPacket.company_policy,false);
 const negative=await a.evaluate(async({endpoint,body})=>{const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body});return response.status;},{endpoint,body:query({principal_id:recipients[1]!.principal_id})});assert.equal(negative,503);
 const foreignProcess=await a.evaluate(async({endpoint,body})=>{const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body});return response.status;},{endpoint,body:query({operation:'process',process_id:'not-in-this-model'})});assert.equal(foreignProcess,503);
 await marker('disable-a');await action(a,'Read current knowledge',0,503);
 {const net=await import('node:net');await new Promise<void>((resolve,reject)=>{const probe=net.createConnection({host:'127.0.0.1',port:meta.tunnel_port});probe.on('connect',()=>{probe.destroy();resolve();});probe.on('error',reject);probe.setTimeout(3000,()=>{probe.destroy();reject(new Error('tunnel liveness probe timeout'));});});}
 await action(b,'Read current knowledge',1);
 // Only this invented disabled_at negative is restored; every original ID,
 // token/profile/admission/expiry remains unchanged. No authority is renewed.
 await marker('restore-a');await action(a,'Read current knowledge',0);await action(a,'Reported process map',0);await a.getByRole('img',{name:'Reported process map',exact:true}).waitFor();
 await marker('revoke-a');const aDownloads=downloadCounts[0];await action(a,'Export process with evidence',0,503);assert.equal(downloadCounts[0],aDownloads);await action(a,'Read current knowledge',0,503);assert.equal(await a.getByRole('img',{name:'Reported process map',exact:true}).count(),0);await action(b,'Read current knowledge',1);
 assert.equal(await a.getByRole('button',{name:'Export evidence CSV',exact:true}).count(),0);
 const absent=await browser.newContext({ignoreHTTPSErrors:true});try{assert.equal((await absent.request.post(origin+endpoint,{headers:{Origin:origin,'Content-Type':'application/json'},data:query()})).status(),503);}finally{await absent.close();}
 await action(b,'Reported process map',1);await b.getByRole('img',{name:'Reported process map',exact:true}).waitFor();auth.state.revokedUsers.add(recipients[1]!.auth_user_id);const bDownloads=downloadCounts[1];await action(b,'Export process with evidence',1,503);assert.equal(downloadCounts[1],bDownloads);await action(b,'Read current knowledge',1,503);assert.equal(await b.getByRole('img',{name:'Reported process map',exact:true}).count(),0);
 assert.ok(auth.state.acceptedUsers.includes(recipients[0]!.auth_user_id)&&auth.state.acceptedUsers.includes(recipients[1]!.auth_user_id));assert.deepEqual(pageErrors,[]);assert.ok(responseCounts.every(n=>n>=3));
 writeFileSync(join(meta.scratch,'receipt.json'),JSON.stringify({actual_next:true,auth:'actual SDK getUser HTTPS against invented issuer',employee:'actual unique employee SQL join',recipient_principals:recipients.map(r=>r.principal_id),response_counts:responseCounts,statuses,all_requests_original_window:originalRequests.length>0&&originalRequests.every(r=>r.remaining_ms>0&&r.remaining_ms<=30000),page_errors:pageErrors,workflow_fixture:meta.workflow_fixture,workflow_drawing_required:true,workflow_export_current:true,download_counts:downloadCounts,real_employee_proven:false,business_accepted:false})+'\n',{mode:0o600});
}finally{
 for(const context of contexts)await context.close();if(browser)await browser.close();writeFileSync(join(meta.scratch,'next-process.txt'),output,{mode:0o600});
 try{child.kill('SIGTERM');}catch{}await Promise.race([new Promise(r=>child.once('exit',r)),new Promise(r=>setTimeout(r,3000))]);try{child.kill('SIGKILL');}catch{}await auth.close();
}
