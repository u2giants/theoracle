import test from 'node:test';
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { verifyRecallRequest } from './recall';
const secret = 'whsec_' + Buffer.alloc(48, 7).toString('base64');
function fixture(payload='{"event":"transcript.data"}', seconds=Math.floor(Date.now()/1000)) {
  const id='msg_exact';const timestamp=String(seconds);
  const sig=createHmac('sha256',Buffer.alloc(48,7)).update(`${id}.${timestamp}.${payload}`).digest('base64');
  return {secret,payload,headers:new Headers({'webhook-id':id,'webhook-timestamp':timestamp,'webhook-signature':`v1,${sig}`}),policy:'replacement-v1' as const};
}
test('replacement verifies exact current account bytes, preserving legacy option',()=>{
  verifyRecallRequest(fixture());
  const old=fixture('legacy',1);delete (old as {policy?:string}).policy;verifyRecallRequest(old);
  const legacy=fixture();for(const suffix of ['id','timestamp','signature']) {legacy.headers.set(`svix-${suffix}`,legacy.headers.get(`webhook-${suffix}`)!);legacy.headers.delete(`webhook-${suffix}`);}delete (legacy as {policy?:string}).policy;verifyRecallRequest(legacy);
});
test('replacement refuses stale/future/noncanonical timestamp and mixed header family',()=>{
  for(const t of [Math.floor(Date.now()/1000)-301,Math.floor(Date.now()/1000)+31]) assert.throws(()=>verifyRecallRequest(fixture('x',t)));
  for(const stamp of ['01','1.5','+1','NaN','1, 1',' 1']) {const f=fixture();f.headers.set('webhook-timestamp',stamp);assert.throws(()=>verifyRecallRequest(f));}
  for(const suffix of ['id','timestamp','signature']) {const f=fixture();f.headers.set(`svix-${suffix}`,'x');assert.throws(()=>verifyRecallRequest(f));}
});
test('replacement bounds canonical keys, signature population, IDs and original UTF8 bytes',()=>{
  for(const key of ['', 'whsec_YQ==',secret+'=', 'whsec_'+Buffer.alloc(129).toString('base64')]) assert.throws(()=>verifyRecallRequest({...fixture(),secret:key}));
  for(const id of ['', 'x'.repeat(257),'é','one,two']) {const f=fixture();f.headers.set('webhook-id',id);assert.throws(()=>verifyRecallRequest(f));}
  for(const sig of ['v1,AA==','v2,'+'A'.repeat(43)+'=', 'v1,'+'A'.repeat(44),' '.repeat(197)]) {const f=fixture();f.headers.set('webhook-signature',sig);assert.throws(()=>verifyRecallRequest(f));}
  const f=fixture();const valid=f.headers.get('webhook-signature')!;f.headers.set('webhook-signature',Array(4).fill(valid).join(' '));verifyRecallRequest(f);f.headers.set('webhook-signature',Array(5).fill(valid).join(' '));assert.throws(()=>verifyRecallRequest(f));
  assert.throws(()=>verifyRecallRequest(fixture('x'.repeat(1024*1024+1))));
  assert.throws(()=>verifyRecallRequest(fixture('\ud800')));
  verifyRecallRequest(fixture('原文'));assert.throws(()=>verifyRecallRequest({...fixture('原文'),payload:'changed'}));
});
