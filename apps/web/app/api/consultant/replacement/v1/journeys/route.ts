// POST /api/consultant/replacement/v1/journeys
// Create a replacement journey over an ordered complete source population.
// Strict unknown-field refusal. actor/workspace derived server-side.
import { NextResponse, type NextRequest } from 'next/server';
import { authorizeReplacementRequest } from '@/lib/replacement-auth';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const auth = await authorizeReplacementRequest(req.headers, 'write');
    if (!auth.ok) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
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
      workspaceId: auth.principal.workspaceId,
      actorId: auth.principal.actorId,
      sourceIds: sourceIds as string[],
    });
    return NextResponse.json(store.validatedSnapshot(record), { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'journey create failed';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

export async function GET(req: NextRequest) {
  const auth = await authorizeReplacementRequest(req.headers, 'read');
  if (!auth.ok) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }
  const store = replacementFixtureStore();
  return NextResponse.json({
    journeys: store.listJourneys(auth.principal.actorId).map((j) => store.validatedSnapshot(j)),
  });
}
