import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {triggerSettings,createTriggerNativeSession,authorizeTriggerNativeRequest,triggerNativeHandler,nativeTriggerCompletionMatches} from './native-trigger';
const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
const enc=(s:string)=>Buffer.from(s).toString('base64');
function install(patch:Record<string,unknown>={}){
 const now=Math.floor(Date.now()/1000);
 const body={schema_version:1,purpose:'public-invented-trigger-v1',issued_at:now-1,expires_at:now+100,runtime_hash:'a'.repeat(64),review_hash:'b'.repeat(64),release_hash:'c'.repeat(64),admission_hash:hash('oracle-public-invented-trigger-fixture/v1'),files:{database_url:enc('postgresql://oracle_synthetic_gateway.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v1'),database_ca:enc('invented unit CA only')},...patch};
 const raw=JSON.stringify(body);process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE=raw;process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE_SHA256=hash(raw);return body;
}
test('new native web bundle keeps exact isolated SQL target and verify-full',()=>{install();const s=triggerSettings();assert.match(s.url,/sslmode=verify-full/);assert.match(s.url,/oracle_native_proof_v1/);});
test('expired, foreign or extended authority is rejected without a connection',()=>{
 for(const patch of [{purpose:'public-invented-v1'},{expires_at:1},{issued_at:1,expires_at:9999999999},{runtime_hash:'bad'}]){install(patch);assert.throws(()=>triggerSettings());}
});
test('missing/tampered bundle cannot grant native permission',()=>{install();process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE_SHA256='0'.repeat(64);assert.throws(()=>triggerSettings());delete process.env.ORACLE2_NATIVE_TRIGGER_WEB_BUNDLE;assert.throws(()=>triggerSettings());});
test('retained pilot DB and SSL override cannot become native SQL target',()=>{
 for(const url of ['postgresql://oracle_synthetic_gateway.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/postgres','postgresql://oracle_synthetic_gateway.wfdrklofsczspazshaib:invented@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v1?sslmode=disable']){install({files:{database_url:enc(url),database_ca:enc('invented')}});assert.throws(()=>triggerSettings());}
});
test('Vercel access and wrong native token do not grant native session',async()=>{
 install();process.env.ORACLE2_NATIVE_TRIGGER_TOKEN='invented-native-token';assert.equal((await createTriggerNativeSession('wrong')).ok,false);assert.equal((await authorizeTriggerNativeRequest(new Headers())).ok,false);
 const response=await triggerNativeHandler(new Request('https://oracle.designflow.app/api/consultant/native-acceptance'),'result');assert.equal(response.status,401);assert.deepEqual(await response.json(),{error:'Hosted invented-data test unavailable'});
});

test('Trigger completion must bind actual artifact and canonical result, not just a successful job',()=>{
 const expected={runtimeHash:'a'.repeat(64),releaseHash:'b'.repeat(64),artifactHash:'c'.repeat(64),resultSha256:'d'.repeat(64),expiresAt:1234};
 const output={schema_version:1,state:'completed',job_id:'9c9c7424-8e16-4f71-be10-c935160e16c7',workspace_id:'6426980e-6287-4f58-9e94-d1cb49b5cd5d',runtime_hash:expected.runtimeHash,release_hash:expected.releaseHash,artifact_hash:expected.artifactHash,result_sha256:expected.resultSha256,sdk_version:'1.4.0',graph_name:'oracle_operating_model_v1_6426980e62874f589e94d1cb49b5cd5d_992fa7e3138e443a99fda466205b2fde_1_b30a0da35a5b4a979c51733e383aa21e',expires_at:1234};
 assert.equal(nativeTriggerCompletionMatches(output,expected),true);
 for(const patch of [{artifact_hash:'e'.repeat(64)},{result_sha256:'f'.repeat(64)},{job_id:'77777777-7777-4777-8777-777777777777'},{expires_at:1235},{private_text:'forbidden'}])assert.equal(nativeTriggerCompletionMatches({...output,...patch},expected),false);
});
