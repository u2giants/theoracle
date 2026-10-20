// POST /api/consultant/replacement/v1/journeys/[id]/cancel
// Opaque control/cancel. Preserves spent liability, never replays, never
// claims 'not sent' for an in-flight paid attempt.
import { NextResponse, type NextRequest } from 'next/server';
import { authorizeReplacementRequest } from '@/lib/replacement-auth';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

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
    const allowed = new Set(['expectedStateRevision', 'idempotencyKey']);
    for (const key of Object.keys(body)) {
      if (!allowed.has(key)) {
        return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
      }
    }
    const expectedStateRevision = body.expectedStateRevision;
    if (typeof expectedStateRevision !== 'number' || !Number.isInteger(expectedStateRevision)) {
      return NextResponse.json({ error: 'expectedStateRevision required' }, { status: 400 });
    }
    const store = replacementFixtureStore();
    const record = store.getJourney(id);
    if (!record) {
      return NextResponse.json({ error: 'unknown journey' }, { status: 404 });
    }
    if (record.state === 'cancel_requested') {
      store.completeCancel({ journeyId: id, expectedStateRevision });
    } else {
      store.requestCancel({ journeyId: id, expectedStateRevision });
    }
    const updated = store.getJourney(id);
    if (!updated) throw new Error('journey disappeared');
    return NextResponse.json({
      ...store.validatedSnapshot(updated),
      attempts: updated.attempts,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'cancel failed';
    const status = message.includes('stale') ? 409 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}
