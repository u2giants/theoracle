/** Actual pinned SDK catalog/indexing; no Trigger dispatch or target call. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {dirname,join} from 'node:path';
import {MEETING_TASK_FILES} from './meeting-target-profile.mjs';
const require=createRequire(import.meta.url);
const {resourceCatalog}=require('@trigger.dev/core/v3');
const {StandardResourceCatalog}=require(join(dirname(require.resolve('@trigger.dev/core/v3')),'resource-catalog/standardResourceCatalog.js'));
// Use the SAME installed SDK's real indexer catalog, not a replacement task().
resourceCatalog.setGlobalResourceCatalog(new StandardResourceCatalog());
const identity='12345678-1234-4234-8234-123456789012';
for(const name of MEETING_TASK_FILES)test('actual SDK closed callback and one-attempt metadata '+name,async()=>{
 resourceCatalog.setCurrentFileContext(name,name);
 const taskModule=await import('./src/trigger/'+name);
 resourceCatalog.clearCurrentFileContext();
 const values=Object.values(taskModule) as Array<{id:string}>;
 assert.equal(values.length,1);
 const metadata=resourceCatalog.getTask(values[0]!.id);
 assert.ok(metadata,values[0]!.id);
 assert.equal(metadata.retry.maxAttempts,1);assert.equal(metadata.maxDuration,30);
 const invalid=[{actor_id:identity},Object.create({actor_id:identity}),Object.defineProperty({},'hidden',{value:identity}),{[Symbol('selector')]:identity},[],null];
 for(const payload of invalid)await assert.rejects(()=>metadata.fns.run(payload));
 const payload=name==='oracle2-meeting-ingress-normalize.ts'?{ingress_event_id:identity}:{};
 // No separately installed profile exists in this test. Closed callback stays
 // UNKNOWN, without SDK trigger() or a fallback to legacy runtime credentials.
 const result=await metadata.fns.run(payload);
 assert.equal(result.outcome??result.state,'UNKNOWN');
 assert.equal(result.remote_stop_proven??result.source_read_permission,false);
});
