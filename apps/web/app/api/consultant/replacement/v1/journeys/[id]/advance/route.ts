// POST /api/consultant/replacement/v1/journeys/[id]/advance
// Fixture pipeline step: CAS-advance the journey through the state machine.
// Also handles land_draft / land_revision / confirm / answer via named action.
// Unknown actions and stale expectedStateRevision fail closed.
import { NextResponse, type NextRequest } from 'next/server';
import { authorizeReplacementRequest } from '@/lib/replacement-auth';
import { replacementFixtureStore } from '@/lib/replacement-store';
import type { JourneyAction } from '@/lib/replacement-contract';

export const dynamic = 'force-dynamic';

const FIXTURE_ACTIONS = new Set<JourneyAction>([
  'advance_reading',
  'advance_admission',
  'advance_processing',
  'land_draft',
  'land_revision',
  'fail_spent',
  'error',
  'evidence_missing',
  'invalidate',
]);

export async function POST(
  req: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const auth = await authorizeReplacementRequest(req.headers, 'write');
  if (!auth.ok) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }
  const { id } = await context.params;
  try {
    const body = (await req.json()) as Record<string, unknown>;
    const allowed = new Set(['action', 'expectedStateRevision']);
    for (const key of Object.keys(body)) {
      if (!allowed.has(key)) {
        return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
      }
    }
    const action = body.action;
    const expectedStateRevision = body.expectedStateRevision;
    if (typeof action !== 'string' || !FIXTURE_ACTIONS.has(action as JourneyAction)) {
      return NextResponse.json({ error: 'unsupported action' }, { status: 400 });
    }
    if (typeof expectedStateRevision !== 'number' || !Number.isInteger(expectedStateRevision)) {
      return NextResponse.json({ error: 'expectedStateRevision required' }, { status: 400 });
    }
    const store = replacementFixtureStore();
    const record = store.getJourney(id, auth.principal.actorId);
    if (!record) {
      return NextResponse.json({ error: 'unknown journey' }, { status: 404 });
    }
    if (action === 'land_draft') {
      store.landDraft({ journeyId: id, expectedStateRevision, callerActorId: auth.principal.actorId });
    } else if (action === 'land_revision') {
      store.landRevision({ journeyId: id, expectedStateRevision, callerActorId: auth.principal.actorId });
    } else if (action === 'invalidate') {
      store.invalidateCurrent({ journeyId: id, expectedStateRevision, callerActorId: auth.principal.actorId });
    } else {
      store.applyAction({
        journeyId: id,
        expectedStateRevision,
        action: action as JourneyAction,
        callerActorId: auth.principal.actorId,
      });
    }
    const updated = store.getJourney(id, auth.principal.actorId);
    if (!updated) throw new Error('journey disappeared');
    return NextResponse.json(store.validatedSnapshot(updated));
  } catch (error) {
    const message = error instanceof Error ? error.message : 'advance failed';
    const status = message.includes('stale') ? 409 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}
