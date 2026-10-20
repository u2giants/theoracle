// POST /api/consultant/replacement/v1/journeys
// Create a replacement journey over an ordered complete source population.
// Strict unknown-field refusal. actor/workspace derived server-side.
import { NextResponse, type NextRequest } from 'next/server';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as Record<string, unknown>;
    const allowed = new Set(['sourceIds', 'idempotencyKey']);
    for (const key of Object.keys(body)) {
      if (!allowed.has(key)) {
        return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
      }
    }
    const sourceIds = body.sourceIds;
    if (!Array.isArray(sourceIds) || sourceIds.length < 1 || sourceIds.length > 100) {
      return NextResponse.json({ error: 'sourceIds required' }, { status: 400 });
    }
    for (const id of sourceIds) {
      if (typeof id !== 'string' || !id) {
        return NextResponse.json({ error: 'invalid source id' }, { status: 400 });
      }
    }
    const store = replacementFixtureStore();
    const record = store.createJourney({
      workspaceId: '00000000-0000-4000-8000-0000000000f1',
      actorId: '00000000-0000-4000-8000-0000000000a1',
      sourceIds: sourceIds as string[],
    });
    return NextResponse.json(store.validatedSnapshot(record), { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'journey create failed';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

export async function GET() {
  const store = replacementFixtureStore();
  return NextResponse.json({
    journeys: store.listJourneys().map((j) => store.validatedSnapshot(j)),
  });
}
