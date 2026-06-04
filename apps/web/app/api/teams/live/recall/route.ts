// POST /api/teams/live/recall
//
// Recall.ai real-time transcript endpoint. Recall sends finalized
// `transcript.data` utterances here while the meeting is still in progress.
// Keep this handler fast: verify the signature, enqueue a worker task, return
// 202. The worker owns DB writes, LLM calls, and Teams chat replies.

import { NextResponse, type NextRequest } from 'next/server';
import { triggerTask } from '@/lib/trigger';
import { verifyRecallRequest } from '@/lib/recall';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function POST(req: NextRequest): Promise<NextResponse> {
  const raw = await req.text();
  const secret = process.env.RECALL_WEBHOOK_SECRET;
  if (!secret) {
    console.warn('[teams/live/recall] RECALL_WEBHOOK_SECRET missing');
    return NextResponse.json({ error: 'not_configured' }, { status: 503 });
  }

  try {
    verifyRecallRequest({ secret, headers: req.headers, payload: raw });
  } catch (err) {
    console.warn('[teams/live/recall] signature verification failed', err);
    return NextResponse.json({ error: 'invalid_signature' }, { status: 400 });
  }

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }

  void triggerTask('teams-live-recall-utterance', {
    receivedAt: new Date().toISOString(),
    event: body,
  });

  return new NextResponse(null, { status: 202 });
}
