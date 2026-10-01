// Pilot session auth for the isolated S03 preview.
// The pilot token is typed once into the UI password field; the server issues
// an httpOnly session bound to the configured pilot actor. Caller-supplied
// body identities are ignored. Scopes come from ORACLE2_PILOT_SCOPES so a
// missing-scope denial is testable.

import { randomUUID } from 'crypto';
import { grantAuthority } from '@/lib/oracle2-client';

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
  return process.env.ORACLE2_PILOT_ACTOR ?? 'pilot-user';
}

export function pilotScopes(): Array<'review' | 'confirm'> {
  const raw = process.env.ORACLE2_PILOT_SCOPES ?? 'review,confirm';
  const scopes: Array<'review' | 'confirm'> = [];
  for (const part of raw.split(',').map((s) => s.trim()).filter(Boolean)) {
    if (part === 'review' || part === 'confirm') scopes.push(part);
  }
  return scopes.length > 0 ? scopes : ['review'];
}

export function createSession(token: string):
  | { ok: true; sessionId: string; actorId: string }
  | { ok: false; error: string; status: number } {
  const expected = pilotToken();
  if (!expected) {
    return { ok: false, error: 'pilot token is not configured on this preview', status: 503 };
  }
  if (token !== expected) {
    return { ok: false, error: 'invalid pilot token', status: 401 };
  }
  const actorId = pilotActor();
  const sessionId = randomUUID();
  sessions.set(sessionId, { sessionId, actorId, createdAt: Date.now() });
  for (const scope of pilotScopes()) {
    grantAuthority(actorId, scope);
  }
  return { ok: true, sessionId, actorId };
}

export function destroySession(sessionId: string | undefined): void {
  if (sessionId) sessions.delete(sessionId);
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
