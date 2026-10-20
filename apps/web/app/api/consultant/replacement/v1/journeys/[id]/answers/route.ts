// POST /api/consultant/replacement/v1/journeys/[id]/answers
// Connected documentary answer for the confirmed exact scope only.
// Unsupported intents abstain; suggestions stay labeled, never established fact.
import { NextResponse, type NextRequest } from 'next/server';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

const ALLOWED_INTENTS = new Set([
  'overview',
  'process_steps',
  'roles',
  'artifacts',
  'interfaces',
  'findings',
]);

export async function POST(
  req: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  try {
    const body = (await req.json()) as Record<string, unknown>;
    const allowed = new Set(['intent', 'expectedJourneyRevision', 'idempotencyKey']);
    for (const key of Object.keys(body)) {
      if (!allowed.has(key)) {
        return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
      }
    }
    const intent = body.intent;
    if (typeof intent !== 'string' || !ALLOWED_INTENTS.has(intent)) {
      return NextResponse.json({ error: 'unsupported intent' }, { status: 400 });
    }
    const expected = body.expectedJourneyRevision;
    if (typeof expected !== 'number' || !Number.isInteger(expected)) {
      return NextResponse.json({ error: 'expectedJourneyRevision required' }, { status: 400 });
    }
    const store = replacementFixtureStore();
    const record = store.getJourney(id);
    if (!record) {
      return NextResponse.json({ error: 'unknown journey' }, { status: 404 });
    }
    if (!record.confirmation?.current) {
      return NextResponse.json(
        { error: 'confirmation required before answer' },
        { status: 409 },
      );
    }
    store.produceAnswer({ journeyId: id, expectedStateRevision: expected });
    const updated = store.getJourney(id);
    if (!updated) throw new Error('journey disappeared');
    return NextResponse.json(store.validatedSnapshot(updated));
  } catch (error) {
    const message = error instanceof Error ? error.message : 'answer failed';
    const status = message.includes('stale') ? 409 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}
