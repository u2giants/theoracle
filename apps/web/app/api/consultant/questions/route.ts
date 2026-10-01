// POST /api/consultant/questions — ask a question and get a cited answer.
import { NextResponse, type NextRequest } from 'next/server';
import { randomUUID } from 'crypto';
import {
  answerQuestion,
  getDraft,
  getSource,
  retrieveSpans,
  storeRun,
  type Run,
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
    const { question, sourceId, draftId, workspaceId } = body;
    const actorId = auth.actorId;
    if (!question || typeof question !== 'string' || !question.trim()) {
      return NextResponse.json({ error: 'question is required' }, { status: 400 });
    }
    const source = getSource(sourceId);
    if (!source) {
      return NextResponse.json({ error: 'source not found' }, { status: 404 });
    }
    if (!draftId) {
      return NextResponse.json({ error: 'draftId is required' }, { status: 400 });
    }
    const draft = getDraft(draftId);
    if (!draft) {
      return NextResponse.json({ error: 'draft not found' }, { status: 404 });
    }
    if (draft.sourceId !== sourceId) {
      return NextResponse.json({ error: 'draft does not belong to source' }, { status: 400 });
    }
    if (draft.status !== 'confirmed') {
      return NextResponse.json({ error: 'draft must be confirmed before questions' }, { status: 409 });
    }
    const connections = draft.connections ?? [];
    const connectedBlocks = source.blocks.filter((b) =>
      connections.some((c) => c.from === b.blockIndex || c.to === b.blockIndex),
    );
    const spans = retrieveSpans(question, source.blocks, 5, connections);
    const answer = answerQuestion(question, spans, connections, connectedBlocks);
    const runId = randomUUID();
    const run: Run = {
      runId,
      workspaceId: workspaceId ?? 'default',
      actorId: actorId ?? 'pilot-user',
      sourceId,
      draftId: draftId ?? null,
      question,
      status: 'completed',
      answer,
      error: null,
      createdAt: new Date().toISOString(),
    };
    storeRun(run);
    return NextResponse.json({ runId, answer });
  } catch {
    return NextResponse.json({ error: 'question failed' }, { status: 500 });
  }
}
