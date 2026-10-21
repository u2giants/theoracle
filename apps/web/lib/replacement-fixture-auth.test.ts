import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fixtureConfig, fixtureRequestAllowed, fixtureSameOrigin, fixtureSession, fixtureSessionCookie } from './replacement-fixture-auth';

const valid = {
  NODE_ENV: 'test', ORACLE2_REPLACEMENT_FIXTURE_MODE: '1',
  ORACLE2_REPLACEMENT_TOKEN: 'invented-fixture-test-token-000000000000000',
  ORACLE2_REPLACEMENT_FIXTURE_SESSION_KEY: 'invented-fixture-signing-key-111111111111111',
};

test('fixture configuration fails closed outside explicit local mode', () => {
  assert.ok(fixtureConfig(valid));
  for (const change of [
    { NODE_ENV: 'production' }, { ORACLE2_REPLACEMENT_FIXTURE_MODE: '' },
    { ORACLE2_REPLACEMENT_TOKEN: '' }, { ORACLE2_REPLACEMENT_FIXTURE_SESSION_KEY: '' },
    { ORACLE2_REPLACEMENT_TOKEN: valid.ORACLE2_REPLACEMENT_FIXTURE_SESSION_KEY },
  ]) assert.equal(fixtureConfig({ ...valid, ...change }), null);
});

test('fixture request and signed session enforce local origin, signature and expiry', () => {
  const previous = { ...process.env };
  Object.assign(process.env, valid);
  try {
    const headers = new Headers({ host: '127.0.0.1:3000', origin: 'http://127.0.0.1:3000' });
    assert.equal(fixtureRequestAllowed(headers, 'http://127.0.0.1:3000/api/session'), true);
    assert.equal(fixtureRequestAllowed(headers, 'http://localhost:3000/api/session'), true);
    assert.equal(fixtureRequestAllowed(headers, 'https://localhost:3000/api/session'), false);
    assert.equal(fixtureRequestAllowed(headers, 'http://localhost:3001/api/session'), false);
    assert.equal(fixtureSameOrigin(headers), true);
    const id = '00000000-0000-4000-8000-000000000001';
    const now = 1000000;
    headers.set('cookie', fixtureSessionCookie(id, now).split(';')[0]!);
    assert.equal(fixtureSession(headers, now), id);
    assert.equal(fixtureSession(headers, now + 900000), null);
    headers.set('cookie', headers.get('cookie')!.replace(id, 'forged') + 'x');
    assert.equal(fixtureSession(headers, now), null);
    headers.set('host', 'example.com');
    headers.set('x-forwarded-host', '127.0.0.1:3000');
    assert.equal(fixtureRequestAllowed(headers), false);
    headers.set('host', '127.0.0.1:3000');
    assert.equal(fixtureRequestAllowed(headers, 'http://example.com/api/session'), false);
    headers.set('origin', 'https://127.0.0.1:3000');
    headers.set('x-forwarded-proto', 'https');
    assert.equal(fixtureSameOrigin(headers), false);
    Object.assign(process.env, { NODE_ENV: 'production' });
    assert.equal(fixtureRequestAllowed(headers), false);
    assert.equal(fixtureSession(headers, now), null);
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
  }
});
