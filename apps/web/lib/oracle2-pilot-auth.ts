// Pilot session auth for the isolated S03 preview.
// Token is typed into the UI; the server issues an httpOnly session bound to
// the configured allowlisted actor. Scopes are proven in oracle2.appointments
// (S02), not granted in process memory. Body identities are ignored.

import { randomUUID } from 'crypto';
import { hasAuthority, type PilotScope } from '@/lib/oracle2-authority';

const SESSION_COOKIE = 'oracle2_pilot_session';
const SESSION_TTL_MS = 8 * 60 * 60 * 1000;

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
  return pilotActors().values().next().value ?? '00000000-0000-4000-8000-000000000003';
}

export function pilotActors(): Set<string> {
  const raw =
    process.env.ORACLE2_PILOT_ACTOR ??
    process.env.ORACLE2_PILOT_ACTORS ??
    '00000000-0000-4000-8000-000000000003';
  return new Set(
    raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  );
}

export async function createSession(token: string): Promise<
  { ok: true; sessionId: string; actorId: string } | { ok: false; error: string; status: number }
> {
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
  // Login does not require a particular scope; per-action checks run in-tx.
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

export async function authorizePilotRequest(
  headers: Headers,
): Promise<
  { ok: true; actorId: string; sessionId: string } | { ok: false; error: string; status: number }
> {
  const cookies = parseCookies(headers.get('cookie'));
  const sessionId = cookies[SESSION_COOKIE];
  const session = sessionId ? sessions.get(sessionId) : undefined;
  if (!session || !sessionId) {
    return { ok: false, error: 'pilot session required', status: 401 };
  }
  if (Date.now() - session.createdAt > SESSION_TTL_MS) {
    sessions.delete(sessionId);
    return { ok: false, error: 'pilot session expired', status: 401 };
  }
  // Drop the session if the actor no longer holds any live pilot scope.
  const stillMember = (await hasAuthority(session.actorId, 'review')) ||
    (await hasAuthority(session.actorId, 'confirm'));
  if (!stillMember) {
    sessions.delete(sessionId);
    return { ok: false, error: 'pilot session revoked', status: 403 };
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
