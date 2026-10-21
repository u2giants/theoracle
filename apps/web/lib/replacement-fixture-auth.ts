// Explicit local invented-data session transport. Never admitted in production.
import { createHmac, timingSafeEqual } from 'node:crypto';

export const FIXTURE_ACTOR = '00000000-0000-4000-8000-0000000000f2';
const TTL_SECONDS = 15 * 60;
const COOKIE = 'oracle2_replacement_fixture';

export function fixtureConfig(env: Record<string, string | undefined> = process.env) {
  if (!['development', 'test'].includes(env.NODE_ENV ?? '') ||
      env.ORACLE2_REPLACEMENT_FIXTURE_MODE !== '1') return null;
  const token = env.ORACLE2_REPLACEMENT_TOKEN ?? '';
  const key = env.ORACLE2_REPLACEMENT_FIXTURE_SESSION_KEY ?? '';
  if (token.length < 32 || key.length < 32 || token === key) return null;
  return { token, key };
}

export function fixtureRequestAllowed(headers: Headers, requestUrl?: string): boolean {
  if (!fixtureConfig()) return false;
  const host = headers.get('host') ?? '';
  try {
    const local = new URL(`http://${host}`);
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(local.hostname) ||
        local.host !== host || local.username || local.password) return false;
    if (requestUrl) {
      const request = new URL(requestUrl);
      if (request.protocol !== 'http:' || request.port !== local.port ||
          !['127.0.0.1', 'localhost', '[::1]'].includes(request.hostname) ||
          request.username || request.password) return false;
    }
    return true;
  } catch { return false; }
}

export function fixtureSameOrigin(headers: Headers): boolean {
  // Local HTTP only. Proxy headers never select the trusted origin.
  return fixtureRequestAllowed(headers) &&
    headers.get('origin') === `http://${headers.get('host')}` &&
    ['', 'same-origin', 'none'].includes(headers.get('sec-fetch-site') ?? '');
}

export function fixtureSessionCookie(sessionId: string, now = Date.now()): string {
  const config = fixtureConfig();
  if (!config) throw new Error('fixture authentication unavailable');
  const body = Buffer.from(JSON.stringify([sessionId, Math.floor(now / 1000) + TTL_SECONDS])).toString('base64url');
  const signature = createHmac('sha256', config.key).update(body).digest('base64url');
  return `${COOKIE}=${body}.${signature}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${TTL_SECONDS}`;
}

export function fixtureSession(headers: Headers, now = Date.now()): string | null {
  const config = fixtureConfig();
  if (!config || !fixtureRequestAllowed(headers)) return null;
  const cookies = (headers.get('cookie') ?? '').split(';').map(x => x.trim()).filter(x => x.startsWith(`${COOKIE}=`));
  if (cookies.length !== 1) return null;
  const parts = cookies[0]!.slice(COOKIE.length + 1).split('.');
  if (parts.length !== 2) return null;
  const [body, signature] = parts as [string, string];
  if (body.length > 1024 || !/^[A-Za-z0-9_-]{43}$/.test(signature)) return null;
  const expected = createHmac('sha256', config.key).update(body).digest('base64url');
  if (!timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  try {
    const data: unknown = JSON.parse(Buffer.from(body, 'base64url').toString());
    if (!Array.isArray(data) || data.length !== 2 || typeof data[0] !== 'string' ||
        !/^[0-9a-f-]{36}$/.test(data[0]) || !Number.isSafeInteger(data[1])) return null;
    const seconds = Math.floor(now / 1000);
    if (data[1] <= seconds || data[1] > seconds + TTL_SECONDS) return null;
    return data[0];
  } catch { return null; }
}
