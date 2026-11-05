// POST /api/teams/bot/proactive  (plan step 12)
//
// Called only by the brain's interview tick with the shared token:
// { employee_id, text }. Sends into the employee's Teams chat using the
// stored conversation reference. When none is stored (Teams never delivered
// a conversation update and the employee never opened the chat — 11
// install-wave employees were stuck this way), the bot opens the 1:1 chat
// itself, stores the reference with the brain, and sends. 404 not_reachable
// when no Teams chat can be opened at all; the outbound interview tick stays
// gated on the interviews switch.

import { NextResponse, type NextRequest } from 'next/server';
import {
  TurnContext,
  type ConversationParameters,
  type ConversationReference,
} from 'botbuilder';
import { brainService, isBrainToken } from '@/lib/brain-service';
import { getTeamsBotAdapter, teamsBotAppId } from '@/lib/teams-bot-adapter';
import { listTenantUsers } from '@/lib/microsoft-graph';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

type Body = { employee_id?: unknown; text?: unknown };

type EmployeeLookup = {
  conversation_ref?: Partial<ConversationReference> | null;
  name?: string | null;
  emails?: string[];
  service_url?: string | null;
  detail?: string;
};

const TEAMS_CHANNEL_ID = 'msteams';
const BOT_CONNECTOR_AUDIENCE = 'https://api.botframework.com';
// Retain opened references across persistence retries in this process.
const pendingReferences = new Map<string, Partial<ConversationReference>>();

function botTenantId(): string {
  const tenant = process.env.MICROSOFT_BOT_TENANT_ID ?? process.env.AZURE_TENANT_ID;
  if (!tenant) throw new Error('MICROSOFT_BOT_TENANT_ID / AZURE_TENANT_ID is not configured');
  return tenant;
}

// Only explicit recipient failures may advance the interview to another person.
function isClientError(err: unknown): boolean {
  const record = err as { code?: unknown; body?: { error?: { code?: unknown } } } | null;
  const code = record?.body?.error?.code ?? record?.code;
  return typeof code === 'string' && new Set([
    'BotNotInConversation', 'MissingConversationParameter',
    'ConversationNotFound', 'UserNotFound', 'MessageWritesBlocked',
  ]).has(code);
}

async function resolveTeamsUser(emails: string[]): Promise<{ id: string; name?: string } | null> {
  const wanted = new Set(emails.map((e) => e.trim().toLowerCase()).filter(Boolean));
  if (wanted.size === 0) return null;
  for (const user of await listTenantUsers()) {
    if (wanted.has(user.email.toLowerCase())) {
      return user.accountEnabled ? { id: user.id, name: user.displayName } : null;
    }
  }
  return null;
}

// Open the 1:1 chat the employee never opened themselves and hand the
// reference to the brain so later sends reuse the same chat.
const openingConversations = new Map<string, Promise<Partial<ConversationReference>>>();

async function openConversation(employeeId: string, lookup: EmployeeLookup): Promise<Partial<ConversationReference>> {
  const existing = openingConversations.get(employeeId);
  if (existing) return existing;
  const opening = createAndStoreConversation(employeeId, lookup);
  openingConversations.set(employeeId, opening);
  try {
    return await opening;
  } finally {
    openingConversations.delete(employeeId);
  }
}

async function createAndStoreConversation(
  employeeId: string,
  lookup: EmployeeLookup,
): Promise<Partial<ConversationReference>> {
  const pending = pendingReferences.get(employeeId);
  if (pending) {
    await persistConversation(employeeId, pending);
    return pending;
  }
  const user = await resolveTeamsUser(lookup.emails ?? []);
  if (!user) {
    throw Object.assign(new Error('no tenant user matches this employee'), { unreachable: true });
  }
  const appId = teamsBotAppId();
  const tenantId = botTenantId();
  const serviceUrl =
    process.env.TEAMS_SERVICE_URL;
  if (!serviceUrl) throw new Error('TEAMS_SERVICE_URL is not configured');
  const displayName = user.name ?? lookup.name ?? 'employee';
  const holder: { ref: Partial<ConversationReference> | null } = { ref: null };
  const parameters: ConversationParameters = {
    isGroup: false,
    bot: { id: appId, name: 'theoracle' },
    members: [{ id: user.id, name: displayName }],
    tenantId,
    channelData: { tenant: { id: tenantId } },
  };
  await getTeamsBotAdapter().createConversationAsync(
    appId,
    TEAMS_CHANNEL_ID,
    serviceUrl,
    BOT_CONNECTOR_AUDIENCE,
    parameters,
    async (context) => {
      const ref = TurnContext.getConversationReference(context.activity);
      ref.user = { id: user.id, name: displayName };
      holder.ref = ref;
    },
  );
  if (!holder.ref) throw new Error('createConversation produced no reference');
  pendingReferences.set(employeeId, holder.ref);
  await persistConversation(employeeId, holder.ref);
  return holder.ref;
}

async function persistConversation(employeeId: string, ref: Partial<ConversationReference>): Promise<void> {
  const response = await brainService<{ stored?: boolean }>('interview/teams/conversation', {
    method: 'POST',
    body: { employee_id: employeeId, conversation_ref: ref },
  });
  if (response.status !== 200 || response.body?.stored !== true) {
    throw new Error('could not store the new conversation reference');
  }
  pendingReferences.delete(employeeId);
}

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

  let lookup: EmployeeLookup;
  try {
    const response = await brainService<EmployeeLookup>(
      `interview/teams/conversation/${encodeURIComponent(employeeId)}`,
    );
    if (response.status === 404) {
      return NextResponse.json(
        { error: 'unknown_employee', detail: response.body?.detail ?? 'no such employee' },
        { status: 404 },
      );
    }
    if (response.status !== 200 || !response.body) {
      return NextResponse.json({ error: 'brain unreachable' }, { status: 502 });
    }
    lookup = response.body;
  } catch {
    return NextResponse.json({ error: 'brain unreachable' }, { status: 502 });
  }

  let ref = lookup.conversation_ref ?? null;
  if (!ref) {
    try {
      ref = await openConversation(employeeId, lookup);
    } catch (err) {
      if ((err as { unreachable?: boolean }).unreachable || isClientError(err)) {
        console.warn('[teams/bot/proactive] cannot open a chat for', employeeId, err);
        return NextResponse.json(
          { error: 'not_reachable', detail: err instanceof Error ? err.message : String(err) },
          { status: 404 },
        );
      }
      console.error('[teams/bot/proactive] open chat failed', err);
      return NextResponse.json({ error: 'send_failed' }, { status: 502 });
    }
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
