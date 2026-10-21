// POST /api/consultant/replacement/v1/journeys/[id]/corrections
// Connection correction as append-only ORIGINAL review evidence -> genuinely
// NEW model revision. No body editing. Strict field set (U4 DTO).
import { NextResponse, type NextRequest } from 'next/server';
import { authorizeReplacementRequest } from '@/lib/replacement-auth';
import { replacementFixtureStore } from '@/lib/replacement-store';

export const dynamic = 'force-dynamic';

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
    const allowed = new Set([
      'baseVersion',
      'baseContentHash',
      'transitionId',
      'expectedFromId',
      'expectedToId',
      'newFromId',
      'newToId',
      'reason',
      'idempotencyKey',
      'expectedJourneyRevision',
    ]);
    for (const key of Object.keys(body)) {
      if (!allowed.has(key)) {
        return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
      }
    }
    const num = (v: unknown): number => {
      if (typeof v !== 'number' || !Number.isInteger(v)) throw new Error('invalid numeric field');
      return v;
    };
    const str = (v: unknown): string => {
      if (typeof v !== 'string' || !v) throw new Error('invalid string field');
      return v;
    };
    const store = replacementFixtureStore();
    const result = store.applyCorrection({
      journeyId: id,
      expectedStateRevision: num(body.expectedJourneyRevision),
      baseVersion: num(body.baseVersion),
      baseContentHash: str(body.baseContentHash),
      transitionId: str(body.transitionId),
      expectedFromId: str(body.expectedFromId),
      expectedToId: str(body.expectedToId),
      newFromId: str(body.newFromId),
      newToId: str(body.newToId),
      reason: str(body.reason),
      idempotencyKey: str(body.idempotencyKey),
      callerActorId: auth.principal.actorId,
      callerWorkspaceId: auth.principal.workspaceId,
    });
    return NextResponse.json(
      {
        ...store.validatedSnapshot(result.record),
        correction: result.correction,
      },
      { status: 201 },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : 'correction failed';
    const status = message.includes('stale') ? 409 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}
