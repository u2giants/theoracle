// Pilot session auth for the isolated S03 preview.
// Token is typed into the UI; the server issues an httpOnly session bound to
// the configured allowlisted actor. Scopes are proven in oracle2.appointments
// (S02), not granted in process memory. Body identities are ignored.

import { randomUUID } from 'crypto';
import { hasAuthority, type PilotScope } from '@/lib/oracle2-authority';

const SESSION_COOKIE = 'oracle2_pilot_session';

type Session = {
  sessionId: string;
  actorId: string;
  createdAt: number;
};

const sessions = new Map<string, Session>();

export function pilotToken(): string | undefined {
  return process.env.ORACLE2_PILOT_TOKEN;
}

export function pilotActor(): string {
  return pilotActors().values().next().value ?? 'pilot-user';
}

export function pilotActors(): Set<string> {
  const raw = process.env.ORACLE2_PILOT_ACTOR ?? process.env.ORACLE2_PILOT_ACTORS ?? 'pilot-user';
  return new Set(
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  );
}

export async function createSession(token: string):
  | Promise<{ ok: true; sessionId: string; actorId: string }>
  | Promise<{ ok: false; error: string; status: number }> {
  const expected = pilotToken();
  if (!expected) {
    return { ok: false, error: 'pilot token is not configured on this preview', status: 503 };
  }
  if (token !== expected) {
    return { ok: false, error: 'invalid pilot token', status: 401 };
  }
  const actorId = pilotActor();
  if (!pilotActors().has(actorId)) {
    return { ok: false, error: 'actor is not on the pilot allowlist', status: 403 };
  }
  // Store-backed gate: the actor must already hold review in oracle2.appointments.
  const ok = await hasAuthority(actorId, 'review');
  if (!ok) {
    return {
      ok: false,
      error: 'actor lacks store-backed review authority (oracle2.appointments)',
      status: 403,
    };
  }
  const sessionId = randomUUID();
  sessions.set(sessionId, { sessionId, actorId, createdAt: Date.now() });
  return { ok: true, sessionId, actorId };
}

export async function sessionHasScope(
  actorId: string,
  scope: PilotScope,
): Promise<boolean> {
  return hasAuthority(actorId, scope);
}

export function destroySession(sessionId: string | undefined): void {
  if (!sessionId) return;
  sessions.delete(sessionId);
}

function parseCookies(header: string | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!header) return out;
  for (const part of header.split(';')) {
    const idx = part.indexOf('=');
    if (idx <= 0) continue;
    out[part.slice(0, idx).trim()] = decodeURIComponent(part.slice(idx + 1).trim());
  }
  return out;
}

export function authorizePilotRequest(
  headers: Headers,
): { ok: true; actorId: string; sessionId: string } | { ok: false; error: string; status: number } {
  const cookies = parseCookies(headers.get('cookie'));
  const sessionId = cookies[SESSION_COOKIE];
  const session = sessionId ? sessions.get(sessionId) : undefined;
  if (!session) {
    return { ok: false, error: 'pilot session required', status: 401 };
  }
  return { ok: true, actorId: session.actorId, sessionId: session.sessionId };
}

export function sessionCookieName(): string {
  return SESSION_COOKIE;
}

export function sessionCookie(sessionId: string): string {
  return `${SESSION_COOKIE}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax`;
}

export function clearSessionCookie(): string {
  return `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}
