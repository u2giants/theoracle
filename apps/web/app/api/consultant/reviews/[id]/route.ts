// POST /api/consultant/reviews/[id] — draft correction or scoped confirmation.
import { NextResponse, type NextRequest } from 'next/server';
import { randomUUID } from 'crypto';
import {
  getDraft,
  getSource,
  hasActiveConfirm,
  storeDraft,
  storeReview,
  type Draft,
  type DraftConnection,
  type Review,
} from '@/lib/oracle2-client';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import { hasAuthority } from '@/lib/oracle2-authority';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const auth = authorizePilotRequest(req.headers);
    if (!auth.ok) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
    const { id } = await params;
    const body = await req.json();
    const { action, connections, processName, scope, workspaceId } = body;
    const draft = getDraft(id);
    if (!draft) {
      return NextResponse.json({ error: 'draft not found' }, { status: 404 });
    }
    const actor = auth.actorId;
    if (action === 'correct') {
      if (!(await hasAuthority(actor, 'review'))) {
        return NextResponse.json({ error: 'actor lacks review authority for draft correction' }, { status: 403 });
      }
      if (draft.status !== 'draft') {
        return NextResponse.json({ error: 'only draft-status documents can be corrected' }, { status: 400 });
      }
      const nextConnections = connections ?? draft.connections;
      if (!Array.isArray(nextConnections)) {
        return NextResponse.json({ error: 'connections must be an array' }, { status: 400 });
      }
      const source = getSource(draft.sourceId);
      const blockCount = source?.blocks.length ?? 0;
      for (const connection of nextConnections as DraftConnection[]) {
        if (
          !connection ||
          typeof connection.from !== 'number' ||
          typeof connection.to !== 'number' ||
          connection.from < 0 ||
          connection.to < 0 ||
          connection.from >= blockCount ||
          connection.to >= blockCount
        ) {
          return NextResponse.json({ error: 'connection endpoints must address source blocks' }, { status: 400 });
        }
      }
      const updated: Draft = {
        ...draft,
        connections: nextConnections as DraftConnection[],
        processName: processName ?? draft.processName,
        updatedAt: new Date().toISOString(),
      };
      storeDraft(updated);
      const review: Review = {
        reviewId: randomUUID(),
        draftId: id,
        workspaceId: workspaceId ?? draft.workspaceId,
        actorId: actor,
        action: 'correct',
        payload: { connections: updated.connections },
        createdAt: new Date().toISOString(),
      };
      storeReview(review);
      return NextResponse.json({ draft: updated, reviewId: review.reviewId });
    }
    if (action === 'confirm') {
      if (!(await hasAuthority(actor, 'confirm'))) {
        return NextResponse.json({ error: 'actor lacks confirm authority for scoped confirmation' }, { status: 403 });
      }
      if (draft.status === 'confirmed') {
        return NextResponse.json({ error: 'draft already confirmed' }, { status: 409 });
      }
      if (hasActiveConfirm(id)) {
        return NextResponse.json({ error: 'a confirmation is already in progress' }, { status: 409 });
      }
      const updated: Draft = { ...draft, status: 'confirmed', updatedAt: new Date().toISOString() };
      storeDraft(updated);
      const review: Review = {
        reviewId: randomUUID(),
        draftId: id,
        workspaceId: workspaceId ?? draft.workspaceId,
        actorId: actor,
        action: 'confirm',
        payload: { scope: scope ?? 'process-map' },
        createdAt: new Date().toISOString(),
      };
      storeReview(review);
      return NextResponse.json({ draft: updated, reviewId: review.reviewId });
    }
    return NextResponse.json({ error: 'unknown action' }, { status: 400 });
  } catch {
    return NextResponse.json({ error: 'review failed' }, { status: 500 });
  }
}
