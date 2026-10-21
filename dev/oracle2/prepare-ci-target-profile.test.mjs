import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, statSync, existsSync, rmSync, mkdirSync, writeFileSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { defaultTargetProfile } from './private-target-profile.mjs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
const script = new URL('./prepare-ci-target-profile.mjs', import.meta.url);
const profile = readFileSync(defaultTargetProfile(), 'utf8');
function setup() {
  const root = mkdtempSync(join(tmpdir(), 'oracle-ci-metadata-'));
  const path = join(root, 'oracle-target-123-1/targets.json');
  const env = {...process.env, RUNNER_TEMP:root, GITHUB_RUN_ID:'123', GITHUB_RUN_ATTEMPT:'1', ORACLE_TARGET_PROFILE_PATH:path};
  delete env.ORACLE_TARGET_PROFILE_JSON;
  return {root,path,env};
}
function run(env,args=[]) { return spawnSync(process.execPath,[script.pathname,...args],{env,encoding:'utf8'}); }
test('exact current profile privately provisioned, member masked, then removed',()=>{
  const s=setup();try {
    const r=run({...s.env,ORACLE_TARGET_PROFILE_JSON:profile});assert.equal(r.status,0,r.stderr);
    assert.equal(readFileSync(s.path,'utf8'),profile);assert.equal(statSync(s.path).mode&0o777,0o600);
    assert.equal(statSync(join(s.root,'oracle-target-123-1')).mode&0o777,0o700);
    for(const v of Object.values(JSON.parse(profile).targets)) assert.ok(r.stdout.includes(`::add-mask::${v}\n`));
    assert.equal(run({...s.env,ORACLE_TARGET_PROFILE_JSON:profile}).status,1);
    assert.equal(run(s.env,['--cleanup']).status,0);assert.equal(existsSync(s.path),false);
    assert.equal(run(s.env,['--cleanup']).status,0);
  }finally{rmSync(s.root,{recursive:true,force:true});}
});
for(const [name,patch] of [['missing',{}],['malformed',{ORACLE_TARGET_PROFILE_JSON:'{' }],['wrong bytes',{ORACLE_TARGET_PROFILE_JSON:profile+' '}],['wrong path',{ORACLE_TARGET_PROFILE_JSON:profile,ORACLE_TARGET_PROFILE_PATH:'/var/targets.json'}],['invalid run',{ORACLE_TARGET_PROFILE_JSON:profile,GITHUB_RUN_ID:'../other'}]]) {
  test(`fails closed for ${name}`,()=>{const s=setup();try{const r=run({...s.env,...patch});assert.equal(r.status,1);assert.equal(existsSync(s.path),false);assert.equal(r.stdout,'');assert.equal(r.stderr,'Required pinned CI target metadata unavailable\n');}finally{rmSync(s.root,{recursive:true,force:true});}});
}

for (const kind of ['parent','leaf']) test(`cleanup refuses ${kind} symlink without deleting unrelated data`,()=>{
  const s=setup();try {
    const unrelated=join(s.root,'unrelated');mkdirSync(unrelated,{mode:0o700});
    const victim=join(unrelated,'targets.json');writeFileSync(victim,'recoverable fixture',{mode:0o600});
    if(kind==='parent') symlinkSync(unrelated,join(s.root,'oracle-target-123-1'));
    else {mkdirSync(join(s.root,'oracle-target-123-1'),{mode:0o700});symlinkSync(victim,s.path);}
    assert.equal(run(s.env,['--cleanup']).status,1);
    assert.equal(readFileSync(victim,'utf8'),'recoverable fixture');
  }finally{rmSync(s.root,{recursive:true,force:true});}
});
