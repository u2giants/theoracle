import assert from 'node:assert/strict';
import { test, after } from 'node:test';
import { createHash } from 'node:crypto';
import { mkdtempSync, writeFileSync, mkdirSync, chmodSync, symlinkSync, linkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync, spawn, execFileSync } from 'node:child_process';
import { validateTargetDocument, readBoundedTargetJson, isPinnedTarget, readPrivateTarget,
  resolveNativeTriggerProject, targetPins } from './private-target-profile.mjs';
import { supabaseMcpCommand } from '../../scripts/oracle2/supabase_mcp.mjs';

const scratch=mkdtempSync(join(tmpdir(),'oracle-target-profile-test-'));
after(()=>rmSync(scratch,{recursive:true,force:true}));
const hash=v=>createHash('sha256').update(v).digest('hex');
const sample={legacy_trigger_project:'proj_'+'a'.repeat(20),native_trigger_project:'proj_'+'b'.repeat(20),
 oracle_supabase_project:'c'.repeat(20),native_supabase_project:'d'.repeat(20),coolify_api_base_url:'https://fixture.invalid/api/v1'};
const pins=Object.fromEntries(Object.entries(sample).map(([k,v])=>[k,hash(v)]));
const document=()=>({schema_version:1,targets:{...sample}});

test('metadata schema accepts a complete correctly pinned profile',()=>{
 assert.deepEqual({...validateTargetDocument(document(),pins)},sample);
});
for(const [name,change] of [
 ['missing target',v=>delete v.targets.native_trigger_project],
 ['extra credential field',v=>v.password='not-a-credential'],
 ['wrong version',v=>v.schema_version=2],
 ['null targets',v=>v.targets=null],
 ['array targets',v=>v.targets=[]],
 ['foreign target',v=>v.targets.native_trigger_project='proj_'+'e'.repeat(20)],
 ['empty target',v=>v.targets.oracle_supabase_project=''],
 ['shell syntax',v=>v.targets.oracle_supabase_project='x;echo denied'],
 ['controlplane credential URL',v=>v.targets.coolify_api_base_url='https://user:pass@fixture.invalid/api/v1'],
 ['controlplane query override',v=>v.targets.coolify_api_base_url='https://fixture.invalid/api/v1?host=other'],
 ['controlplane fragment',v=>v.targets.coolify_api_base_url='https://fixture.invalid/api/v1#other'],
 ['controlplane wrong path',v=>v.targets.coolify_api_base_url='https://fixture.invalid/api/v2'],
])test(`metadata schema rejects ${name}`,()=>{const v=document();change(v);assert.throws(()=>validateTargetDocument(v,pins),/Private target metadata unavailable/);});

test('production registry is pinned and cannot be changed through returned metadata',()=>{
 const p=targetPins();assert.ok(Object.isFrozen(p));assert.throws(()=>p.native_trigger_project='0'.repeat(64));
 assert.equal(isPinnedTarget('native_trigger_project',sample.native_trigger_project),false);
 assert.equal(isPinnedTarget('unknown',sample.native_trigger_project),false);
});

test('missing or malformed metadata fails closed without exposing content',()=>{
 assert.throws(()=>readBoundedTargetJson(join(scratch,'absent.json')),/Private target metadata unavailable/);
 const p=join(scratch,'bad.json');writeFileSync(p,'{not-json}',{mode:0o600});
 assert.throws(()=>readBoundedTargetJson(p,{privateProfile:true}),/Private target metadata unavailable/);
});

test('private metadata refuses a symlink and group-readable file',()=>{
 const p=join(scratch,'readable.json');writeFileSync(p,JSON.stringify(document()),{mode:0o600});
 const linked=join(scratch,'link.json');symlinkSync(p,linked);
 assert.throws(()=>readBoundedTargetJson(linked,{privateProfile:true}),/Private target metadata unavailable/);
 chmodSync(p,0o640);assert.throws(()=>readBoundedTargetJson(p,{privateProfile:true}),/Private target metadata unavailable/);
});

test('private metadata refuses a non-private parent',()=>{
 const d=join(scratch,'public-parent');mkdirSync(d,{mode:0o755});chmodSync(d,0o755);const p=join(d,'targets.json');
 writeFileSync(p,JSON.stringify(document()),{mode:0o600});
 assert.throws(()=>readBoundedTargetJson(p,{privateProfile:true}),/Private target metadata unavailable/);
});

test('metadata and build manifests are bounded and cannot be FIFOs or directories',()=>{
 assert.throws(()=>readBoundedTargetJson(scratch),/Private target metadata unavailable/);
 const p=join(scratch,'oversize.json');writeFileSync(p,' '.repeat(16385),{mode:0o600});
 assert.throws(()=>readBoundedTargetJson(p,{privateProfile:true}),/Private target metadata unavailable/);
});

test('private metadata rejects hardlinks',()=>{
 const p=join(scratch,'hardlink-source.json');writeFileSync(p,JSON.stringify(document()),{mode:0o600});
 linkSync(p,join(scratch,'hardlink-copy.json'));
 assert.throws(()=>readBoundedTargetJson(p,{privateProfile:true}),/Private target metadata unavailable/);
});

test('FIFO metadata refuses without blocking',()=>{
 const p=join(scratch,'metadata-fifo');execFileSync('mkfifo',[p]);
 const started=Date.now();assert.throws(()=>readBoundedTargetJson(p,{privateProfile:true}),/Private target metadata unavailable/);
 assert.ok(Date.now()-started<1000);
});

test('actual provisioned controller profile matches public commitments without printing targets',()=>{
 for(const k of Object.keys(targetPins()))assert.equal(isPinnedTarget(k,readPrivateTarget(k)),true);
 assert.equal(resolveNativeTriggerProject({}),readPrivateTarget('native_trigger_project'));
});

test('native env selectors preserve explicit rejection and v1 missing-target refusal',()=>{
 assert.throws(()=>resolveNativeTriggerProject({}, {allowDefault:false}),/Exact dedicated isolated native proof project required/);
 for(const env of [{TRIGGER_PROJECT_REF:''},{ORACLE2_NATIVE_TRIGGER_PROJECT_REF:'proj_wrong'},
  {TRIGGER_PROJECT_REF:'proj_wrong',ORACLE2_NATIVE_TRIGGER_PROJECT_REF:readPrivateTarget('native_trigger_project')}])
  assert.throws(()=>resolveNativeTriggerProject(env),/Exact dedicated isolated native proof project required/);
 const p=readPrivateTarget('native_trigger_project');assert.equal(resolveNativeTriggerProject({TRIGGER_PROJECT_REF:p}),p);
});

test('official index manifest supplies only its pinned project when controller env is absent',()=>{
 const p=join(scratch,'build.json');const value=readPrivateTarget('native_trigger_project');
 writeFileSync(p,JSON.stringify({config:{project:value}}));
 assert.equal(resolveNativeTriggerProject({TRIGGER_BUILD_MANIFEST_PATH:p,TRIGGER_INDEXING:'1'}),value);
 assert.equal(resolveNativeTriggerProject({TRIGGER_BUILD_MANIFEST_PATH:p}),value);
 writeFileSync(p,JSON.stringify({config:{project:sample.native_trigger_project}}));
 assert.throws(()=>resolveNativeTriggerProject({TRIGGER_BUILD_MANIFEST_PATH:p}),/Exact dedicated isolated native proof project required/);
});

test('MCP command remains read-only and never accepts shell syntax',()=>{
 const p=sample.oracle_supabase_project;
 const unix=supabaseMcpCommand(p,'linux');assert.equal(unix.command,'npx');
 assert.deepEqual(unix.args,['-y','@supabase/mcp-server-supabase@latest','--read-only','--project-ref',p]);
 const win=supabaseMcpCommand(p,'win32');assert.equal(win.command,'cmd.exe');
 assert.deepEqual(win.args,['/d','/s','/c','npx',...unix.args]);
 assert.throws(()=>supabaseMcpCommand(p+' & exit 0'));
});

test('documented child root resolves the MCP entrypoint independently of CWD',()=>{
 const root=join(scratch,'mock-project');mkdirSync(join(root,'scripts','oracle2'),{recursive:true});
 writeFileSync(join(root,'scripts','oracle2','supabase_mcp.mjs'),"export async function runSupabaseMcp(){console.log('child-root-ok')}");
 const entry=JSON.parse(spawnSync(process.execPath,['--input-type=module','--eval',
  "import{readFileSync}from'node:fs';console.log(JSON.stringify(JSON.parse(readFileSync('.mcp.json','utf8')).mcpServers['supabase-oracle'].args))"],
  {cwd:resolve(import.meta.dirname,'../..'),encoding:'utf8'}).stdout);
 assert.equal(entry[2],'node');assert.equal(entry[3],'--input-type=module');assert.equal(entry[4],'--eval');
 const result=spawnSync(process.execPath,entry.slice(3),{cwd:scratch,env:{...process.env,CLAUDE_PROJECT_DIR:root},encoding:'utf8'});
 assert.equal(result.status,0);assert.equal(result.stdout.trim(),'child-root-ok');
 assert.equal(/[&|<>^%]/.test(entry[5]),false,'fixed bootstrap must not contain cmd expansion/metacharacters');
});

test('MCP relay preserves stdin/stdout and child exit status',()=>{
 const module=pathToFileURL(resolve(import.meta.dirname,'../../scripts/oracle2/supabase_mcp.mjs')).href;
 const script=`import{relayMcp}from ${JSON.stringify(module)};const r=await relayMcp(process.execPath,['-e',"let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{console.log('echo:'+s);process.exit(7)})"]);process.exitCode=r.code;`;
 const r=spawnSync(process.execPath,['--input-type=module','--eval',script],{input:'invented-input',encoding:'utf8'});
 assert.equal(r.status,7);assert.equal(r.stdout.trim(),'echo:invented-input');
});

test('MCP relay forwards termination to its owned child',async()=>{
 const module=pathToFileURL(resolve(import.meta.dirname,'../../scripts/oracle2/supabase_mcp.mjs')).href;
 const inner="process.on('SIGTERM',()=>{console.log('child-stopped');process.exit(0)});console.log('child-ready');setInterval(()=>{},1000)";
 const script=`import{relayMcp}from ${JSON.stringify(module)};const r=await relayMcp(process.execPath,['-e',${JSON.stringify(inner)}]);process.exitCode=r.code;`;
 const child=spawn(process.execPath,['--input-type=module','--eval',script],{stdio:['ignore','pipe','pipe']});
 let output='';await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{child.kill('SIGKILL');reject(Error('relay fixture did not start'));},3000);child.stdout.on('data',b=>{output+=b;if(output.includes('child-ready')){clearTimeout(timer);resolve();}});child.once('error',reject);});
 child.kill('SIGTERM');await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{child.kill('SIGKILL');reject(Error('relay did not stop'));},3000);child.once('close',code=>{clearTimeout(timer);code===0?resolve():reject(Error('relay exit failed'));});});
 assert.match(output,/child-stopped/);
});

test('explicit private profile selector rejects empty or relative paths',()=>{
 const previous=process.env.ORACLE_TARGET_PROFILE_PATH;
 try {for(const value of ['', 'relative.json']){process.env.ORACLE_TARGET_PROFILE_PATH=value;assert.throws(()=>readPrivateTarget('native_supabase_project'));}}
 finally {if(previous===undefined)delete process.env.ORACLE_TARGET_PROFILE_PATH;else process.env.ORACLE_TARGET_PROFILE_PATH=previous;}
});

test('explicit protected profile selector preserves every pinned target',()=>{
 const selected=join(scratch,'selected-targets.json');
 const targets=Object.fromEntries(Object.keys(targetPins()).map(key=>[key,readPrivateTarget(key)]));
 writeFileSync(selected,JSON.stringify({schema_version:1,targets}),{mode:0o600});
 const previous=process.env.ORACLE_TARGET_PROFILE_PATH;
 try {process.env.ORACLE_TARGET_PROFILE_PATH=selected;for(const key of Object.keys(targets))assert.equal(readPrivateTarget(key),targets[key]);}
 finally {if(previous===undefined)delete process.env.ORACLE_TARGET_PROFILE_PATH;else process.env.ORACLE_TARGET_PROFILE_PATH=previous;}
});
