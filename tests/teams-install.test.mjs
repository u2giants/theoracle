import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const ts = createRequire(import.meta.url)('typescript');
import assert from 'node:assert/strict';

function load(path, mocks, names) {
  const source = ts.transpileModule(readFileSync(path, 'utf8').replace(/^import .*;\n/gm, '').replace(/export /g, ''), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  return new Function(...Object.keys(mocks), `${source}\nreturn {${names}};`)(...Object.values(mocks));
}
const users = Array.from({ length: 12 }, (_, i) => ({ id: String(i).padStart(2, '0'), email: `${i}@popcre.com`, accountEnabled: true }));
process.env.MICROSOFT_BOT_APP_ID = 'bot';
process.env.TEAMS_APP_CATALOG_ID = 'catalog';
let calls = [], mode = 'normal', active = 0, peak = 0;
const fetchMock = async (url, init) => {
  calls.push([String(url), init.method]);
  const callNumber = calls.length;
  active++; peak = Math.max(peak, active);
  await Promise.resolve(); active--;
  if (init.method === 'POST') return new Response('denied', { status: mode === 'conflict' ? 409 : 403 });
  if (mode === 'read-error') return new Response('throttled', { status: 403 });
  if (mode === 'retry' && callNumber === 1) return new Response('', { status: 429, headers: { 'retry-after': '0' } });
  if (mode === 'pages') return Response.json(String(url).includes('page=2')
    ? { value: [{ teamsApp: { id: 'catalog' }, teamsAppDefinition: { bot: { id: 'bot' } } }] }
    : { value: [], '@odata.nextLink': 'https://graph.microsoft.com/v1.0/apps?page=2' });
  return Response.json({ value: [] });
};
const { installOracleForTenant } = load('apps/web/lib/teams-proactive-install.ts', {
  getGraphAccessToken: async () => 'token', listTenantUsers: async () => users, fetch: fetchMock,
}, 'installOracleForTenant');
let result = await installOracleForTenant();
assert.equal(result.nextCursor, '09');
assert.equal(calls.filter(c => c[1] === 'POST').length, 0);
assert(peak <= 5);
calls = []; result = await installOracleForTenant({ dryRun: false });
assert.equal(result.failed, 10); assert.match(result.failures[0], /@popcre.com \(\d+\): 403/);
mode = 'conflict'; result = await installOracleForTenant({ dryRun: false, cursor: '09' });
assert.equal(result.already, 2); assert.equal(result.nextCursor, null);
mode = 'pages'; result = await installOracleForTenant(); assert.equal(result.already, 10);
mode = 'read-error'; calls = []; await assert.rejects(installOracleForTenant({ dryRun: false }), /read: 403/);
assert(!calls.some(c => c[1] === 'POST'));
mode = 'retry'; calls = []; await installOracleForTenant(); assert(calls.length > 10);

class ConfigError extends Error {}
let options, authError = false;
const { POST } = load('apps/web/app/api/admin/teams/install/route.ts', {
  NextResponse: { json: (body, init) => ({ body, status: init?.status ?? 200 }) },
  getCurrentEmployee: async () => { if (authError) throw Error('database'); return { isAdmin: false }; },
  isBrainToken: token => token === 'valid', GraphNotConfiguredError: ConfigError,
  TeamsInstallConfigurationError: ConfigError,
  installOracleForTenant: async opts => { options = opts; return {}; },
}, 'POST');
const req = (body, token = 'valid') => ({ headers: new Headers({ 'x-brain-token': token }), json: async () => body });
assert.equal((await POST(req({}))).status, 200); assert.equal(options.dryRun, true);
await POST(req({ dryRun: false })); assert.equal(options.dryRun, false);
assert.equal((await POST(req(null))).status, 400);
assert.equal((await POST(req({}, 'bad'))).status, 403);
authError = true; assert.equal((await POST(req({}, 'bad'))).status, 500);
console.log('Teams install and admin route tests passed');

process.env.BRAIN_BASE_URL = 'https://brain.invalid';
process.env.BRAIN_SHARED_TOKEN = 'token';
let replies = [], tries = 0, fail = false;
const { handleTurn } = load('apps/web/app/api/teams/bot/messages/route.ts', {
  ActivityTypes: { Message: 'message', ConversationUpdate: 'conversationUpdate', InstallationUpdate: 'installationUpdate' },
  TeamsInfo: { getMember: async () => ({ email: 'employee@popcre.com' }) },
  TurnContext: { getConversationReference: activity => ({ conversation: activity.conversation }) },
  brainService: async () => { tries++; if (fail) throw Error('offline'); return { status: 200, body: { handled: true, reply: null } }; },
  console: { warn() {} },
}, 'handleTurn');
const context = type => ({ activity: { type, action: 'add', conversation: { conversationType: 'personal' }, from: { id: 'user' }, membersAdded: [{ id: 'user' }] }, sendActivity: async text => replies.push(text) });
await handleTurn(context('installationUpdate'), {}); assert.equal(replies.length, 1);
await handleTurn(context('conversationUpdate'), {}); assert.equal(replies.length, 2);
fail = true; tries = 0; await assert.rejects(handleTurn(context('installationUpdate'), {}), /offline/); assert.equal(tries, 3);
const graph = load('apps/web/lib/microsoft-graph.ts', { fetch: async () => Response.json({ access_token: 'access', expires_in: 3600 }) }, 'getGraphAccessToken, GraphNotConfiguredError');
delete process.env.AZURE_TENANT_ID;
await assert.rejects(graph.getGraphAccessToken(), graph.GraphNotConfiguredError);
Object.assign(process.env, { AZURE_TENANT_ID: 'tenant', AZURE_GRAPH_CLIENT_ID: 'client', AZURE_GRAPH_CLIENT_SECRET: 'test' });
assert.equal(await graph.getGraphAccessToken(), 'access');
assert.equal(await graph.getGraphAccessToken(), 'access');
console.log('Teams welcome retry and Graph token tests passed');
