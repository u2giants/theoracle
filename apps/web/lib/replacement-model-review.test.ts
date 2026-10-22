/** Closed model-review wire only. These DTO tests issue no authority. */
import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ModelReview from '../app/consultant/replacement/review/review';
import { canonicalJson } from './replacement-server-binding';
import { parseModelReviewResponse,validateModelReviewRequest } from './replacement-protected-client';
const id='11111111-1111-4111-8111-111111111111',hash='a'.repeat(64);
const scope=()=>({schema_version:1,...Object.fromEntries(['process','customer','product','region'].map(k=>[k,{schema_version:1,mode:'unknown',identities:[]}]))});
const inspect=()=>({schema_version:1,operation:'inspect',model_id:id,base_version:1,caller_deadline:'2099-01-01T00:00:00Z'});
const assertion=()=>({schema_version:1,assertion_id:id,revision:1,predecessor_hash:null,subject_id:id,predicate:'reported_step',value:'Invented reported account',unit:null,provenance:'employee_account',scope:scope(),valid_time:'unknown',valid_from:null,valid_to:null,supporting_observations:[],opposing_observations:[],unknown_finding_ids:[],temporal_observations:[]});
const view=()=>({modelId:id,currentVersion:1,currentContentHash:hash,conflict:false,basePermitted:true,message:'Review exact changes before a new decision.',automaticRebase:false,policyEligibility:'unknown',baseRecordedAt:'2099-01-01T00:00:00Z',currentRecordedAt:'2099-01-01T00:00:00Z',currentAssertions:[{assertion:assertion(),evidence:{supporting:[],opposing:[],unknown:[],temporal:[]}}],totalAssertions:1,businessDecisions:[],changes:[],totalChanges:0,truncated:false});
const bytes=(value:unknown)=>Buffer.from(canonicalJson(value));
test('strict inspect and same exact decision assertion tuple preserve original narrowing',()=>{
 assert.equal(validateModelReviewRequest(bytes(inspect())).caller_deadline,'2099-01-01T00:00:00Z');
 const decision={...inspect(),operation:'decide',version:1,expected_hash:hash,decision:'accept',decision_kind:'employee-account',scope:scope(),assertions:[{assertion_id:id,revision:1}],command_id:id};delete (decision as Partial<{base_version:number}>).base_version;
 assert.equal(validateModelReviewRequest(bytes(decision)).decision_kind,'employee-account');
});
for(const key of ['actor','workspace','role','config','url','provider','grant','advance'])test('request refuses caller selector '+key,()=>assert.throws(()=>validateModelReviewRequest(bytes({...inspect(),[key]:id}))));
test('duplicates, noncanonical bytes and boolean revisions refuse',()=>{
 assert.throws(()=>validateModelReviewRequest(Buffer.from(canonicalJson(inspect()).replace('"base_version":1','"base_version":1,"base_version":1'))));
 assert.throws(()=>validateModelReviewRequest(Buffer.from(JSON.stringify(inspect()))));assert.throws(()=>validateModelReviewRequest(bytes({...inspect(),base_version:true})));
});
test('actual readonly response remains documentary, exact and bounded',()=>assert.equal(parseModelReviewResponse(bytes(view())).policyEligibility,'unknown'));
for(const damage of ['top','assertion','evidence','approval','unbounded'])test('peer cannot insert private data or authority '+damage,()=>{
 const value=view();if(damage==='top')Object.assign(value,{role:'private'});else if(damage==='assertion')Object.assign(value.currentAssertions[0]!.assertion,{database_url:'private'});else if(damage==='evidence')Object.assign(value.currentAssertions[0]!.evidence,{config:'private'});else if(damage==='approval')value.policyEligibility='accepted';else value.currentAssertions=Array(65).fill(value.currentAssertions[0]);
 assert.throws(()=>parseModelReviewResponse(bytes(value)));
});

for(const damage of ['provenance-array','scope-array'])test('response refuses coercible enum '+damage,()=>{
 const value=view();if(damage==='provenance-array')Object.assign(value.currentAssertions[0]!.assertion,{provenance:['employee_account']});else Object.assign(Reflect.get(value.currentAssertions[0]!.assertion.scope,'process'),{mode:['unknown']});
 assert.throws(()=>parseModelReviewResponse(bytes(value)));
});
for(const damage of ['decision','decision_kind','scope'])test('request refuses coercible enum '+damage,()=>{
 const decision={schema_version:1,operation:'decide',model_id:id,caller_deadline:'2099-01-01T00:00:00Z',version:1,expected_hash:hash,decision:'accept',decision_kind:'employee-account',scope:scope(),assertions:[{assertion_id:id,revision:1}],command_id:id};
 if(damage==='scope')Object.assign(Reflect.get(decision.scope,'process'),{mode:['unknown']});else Object.assign(decision,{[damage]:[decision[damage as 'decision'|'decision_kind']]});
 assert.throws(()=>validateModelReviewRequest(bytes(decision)));
});

// Render the actual component without running effects, as Next does before hydration.
test('server-rendered review cannot submit a native form before hydration',()=>{
 const prior=Reflect.get(globalThis,'React');
 Reflect.set(globalThis,'React',React);
 try{
  const html=renderToStaticMarkup(React.createElement(ModelReview,{modelId:id}));
  assert.match(html,/<button[^>]*disabled=""[^>]*type="submit">Load review<\/button>/);
  assert.match(html,/Version last reviewed/);
 }finally{if(prior===undefined)Reflect.deleteProperty(globalThis,'React');else Reflect.set(globalThis,'React',prior);}
});

test('actual browser waits for hydration, then submits one review POST in StrictMode',async()=>{
 const {createServer}=await import('node:http');
 const {createRequire}=await import('node:module');
 const {resolve}=await import('node:path');
 const {chromium}=await import('@playwright/test');
 const require=createRequire(import.meta.url),tsxRequire=createRequire(require.resolve('tsx/package.json'));
 const esbuild=tsxRequire('esbuild') as typeof import('esbuild');
 const bundle=await esbuild.build({stdin:{contents:"import React from 'react';import {hydrateRoot} from 'react-dom/client';import ModelReview from './app/consultant/replacement/review/review';hydrateRoot(document.getElementById('root'),React.createElement(React.StrictMode,null,React.createElement(ModelReview,{modelId:'"+id+"'})));",resolveDir:resolve('.'),loader:'tsx'},bundle:true,write:false,platform:'browser',format:'iife',jsx:'automatic',tsconfig:resolve('tsconfig.json'),define:{'process.env.NODE_ENV':'"development"'}});
 const prior=Reflect.get(globalThis,'React');Reflect.set(globalThis,'React',React);
 let html:string;try{html=renderToStaticMarkup(React.createElement(ModelReview,{modelId:id}));}finally{if(prior===undefined)Reflect.deleteProperty(globalThis,'React');else Reflect.set(globalThis,'React',prior);}
 let posts=0,gets=0;
 const server=createServer((request,response)=>{
  if(request.method==='GET'){gets++;response.writeHead(200,{'Content-Type':'text/html'});response.end('<!doctype html><html><body><div id="root">'+html+'</div></body></html>');return;}
  assert.equal(request.method,'POST');assert.equal(request.url,'/api/consultant/replacement/v1/protected/model-review');posts++;
  request.resume();request.on('end',()=>{response.writeHead(200,{'Content-Type':'application/json'});response.end(JSON.stringify({...view(),changes:[{assertionId:id,change:'changed',before:assertion(),after:assertion()}]}));});
 });
 await new Promise<void>(done=>server.listen(0,'127.0.0.1',done));
 const address=server.address();assert.ok(address&&typeof address!=='string');
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:'+address.port+'/review');
  const button=page.getByRole('button',{name:'Load review',exact:true});assert.equal(await button.isDisabled(),true);
  await button.click({force:true});await page.getByLabel('Version last reviewed').press('Enter');
  assert.equal(posts,0);assert.equal(gets,1,'unhydrated form must not navigate');
  await page.addScriptTag({content:bundle.outputFiles[0]!.text});
  // Playwright waits for the real effect-enabled button; no sleep or API substitute.
  await button.click();await page.getByText('Changed account',{exact:true}).waitFor();
  assert.equal(posts,1);assert.equal(gets,1);assert.deepEqual(errors,[]);
 }finally{await browser.close();await new Promise<void>((done,reject)=>server.close(error=>error?reject(error):done()));}
});
