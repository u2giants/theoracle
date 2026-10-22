/** UI-only retained actual-wire replay. No current auth, SQL, spend or acceptance. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import * as https from 'node:https';
import React from 'react';
import {renderToString} from 'react-dom/server';
import {chromium} from '@playwright/test';
import {InterviewPanel} from '../../components/consultant/interview-panel';
import {parseConversationResponse} from '@oracle/shared/protected-conversation-contract';
(globalThis as unknown as Record<string,unknown>).React=React;
const paths=process.argv.slice(2);assert.equal(paths.length,7,'four unchanged wires, invented TLS cert/key and owned scratch required');
const packets=paths.slice(0,4).map(p=>{const raw=readFileSync(p);return {raw,packet:parseConversationResponse(raw)};});
const scratch=paths[6]!;mkdirSync(scratch,{recursive:true,mode:0o700});
const req=createRequire(import.meta.url),tsxReq=createRequire(req.resolve('tsx/package.json'));const esbuild=tsxReq('esbuild') as typeof import('esbuild');
const built=await esbuild.build({stdin:{contents:`import React from 'react';import {hydrateRoot} from 'react-dom/client';import {InterviewPanel} from './components/consultant/interview-panel';hydrateRoot(document.getElementById('root'),React.createElement(InterviewPanel,{threadId:document.body.dataset.thread}));`,resolveDir:resolve('.'),loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:resolve('tsconfig.json'),define:{'process.env.NODE_ENV':'"production"'}});
let index=0,deny=false;const thread=(i:number)=>{const p=packets[i]!.packet;assert.ok('thread_id'in p);return p.thread_id!;};
const server=https.createServer({cert:readFileSync(paths[4]!),key:readFileSync(paths[5]!)},(request,response)=>{if(request.url==='/view.js'){response.writeHead(200,{'Content-Type':'text/javascript'});response.end(built.outputFiles[0]!.contents);}else{response.writeHead(200,{'Content-Type':'text/html'});response.end('<!doctype html><html><body data-thread="'+thread(index)+'"><div id="root">'+renderToString(React.createElement(InterviewPanel,{threadId:thread(index)}))+'</div><script src="/view.js"></script></body></html>');}});
await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const address=server.address();assert.ok(address&&typeof address!=='string');const browser=await chromium.launch({headless:true});const reports=[];
try{
 const page=await browser.newPage({ignoreHTTPSErrors:true});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/consultant/interviews/**/turns',async route=>{if(deny){await route.fulfill({status:503,json:{error:'UI-only denied fixture'}});return;}const p=structuredClone(packets[index]!.packet);assert.ok('events'in p&&p.qualified_effect);/* Explicit UI-only display clock, never changes immutable saved wire or claims current authority. */p.qualified_effect={...p.qualified_effect,checked_at:new Date().toISOString(),expires_at:new Date(Date.now()+20000).toISOString()};await route.fulfill({status:200,json:p});});
 for(index=0;index<4;index++){
  deny=false;await page.goto('https://127.0.0.1:'+address.port+'/consultant/interviews/'+thread(index));await page.getByTestId('interview-question').waitFor();
  const p=packets[index]!.packet;assert.ok('events'in p&&p.qualified_effect);const effect=p.qualified_effect;
  assert.equal(await page.getByTestId('interview-question').count(),1);assert.equal(await page.getByTestId('interview-question').textContent(),p.question);
  if(index%2===0){
   const records=effect.answer!.records as {assertion:{assertion_id:string;value:string};evidence:Record<string,{quote:string}[]>}[];
   assert.ok(records.length);await page.locator('[data-qualified-assertion]').first().waitFor();assert.equal(await page.locator('[data-qualified-assertion]').count(),records.length);
   for(const r of records){const section=page.locator('[data-qualified-assertion="'+r.assertion.assertion_id+'"]');assert.equal(await section.count(),1);assert.ok((await section.textContent())!.includes(r.assertion.value));for(const kind of ['supporting','opposing','unknown','temporal'])for(const q of r.evidence[kind]!)assert.ok((await section.textContent())!.includes(q.quote));}
   await page.getByText('Coverage and limits',{exact:true}).click();assert.ok((await page.locator('body').textContent())!.includes('Company-wide completeness is not verified.'));
   if(index===2)await page.getByRole('region',{name:'Synthesis limits'}).waitFor();
  }else{await page.getByText('The answer outcome is uncertain. Your response remains saved. Nothing will be sent again automatically.',{exact:true}).waitFor();assert.equal(await page.locator('[data-qualified-assertion]').count(),0);}
  await page.screenshot({path:join(scratch,'retained-case-'+index+'.png'),fullPage:true});
  deny=true;await page.getByRole('button',{name:'Refresh saved history',exact:true}).click();await page.getByText('This conversation is unavailable. Saved history remains on the server; its contents are withheld until access is verified.',{exact:true}).waitFor();assert.equal(await page.locator('[data-qualified-assertion]').count(),0);assert.equal(await page.getByTestId('interview-question').count(),0);
  reports.push({wire_sha256:createHash('sha256').update(packets[index]!.raw).digest('hex'),observed_state:effect.state,unchanged_original_wire:true,ui_only_display_clock:true,sole_sql_question_preserved:true,full_records_and_quotes_preserved:true,denied_refresh_withholds:true});
 }
 assert.deepEqual(errors,[]);writeFileSync(join(scratch,'receipt.json'),JSON.stringify({scope:'UI-only replay of unchanged actual invented backend wires; no current authority, auth, SQL, paid provider, semantic qualification or business acceptance',page_errors:errors,cases:reports},null,2)+'\n',{mode:0o600});
}finally{await browser.close();server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));}
