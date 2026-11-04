// POST /api/teams/live/recall
//
// Recall.ai real-time transcript endpoint. Recall sends finalized
// Verify the signature, return 202, and record finished transcripts in the
// Company Map.
//
// Company Map (plan step 12): when Recall reports a finished transcript
// (`transcript.done` or `bot.done`), the final transcript is also recorded
// in the brain as a `transcript` source, after the response is sent.

import { after, NextResponse, type NextRequest } from 'next/server';
import { verifyRecallRequest } from '@/lib/recall';
import { finishedTranscriptRef, recordFinishedTranscript } from '@/lib/recall-cmap';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function POST(req: NextRequest): Promise<Response> {
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

  if (finishedTranscriptRef(body)) {
    after(async () => {
      try {
        await recordFinishedTranscript(body);
      } catch (err) {
        console.warn('[teams/live/recall] company map transcript capture failed', err);
      }
    });
  }

  return new NextResponse(null, { status: 202 });
}
