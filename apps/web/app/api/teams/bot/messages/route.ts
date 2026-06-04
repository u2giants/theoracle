// POST /api/teams/bot/messages
//
// Microsoft Teams Bot Framework endpoint. This is the Teams-native entry point
// so users can add The Oracle app inside Teams and type:
//
//   @The Oracle join <Teams meeting link>
//
// In meeting scope, TeamsInfo.getMeetingInfo() may provide the join URL, so a
// plain "join" can work there. If Teams does not provide it, we ask for the
// link. The actual live listener is still Recall.ai; this bot is the Teams UX
// wrapper that summons Recall into the meeting.

import { NextResponse, type NextRequest } from 'next/server';
import {
  ActivityTypes,
  CloudAdapter,
  ConfigurationBotFrameworkAuthentication,
  TeamsInfo,
  TurnContext,
  type Activity,
} from 'botbuilder';
import { createRecallLiveBot, type RecallSttProvider } from '@/lib/recall';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

let adapterSingleton: CloudAdapter | null = null;

function getAdapter(): CloudAdapter {
  const appId = process.env.MICROSOFT_BOT_APP_ID;
  const appPassword = process.env.MICROSOFT_BOT_APP_PASSWORD;
  const appTenantId = process.env.MICROSOFT_BOT_TENANT_ID;
  if (!appId || !appPassword) {
    throw new Error('MICROSOFT_BOT_APP_ID / MICROSOFT_BOT_APP_PASSWORD are not configured');
  }
  if (!adapterSingleton) {
    adapterSingleton = new CloudAdapter(
      new ConfigurationBotFrameworkAuthentication({
        MicrosoftAppId: appId,
        MicrosoftAppPassword: appPassword,
        MicrosoftAppType: appTenantId ? 'SingleTenant' : 'MultiTenant',
        MicrosoftAppTenantId: appTenantId,
      }),
    );
  }
  return adapterSingleton;
}

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

async function handleTurn(context: TurnContext, req: NextRequest): Promise<void> {
  if (context.activity.type !== ActivityTypes.Message) {
    if (context.activity.type === ActivityTypes.ConversationUpdate) {
      await context.sendActivity('The Oracle is ready. In a meeting chat, type "join" or "join <Teams meeting link>".');
    }
    return;
  }

  const commandText = removeBotMention(context);
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
      botName: 'The Oracle',
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
    const adapter = getAdapter();
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
