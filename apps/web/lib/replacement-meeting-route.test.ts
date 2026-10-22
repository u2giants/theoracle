/** Actual exported route routing only. Production ingress mTLS, signature and
 * framing checks have their own actual-wire suite; no live delivery claim. */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { registerHooks } from 'node:module';
import { NextRequest } from 'next/server';

const fixture = { strict: [] as Request[], verified: [] as unknown[], queued: [] as unknown[] };
(globalThis as unknown as Record<string, unknown>).__meetingRouteFixture = fixture;
const hooks = registerHooks({
  resolve(specifier, context, next) {
    if (context.parentURL?.endsWith('/api/teams/live/recall/route.ts')) {
      if (specifier === '@/lib/trigger') return {url:'meeting-route-test:trigger',shortCircuit:true};
      if (specifier === '@/lib/recall') return {url:'meeting-route-test:verify',shortCircuit:true};
      if (specifier === '@/lib/replacement-protected-client') return {url:'meeting-route-test:strict',shortCircuit:true};
    }
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url === 'meeting-route-test:trigger') return {format:'module',shortCircuit:true,source:`export async function triggerTask(...args){globalThis.__meetingRouteFixture.queued.push(args);}`};
    if (url === 'meeting-route-test:verify') return {format:'module',shortCircuit:true,source:`export function verifyRecallRequest(args){globalThis.__meetingRouteFixture.verified.push(args);}`};
    if (url === 'meeting-route-test:strict') return {format:'module',shortCircuit:true,source:`export async function requestReplacementMeetingIngress(req){globalThis.__meetingRouteFixture.strict.push(req);return new Response(null,{status:202});}`};
    return next(url, context);
  },
});
let route: typeof import('../app/api/teams/live/recall/route');
before(async () => { route = await import('../app/api/teams/live/recall/route'); });
const originalMode = process.env.ORACLE2_MEETING_ROUTING_MODE;
const originalSecret = process.env.RECALL_WEBHOOK_SECRET;
after(() => {
  hooks.deregister();
  for (const [key, value] of [['ORACLE2_MEETING_ROUTING_MODE',originalMode],['RECALL_WEBHOOK_SECRET',originalSecret]]) {
    if (value === undefined) delete process.env[key!]; else process.env[key!] = value;
  }
  delete (globalThis as unknown as Record<string, unknown>).__meetingRouteFixture;
});
const request = () => new NextRequest('https://invented.example.test/api/teams/live/recall', {method:'POST',body:'{"event":"invented"}'});

test('replacement mode passes the identical unread request exclusively to strict ingress', async () => {
  process.env.ORACLE2_MEETING_ROUTING_MODE = 'replacement';
  delete process.env.RECALL_WEBHOOK_SECRET;
  const req = request();
  Object.defineProperty(req,'text',{value:()=>{throw new Error('legacy body read');}});
  assert.equal((await route.POST(req)).status,202);
  assert.equal(fixture.strict.length,1);
  assert.equal(fixture.strict[0],req);
  assert.equal(req.bodyUsed,false);
  assert.equal(fixture.verified.length,0);
  assert.equal(fixture.queued.length,0);
});
test('unknown and empty routing modes refuse before body, secret, verifier or either delivery path', async () => {
  for (const mode of ['', 'Replacement', 'invented-invalid']) {
    process.env.ORACLE2_MEETING_ROUTING_MODE = mode;
    const req = request();
    Object.defineProperty(req,'text',{value:()=>{throw new Error('unexpected body read');}});
    const response = await route.POST(req);
    assert.equal(response.status,503);
    assert.equal(response.headers.get('cache-control'),'private, no-store, max-age=0');
    assert.equal(req.bodyUsed,false);
  }
  assert.equal(fixture.strict.length,1);
  assert.equal(fixture.verified.length,0);
  assert.equal(fixture.queued.length,0);
});
test('default and explicit legacy modes retain the original verification and single queue contract', async () => {
  process.env.RECALL_WEBHOOK_SECRET = 'invented-route-fixture-only';
  for (const mode of [undefined,'legacy']) {
    if (mode === undefined) delete process.env.ORACLE2_MEETING_ROUTING_MODE;
    else process.env.ORACLE2_MEETING_ROUTING_MODE = mode;
    const req = request();
    assert.equal((await route.POST(req)).status,202);
    assert.equal(req.bodyUsed,true);
  }
  assert.equal(fixture.strict.length,1);
  assert.equal(fixture.verified.length,2);
  assert.equal(fixture.queued.length,2);
  for (const args of fixture.queued as [string,{receivedAt:string;event:unknown}][]) {
    assert.equal(args[0],'teams-live-recall-utterance');
    assert.deepEqual(args[1].event,{event:'invented'});
    assert.ok(Number.isFinite(Date.parse(args[1].receivedAt)));
  }
});
