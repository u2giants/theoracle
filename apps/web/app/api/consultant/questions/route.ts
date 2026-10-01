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

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { question, sourceId, draftId, workspaceId, actorId } = body;
    if (!question || typeof question !== 'string' || !question.trim()) {
      return NextResponse.json({ error: 'question is required' }, { status: 400 });
    }
    const source = getSource(sourceId);
    if (!source) {
      return NextResponse.json({ error: 'source not found' }, { status: 404 });
    }
    const draft = draftId ? getDraft(draftId) : null;
    const connections = draft?.connections ?? [];
    const spans = retrieveSpans(question, source.blocks, 5, connections);
    const answer = answerQuestion(question, spans, connections);
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
