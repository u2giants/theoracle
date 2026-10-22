import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {MEETING_TASK_FILES} from './meeting-target-profile.mjs';
const require=createRequire(import.meta.url);
const {build}=require('esbuild') as typeof import('esbuild');
for(const name of MEETING_TASK_FILES)test('actual isolated meeting bundle '+name,async()=>{
 const result=await build({entryPoints:[fileURLToPath(new URL('./src/trigger/'+name,import.meta.url))],bundle:true,write:false,platform:'node',format:'esm',target:'node24',external:['@trigger.dev/sdk/v3'],metafile:true,logLevel:'silent'});
 const inputs=Object.keys(result.metafile!.inputs);
 assert.ok(inputs.some(p=>p.endsWith('shared/src/protected-meeting-worker.ts')));
 assert.ok(inputs.some(p=>p.endsWith('shared/src/protected-service-channel.ts')));
 assert.ok(!inputs.some(p=>/packages\/(db|auth|ai)\/|apps\/web\/|oracle2-python|legacy/i.test(p)));
 // The existing Recall semantic helper is permitted only for participation;
 // actual esbuild output must eliminate every retained legacy credential path.
 if(name!=='oracle2-meeting-participation.ts')assert.ok(!inputs.some(p=>p.endsWith('src/lib/recall.ts')));
 assert.equal(result.outputFiles!.length,1);
 const output=result.outputFiles![0]!.text;
 assert.match(output,/maxAttempts: 1/);
 for(const forbidden of ['SUPABASE_SERVICE_ROLE_KEY','RECALL_API_KEY','TRIGGER_SECRET_KEY','process.env.RECALL_BASE_URL'])assert.ok(!output.includes(forbidden),forbidden);
});
