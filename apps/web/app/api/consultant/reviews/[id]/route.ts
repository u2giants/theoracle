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
    if (typeof action === 'string' && action.startsWith('finding_')) {
      const note=body.note;
      if(typeof scope!=='string'||typeof note!=='string'||note.length>4000||JSON.stringify(body).length>8192)return NextResponse.json({error:'Bounded scoped review required'},{status:400});
      const {createFindingAction}=await import('@/lib/operating-action-store');
      const job=await createFindingAction(auth.actorId,id,{action:action.slice(8),scope,note});
      const key=process.env.ORACLE2_OPERATING_TRIGGER_SECRET_KEY;
      if(key){const {tasks}=await import('@trigger.dev/sdk/v3');await tasks.trigger('oracle2-operating-finding-review',job,undefined,{clientConfig:{accessToken:key}});}
      return NextResponse.json({state:'pending',runId:job.runId},{status:202});
    }
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
    if (message.includes('already confirmed') || message.includes('unique')) {
      return NextResponse.json({ error: 'draft already confirmed' }, { status: 409 });
    }
    if (message.includes('withdrawn')) {
      return NextResponse.json({ error: 'withdrawn draft cannot be confirmed' }, { status: 409 });
    }
    if (message.includes('only draft-status')) {
      return NextResponse.json({ error: 'only draft-status documents can be corrected' }, { status: 409 });
    }
    if (message.includes('not found')) {
      return NextResponse.json({ error: 'draft not found' }, { status: 404 });
    }
    return NextResponse.json({ error: 'review failed' }, { status: 500 });
  }
}



export async function GET(req:NextRequest,{params}:{params:Promise<{id:string}>}){
 const auth=await authorizePilotRequest(req.headers);if(!auth.ok)return NextResponse.json({error:auth.error},{status:auth.status});
 try{
  const {id}=await params;const runId=req.nextUrl.searchParams.get('runId');
  if(!runId||! /^[0-9a-f-]{36}$/i.test(runId))return NextResponse.json({error:'Opaque review identity required'},{status:400});
  const {readFindingAction}=await import('@/lib/operating-action-store');
  return NextResponse.json(await readFindingAction(auth.actorId,id,runId));
 }catch{return NextResponse.json({error:'Current review unavailable or denied'},{status:409});}
}
