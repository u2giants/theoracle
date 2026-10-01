// POST /api/consultant/session — exchange pilot token for an httpOnly session.
// DELETE /api/consultant/session — end the session.
import { NextResponse, type NextRequest } from 'next/server';
import {
  clearSessionCookie,
  createSession,
  destroySession,
  authorizePilotRequest,
  sessionCookie,
} from '@/lib/oracle2-pilot-auth';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { token, actorId } = body;
    if (!token || typeof token !== 'string') {
      return NextResponse.json({ error: 'token is required' }, { status: 400 });
    }
    const actor = typeof actorId === 'string' && actorId.trim() ? actorId.trim() : 'pilot-user';
    const result = createSession(token, actor);
    if (!result.ok) {
      return NextResponse.json({ error: result.error }, { status: result.status });
    }
    return NextResponse.json(
      { actorId: result.actorId },
      {
        status: 200,
        headers: { 'set-cookie': sessionCookie(result.sessionId) },
      },
    );
  } catch {
    return NextResponse.json({ error: 'session failed' }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  const auth = authorizePilotRequest(req.headers);
  if (auth.ok) {
    destroySession(auth.sessionId);
  }
  return NextResponse.json(
    { ok: true },
    { headers: { 'set-cookie': clearSessionCookie() } },
  );
}
