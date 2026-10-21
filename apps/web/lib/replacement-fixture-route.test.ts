// Direct local fixture login endpoint denials. Invented identities only.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NextRequest } from 'next/server';
import { POST } from '../app/api/consultant/replacement/v1/session/route';
import { FIXTURE_ACTOR, fixtureSession } from './replacement-fixture-auth';

const TOKEN = 'invented-endpoint-test-token-000000000000000';
const KEY = 'invented-endpoint-test-key-11111111111111111';
const URL = 'http://127.0.0.1:3198/api/consultant/replacement/v1/session';

async function inFixture(run: () => Promise<void>, overrides: Record<string, string> = {}) {
  const prior = { ...process.env };
  Object.assign(process.env, {
    NODE_ENV: 'test', ORACLE2_REPLACEMENT_FIXTURE_MODE: '1',
    ORACLE2_REPLACEMENT_TOKEN: TOKEN, ORACLE2_REPLACEMENT_FIXTURE_SESSION_KEY: KEY,
    ORACLE2_REPLACEMENT_ACTOR: 'untrusted-configured-actor',
    ORACLE2_REPLACEMENT_ROLE: 'untrusted-configured-role', ...overrides,
  });
  try { await run(); }
  finally {
    for (const key of Object.keys(process.env)) if (!(key in prior)) delete process.env[key];
    Object.assign(process.env, prior);
  }
}

function request(body: unknown, headers: Record<string, string> = {}) {
  return new NextRequest(URL, {
    method: 'POST', headers: {
      host: '127.0.0.1:3198', origin: 'http://127.0.0.1:3198',
      'content-type': 'application/json', ...headers,
    }, body: JSON.stringify(body),
  });
}

for (const [name, overrides] of [
  ['production', { NODE_ENV: 'production' }],
  ['disabled fixture', { ORACLE2_REPLACEMENT_FIXTURE_MODE: '' }],
  ['missing configured token', { ORACLE2_REPLACEMENT_TOKEN: '' }],
  ['missing configured key', { ORACLE2_REPLACEMENT_FIXTURE_SESSION_KEY: '' }],
] as const) {
  test(`fixture login endpoint refuses ${name}`, async () => {
    await inFixture(async () => {
      const response = await POST(request({ token: TOKEN }));
      assert.equal(response.status, 404);
      assert.equal(response.headers.get('set-cookie'), null);
    }, overrides);
  });
}

for (const [name, body] of [
  ['wrong token', { token: 'wrong-token' }], ['missing token', {}],
  ['array body', [{ token: TOKEN }]], ['null body', null],
  ['non-string token', { token: 123 }],
  ['caller actor', { token: TOKEN, actorId: 'caller-actor' }],
  ['caller workspace', { token: TOKEN, workspaceId: 'caller-workspace' }],
  ['caller role', { token: TOKEN, role: 'admin' }],
  ['unknown field', { token: TOKEN, extra: true }],
] as const) {
  test(`fixture login endpoint refuses ${name}`, async () => {
    await inFixture(async () => {
      const response = await POST(request(body));
      assert.equal(response.status, 401);
      assert.equal(response.headers.get('set-cookie'), null);
    });
  });
}

for (const [name, headers] of [
  ['missing origin', { origin: '' }],
  ['cross origin', { origin: 'http://elsewhere.example' }],
  ['wrong scheme', { origin: 'https://127.0.0.1:3198' }],
  ['cross-site fetch', { 'sec-fetch-site': 'cross-site' }],
] as const) {
  test(`fixture login endpoint refuses ${name}`, async () => {
    await inFixture(async () => {
      const response = await POST(request({ token: TOKEN }, headers));
      assert.equal(response.status, 403);
      assert.equal(response.headers.get('set-cookie'), null);
    });
  });
}

test('fixture login endpoint issues only fixed invented actor and signed HTTP-only cookie', async () => {
  await inFixture(async () => {
    const response = await POST(request({ token: TOKEN }));
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { actorId: FIXTURE_ACTOR });
    const cookie = response.headers.get('set-cookie');
    assert.ok(cookie);
    assert.match(cookie, /HttpOnly/);
    assert.match(cookie, /SameSite=Strict/);
    const headers = new Headers({ host: '127.0.0.1:3198', cookie: cookie.split(';')[0]! });
    assert.match(fixtureSession(headers) ?? '', /^[0-9a-f-]{36}$/);
  });
});
