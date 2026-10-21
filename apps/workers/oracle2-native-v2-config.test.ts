import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { readPrivateTarget, targetPins } from '../../dev/oracle2/private-target-profile.mjs';
const PROJECT=readPrivateTarget('native_trigger_project');
const LEGACY=readPrivateTarget('legacy_trigger_project');
const cwd=fileURLToPath(new URL('.',import.meta.url));
function load(custom:string|undefined,official:string|undefined){
  const env={...process.env};
  delete env.ORACLE2_NATIVE_TRIGGER_PROJECT_REF;delete env.TRIGGER_PROJECT_REF;
  if(custom!==undefined)env.ORACLE2_NATIVE_TRIGGER_PROJECT_REF=custom;
  if(official!==undefined)env.TRIGGER_PROJECT_REF=official;
  // Import the actual config with its real SDK and Python extension, in a fresh
  // process so environment admission cannot be hidden by the module cache.
  return spawnSync(process.execPath,['--import','tsx','--input-type=module','--eval',
    `const {createHash}=await import('node:crypto');const projectSha=(v)=>createHash('sha256').update(v).digest('hex');const {default:c}=await import('./trigger.oracle2-native-invented-v2.config.ts');console.log(JSON.stringify({projectSha256:projectSha(c.project),runtime:c.runtime,maxDuration:c.maxDuration,retries:c.retries,dirs:c.dirs,ignorePatterns:c.ignorePatterns}));`],
    {cwd,env,encoding:'utf8',timeout:10000});
}
for(const [name,custom,official] of [
 ['custom wrong','proj_wrong',undefined],['official wrong',undefined,'proj_wrong'],
 ['custom shared',LEGACY,undefined],['official shared',undefined,LEGACY],
 ['conflicting custom',PROJECT,'proj_wrong'],['conflicting official','proj_wrong',PROJECT],['explicit empty custom','',PROJECT],['explicit empty official',PROJECT,''],['empty custom alone','',undefined],['empty official alone',undefined,''],['both empty','',''],['same foreign overrides','proj_wrong','proj_wrong'],
] as const)test(`native config rejects ${name}`,()=>{const r=load(custom,official);assert.notEqual(r.status,0);assert.match(r.stderr,/Exact dedicated isolated native proof project required/);});
for(const [name,custom,official] of [
 ['official index child omits both overrides',undefined,undefined],['custom only',PROJECT,undefined],['official indexer only',undefined,PROJECT],['matching both',PROJECT,PROJECT],
] as const)test(`native config admits ${name} without changing runtime isolation`,()=>{
 const r=load(custom,official);assert.equal(r.status,0,r.stderr);
 const c=JSON.parse(r.stdout.trim());assert.equal(c.projectSha256,targetPins().native_trigger_project);assert.equal(c.runtime,'node-24');assert.equal(c.maxDuration,120);
 assert.deepEqual(c.retries,{enabledInDev:false,default:{maxAttempts:1}});assert.deepEqual(c.dirs,['./src/trigger']);
 assert.ok(!c.ignorePatterns.includes('**/oracle2-native-invented-v2.ts'));
 assert.ok(c.ignorePatterns.includes('**/oracle2-native-invented.ts'));
 assert.ok(c.ignorePatterns.includes('**/oracle2-holistic.ts'));
 assert.ok(c.ignorePatterns.includes('**/oracle2-project.ts'));
});

// Exercise the failing cloud boundary: the official controller passes only
// server runtime variables to indexWorkerManifest's fork, dropping its own
// TRIGGER_PROJECT_REF. A config-only import/dry-run cannot prove this path.
import {execFileSync} from 'node:child_process';
import {mkdtempSync,readFileSync,realpathSync,writeFileSync,mkdirSync,rmSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {after,before} from 'node:test';
const indexScratch=mkdtempSync(join(tmpdir(),'oracle-v2-index-child-'));
let cliModules:string;
const image=process.env.ORACLE2_INDEX_TEST_IMAGE??'node:24-bookworm-slim';
const minimal=()=>Object.fromEntries(['PATH','HOME','USER','LOGNAME','TMPDIR','LANG'].flatMap(k=>process.env[k]===undefined?[]:[[k,process.env[k]!]]));
before(()=>{
 const executable=execFileSync('npx',['--yes','--package','trigger.dev@4.5.15','--','which','trigger'],{encoding:'utf8',env:minimal()}).trim();
 const cli=resolve(dirname(realpathSync(executable)),'../..');
 assert.equal(JSON.parse(readFileSync(join(cli,'package.json'),'utf8')).version,'4.5.15');
 cliModules=dirname(cli);
 execFileSync('sh',[resolve(cwd,'../../scripts/oracle2/sync_worker_python.sh')],{cwd,env:minimal()});
 writeFileSync(join(indexScratch,'build.mjs'),`
  import {loadConfig} from ${JSON.stringify('file://'+join(cli,'dist/esm/config.js'))};
  import {buildWorker} from ${JSON.stringify('file://'+join(cli,'dist/esm/build/buildWorker.js'))};
  const resolvedConfig=await loadConfig({cwd:process.argv[2],configFile:'trigger.oracle2-native-invented-v2.config.ts'});
  const build=await buildWorker({target:'deploy',environment:'prod',destination:process.argv[3],resolvedConfig,rewritePaths:true,envVars:{PYTHON_BIN_PATH:'/opt/venv/bin/python'},forcedExternals:[]});
  if(build.config.project!==${JSON.stringify(PROJECT)})throw Error('fixed project changed');
 `);
 const built=spawnSync(process.execPath,[join(indexScratch,'build.mjs'),cwd,join(indexScratch,'bundle')],{cwd,env:minimal(),encoding:'utf8',timeout:60000});
 assert.equal(built.status,0,built.stderr);
 mkdirSync(join(indexScratch,'bundle/node_modules'),{recursive:true});
 writeFileSync(join(indexScratch,'index.mjs'),`
  import {readFile} from 'node:fs/promises';
  import {indexWorkerManifest} from '/deps/node_modules/trigger.dev/dist/esm/indexing/indexWorkerManifest.js';
  import {execOptionsForRuntime} from '/deps/node_modules/@trigger.dev/core/dist/esm/v3/build/index.js';
  const build=JSON.parse(await readFile('/app/build.json','utf8'));
  try{
   const out=await indexWorkerManifest({runtime:build.runtime,indexWorkerPath:build.indexWorkerEntryPoint,buildManifestPath:'/app/build.json',nodeOptions:execOptionsForRuntime(build.runtime,build),env:{PYTHON_BIN_PATH:'/opt/venv/bin/python',...JSON.parse(process.argv[2])},cwd:'/app'});
   console.log(JSON.stringify({state:'indexed',projectSha256:(await import('node:crypto')).createHash('sha256').update(build.config.project).digest('hex'),runtime:out.runtime,runtimeVersion:out.runtimeVersion,tasks:out.tasks.map(t=>({id:t.id,maxDuration:t.maxDuration,retry:t.retry}))}));
  }catch(e){console.log(JSON.stringify({state:'denied',error:e.message}));process.exitCode=1;}
 `);
});
after(()=>rmSync(indexScratch,{recursive:true,force:true}));
function indexChild(custom:string|undefined,official:string|undefined){
 const overrides:Record<string,string>={};
 if(custom!==undefined)overrides.ORACLE2_NATIVE_TRIGGER_PROJECT_REF=custom;
 if(official!==undefined)overrides.TRIGGER_PROJECT_REF=official;
 return spawnSync('docker',['run','--rm','--network','none','--read-only',
  '-e',`TRIGGER_PROJECT_REF=${PROJECT}`,
  '-v',`${join(indexScratch,'bundle')}:/app:ro`,'-v',`${cliModules}:/deps/node_modules:ro`,
  '-v',`${cliModules}:/app/node_modules:ro`,'-v',`${join(indexScratch,'index.mjs')}:/index.mjs:ro`,
  '-w','/app',image,'node','/index.mjs',JSON.stringify(overrides)],{encoding:'utf8',env:minimal(),timeout:30000});
}
for(const [name,custom,official] of [
 ['runtime env omits both overrides',undefined,undefined],['explicit custom',PROJECT,undefined],
 ['explicit official',undefined,PROJECT],['matching both',PROJECT,PROJECT],
] as const)test(`official Docker index child admits ${name} at fixed project only`,()=>{
 const r=indexChild(custom,official);assert.equal(r.status,0,r.stderr+'\n'+r.stdout);
 const out=JSON.parse(r.stdout.trim());assert.equal(out.projectSha256,targetPins().native_trigger_project);assert.equal(out.runtime,'node-24');assert.match(out.runtimeVersion,/^24\./);
 assert.equal(out.tasks.length,1);assert.equal(out.tasks[0].id,'oracle2-native-invented-v2');assert.equal(out.tasks[0].maxDuration,120);assert.equal(out.tasks[0].retry.maxAttempts,1);
});
for(const [name,custom,official] of [
 ['wrong custom','proj_wrong',undefined],['wrong official',undefined,'proj_wrong'],
 ['shared custom',LEGACY,undefined],['shared official',undefined,LEGACY],
 ['conflicting custom',PROJECT,'proj_wrong'],['conflicting official','proj_wrong',PROJECT],
 ['empty custom','',PROJECT],['empty official',PROJECT,''],['empty custom alone','',undefined],['empty official alone',undefined,''],['both empty','',''],['same foreign overrides','proj_wrong','proj_wrong'],
] as const)test(`official Docker index child rejects ${name} despite correct parent target`,()=>{
 const r=indexChild(custom,official);assert.notEqual(r.status,0);assert.match(r.stdout,/Exact dedicated isolated native proof project required/);
});
