// Pilot session auth for the isolated S03 preview.
// Credentials are not browser-bundled: the operator types the pilot token once;
// the server issues an httpOnly session bound to an allowlisted actor. Body
// identities are never trusted.

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

export function pilotActors(): Set<string> {
  const raw = process.env.ORACLE2_PILOT_ACTORS ?? 'pilot-user';
  return new Set(
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  );
}

export function createSession(token: string, actorId: string):
  | { ok: true; sessionId: string; actorId: string }
  | { ok: false; error: string; status: number } {
  const expected = pilotToken();
  if (!expected) {
    return { ok: false, error: 'pilot token is not configured on this preview', status: 503 };
  }
  if (token !== expected) {
    return { ok: false, error: 'invalid pilot token', status: 401 };
  }
  if (!pilotActors().has(actorId)) {
    return { ok: false, error: 'actor is not on the pilot allowlist', status: 403 };
  }
  const sessionId = randomUUID();
  sessions.set(sessionId, { sessionId, actorId, createdAt: Date.now() });
  // Scopes are granted only after token + allowlist succeed (not on upload).
  grantAuthority(actorId, 'review');
  grantAuthority(actorId, 'confirm');
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
  // httpOnly; Path limited to consultant APIs and UI; no Secure on loopback http.
  return `${SESSION_COOKIE}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax`;
}

export function clearSessionCookie(): string {
  return `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}
