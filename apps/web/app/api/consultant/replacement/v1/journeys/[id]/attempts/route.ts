// GET/POST /api/consultant/replacement/v1/journeys/[id]/attempts
// native1..N attempt visibility. POST dispatches a NEW attempt (never replays).
// GET lists attempts with spent/new status. Replay of a spent attempt is
// rejected with 'attempt already spent; no replay'.
import { NextResponse, type NextRequest } from 'next/server';
import { authorizeReplacementRequest } from '@/lib/replacement-auth';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const auth = await authorizeReplacementRequest(req.headers);
  if (!auth.ok) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }
  const { id } = await context.params;
  const store = replacementFixtureStore();
  const record = store.getJourney(id);
  if (!record) {
    return NextResponse.json({ error: 'unknown journey' }, { status: 404 });
  }
  return NextResponse.json({ attempts: record.attempts });
}

export async function POST(
  req: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const auth = await authorizeReplacementRequest(req.headers);
  if (!auth.ok) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }
  const { id } = await context.params;
  try {
    const body = (await req.json()) as Record<string, unknown>;
    const allowed = new Set(['op', 'attemptId']);
    for (const key of Object.keys(body)) {
      if (!allowed.has(key)) {
        return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
      }
    }
    const store = replacementFixtureStore();
    const op = body.op;
    if (op === 'dispatch') {
      store.dispatchAttempt({ journeyId: id });
    } else if (op === 'spend') {
      const attemptId = body.attemptId;
      if (typeof attemptId !== 'string' || !attemptId) {
        return NextResponse.json({ error: 'attemptId required' }, { status: 400 });
      }
      store.spendAttempt({ journeyId: id, attemptId });
    } else if (op === 'replay') {
      const attemptId = body.attemptId;
      if (typeof attemptId !== 'string' || !attemptId) {
        return NextResponse.json({ error: 'attemptId required' }, { status: 400 });
      }
      store.replayAttempt({ journeyId: id, attemptId });
    } else {
      return NextResponse.json({ error: 'unknown op' }, { status: 400 });
    }
    const record = store.getJourney(id);
    if (!record) throw new Error('journey disappeared');
    return NextResponse.json({ attempts: record.attempts });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'attempt op failed';
    return NextResponse.json({ error: message }, { status: 409 });
  }
}
