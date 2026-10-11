// POST /api/consultant/questions — ask a question and get a cited answer.
import { NextResponse, type NextRequest } from 'next/server';
import { tasks } from '@trigger.dev/sdk/v3';
import { authorizePilotRequest } from '@/lib/oracle2-pilot-auth';
import {
  getDraft,
  startHolisticRun,
  failHolisticRun,
  pilotWorkspaceId,
} from '@/lib/oracle2-store';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  try {
    const auth = await authorizePilotRequest(req.headers);
    if (!auth.ok) {
      return NextResponse.json({ error: auth.error }, { status: auth.status });
    }
    const body = await req.json();
    const { question, sourceId, draftId } = body;
    const actorId = auth.actorId;
    const workspaceId = pilotWorkspaceId();
    if (!question || typeof question !== 'string' || !question.trim() || question.length > 4000) {
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
    // No obsolete passage-matching fallback. Readiness is exact-corpus/config bound.
    const key = process.env.ORACLE2_HOLISTIC_TRIGGER_SECRET_KEY;
    const corpusDigest = process.env.ORACLE2_HOLISTIC_CORPUS_DIGEST;
    if (!key || !corpusDigest || !/^[a-f0-9]{64}$/.test(corpusDigest)) {
      return NextResponse.json(
        { error: 'The connected-document pilot is not ready for questions yet.' },
        { status: 409 },
      );
    }
    const runId = await startHolisticRun({
      workspaceId, actorId, sourceId, draftId, question,
    });
    try {
      // Dedicated preview project credential; no source text or question in task payload/logs.
      await tasks.trigger('oracle2-holistic-answer', { runId, workspaceId, corpusDigest },
        undefined, { clientConfig: { accessToken: key } });
    } catch {
      await failHolisticRun(runId, workspaceId, actorId);
      return NextResponse.json({ error: 'Connected answer service unavailable' }, { status: 503 });
    }
    return NextResponse.json({ runId, status: 'pending' }, { status: 202 });
  } catch (e) {
    console.error('questions-route-error', e instanceof Error ? e.name : 'UnknownError');
    return NextResponse.json({ error: 'question failed' }, { status: 500 });
  }
}
