// POST /api/consultant/sources — upload a document for the pilot journey.
import { NextResponse, type NextRequest } from 'next/server';
import { parseTextToBlocks } from '@/lib/oracle2-client';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import { insertSource, pilotWorkspaceId } from '@/lib/oracle2-store';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const auth = authorizePilotRequest(req.headers);
    if (!auth.ok) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
    const body = await req.json();
    const { text, filename, processName } = body;
    const actorId = auth.actorId;
    // Workspace is bound to the authorized pilot workspace, never caller-supplied.
    const workspaceId = pilotWorkspaceId();
    if (!text || typeof text !== 'string' || !text.trim()) {
      return NextResponse.json({ error: 'text is required' }, { status: 400 });
    }
    const sourceIdForBlocks = 'pending';
    const blocks = parseTextToBlocks(text, sourceIdForBlocks);
    if (blocks.length === 0) {
      return NextResponse.json({ error: 'no content blocks found' }, { status: 400 });
    }
    const { sourceId, draftId } = await insertSource({
      workspaceId,
      actorId,
      filename: filename ?? 'document.txt',
      contentType: 'text/plain',
      blocks,
    });
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
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : 'upload failed' },
      { status: 500 },
    );
  }
}
