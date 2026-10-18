import assert from 'node:assert/strict';
import {test} from 'node:test';
import identity from '../../dev/oracle2/native-v2-fixed-identities.json';
import {validateNativeV2Payload,validateNativeV2Result,oracle2NativeInventedV2,NATIVE_V2_GRAPH} from './src/trigger/oracle2-native-invented-v2';
test('v2 task only permits exact public opaque identity with no extra fields',()=>{
 const payload={jobId:identity.run,workspaceId:identity.workspace};validateNativeV2Payload(payload,{});
 for(const bad of [null,[],{}, {...payload,text:'private'}, {...payload,jobId:'9c9c7424-8e16-4f71-be10-c935160e16c7'},{...payload,workspaceId:'6426980e-6287-4f58-9e94-d1cb49b5cd5d'}])assert.throws(()=>validateNativeV2Payload(bad,{}));
});
test('v2 task refuses old bundles and privileged credentials even when empty',()=>{
 for(const key of ['ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','GROQ_API_KEY','MISTRAL_API_KEY','ZHIPU_API_KEY','AZURE_OPENAI_API_KEY','ORACLE2_NATIVE_TRIGGER_BUNDLE','ORACLE2_NATIVE_TRIGGER_BUNDLE_SHA256','ORACLE2_PREVIEW_ADMIN_URL','ORACLE_NATIVE_ADMIN_URL','DATABASE_URL','ORACLE2_DATABASE_URL','TRIGGER_ACCESS_TOKEN','ORACLE2_PROJECTOR_GRAPH_URL','SUPABASE_SERVICE_ROLE_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','ORACLE2_CONFIRMED_GRAPH_URL','ORACLE2_PROJECTION_SIGNING_KEY','ORACLE2_CHECKPOINT_DATABASE_URL'])assert.throws(()=>validateNativeV2Payload({jobId:identity.run,workspaceId:identity.workspace},{[key]:''}));
});

test('v2 task and graph identities match the single public manifest',()=>{assert.equal(oracle2NativeInventedV2.id,identity.task);assert.equal(NATIVE_V2_GRAPH,identity.graph_name);});

test('v2 task refuses stale, incomplete, malformed or foreign completion metadata',()=>{
 const payload={jobId:identity.run,workspaceId:identity.workspace};
 const output={schema_version:1,state:'completed',job_id:identity.run,workspace_id:identity.workspace,runtime_hash:'a'.repeat(64),release_hash:'b'.repeat(64),artifact_hash:'c'.repeat(64),result_sha256:'d'.repeat(64),sdk_version:'1.4.0',graph_name:identity.graph_name,expires_at:1001};
 validateNativeV2Result(output,payload,1000);
 for(const patch of [{expires_at:1000},{expires_at:999},{expires_at:1.2},{state:'counterfeit'},{artifact_hash:'bad'},{job_id:'9c9c7424-8e16-4f71-be10-c935160e16c7'},{graph_name:'old-v1'},{extra:'forbidden'}])assert.throws(()=>validateNativeV2Result({...output,...patch},payload,1000));
 for(const bad of [null,[],{},'completed'])assert.throws(()=>validateNativeV2Result(bad,payload,1000));
});
