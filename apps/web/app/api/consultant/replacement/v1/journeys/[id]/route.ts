// GET /api/consultant/replacement/v1/journeys/[id]
// Current journey metadata + validated public pack. Rechecks current state on
// every poll/reload; metadata alone never yields ready.
import { NextResponse, type NextRequest } from 'next/server';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const store = replacementFixtureStore();
  const record = store.getJourney(id);
  if (!record) {
    return NextResponse.json({ error: 'unknown journey' }, { status: 404 });
  }
  const snapshot = store.validatedSnapshot(record);
  return NextResponse.json({
    ...snapshot,
    attempts: record.attempts,
    corrections: record.corrections,
    confirmations: record.confirmations,
    invalidatedAt: record.invalidatedAt,
    modelArtifactId: record.modelArtifactId,
  });
}
