// Local invented-data browser login; unavailable outside explicit fixture mode.
import { NextResponse, type NextRequest } from 'next/server';
import { createReplacementSession, destroyReplacementSession } from '@/lib/replacement-auth';
import { fixtureRequestAllowed, fixtureSameOrigin, fixtureSessionCookie } from '@/lib/replacement-fixture-auth';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  if (!fixtureRequestAllowed(req.headers, req.url)) {
    return NextResponse.json({ error: 'fixture login unavailable' }, { status: 404 });
  }
  if (!fixtureSameOrigin(req.headers)) {
    return NextResponse.json({ error: 'cross-origin write denied' }, { status: 403 });
  }
  try {
    const body = await req.json();
    if (!body || typeof body !== 'object' || Array.isArray(body) ||
        Object.keys(body).some(key => key !== 'token') || typeof body.token !== 'string') {
      return NextResponse.json({ error: 'token required' }, { status: 401 });
    }
    const session = createReplacementSession(body.token);
    if (!session.ok) return NextResponse.json({ error: session.error }, { status: session.status });
    const cookie = fixtureSessionCookie(session.sessionId);
    destroyReplacementSession(session.sessionId);
    return NextResponse.json({ actorId: session.principal.actorId }, {
      headers: { 'set-cookie': cookie },
    });
  } catch {
    return NextResponse.json({ error: 'fixture login failed' }, { status: 400 });
  }
}
