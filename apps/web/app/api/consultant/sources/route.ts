// POST /api/consultant/sources — upload a document for the pilot journey.
import { NextResponse, type NextRequest } from 'next/server';
import { randomUUID } from 'crypto';
import {
  parseTextToBlocks,
  storeDraft,
  storeSource,
  type Draft,
} from '@/lib/oracle2-client';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const auth = authorizePilotRequest(req.headers);
    if (!auth.ok) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
    const body = await req.json();
    const { text, filename, workspaceId, processName } = body;
    const actorId = auth.actorId;
    if (!text || typeof text !== 'string' || !text.trim()) {
      return NextResponse.json({ error: 'text is required' }, { status: 400 });
    }
    const sourceId = randomUUID();
    const blocks = parseTextToBlocks(text, sourceId);
    if (blocks.length === 0) {
      return NextResponse.json({ error: 'no content blocks found' }, { status: 400 });
    }
    storeSource(sourceId, workspaceId ?? 'default', filename ?? 'document.txt', blocks);
    const pilotActor = actorId;
    const draftId = randomUUID();
    const draft: Draft = {
      draftId,
      sourceId,
      workspaceId: workspaceId ?? 'default',
      createdBy: pilotActor,
      processName: processName ?? 'Process draft',
      connections: [],
      status: 'draft',
      updatedAt: new Date().toISOString(),
    };
    storeDraft(draft);
    return NextResponse.json({
      sourceId,
      draftId,
      blocks: blocks.map((b) => ({
        blockId: b.blockId,
        blockIndex: b.blockIndex,
        text: b.text,
        spanStart: b.spanStart,
        spanEnd: b.spanEnd,
      })),
    });
  } catch {
    return NextResponse.json({ error: 'upload failed' }, { status: 500 });
  }
}
