// POST /api/consultant/replacement/v1/journeys/[id]/confirmations
// Exact scoped confirmation of the current map/version/scope only (U5 DTO).
// DELETE withdraws the CURRENT badge; historical reviewed-then fact remains.
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
      'version',
      'contentHash',
      'workflowId',
      'expectedJourneyRevision',
      'idempotencyKey',
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
    const record = store.confirmScope({
      journeyId: id,
      expectedStateRevision: num(body.expectedJourneyRevision),
      workflowId: str(body.workflowId),
      version: num(body.version),
      contentHash: str(body.contentHash),
      idempotencyKey: str(body.idempotencyKey),
      callerActorId: auth.principal.actorId,
      callerWorkspaceId: auth.principal.workspaceId,
    });
    return NextResponse.json(store.validatedSnapshot(record));
  } catch (error) {
    const message = error instanceof Error ? error.message : 'confirm failed';
    const status = message.includes('stale') || message.includes('differs') ? 409 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}

export async function DELETE(
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
    const allowed = new Set(['expectedJourneyRevision']);
    for (const key of Object.keys(body)) {
      if (!allowed.has(key)) {
        return NextResponse.json({ error: `unknown field ${key}` }, { status: 400 });
      }
    }
    const expected = body.expectedJourneyRevision;
    if (typeof expected !== 'number' || !Number.isInteger(expected)) {
      return NextResponse.json({ error: 'expectedJourneyRevision required' }, { status: 400 });
    }
    const store = replacementFixtureStore();
    const record = store.withdrawConfirmation({
      journeyId: id,
      expectedStateRevision: expected,
      callerActorId: auth.principal.actorId,
      callerWorkspaceId: auth.principal.workspaceId,
    });
    return NextResponse.json(store.validatedSnapshot(record));
  } catch (error) {
    const message = error instanceof Error ? error.message : 'withdraw failed';
    const status = message.includes('stale') ? 409 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}
