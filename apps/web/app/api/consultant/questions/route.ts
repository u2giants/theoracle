// POST /api/consultant/questions — ask a question and get a cited answer.
import { NextResponse, type NextRequest } from 'next/server';
import {
  answerQuestion,
  retrieveSpans,
  type SourceBlock,
} from '@/lib/oracle2-client';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import {
  getDraft,
  getSourceBlocks,
  pilotWorkspaceId,
  storeRun,
} from '@/lib/oracle2-store';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const auth = authorizePilotRequest(req.headers);
    if (!auth.ok) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
    const body = await req.json();
    const { question, sourceId, draftId } = body;
    const actorId = auth.actorId;
    const workspaceId = pilotWorkspaceId();
    if (!question || typeof question !== 'string' || !question.trim()) {
      return NextResponse.json({ error: 'question is required' }, { status: 400 });
    }
    if (!sourceId || !draftId) {
      return NextResponse.json({ error: 'sourceId and draftId are required' }, { status: 400 });
    }
    const draft = await getDraft(draftId, workspaceId);
    if (!draft) {
      return NextResponse.json({ error: 'draft not found' }, { status: 404 });
    }
    if (draft.sourceId !== sourceId) {
      return NextResponse.json({ error: 'draft does not belong to source' }, { status: 400 });
    }
    if (draft.status !== 'confirmed') {
      return NextResponse.json(
        { error: 'draft must be confirmed before questions' },
        { status: 409 },
      );
    }
    const blocks = await getSourceBlocks(sourceId, workspaceId);
    const connections = draft.connections ?? [];
    const connectedBlocks = blocks.filter((b) =>
      connections.some((c) => c.from === b.blockIndex || c.to === b.blockIndex),
    );
    const spans = retrieveSpans(question, blocks as SourceBlock[], 5, connections);
    const answer = answerQuestion(question, spans, connections, connectedBlocks);
    const runId = await storeRun({
      workspaceId,
      actorId,
      sourceId,
      draftId,
      question,
      answer,
    });
    return NextResponse.json({ runId, answer });
  } catch {
    return NextResponse.json({ error: 'question failed' }, { status: 500 });
  }
}
