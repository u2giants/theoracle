// POST /api/consultant/reviews/[id] — draft correction or scoped confirmation.
import { NextResponse, type NextRequest } from 'next/server';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import {
  confirmDraft,
  correctDraft,
  getDraft,
  getSourceBlocks,
  pilotWorkspaceId,
} from '@/lib/oracle2-store';
import type { DraftConnection } from '@/lib/oracle2-client';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const auth = await authorizePilotRequest(req.headers);
    if (!auth.ok) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
    const { id } = await params;
    const body = await req.json();
    const { action, connections, processName, scope } = body;
    const workspaceId = pilotWorkspaceId();
    const actor = auth.actorId;
    const draft = await getDraft(id, workspaceId);
    if (!draft) {
      return NextResponse.json({ error: 'draft not found' }, { status: 404 });
    }
    if (action === 'correct') {
      // Authority is re-checked inside the mutation transaction (no TOCTOU).
      const nextConnections = connections ?? draft.connections;
      if (!Array.isArray(nextConnections)) {
        return NextResponse.json({ error: 'connections must be an array' }, { status: 400 });
      }
      const sourceBlocks = await getSourceBlocks(draft.sourceId, workspaceId);
      const blockCount = sourceBlocks.length;
      for (const connection of nextConnections as DraftConnection[]) {
        if (
          !connection ||
          typeof connection.from !== 'number' ||
          typeof connection.to !== 'number' ||
          !Number.isInteger(connection.from) ||
          !Number.isInteger(connection.to) ||
          connection.from < 0 ||
          connection.to < 0 ||
          connection.from >= blockCount ||
          connection.to >= blockCount
        ) {
          return NextResponse.json(
            { error: 'connection endpoints must address source blocks' },
            { status: 400 },
          );
        }
      }
      await correctDraft({
        draftId: id,
        workspaceId,
        actorId: actor,
        connections: nextConnections as DraftConnection[],
        processName,
      });
      return NextResponse.json({ draftId: id, status: 'draft' });
    }
    if (action === 'confirm') {
      const confirmScope = scope ?? 'process-map';
      if (confirmScope !== 'process-map') {
        return NextResponse.json({ error: 'unsupported confirmation scope' }, { status: 400 });
      }
      await confirmDraft({
        draftId: id,
        workspaceId,
        actorId: actor,
        scope: confirmScope,
      });
      return NextResponse.json({ draftId: id, status: 'confirmed' });
    }
    return NextResponse.json({ error: 'unknown action' }, { status: 400 });
  } catch (e) {
    const message = e instanceof Error ? e.message : 'review failed';
    if (message.includes('lacks')) {
      return NextResponse.json({ error: 'forbidden' }, { status: 403 });
    }
    if (message.includes('already confirmed')) {
      return NextResponse.json({ error: 'draft already confirmed' }, { status: 409 });
    }
    return NextResponse.json({ error: 'review failed' }, { status: 400 });
  }
}


