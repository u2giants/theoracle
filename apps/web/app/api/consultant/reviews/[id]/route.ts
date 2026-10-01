// POST /api/consultant/reviews/[id] — draft correction or scoped confirmation.
import { NextResponse, type NextRequest } from 'next/server';
import { randomUUID } from 'crypto';
import {
  getDraft,
  hasActiveConfirm,
  hasAuthority,
  storeDraft,
  storeReview,
  type Draft,
  type Review,
} from '@/lib/oracle2-client';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';

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
      if (!hasAuthority(actor, 'review')) {
        return NextResponse.json({ error: 'actor lacks review authority for draft correction' }, { status: 403 });
      }
      if (draft.status !== 'draft') {
        return NextResponse.json({ error: 'only draft-status documents can be corrected' }, { status: 400 });
      }
      const updated: Draft = {
        ...draft,
        connections: connections ?? draft.connections,
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
      if (!hasAuthority(actor, 'confirm')) {
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
