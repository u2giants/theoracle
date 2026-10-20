// Fail-closed auth gate for the replacement v1 fixture API.
// Workspace+role bounds mirror apps/web/lib/replacement-contract.ts.
// Identity is server-derived at session issue; body identities are ignored.
// Unauthenticated callers get 401; out-of-scope principals get 403.

import { randomUUID, createHash } from 'node:crypto';
import {
  authorizePilotRequest,
  pilotActor,
  pilotToken,
} from './oracle2-pilot-auth';

export const REPLACEMENT_COOKIE = 'oracle2_replacement_session';
export const REPLACEMENT_WORKSPACE_ID = '00000000-0000-4000-8000-0000000000f1';
export const REPLACEMENT_ROLE = 'replacement_requester';

const ALLOWED_ROLES: ReadonlySet<string> = new Set([REPLACEMENT_ROLE]);
const BOUND_WORKSPACE_ID = REPLACEMENT_WORKSPACE_ID;
const SESSION_TTL_MS = 8 * 60 * 60 * 1000;
const MAX_SESSIONS = 32;

export type ReplacementPrincipal = {
  actorId: string;
  workspaceId: string;
  role: string;
};

export type ReplacementAuthResult =
  | { ok: true; principal: ReplacementPrincipal; sessionId: string }
  | { ok: false; error: string; status: number };

type Session = {
  sessionId: string;
  principal: ReplacementPrincipal;
  createdAt: number;
};

function fingerprint(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

/** Workspace+role permission boundary (mirrors replacement-contract bounds). */
export function withinReplacementBounds(principal: ReplacementPrincipal): boolean {
  return ALLOWED_ROLES.has(principal.role) && principal.workspaceId === BOUND_WORKSPACE_ID;
}

export type ReplacementAuthDeps = {
  token: () => string | undefined;
  actorId: () => string;
  workspaceId: () => string;
  role: () => string;
  clock: () => number;
};

export function replacementAuth(deps: ReplacementAuthDeps) {
  const sessions = new Map<string, Session>();

  function prune(now: number): void {
    for (const [key, value] of sessions) {
      if (now - value.createdAt > SESSION_TTL_MS) sessions.delete(key);
    }
  }

  function principalFromConfig(): ReplacementPrincipal {
    return {
      actorId: deps.actorId(),
      workspaceId: deps.workspaceId(),
      role: deps.role(),
    };
  }

  function create(token: string): ReplacementAuthResult {
    const expected = deps.token();
    if (!expected) {
      return { ok: false, error: 'replacement token is not configured', status: 503 };
    }
    if (typeof token !== 'string' || !token || token.length > 4096) {
      return { ok: false, error: 'replacement token required', status: 401 };
    }
    if (fingerprint(token) !== fingerprint(expected)) {
      return { ok: false, error: 'invalid replacement token', status: 401 };
    }
    const principal = principalFromConfig();
    if (!withinReplacementBounds(principal)) {
      return { ok: false, error: 'replacement principal out of scope', status: 403 };
    }
    const now = deps.clock();
    prune(now);
    if (sessions.size >= MAX_SESSIONS) {
      return { ok: false, error: 'replacement session limit reached', status: 429 };
    }
    const sessionId = randomUUID();
    sessions.set(sessionId, { sessionId, principal, createdAt: now });
    return { ok: true, principal, sessionId };
  }

  function authorize(headers: Headers): ReplacementAuthResult {
    const cookieHeader = headers.get('cookie') ?? '';
    const matches = cookieHeader
      .split(';')
      .map((x) => x.trim())
      .filter((x) => x.startsWith(REPLACEMENT_COOKIE + '='));
    if (matches.length !== 1) {
      return { ok: false, error: 'replacement session required', status: 401 };
    }
    const sessionId = decodeURIComponent(matches[0]!.slice(REPLACEMENT_COOKIE.length + 1));
    const now = deps.clock();
    prune(now);
    const session = sessions.get(sessionId);
    if (!session || now - session.createdAt > SESSION_TTL_MS) {
      if (sessionId) sessions.delete(sessionId);
      return { ok: false, error: 'replacement session expired', status: 401 };
    }
    if (!withinReplacementBounds(session.principal)) {
      sessions.delete(sessionId);
      return { ok: false, error: 'replacement principal out of scope', status: 403 };
    }
    return { ok: true, principal: session.principal, sessionId };
  }

  function destroy(sessionId: string): void {
    sessions.delete(sessionId);
  }

  return { create, authorize, destroy };
}

function configToken(): string | undefined {
  return process.env.ORACLE2_REPLACEMENT_TOKEN ?? pilotToken();
}

function configActorId(): string {
  return process.env.ORACLE2_REPLACEMENT_ACTOR ?? pilotActor();
}

function configRole(): string {
  return process.env.ORACLE2_REPLACEMENT_ROLE ?? REPLACEMENT_ROLE;
}

const owned = replacementAuth({
  token: configToken,
  actorId: configActorId,
  workspaceId: () => REPLACEMENT_WORKSPACE_ID,
  role: configRole,
  clock: () => Date.now(),
});

export function createReplacementSession(token: string): ReplacementAuthResult {
  return owned.create(token);
}

/**
 * Fail-closed request authorization for replacement v1 routes.
 * Dedicated replacement session first; otherwise the existing pilot session
 * pattern. Workspace+role bounds are re-checked on every request.
 */
export async function authorizeReplacementRequest(
  headers: Headers,
): Promise<ReplacementAuthResult> {
  const dedicated = owned.authorize(headers);
  if (dedicated.ok) return dedicated;
  if (dedicated.status !== 401) return dedicated;

  const pilot = await authorizePilotRequest(headers);
  if (!pilot.ok) {
    return { ok: false, error: pilot.error, status: pilot.status };
  }
  const principal: ReplacementPrincipal = {
    actorId: pilot.actorId,
    workspaceId: REPLACEMENT_WORKSPACE_ID,
    role: configRole(),
  };
  if (!withinReplacementBounds(principal)) {
    return { ok: false, error: 'replacement principal out of scope', status: 403 };
  }
  return { ok: true, principal, sessionId: pilot.sessionId };
}

export function destroyReplacementSession(sessionId: string): void {
  owned.destroy(sessionId);
}

export function replacementSessionCookie(sessionId: string): string {
  return `${REPLACEMENT_COOKIE}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax`;
}

export function clearReplacementSessionCookie(): string {
  return `${REPLACEMENT_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}
