/** UI-ONLY replay of an invented saved response. No currentness/auth/SQL/MCP proof. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {createRequire} from 'node:module';
import * as https from 'node:https';
import React from 'react';
import {renderToString} from 'react-dom/server';
import {chromium} from '@playwright/test';
import {ConnectedAnswerPanel} from '../../components/consultant/connected-answer-panel';
(globalThis as unknown as Record<string,unknown>).React=React;
const packet=JSON.parse(readFileSync(process.argv[2]!,'utf8'));const metadata=JSON.parse(readFileSync(process.argv[3]!,'utf8'));const scratch=process.argv[4]!;mkdirSync(scratch,{recursive:true,mode:0o700});
const req=createRequire(import.meta.url),tsxReq=createRequire(req.resolve('tsx/package.json'));const esbuild=tsxReq('esbuild') as typeof import('esbuild');
const built=await esbuild.build({stdin:{contents:`import React from 'react';import {hydrateRoot} from 'react-dom/client';import {ConnectedAnswerPanel} from './components/consultant/connected-answer-panel';hydrateRoot(document.getElementById('root'),React.createElement(ConnectedAnswerPanel));`,resolveDir:resolve('.'),loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:resolve('tsconfig.json'),define:{'process.env.NODE_ENV':'"production"'}});
const server=https.createServer({key:readFileSync(metadata.server_key_file),cert:readFileSync(metadata.server_certificate_file)},(_,r)=>{if(_.url==='/answer.js'){r.writeHead(200,{'Content-Type':'text/javascript'});r.end(built.outputFiles[0]!.contents);}else{r.writeHead(200,{'Content-Type':'text/html'});r.end('<!doctype html><html><body><div id="root">'+renderToString(React.createElement(ConnectedAnswerPanel))+'</div><script src="/answer.js"></script></body></html>');}});
await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const address=server.address();assert.ok(address&&typeof address!=='string');const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({ignoreHTTPSErrors:true});const errors:string[]=[];page.on('pageerror',e=>{errors.push(e.message);writeFileSync(join(scratch,'page-errors.json'),JSON.stringify(errors));});
 let started:(()=>void)|undefined;const heldRequest=new Promise<void>(r=>{started=r;});let release:((()=>void)|null)=null;let hold=false;let deny=false;await page.route('**/api/consultant/replacement/v1/protected/answer',async route=>{if(hold){started!();await new Promise<void>(r=>{release=r;});}if(deny){await route.fulfill({status:503,json:{error:'UI-only denied fixture'}});return;}await route.fulfill({status:200,json:{...packet,expires_at:new Date(Date.now()+20000).toISOString()}});});
 await page.goto('https://127.0.0.1:'+address.port+'/consultant/ask');
 await page.getByLabel('Your question').fill('Who receives the design handoff?');await page.getByRole('button',{name:'Ask',exact:true}).click();await page.getByRole('link',{name:'Open original under current access'}).first().waitFor();
 await page.getByText('Coverage and limits',{exact:true}).click();await page.getByText('Dates and retained history',{exact:true}).click();
 await page.screenshot({path:join(scratch,'ui-evidence.png'),fullPage:true});
 hold=true;await page.getByRole('button',{name:'Ask',exact:true}).click();await page.getByRole('button',{name:'Reading current evidence…',exact:true}).waitFor();await heldRequest;await page.getByLabel('Your question').fill('A different unsent question');(release as ()=>void)();hold=false;await page.getByRole('button',{name:'Ask',exact:true}).waitFor();assert.equal(await page.getByRole('link',{name:'Open original under current access'}).count(),0);
 deny=true;await page.getByRole('button',{name:'Ask',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.getByRole('link',{name:'Open original under current access'}).count(),0);
 await page.screenshot({path:join(scratch,'ui-denied.png')});writeFileSync(join(scratch,'receipt.json'),JSON.stringify({scope:'UI-only replay; no authority, fresh original, auth, SQL, MCP or company proof',page_errors:errors}));assert.deepEqual(errors,[]);
}finally{await browser.close();server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));}
