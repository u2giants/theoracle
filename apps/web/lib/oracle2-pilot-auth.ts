// Pilot API authentication for the isolated S03 preview.
// Loopback is not authorization: mutating consultant routes require a pilot
// token and an allowlisted actor. Preview-only; S04+ replaces this with real
// identity.

const TOKEN_HEADER = 'x-oracle2-pilot-token';
const ACTOR_HEADER = 'x-oracle2-actor-id';

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

export function authorizePilotRequest(
  headers: Headers,
): { ok: true; actorId: string } | { ok: false; error: string; status: number } {
  const expected = pilotToken();
  if (!expected) {
    return {
      ok: false,
      error: 'pilot token is not configured on this preview',
      status: 503,
    };
  }
  const provided = headers.get(TOKEN_HEADER);
  if (!provided || provided !== expected) {
    return { ok: false, error: 'invalid pilot token', status: 401 };
  }
  const actorId = headers.get(ACTOR_HEADER);
  if (!actorId || !pilotActors().has(actorId)) {
    return { ok: false, error: 'actor is not on the pilot allowlist', status: 403 };
  }
  return { ok: true, actorId };
}
