import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
let compile;
try {
  const ts = require('typescript');
  compile = (source) => ts.transpile(source, { target: ts.ScriptTarget.ES2022 });
} catch {
  // The offline runner provides Babel through the operating system.
  const { transformSync } = require('@babel/core');
  const transformTypescript = require('@babel/plugin-transform-typescript');
  compile = (source) => transformSync(source, { filename: 'route.ts', plugins: [transformTypescript], configFile: false, babelrc: false }).code;
}
import vm from 'node:vm';

function fixture({ users, graphError, openError, storeStatus = 200, lookupStatus = 200 } = {}) {
  let source = readFileSync(new URL('../app/api/teams/bot/proactive/route.ts', import.meta.url), 'utf8');
  source = source.replace(/import[\s\S]*?from '[^']+';/g, '').replace(/export /g, '');
  const calls = { open: 0, send: 0, store: 0 };
  const env = { MICROSOFT_BOT_TENANT_ID: 'tenant', TEAMS_SERVICE_URL: 'https://configured/' };
  const context = vm.createContext({
    process: { env }, console: { warn() {}, error() {} },
    NextResponse: { json: (body, init) => ({ body, status: init?.status ?? 200 }) },
    isBrainToken: () => true,
    listTenantUsers: async () => { if (graphError) throw graphError; return users ?? [{ id: 'u', email: 'a@b', accountEnabled: true }]; },
    teamsBotAppId: () => 'app',
    TurnContext: { getConversationReference: () => ({ conversation: { id: 'chat' } }) },
    brainService: async (_path, init) => {
      if (init) { calls.store++; return { status: calls.store === 1 ? storeStatus : 200, body: { stored: true } }; }
      return { status: lookupStatus, body: { emails: ['a@b'], service_url: 'https://foreign/' } };
    },
    getTeamsBotAdapter: () => ({
      createConversationAsync: async (_app, _channel, url, _aud, _params, cb) => {
        calls.open++; assert.equal(url, env.TEAMS_SERVICE_URL);
        if (openError) throw openError;
        await cb({ activity: {} });
      },
      continueConversationAsync: async (_app, _ref, cb) => cb({ sendActivity: async () => { calls.send++; } }),
    }),
  });
  vm.runInContext(compile(source), context);
  const post = () => context.POST({ headers: { get: () => 'token' }, json: async () => ({ employee_id: 'e', text: 'hi' }) });
  return { post, calls, env };
}

test('opens, saves and sends using the configured endpoint', async () => {
  const f = fixture(); assert.equal((await f.post()).status, 200);
  assert.deepEqual(f.calls, { open: 1, store: 1, send: 1 });
});
test('recipient codes advance; auth, throttling and service failures retry', async () => {
  for (const code of ['BotNotInConversation', 'MissingConversationParameter', 'UserNotFound']) {
    assert.equal((await fixture({ openError: { code } }).post()).status, 404);
  }
  for (const openError of [{ statusCode: 401 }, { statusCode: 429 }, { code: 'ServiceError' }]) {
    assert.equal((await fixture({ openError }).post()).status, 502);
  }
});
test('missing or disabled recipients skip without opening', async () => {
  for (const users of [[], [{ id: 'u', email: 'a@b', accountEnabled: false }]]) {
    const f = fixture({ users }); assert.equal((await f.post()).status, 404); assert.equal(f.calls.open, 0);
  }
});
test('Graph and endpoint configuration failures retry without skipping', async () => {
  assert.equal((await fixture({ graphError: new Error('not configured') }).post()).status, 502);
  const f = fixture(); delete f.env.TEAMS_SERVICE_URL;
  assert.equal((await f.post()).status, 502); assert.equal(f.calls.open, 0);
});
test('failed persistence prevents sending and reuses the opened reference on retry', async () => {
  const f = fixture({ storeStatus: 503 });
  assert.equal((await f.post()).status, 502); assert.equal(f.calls.send, 0);
  assert.equal((await f.post()).status, 200);
  assert.deepEqual(f.calls, { open: 1, store: 2, send: 1 });
});
test('unknown employees are distinguished from unreachable recipients', async () => {
  const f = fixture({ lookupStatus: 404 });
  assert.equal((await f.post()).body.error, 'unknown_employee'); assert.equal(f.calls.open, 0);
});

test('concurrent requests share conversation creation', async () => {
  const f = fixture();
  const responses = await Promise.all([f.post(), f.post()]);
  assert.ok(responses.every((response) => response.status === 200));
  assert.equal(f.calls.open, 1);
});
