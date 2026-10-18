import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
const PROJECT='proj_jtaztxnmppzfchdsgvea';
const cwd=fileURLToPath(new URL('.',import.meta.url));
function load(custom:string|undefined,official:string|undefined){
  const env={...process.env};
  delete env.ORACLE2_NATIVE_TRIGGER_PROJECT_REF;delete env.TRIGGER_PROJECT_REF;
  if(custom!==undefined)env.ORACLE2_NATIVE_TRIGGER_PROJECT_REF=custom;
  if(official!==undefined)env.TRIGGER_PROJECT_REF=official;
  // Import the actual config with its real SDK and Python extension, in a fresh
  // process so environment admission cannot be hidden by the module cache.
  return spawnSync(process.execPath,['--import','tsx','--input-type=module','--eval',
    `const {default:c}=await import('./trigger.oracle2-native-invented.config.ts');console.log(JSON.stringify({project:c.project,runtime:c.runtime,maxDuration:c.maxDuration,retries:c.retries,dirs:c.dirs,ignorePatterns:c.ignorePatterns}));`],
    {cwd,env,encoding:'utf8',timeout:10000});
}
for(const [name,custom,official] of [
 ['missing',undefined,undefined],['custom wrong','proj_wrong',undefined],['official wrong',undefined,'proj_wrong'],
 ['custom shared','proj_wgpzsvhmsopqhvwqaycn',undefined],['official shared',undefined,'proj_wgpzsvhmsopqhvwqaycn'],
 ['conflicting custom',PROJECT,'proj_wrong'],['conflicting official','proj_wrong',PROJECT],['explicit empty custom','',PROJECT],
] as const)test(`native config rejects ${name}`,()=>{const r=load(custom,official);assert.notEqual(r.status,0);assert.match(r.stderr,/Exact dedicated isolated native proof project required/);});
for(const [name,custom,official] of [
 ['custom only',PROJECT,undefined],['official indexer only',undefined,PROJECT],['matching both',PROJECT,PROJECT],
] as const)test(`native config admits ${name} without changing runtime isolation`,()=>{
 const r=load(custom,official);assert.equal(r.status,0,r.stderr);
 const c=JSON.parse(r.stdout.trim());assert.equal(c.project,PROJECT);assert.equal(c.runtime,'node-24');assert.equal(c.maxDuration,120);
 assert.deepEqual(c.retries,{enabledInDev:false,default:{maxAttempts:1}});assert.deepEqual(c.dirs,['./src/trigger']);
 assert.ok(!c.ignorePatterns.includes('**/oracle2-native-invented.ts'));
 assert.ok(c.ignorePatterns.includes('**/oracle2-holistic.ts'));
 assert.ok(c.ignorePatterns.includes('**/oracle2-project.ts'));
});
