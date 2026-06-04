// POST /api/teams/live/start
//
// Admin-only helper to send a Recall.ai bot into a live Teams meeting with
// real-time transcription enabled. This does not replace the Microsoft Graph
// post-call transcript pipeline; it adds live participation.

import { NextResponse, type NextRequest } from 'next/server';
import { z } from 'zod';
import { requireAdmin } from '@/lib/auth-guard';
import { createRecallLiveBot, type RecallSttProvider } from '@/lib/recall';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const BodySchema = z.object({
  meetingUrl: z.url(),
  provider: z.enum(['elevenlabs_streaming', 'assembly_ai_v3_streaming']).optional(),
  botName: z.string().min(1).max(100).optional(),
});

export async function POST(req: NextRequest): Promise<NextResponse> {
  let admin;
  try {
    admin = await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse(await req.json());
  } catch (err) {
    return NextResponse.json({ error: 'bad_request', detail: String(err) }, { status: 400 });
  }

  const webhookUrl =
    process.env.RECALL_REALTIME_WEBHOOK_URL ??
    `${req.nextUrl.origin.replace(/\/+$/, '')}/api/teams/live/recall`;

  try {
    const bot = await createRecallLiveBot({
      meetingUrl: body.meetingUrl,
      webhookUrl,
      provider: body.provider as RecallSttProvider | undefined,
      botName: body.botName,
      metadata: {
        requested_by_employee_id: admin.id,
      },
    });
    return NextResponse.json({ ok: true, bot });
  } catch (err) {
    return NextResponse.json(
      { error: 'recall_create_failed', detail: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
