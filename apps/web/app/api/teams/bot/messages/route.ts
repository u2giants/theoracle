// POST /api/teams/bot/messages
//
// Microsoft Teams Bot Framework endpoint. This is the Teams-native entry point
// so users can add The Oracle app inside Teams and type:
//
//   @theoracle join <Teams meeting link>
//
// In meeting scope, TeamsInfo.getMeetingInfo() may provide the join URL, so a
// plain "join" can work there. If Teams does not provide it, we ask for the
// link. The actual live listener is still Recall.ai; this bot is the Teams UX
// wrapper that summons Recall into the meeting.
//
// Company Map interviews (plan step 12): every message is first offered to
// the brain, which stores the sender's conversation reference (the only way
// the bot may later write to them), handles "stop"/"skip", and records a
// reply to an asked question as a source. Messages the brain does not claim
// fall through to the join-meeting behaviour below.

import { NextResponse, type NextRequest } from 'next/server';
import { ActivityTypes, TeamsInfo, TurnContext, type Activity } from 'botbuilder';
import { createRecallLiveBot, type RecallSttProvider } from '@/lib/recall';
import { brainService } from '@/lib/brain-service';
import { getTeamsBotAdapter } from '@/lib/teams-bot-adapter';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function removeBotMention(context: TurnContext): string {
  const activity = context.activity;
  const botId = activity.recipient?.id;
  let text = activity.text ?? '';
  for (const entity of activity.entities ?? []) {
    if (entity.type !== 'mention') continue;
    const mentioned = entity.mentioned as { id?: string } | undefined;
    if (mentioned?.id && mentioned.id === botId) {
      text = text.replace(entity.text ?? '', '');
    }
  }
  return text.replace(/\s+/g, ' ').trim();
}

function extractTeamsUrl(text: string): string | null {
  const m = text.match(/https:\/\/teams\.microsoft\.com\/[^\s<>"']+/i);
  return m?.[0] ?? null;
}

function extractProvider(text: string): RecallSttProvider {
  if (/\bassembly\b|\bassemblyai\b/i.test(text)) return 'assembly_ai_v3_streaming';
  return 'elevenlabs_streaming';
}

function isJoinCommand(text: string): boolean {
  return /^(join|listen|start|bring oracle in)\b/i.test(text) || extractTeamsUrl(text) !== null;
}

async function meetingJoinUrlFromContext(context: TurnContext): Promise<string | null> {
  const channelData = context.activity.channelData as { meeting?: { id?: string } } | undefined;
  const meetingId = channelData?.meeting?.id;
  if (!meetingId) return null;
  try {
    const info = await TeamsInfo.getMeetingInfo(context, meetingId);
    return info.details?.joinUrl ?? null;
  } catch (err) {
    console.warn('[teams/bot] could not load meeting info', err);
    return null;
  }
}

type InboundResult = { handled?: boolean; reply?: string | null };

async function senderEmail(context: TurnContext): Promise<string | null> {
  const from = context.activity.from;
  if (!from?.id) return null;
  try {
    const member = await TeamsInfo.getMember(context, from.id);
    return member.email ?? member.userPrincipalName ?? null;
  } catch (err) {
    console.warn('[teams/bot] could not load sender profile', err);
    return null;
  }
}

// Returns true when the brain handled the message as an interview reply.
async function offerToInterviews(context: TurnContext, text: string): Promise<boolean> {
  if (!process.env.BRAIN_BASE_URL || !process.env.BRAIN_SHARED_TOKEN) return false;
  const email = await senderEmail(context);
  if (!email) return false;
  try {
    const result = await brainService<InboundResult>('interview/teams/inbound', {
      method: 'POST',
      body: {
        email,
        conversation_ref: TurnContext.getConversationReference(context.activity),
        text,
      },
    });
    if (result.status !== 200 || !result.body?.handled) return false;
    if (result.body.reply) await context.sendActivity(result.body.reply);
    return true;
  } catch (err) {
    console.warn('[teams/bot] interview hand-off failed', err);
    return false;
  }
}

async function handleTurn(context: TurnContext, req: NextRequest): Promise<void> {
  if (context.activity.type !== ActivityTypes.Message) {
    if (context.activity.type === ActivityTypes.ConversationUpdate) {
      await context.sendActivity('theoracle is ready. In a meeting chat, type "join" or "join <Teams meeting link>".');
    }
    return;
  }

  const commandText = removeBotMention(context);
  if (await offerToInterviews(context, commandText)) return;
  if (!isJoinCommand(commandText)) {
    await context.sendActivity('To bring Oracle into this meeting, type "join" or "join <Teams meeting link>".');
    return;
  }

  const meetingUrl = extractTeamsUrl(commandText) ?? (await meetingJoinUrlFromContext(context));
  if (!meetingUrl) {
    await context.sendActivity('I can join, but I need the Teams meeting link. Type "join" followed by the meeting link.');
    return;
  }

  const provider = extractProvider(commandText);
  const webhookUrl =
    process.env.RECALL_REALTIME_WEBHOOK_URL ??
    `${req.nextUrl.origin.replace(/\/+$/, '')}/api/teams/live/recall`;

  try {
    await createRecallLiveBot({
      meetingUrl,
      webhookUrl,
      provider,
      botName: 'theoracle',
      metadata: {
        source: 'teams_bot_command',
        teams_conversation_id: context.activity.conversation?.id ?? '',
        teams_service_url: context.activity.serviceUrl ?? '',
      },
    });
    await context.sendActivity(
      'Oracle is joining now. If Teams shows a lobby prompt, admit it like any other meeting attendee.',
    );
  } catch (err) {
    await context.sendActivity(
      `I could not bring Oracle in yet: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: Activity;
  try {
    body = (await req.json()) as Activity;
  } catch {
    return NextResponse.json({ error: 'bad_json' }, { status: 400 });
  }

  try {
    const adapter = getTeamsBotAdapter();
    await adapter.processActivityDirect(req.headers.get('authorization') ?? '', body, async (context) => {
      await handleTurn(context, req);
    });
    return new NextResponse(null, { status: 200 });
  } catch (err) {
    console.error('[teams/bot] turn failed', err);
    return NextResponse.json(
      { error: 'bot_turn_failed', detail: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
