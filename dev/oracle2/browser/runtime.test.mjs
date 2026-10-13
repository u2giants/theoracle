import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {assertNativeEnvironment,assertNativeSettings,readStaticManifest,nativeRequestAllowed,nativeForwardingAllowed,assertNativeDatabaseURL} from '../../../apps/web/lib/native-browser-runtime.mjs';
const env={NODE_ENV:'production',ORACLE2_NATIVE_BROWSER_ONLY:'1',ORACLE2_PILOT_TOKEN:'invented-test-only',
  ORACLE2_PILOT_WORKSPACE_ID:'invented-workspace',ORACLE2_PILOT_ACTOR:'invented-actor',
  ORACLE2_NATIVE_ACCEPTANCE_SETTINGS:'/run/oracle-native-browser/settings.json',ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256:'a'.repeat(64),
  ORACLE2_NATIVE_BROWSER_PUBLIC_HOST:'invented-native.example.invalid',ORACLE2_NATIVE_BROWSER_SOURCE_REVISION:'b'.repeat(40)};
const manifest={schema_version:1,source_revision:env.ORACLE2_NATIVE_BROWSER_SOURCE_REVISION,assets:[{path:'/_next/static/chunks/native.js',sha256:'c'.repeat(64)}]};
const settings={actor_id:'invented-actor',workspace_id:'invented-workspace',purpose:'public-invented-native-browser',hostname:'gateway',origin:'https://gateway:8443',metadata_role:'oracle2_gateway_metadata',metadata_login:'oracle_synthetic_gateway',public_page_origin:'https://invented-native.example.invalid',
  ...Object.fromEntries(Object.entries({database_url:'database-url',database_ca:'ledger-ca.crt',client_cert:'client.crt',client_key:'client.key',server_ca:'gateway-ca.crt',hmac_key:'hmac-key'}).map(([key,value])=>[key,{path:'/run/oracle-native-browser/'+value}]))};
const allowed=(path,method='GET',custom=env,host=env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST)=>nativeRequestAllowed('https://'+host+path,method,host,custom,manifest);
test('exact native page, API, dedicated session and required static resource',()=>{
  assertNativeEnvironment(env);assertNativeSettings(env,settings);
  for(const [path,methods] of [['/consultant/native-acceptance',['GET','HEAD']],['/api/consultant/native-acceptance',['GET','POST']],['/api/consultant/native-acceptance/session',['POST','DELETE']],['/api/consultant/native-acceptance/source',['GET']],['/_next/static/chunks/native.js',['GET','HEAD']]])for(const method of methods)assert.equal(allowed(path,method),true);
});
test('legacy session, company, employee, admin, providers, health and arbitrary assets denied',()=>{
  for(const path of ['/','/api/consultant/session','/api/consultant/source','/api/consultant/answer','/api/chat','/admin','/api/trigger','/api/native','/health','/_next/static/chunks/company.js','/favicon.ico','/consultant/native-acceptance/extra'])assert.equal(allowed(path),false,path);
});
test('wrong method, host, query and encoded paths denied',()=>{
  assert.equal(allowed('/api/consultant/native-acceptance','DELETE'),false);
  assert.equal(allowed('/api/consultant/native-acceptance/session','GET'),false);
  assert.equal(allowed('/api/consultant/native-acceptance/source','POST'),false);
  assert.equal(allowed('/api/consultant/native-acceptance/source?metadata=1'),false);
  assert.equal(allowed('/api/consultant/native-acceptance/source?private=1'),false);
  assert.equal(allowed('/api/consultant/native-acceptance?operation=company'),false);
  assert.equal(allowed('/api/consultant/native-acceptance','GET',env,'company.example.invalid'),false);
  assert.equal(allowed('/%61pi/consultant/native-acceptance'),false);
});
test('no source mismatch, weak seal, company hostname or absent flag',()=>{
  for(const patch of [{ORACLE2_NATIVE_BROWSER_ONLY:undefined},{ORACLE2_NATIVE_BROWSER_ONLY:'0'},{NODE_ENV:'development'},{ORACLE2_NATIVE_ACCEPTANCE_SETTINGS_SHA256:'bad'},{ORACLE2_NATIVE_BROWSER_SOURCE_REVISION:'z'.repeat(40)},{ORACLE2_NATIVE_BROWSER_PUBLIC_HOST:'oracle.designflow.app'}])assert.throws(()=>allowed('/api/consultant/native-acceptance','GET',{...env,...patch}));
  assert.throws(()=>allowed('/api/consultant/native-acceptance','GET',{...env,ORACLE2_NATIVE_BROWSER_SOURCE_REVISION:'d'.repeat(40)}));
});
test('arbitrary environment and company/provider/admin credentials denied even with flag',()=>{
  for(const key of ['NEXT_PUBLIC_SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','OPENROUTER_API_KEY','TRIGGER_SECRET_KEY','ADMIN_PASSWORD','DATABASE_URL','NODE_OPTIONS','NODE_PATH','CUSTOM_CONFIG','ORACLE2_PROVIDER_ENABLED'])assert.throws(()=>assertNativeEnvironment({...env,[key]:'invented'}),key);
});
test('sealed purpose, actor, network and dedicated volume paths required',()=>{
  for(const patch of [{actor_id:'different'},{workspace_id:'different'},{purpose:'company'},{hostname:'localhost'},{origin:'https://external.invalid'},{metadata_role:'oracle2_migrator'},{metadata_login:undefined},{public_page_origin:'https://company.example.invalid'},{client_key:{path:'/run/core/server.key'}}])assert.throws(()=>assertNativeSettings(env,{...settings,...patch}));
  assert.throws(()=>assertNativeSettings({...env,ORACLE2_PILOT_ACTOR:'invented-actor,extra'},settings));
  assert.throws(()=>assertNativeSettings({...env,ORACLE2_PILOT_ACTORS:'invented-actor'},settings));
});
test('static manifest rejects duplicates, traversal, malformed hashes and unrelated resource paths',()=>{
  const directory=mkdtempSync(join(tmpdir(),'oracle-native-assets-'));const path=join(directory,'manifest.json');
  try{
    writeFileSync(path,JSON.stringify(manifest));assert.deepEqual(readStaticManifest(path),manifest);
    for(const assets of [[...manifest.assets,...manifest.assets],[{path:'/_next/static/../company.js',sha256:'c'.repeat(64)}],[{path:'/company.js',sha256:'c'.repeat(64)}],[{path:'/_next/static/native.js',sha256:'bad'}]]){writeFileSync(path,JSON.stringify({...manifest,assets}));assert.throws(()=>readStaticManifest(path));}
  }finally{rmSync(directory,{recursive:true});}
});
test('candidate compose preserves isolated core and never publishes host ports or extra networks',()=>{
  const source=readFileSync(new URL('./coolify-companion.yaml',import.meta.url),'utf8');
  assert.match(source,/networks: \[browser-ingress, ledger\]/);assert.match(source,/browser-credential:\/run\/oracle-native-browser:ro/);
  for(const field of ['ports:','jobs:','candidate:','confirmed:','privileged:','docker.sock','core-secret'])assert.equal(source.includes(field),false);
  assert.match(source,/read_only: true/);assert.match(source,/cap_drop: \[ALL\]/);
});
test('ordinary deployment settings and Python publisher remain separate',()=>{
  const config=readFileSync(new URL('../../../apps/web/next.config.ts',import.meta.url),'utf8');
  assert.match(config,/ORACLE2_NATIVE_BROWSER_BUILD==='1'\?\{output:'standalone'/);
  const proxy=readFileSync(new URL('../../../apps/web/proxy.ts',import.meta.url),'utf8');assert.match(proxy,/Preserve the original matcher exclusions/);
  const entry=readFileSync(new URL('./entrypoint.sh',import.meta.url),'utf8');assert.match(entry,/NODE_OPTIONS/);assert.equal(entry.includes('next start'),false);
});

test('sole HTTPS forwarding, exact actual Host, absent or same forwarded Host only',()=>{
  const host=env.ORACLE2_NATIVE_BROWSER_PUBLIC_HOST;
  assert.equal(nativeForwardingAllowed(host,'https',host,null,env),true);
  assert.equal(nativeForwardingAllowed(host,'https',null,null,env),true);
  for(const tuple of [[host,null,host,null],[host,'http',host,null],[host,'https, https',host,null],[host,'https','other.invalid',null],[host,'https',host+', '+host,null],['other.invalid','https',host,null],[host,'https',host,'host=other.invalid;proto=https']])assert.equal(nativeForwardingAllowed(...tuple,env),false);
});

test('pinned Next-created internal metadata accepted only after sealed bootstrap',()=>{
  const internal={...env,__NEXT_PRIVATE_STANDALONE_CONFIG:'{}',__NEXT_PRIVATE_ORIGIN:'https://0.0.0.0:3000',NEXT_DEPLOYMENT_ID:'',TURBOPACK:'1'};
  assertNativeEnvironment(internal);assert.throws(()=>assertNativeEnvironment(internal,false));
});

test('only already-pinned isolated ledger PostgreSQL URL can reach metadata',()=>{
  const valid='postgresql://oracle_synthetic_gateway:public-invented-password@ledger:5432/oracle_synthetic?sslmode=verify-full&sslrootcert=%2Frun%2Foracle-native-browser%2Fledger-ca.crt';
  assertNativeDatabaseURL(valid,settings);assertNativeDatabaseURL(valid.replace(':5432/','/'),settings);
  for(const change of [['@ledger:','@company.invalid:'],[':5432/',':5433/'],['/oracle_synthetic?','/company?'],['oracle_synthetic_gateway:','oracle2_migrator:'],['verify-full','require'],['verify-full','disable'],['postgresql:','https:'],['ledger-ca.crt','other-ca.crt']])assert.throws(()=>assertNativeDatabaseURL(valid.replace(...change),settings));
  for(const suffix of ['&hostaddr=127.0.0.1','&host=company.invalid','&sslmode=disable','&options=-c%20role%3Dadmin','&sslrootcert=system','#company'])assert.throws(()=>assertNativeDatabaseURL(valid+suffix,settings));
});
