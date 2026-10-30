// POST /api/teams/bot/proactive  (plan step 12)
//
// Called only by the brain's interview tick with the shared token:
// { employee_id, text }. Looks up the conversation reference the employee
// created by messaging the bot first and sends the question into that chat.
// The brain refuses the lookup (409/404) while interviews are off or the
// employee never wrote to the bot, so nothing can be sent in those cases.

import { NextResponse, type NextRequest } from 'next/server';
import type { ConversationReference } from 'botbuilder';
import { brainService, isBrainToken } from '@/lib/brain-service';
import { getTeamsBotAdapter, teamsBotAppId } from '@/lib/teams-bot-adapter';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

type Body = { employee_id?: unknown; text?: unknown };

export async function POST(req: NextRequest): Promise<NextResponse> {
  if (!isBrainToken(req.headers.get('x-brain-token'))) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  const body = (await req.json().catch(() => null)) as Body | null;
  const employeeId = typeof body?.employee_id === 'string' ? body.employee_id : '';
  const text = typeof body?.text === 'string' ? body.text.trim() : '';
  if (!employeeId || !text) {
    return NextResponse.json({ error: 'employee_id and text are required' }, { status: 400 });
  }

  let ref: ConversationReference;
  try {
    const lookup = await brainService<{ conversation_ref?: ConversationReference; detail?: string }>(
      `interview/teams/conversation/${encodeURIComponent(employeeId)}`,
    );
    if (lookup.status !== 200 || !lookup.body?.conversation_ref) {
      return NextResponse.json(
        { error: 'not_reachable', detail: lookup.body?.detail ?? null },
        { status: lookup.status === 200 ? 404 : lookup.status },
      );
    }
    ref = lookup.body.conversation_ref;
  } catch {
    return NextResponse.json({ error: 'brain unreachable' }, { status: 502 });
  }

  try {
    await getTeamsBotAdapter().continueConversationAsync(teamsBotAppId(), ref, async (context) => {
      await context.sendActivity(text);
    });
  } catch (err) {
    console.error('[teams/bot/proactive] send failed', err);
    return NextResponse.json({ error: 'send_failed' }, { status: 502 });
  }
  return NextResponse.json({ sent: true });
}
