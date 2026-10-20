// Fail-closed auth gate for the replacement v1 fixture API.
// Workspace+role bounds mirror apps/web/lib/replacement-contract.ts.
// Identity is server-derived at session issue; body identities are ignored.
// Unauthenticated callers get 401; out-of-scope principals get 403.

import { randomUUID, createHash } from 'node:crypto';
import {
  authorizePilotRequest,
  pilotActor,
  pilotToken,
  sessionCookieAttributes,
} from './oracle2-pilot-auth';
import { hasAuthority } from './oracle2-authority';
import { pilotWorkspaceId } from './oracle2-store';

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

/** Read is list/detail; write is upload/confirm/cancel/advance and siblings. */
export type ReplacementAccess = 'read' | 'write';

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
 * Fail-closed workspace binding for pilot-fallback replacement access.
 *
 * Pilot permissions are never inherited across workspaces: authorization must
 * be proven in the same workspace id that owns the replacement resource. When
 * the pilot workspace and the replacement workspace differ, an explicit
 * replacement-workspace grant is required. Fails closed when workspace ids do
 * not match and no explicit replacement-workspace grant is proven.
 *
 * `hasConfirmInReplacement` / `hasReviewInReplacement` must already be checked
 * against `replacementWorkspaceId` (never the pilot workspace).
 */
export function bindPilotFallbackWorkspace(input: {
  pilotWorkspaceId: string;
  replacementWorkspaceId: string;
  hasConfirmInReplacement: boolean;
  hasReviewInReplacement: boolean;
  access: ReplacementAccess;
}): { ok: true } | { ok: false; error: string; status: number } {
  const {
    pilotWorkspaceId: pilotWs,
    replacementWorkspaceId: replacementWs,
    hasConfirmInReplacement,
    hasReviewInReplacement,
    access,
  } = input;
  const sameWorkspace = pilotWs === replacementWs;
  const hasGrant = hasConfirmInReplacement || hasReviewInReplacement;

  if (!hasGrant) {
    return {
      ok: false,
      error: sameWorkspace
        ? 'replacement scope missing or unknown'
        : 'cross-workspace replacement grant required',
      status: 403,
    };
  }
  if (access === 'write' && !hasConfirmInReplacement) {
    return { ok: false, error: 'write scope required', status: 403 };
  }
  return { ok: true };
}

/**
 * Fail-closed request authorization for replacement v1 routes.
 * Dedicated replacement session first; otherwise the existing pilot session
 * pattern. Pilot sessions must prove a store-backed scope in the REPLACEMENT
 * workspace (never the pilot workspace): write requires the privileged confirm
 * scope; read accepts review or confirm. Scope is checked at every request and
 * fails closed when missing or unknown. Cross-workspace pilot permissions are
 * never inherited — an explicit replacement-workspace grant is required when
 * workspace ids differ.
 */
export async function authorizeReplacementRequest(
  headers: Headers,
  access: ReplacementAccess = 'write',
): Promise<ReplacementAuthResult> {
  // CSRF: cookie-authenticated writes must prove same-origin. Enforced before
  // any session lookup so cross-origin requests are rejected uniformly.
  if (access === 'write' && !isSameOriginWrite(headers)) {
    return { ok: false, error: 'cross-origin write denied', status: 403 };
  }
  const dedicated = owned.authorize(headers);
  if (dedicated.ok) return dedicated;
  if (dedicated.status !== 401) return dedicated;

  const pilot = await authorizePilotRequest(headers);
  if (!pilot.ok) {
    return { ok: false, error: pilot.error, status: pilot.status };
  }
  const actorId = pilot.actorId;
  // Scope must be proven in the REPLACEMENT workspace — never inherited from
  // the pilot workspace. This binds authorization to the workspace that owns
  // the replacement resource.
  const hasConfirm = await hasAuthority(actorId, 'confirm', REPLACEMENT_WORKSPACE_ID);
  const hasReview = await hasAuthority(actorId, 'review', REPLACEMENT_WORKSPACE_ID);
  const bound = bindPilotFallbackWorkspace({
    pilotWorkspaceId: pilotWorkspaceId(),
    replacementWorkspaceId: REPLACEMENT_WORKSPACE_ID,
    hasConfirmInReplacement: hasConfirm,
    hasReviewInReplacement: hasReview,
    access,
  });
  if (!bound.ok) {
    return bound;
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

export function replacementCookieAttributes(): string {
  return sessionCookieAttributes();
}

export function replacementSessionCookie(sessionId: string): string {
  return `${REPLACEMENT_COOKIE}=${encodeURIComponent(sessionId)}; Path=/; ${replacementCookieAttributes()}`;
}

export function clearReplacementSessionCookie(): string {
  return `${REPLACEMENT_COOKIE}=; Path=/; ${replacementCookieAttributes()}; Max-Age=0`;
}

/**
 * Same-origin gate for state-changing (write) requests.
 *
 * Accepts a request only when the browser proves same-origin via `Origin`
 * (host must match the Host header) and/or `Sec-Fetch-Site: same-origin|none`.
 * `same-site` is NOT accepted: a sibling subdomain under the same registrable
 * domain is same-site but not same-origin, and is exactly the CSRF vector
 * SameSite=Lax does not stop. Missing both headers fails closed on writes.
 */
export function isSameOriginWrite(headers: Headers): boolean {
  const host = (headers.get('host') ?? '').toLowerCase();
  const origin = headers.get('origin');
  const secFetchSite = (headers.get('sec-fetch-site') ?? '').toLowerCase();

  const siteOk =
    secFetchSite === '' || secFetchSite === 'same-origin' || secFetchSite === 'none';
  if (!siteOk) return false;

  if (origin) {
    if (!host || origin === 'null') return false;
    try {
      return new URL(origin).host.toLowerCase() === host;
    } catch {
      return false;
    }
  }
  // No Origin header: only a same-origin/none Sec-Fetch-Site proves intent.
  return secFetchSite === 'same-origin' || secFetchSite === 'none';
}
