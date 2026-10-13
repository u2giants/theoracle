import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createHash} from 'node:crypto';
import {compileIngress} from './compile-ingress.mjs';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const revision='a'.repeat(40),image='sha256:'+'b'.repeat(64);
const manifest={schema_version:1,source_revision:revision,assets:Array.from({length:11},(_,i)=>({path:`/_next/static/chunks/invented-${i}.js`,sha256:'c'.repeat(64)}))};
const files=Object.fromEntries(['dev/oracle2/browser/Dockerfile','dev/oracle2/browser/Dockerfile.dockerignore','dev/oracle2/browser/compile-ingress.mjs','dev/oracle2/browser/coolify-companion.yaml','apps/web/proxy.ts','apps/web/lib/native-browser-runtime.mjs'].map(path=>[path,'d'.repeat(64)]));
files['dev/oracle2/browser/compile-ingress.mjs']=sha(readFileSync(new URL('./compile-ingress.mjs',import.meta.url)));
files['dev/oracle2/browser/coolify-companion.yaml']=sha(readFileSync(new URL('./coolify-companion.yaml',import.meta.url)));
const source={schema_version:1,revision,private_data_included:false,files,source_hash:sha(JSON.stringify(files)),archive_sha256:'e'.repeat(64)};
const input=(m=manifest,s=source)=>{const staticBytes=Buffer.from(JSON.stringify(m)),sourceBytes=Buffer.from(JSON.stringify(s));return {staticBytes,sourceBytes,association:{schema_version:1,source_revision:revision,image_digest:image,static_manifest_sha256:sha(staticBytes),source_offer_manifest_sha256:sha(sourceBytes),source_archive_sha256:s.archive_sha256,public_artifact_only:true},publicHost:'invented-native.example.invalid',expectedRevision:revision,expectedImageDigest:image,composeTemplate:readFileSync(new URL('./coolify-companion.yaml',import.meta.url),'utf8')};};
test('fixed exact outer paths and methods, no arbitrary rule or prefix; never admission',()=>{
  const result=compileIngress(input());assert.equal(result.exact_static_assets.length,11);assert.equal(result.authorizes_runtime,false);assert.equal(result.authenticated_artifact_association,false);
  assert.equal(result.platform_route_value.includes('PathPrefix'),false);assert.equal((result.platform_route_value.match(/Path\(/g)||[]).length,15);
  for(const path of ['/consultant/native-acceptance','/api/consultant/native-acceptance','/api/consultant/native-acceptance/session','/api/consultant/native-acceptance/source'])assert.equal(result.platform_route_value.includes('Path(`'+path+'`)'),true);
  for(const path of ['/admin','/api/chat','/api/consultant/session','/api/consultant/source'])assert.equal(result.platform_route_value.includes('Path(`'+path+'`)'),false);
  assert.equal(result.compose.includes('__ORACLE_NATIVE_BROWSER_COMPILED_RULE_REQUIRED__'),false);assert.equal(result.compose.includes('ghcr.io/u2giants/theoracle-native-browser@'+image),true);
});
test('source/image/static/source archive mismatch denied',()=>{
  for(const key of ['source_revision','image_digest','static_manifest_sha256','source_offer_manifest_sha256','source_archive_sha256']){const value=input();value.association[key]='wrong';assert.throws(()=>compileIngress(value));}
  const value=input();value.association.router_rule='Host(`company.invalid`)';assert.throws(()=>compileIngress(value));
  assert.throws(()=>compileIngress(input(manifest,{...source,private_data_included:true})));
});
test('unknown, query, encoded, traversal, duplicate, conflicting or wrong count assets denied',()=>{
  for(const path of ['/admin','/_next/static/native.js?company=1','/_next/static/%61.js','/_next/static/../admin.js','/_next/static//native.js']){
    const m=structuredClone(manifest);m.assets[0].path=path;assert.throws(()=>compileIngress(input(m)));
  }
  const duplicate=structuredClone(manifest);duplicate.assets[1]=duplicate.assets[0];assert.throws(()=>compileIngress(input(duplicate)));
  assert.throws(()=>compileIngress(input({...manifest,assets:manifest.assets.slice(1)})));
  const conflict=structuredClone(manifest);conflict.assets[0].router_rule='PathPrefix(`/`)';assert.throws(()=>compileIngress(input(conflict)));
});
test('uncompiled or caller-selected compose rule and company hostname denied',()=>{
  const v=input();v.composeTemplate=v.composeTemplate.replace('__ORACLE_NATIVE_BROWSER_COMPILED_RULE_REQUIRED__','Host(`company.invalid`)');assert.throws(()=>compileIngress(v));
  assert.throws(()=>compileIngress({...input(),publicHost:'oracle.designflow.app'}));assert.throws(()=>compileIngress({...input(),publicHost:'invented.invalid` || PathPrefix(`/`)'}));
});
