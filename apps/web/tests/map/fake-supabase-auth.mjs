// Stand-in for Supabase Auth used only by the Company Map browser test
// (plan step 10). It answers GET /auth/v1/user for the one test session
// token so the real login check in the app (proxy + requireEmployee) passes
// against the seeded test employee. It runs on localhost and never talks to
// a real Supabase project.
import { createServer } from 'node:http';

const port = Number(process.env.MAP_E2E_AUTH_PORT ?? 54399);
const token = process.env.MAP_E2E_ACCESS_TOKEN ?? 'map-e2e-access-token';
const userId = process.env.MAP_E2E_AUTH_USER_ID ?? '00000000-0000-4000-8000-0000000000e2';

const user = {
  id: userId,
  aud: 'authenticated',
  role: 'authenticated',
  email: 'map-e2e@test.invalid',
  app_metadata: { provider: 'email', providers: ['email'] },
  user_metadata: {},
  identities: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

createServer((req, res) => {
  const url = new URL(req.url ?? '/', `http://localhost:${port}`);
  if (url.pathname === '/health') {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('{"ok":true}');
    return;
  }
  if (url.pathname === '/auth/v1/user' && req.method === 'GET') {
    const auth = req.headers.authorization ?? '';
    if (auth === `Bearer ${token}`) {
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify(user));
      return;
    }
    res.writeHead(401, { 'content-type': 'application/json' });
    res.end('{"code":401,"msg":"invalid token"}');
    return;
  }
  res.writeHead(404, { 'content-type': 'application/json' });
  res.end('{"msg":"not found"}');
}).listen(port, '127.0.0.1');
