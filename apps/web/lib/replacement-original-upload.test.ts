/** Pure browser controller proof; fake fetch grants no session/SQL authority. */
import assert from 'node:assert/strict';
import { afterEach,test } from 'node:test';
import { createHash } from 'node:crypto';
import { createOriginalUploadSession,OriginalUploadUnknown } from './replacement-original-upload';
import { canonicalJson } from './replacement-canonical-json';
import type { UploadResponse } from './replacement-upload-contract';
const originalFetch=globalThis.fetch;
afterEach(()=>{globalThis.fetch=originalFetch;});
const sha=(b:Uint8Array|string)=>createHash('sha256').update(b).digest('hex');
const id='11111111-1111-4111-8111-111111111111';
function fixture(mode='valid'){
 const bodies:Record<string,unknown>[]=[],chunks:Buffer[]=[];let state:UploadResponse|undefined;
 globalThis.fetch=(async(path,options)=>{
  assert.equal(path,'/api/consultant/replacement/v1/protected/upload');assert.equal(options?.method,'POST');assert.equal(options?.redirect,'error');assert.equal(options?.credentials,'same-origin');
  const raw=String(options?.body);assert.ok(Buffer.byteLength(raw)<=2850000);const body=JSON.parse(raw);bodies.push(body);
  if(mode==='uncertain'&&body.operation==='chunk')throw new Error('invented uncertain close');
  if(body.operation==='begin')state={schema_version:1,state:'reserved',reservation_id:id,source_id:id,revision:1,begin_sha256:sha(raw),received_bytes:0,next_chunk_index:0,valid_until:body.caller_deadline,qualification:false,remote_stop_proven:false,observation_only:true,source_snapshot:null};
  else{assert.ok(state);assert.equal(body.caller_deadline,bodies[0]!.caller_deadline);assert.equal(body.begin_sha256,state.begin_sha256);
   if(body.operation==='chunk'){const part=Buffer.from(body.data_base64,'base64');assert.equal(sha(part),body.chunk_sha256);assert.equal(body.offset,chunks.reduce((n,b)=>n+b.length,0));chunks.push(part);state={...state,state:'receiving',received_bytes:state.received_bytes+part.length,next_chunk_index:state.next_chunk_index+1};}
   else if(body.operation==='finalize')state={...state,state:'committed',source_snapshot:{sourceId:id,revision:1,originalSha256:String(bodies[0]!.original_sha256),byteCount:state.received_bytes,mediaType:'application/pdf',filename:String(bodies[0]!.filename),state:'awaiting_original_reading',qualifiedSourceRef:null}};
   else if(body.operation==='cancel')state={...state,state:'cancelled'};
  }
  return new Response(canonicalJson(state),{status:200,headers:{'content-type':'application/json'}});
 }) as typeof fetch;
 return {bodies,chunks};
}
test('selected25MiB File uses13bounded chunks and one unchanged deadline without qualification',async()=>{
 const f=fixture(),data=Buffer.alloc(25*1024*1024,32);data.write('%PDF-1.7\n');const result=await createOriginalUploadSession().run(new File([data],'invented.pdf',{type:'application/pdf'}),()=>undefined);
 assert.equal(f.bodies.length,15);assert.equal(f.chunks.length,13);assert.deepEqual(Buffer.concat(f.chunks),data);assert.equal(result.state,'committed');assert.equal(result.qualification,false);
});
test('uncertain chunk aborts whole chain with no automatic request or finalize retry',async()=>{
 const f=fixture('uncertain'),session=createOriginalUploadSession();await assert.rejects(session.run(new File(['%PDF-invented'],'invented.pdf',{type:'application/pdf'}),()=>undefined),OriginalUploadUnknown);assert.equal(f.bodies.length,2);assert.equal(f.bodies.some(b=>b.operation==='finalize'),false);await assert.rejects(session.run(new File(['%PDF-'],'a.pdf',{type:'application/pdf'}),()=>undefined),OriginalUploadUnknown);assert.equal(f.bodies.length,2);
});
test('stop-sending sends only explicit local cancel after current request and never finalizes',async()=>{
 const f=fixture(),session=createOriginalUploadSession();const result=await session.run(new File(['%PDF-invented'],'invented.pdf',{type:'application/pdf'}),()=>session.cancel());assert.equal(result.state,'cancelled');assert.deepEqual(f.bodies.map(b=>b.operation),['begin','cancel']);assert.equal(result.remote_stop_proven,false);
});
test('invalid selection refuses before any request',async()=>{
 const f=fixture();for(const file of [new File(['no'],'wrong.pdf',{type:'application/pdf'}),new File(['%PDF-'],'wrong.txt',{type:'text/plain'}),new File([new Uint8Array(26*1024*1024)],'large.pdf',{type:'application/pdf'})])await assert.rejects(createOriginalUploadSession().run(file,()=>undefined));assert.equal(f.bodies.length,0);
});
