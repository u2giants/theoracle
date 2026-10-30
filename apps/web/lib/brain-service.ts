// Server-to-server calls to the brain service (plan step 12). The Teams bot
// routes act for no logged-in employee, so they send only the shared token.
// Never import this from client components.

export function brainServiceConfig(): { base: string; token: string } {
  const base = process.env.BRAIN_BASE_URL;
  const token = process.env.BRAIN_SHARED_TOKEN;
  if (!base || !token) {
    throw new Error('BRAIN_BASE_URL and BRAIN_SHARED_TOKEN must be set');
  }
  return { base: base.replace(/\/+$/, ''), token };
}

export async function brainService<T>(
  path: string,
  init: { method?: 'GET' | 'POST'; body?: unknown } = {},
): Promise<{ status: number; body: T | null }> {
  const { base, token } = brainServiceConfig();
  const headers: Record<string, string> = { 'x-brain-token': token };
  if (init.body !== undefined) headers['content-type'] = 'application/json';
  const res = await fetch(`${base}/${path.replace(/^\/+/, '')}`, {
    method: init.method ?? 'GET',
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    signal: AbortSignal.timeout(20_000),
    cache: 'no-store',
  });
  const body = (await res.json().catch(() => null)) as T | null;
  return { status: res.status, body };
}

// Constant-time comparison of the shared token on routes the brain calls.
export function isBrainToken(candidate: string | null): boolean {
  const expected = process.env.BRAIN_SHARED_TOKEN;
  if (!expected || !candidate || candidate.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i += 1) {
    diff |= expected.charCodeAt(i) ^ candidate.charCodeAt(i);
  }
  return diff === 0;
}
