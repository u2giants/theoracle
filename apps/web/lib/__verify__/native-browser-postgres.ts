// Real isolated PostgreSQL scope/LOGIN/effective-role proof; no company data.
import assert from 'node:assert/strict';
import { readFileSync,statSync } from 'node:fs';
import { nativeSessions,NATIVE_COOKIE } from '../native-browser-auth';
import { currentNativeJob,parseSettings,canonical,sha,verifyNativeIdentity,type NativeSettings } from '../native-acceptance';
import { pilotPostgres } from '../oracle2-postgres';
const path=process.env.ORACLE_NATIVE_BROWSER_TEST_CONTEXT;if(!path)throw Error('Protected synthetic fixture required');
assert.equal(statSync(path).mode&0o077,0);
const fixture=JSON.parse(readFileSync(path,'utf8')) as {settings:NativeSettings;admin_url:string;unrelated_login:string;unrelated_url:NativeSettings['database_url']};
for(const url of [fixture.admin_url,readFileSync(fixture.settings.database_url.path,'utf8').trim()])assert.equal(new URL(url).hostname,'127.0.0.1');
const c=fixture.settings;const raw=Buffer.from(canonical(c));parseSettings(raw,sha(raw),Math.floor(Date.now()/1000));
const snapshot=await currentNativeJob(c,c.actor_id);assert.equal(snapshot.status,'pending');let checks=1;
await assert.rejects(currentNativeJob({...c,metadata_login:fixture.unrelated_login,database_url:fixture.unrelated_url},c.actor_id));checks++;
await assert.rejects(currentNativeJob(c,'00000000-0000-4000-8000-000000000099'));checks++;
await assert.rejects(currentNativeJob({...c,source_refs:c.source_refs.map(x=>({...x,original_sha256:'f'.repeat(64)}))},c.actor_id));checks++;
const ownerToken='public-invented-genuine-issuer-test-fixture';
const auth=nativeSessions({token:()=>ownerToken,actors:()=>new Set([c.actor_id]),settings:()=>c,identity:verifyNativeIdentity,current:currentNativeJob,clock:()=>Math.floor(Date.now()/1000)});
const issued=await auth.create(ownerToken);assert.equal(issued.ok,true);checks++;
if(!issued.ok)throw Error('Native issuer fixture failed');
const headers=new Headers({cookie:NATIVE_COOKIE+'='+issued.sessionId});assert.equal((await auth.authorize(headers)).ok,true);checks++;
const admin=pilotPostgres(fixture.admin_url);
try{
 const [grants]=await admin`SELECT count(*)::int AS n FROM oracle2.appointments WHERE actor_id=${c.actor_id}::uuid AND scope IN ('review','confirm')`;
 assert.equal(grants?.n,0);checks++;
 await admin`UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE actor_id=${c.actor_id}::uuid AND scope LIKE 'source-read:%'`;
 assert.equal((await auth.authorize(headers)).ok,false);checks++;
 await assert.rejects(currentNativeJob(c,c.actor_id));checks++;
}finally{await admin.end({timeout:1});}
console.log(`native real PostgreSQL LOGIN/source session verification: ${checks} passed; isolated invented fixture; hosted acceptance false`);
