// Oracle chat route — spec Part 9.1, 9.2, 10.
//
// Trigger: POST { channelId } — fired by the chat UI when the user message
// directly addresses the Oracle (matches /^(@oracle|oracle,)/i).
//
// Behavior:
//   1. Authenticate the requester via Supabase Auth cookies.
//   2. Confirm the requester is a participant of channelId.
//   3. Build a retrieval bundle (spec 9.1): recent messages, employee profile,
//      top open gaps, top relevant approved claims.
//   4. Call OpenRouter via Vercel AI SDK streamText with the spec Part 10 prompt
//      and two tools: search_company_knowledge, check_open_gaps.
//   5. Persist the Oracle's response as a message with role='assistant' so the
//      realtime feed picks it up (spec: assistant inserts require service role).
//
// Note on the streaming model: this route returns a normal JSON response after
// the model finishes because the UI doesn't open a streaming socket for Oracle
// replies — the realtime feed delivers them. Phase 6 may switch to streamed
// SSE if we want progressive Oracle messages.

import { NextResponse, type NextRequest } from 'next/server';
import { eq, and, inArray } from 'drizzle-orm';
import { z } from 'zod';
import { generateText, stepCountIs, tool } from 'ai';
import { createServiceRoleClient } from '@oracle/auth/server';
import {
  ORACLE_SYSTEM_PROMPT,
  ORACLE_SYSTEM_PROMPT_VERSION,
  getOpenRouter,
  getRecentMessages,
  getRelevantOpenGaps,
  searchApprovedClaims,
  getOpenGapsForChannel,
} from '@oracle/ai';
import { KNOWLEDGE_DOMAINS, type KnowledgeDomain } from '@oracle/shared';
import { getDirectDb } from '@oracle/db/client';
import {
  channels,
  channelParticipants,
  documents,
  employeeIdentities,
  employees,
  messageAttachments,
  messages,
  modelRuns,
  settings,
} from '@oracle/db/schema';
import { getServerSupabase } from '@/lib/supabase/server';

const BodySchema = z.object({
  channelId: z.uuid(),
  // Optional: skip the direct-mention gate (used by /admin/test-chat in future).
  force: z.boolean().optional(),
});

const FALLBACK_MODEL = 'anthropic/claude-sonnet-4.6';

export async function POST(req: NextRequest) {
  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse(await req.json());
  } catch (err) {
    return NextResponse.json({ error: 'bad_request', detail: String(err) }, { status: 400 });
  }

  // -------------------------------------------------------------------
  // 1. Auth — must be a signed-in approved employee.
  // -------------------------------------------------------------------
  const supabase = await getServerSupabase();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }

  const db = getDirectDb();
  // Resolve employee through identities (post D2.multi-identity).
  const meRows = await db
    .select({ employee: employees })
    .from(employees)
    .innerJoin(employeeIdentities, eq(employeeIdentities.employeeId, employees.id))
    .where(eq(employeeIdentities.authUserId, userData.user.id))
    .limit(1);
  const me = meRows[0]?.employee;
  if (!me || me.disabledAt) {
    return NextResponse.json({ error: 'not_approved' }, { status: 403 });
  }

  // -------------------------------------------------------------------
  // 2. Confirm participation and load channel metadata.
  // -------------------------------------------------------------------
  const [membership, channelRows] = await Promise.all([
    db
      .select()
      .from(channelParticipants)
      .where(
        and(
          eq(channelParticipants.channelId, body.channelId),
          eq(channelParticipants.employeeId, me.id),
        ),
      )
      .limit(1),
    db
      .select({ isGroupChat: channels.isGroupChat })
      .from(channels)
      .where(eq(channels.id, body.channelId))
      .limit(1),
  ]);

  if (membership.length === 0) {
    return NextResponse.json({ error: 'not_in_channel' }, { status: 403 });
  }

  const isGroupChat = channelRows[0]?.isGroupChat ?? false;

  // -------------------------------------------------------------------
  // 3. Retrieval bundle.
  // -------------------------------------------------------------------
  const recent = await getRecentMessages(db, body.channelId);
  if (recent.length === 0) {
    return NextResponse.json(
      { error: 'no_user_message', detail: 'Channel has no messages.' },
      { status: 400 },
    );
  }

  // Direct-mention gate (spec Part 10 group chat rules). Phase 6 will add
  // lull/contradiction triggers.
  //
  // In DMs the Oracle is the only other participant — it responds to every
  // message. In group chats it only responds when directly addressed with
  // @oracle. The `force` flag bypasses the gate (used by admin test routes).
  const latestUserMessage = [...recent].reverse().find((m) => m.role === 'user');
  if (!latestUserMessage) {
    return NextResponse.json({ ok: true, skipped: 'no_user_message' });
  }
  if (!body.force && isGroupChat) {
    if (!/^\s*(@oracle\b|oracle,)/i.test(latestUserMessage.content)) {
      return NextResponse.json({ ok: true, skipped: 'no_direct_mention' });
    }
  }

  const openGaps = await getRelevantOpenGaps(db, me);
  const queryForClaims = latestUserMessage?.content ?? '';
  const relevantClaims = queryForClaims
    ? await searchApprovedClaims(db, queryForClaims)
    : [];

  // -------------------------------------------------------------------
  // 4. Model call.
  // -------------------------------------------------------------------
  const modelSetting = await db
    .select()
    .from(settings)
    .where(eq(settings.key, 'default_interview_model'))
    .limit(1);
  const modelName =
    (typeof modelSetting[0]?.value === 'string'
      ? (modelSetting[0]!.value as string)
      : null) ??
    process.env.ORACLE_INTERVIEW_MODEL ??
    FALLBACK_MODEL;

  // Tools — spec 9.2.
  const tools = {
    search_company_knowledge: tool({
      description:
        'Search the Oracle\'s approved claims and brain sections for operational knowledge. Filter by knowledge domains if relevant.',
      inputSchema: z.object({
        query: z.string().describe('Free-text question or topic to search for.'),
        domains: z
          .array(z.enum(KNOWLEDGE_DOMAINS as unknown as [string, ...string[]]))
          .optional()
          .describe('Optional list of knowledge domains to filter by.'),
        limit: z.number().int().min(1).max(20).optional(),
      }),
      execute: async ({ query, domains, limit }) => {
        const results = await searchApprovedClaims(db, query, {
          domains: domains as KnowledgeDomain[] | undefined,
          limit,
        });
        return {
          claims: results.map((r) => ({
            id: r.id,
            summary: r.summary,
            claimType: r.claimType,
            impact: r.impactScore,
            confidence: r.confidenceScore,
          })),
          count: results.length,
        };
      },
    }),
    check_open_gaps: tool({
      description:
        'List open knowledge gaps assigned to the current employee, the channel members, or relevant departments. Use these to weave natural questions.',
      inputSchema: z.object({
        limit: z.number().int().min(1).max(10).optional(),
      }),
      execute: async ({ limit }) => {
        const channelGaps = await getOpenGapsForChannel(db, body.channelId, limit ?? 5);
        return {
          gaps: channelGaps.map((g) => ({
            id: g.id,
            question: g.questionToAsk,
            whyItMatters: g.whyItMatters,
            priority: g.priority,
            sectionId: g.sectionId,
          })),
          count: channelGaps.length,
        };
      },
    }),
  };

  // Build the prompt context block. We append to the system prompt rather
  // than concatenating into the user message to keep the model's role
  // boundaries clean.
  const contextLines: string[] = [];
  contextLines.push(`\n\n---\nCONTEXT FOR THIS TURN:`);
  contextLines.push(
    `You are speaking with ${me.name} (${me.role}, ${me.department}).`,
  );
  if (openGaps.length > 0) {
    contextLines.push(`\nOpen gaps you may weave in if relevant:`);
    for (const g of openGaps) {
      contextLines.push(`- [${g.priority}] ${g.questionToAsk}`);
    }
  }
  if (relevantClaims.length > 0) {
    contextLines.push(`\nApproved claims that may be relevant:`);
    for (const c of relevantClaims) {
      contextLines.push(`- ${c.summary} (impact ${c.impactScore})`);
    }
  }
  const systemPrompt = ORACLE_SYSTEM_PROMPT + contextLines.join('\n');

  // Load attachments for every message in the window so the model can see
  // the actual file content (images, PDFs, plain text) rather than just the
  // "Attached: filename" placeholder text.
  const recentIds = recent.map((m) => m.id);
  const attachmentRows =
    recentIds.length > 0
      ? await db
          .select({
            messageId: messageAttachments.messageId,
            storageBucket: documents.storageBucket,
            storagePath: documents.storagePath,
            fileType: documents.fileType,
            fileName: documents.fileName,
          })
          .from(messageAttachments)
          .innerJoin(documents, eq(documents.id, messageAttachments.documentId))
          .where(inArray(messageAttachments.messageId, recentIds))
      : [];

  type AttRow = (typeof attachmentRows)[number];
  const attachmentMap = new Map<string, AttRow[]>();
  for (const att of attachmentRows) {
    const list = attachmentMap.get(att.messageId) ?? [];
    list.push(att);
    attachmentMap.set(att.messageId, list);
  }

  const serviceSupabase = createServiceRoleClient();

  // Build multi-modal conversation messages. For messages with file attachments
  // we fetch the bytes from Storage and pass them as image/file/text parts.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const conversationMessages: any[] = await Promise.all(
    recent
      .filter((m) => m.role !== 'system')
      .map(async (m) => {
        const role = m.role === 'assistant' ? ('assistant' as const) : ('user' as const);
        const textContent =
          m.role === 'user' && m.authorName
            ? `[${m.authorName}] ${m.content}`
            : m.content;

        const atts = attachmentMap.get(m.id) ?? [];
        if (atts.length === 0) return { role, content: textContent };

        type Part =
          | { type: 'text'; text: string }
          | { type: 'image'; image: string }
          | { type: 'file'; data: string; mimeType: string };

        const parts: Part[] = [{ type: 'text', text: textContent }];

        for (const att of atts) {
          try {
            const { data: blob, error } = await serviceSupabase.storage
              .from(att.storageBucket)
              .download(att.storagePath);
            if (error || !blob) {
              console.warn('[chat] could not download attachment', att.storagePath, error?.message);
              continue;
            }
            const buf = Buffer.from(await blob.arrayBuffer());
            const b64 = buf.toString('base64');

            if (att.fileType.startsWith('image/')) {
              parts.push({ type: 'image', image: `data:${att.fileType};base64,${b64}` });
            } else if (att.fileType === 'application/pdf') {
              parts.push({ type: 'file', data: b64, mimeType: 'application/pdf' });
            } else if (att.fileType.startsWith('text/')) {
              const text = buf.toString('utf8');
              parts.push({ type: 'text', text: `\n\n[File: ${att.fileName}]\n${text}\n[/File]` });
            }
            // Other MIME types: skip (binary formats the model can't interpret)
          } catch (err) {
            console.error('[chat] attachment fetch failed', att.storagePath, err);
          }
        }

        return { role, content: parts.length === 1 ? textContent : parts };
      }),
  );

  const startedAt = Date.now();
  let success = false;
  let oracleText = '';
  let inputTokens: number | undefined;
  let outputTokens: number | undefined;
  let modelError: string | undefined;

  try {
    const openrouter = getOpenRouter();
    const model = openrouter(modelName);
    const result = await generateText({
      model,
      system: systemPrompt,
      messages: conversationMessages,
      tools,
      stopWhen: stepCountIs(4),
      temperature: 0.4,
    });
    oracleText = result.text;
    inputTokens = result.usage?.inputTokens;
    outputTokens = result.usage?.outputTokens;
    success = true;
  } catch (err) {
    modelError = err instanceof Error ? err.message : String(err);
    console.error('[chat] model error', err);
  }

  // Log the model run.
  await db.insert(modelRuns).values({
    taskType: 'interview_chat',
    model: modelName,
    provider: 'openrouter',
    promptVersion: ORACLE_SYSTEM_PROMPT_VERSION,
    inputTokens: inputTokens ?? null,
    outputTokens: outputTokens ?? null,
    latencyMs: Date.now() - startedAt,
    success,
    error: modelError ?? null,
  });

  if (!success || !oracleText.trim()) {
    return NextResponse.json(
      { error: 'model_failed', detail: modelError ?? 'empty response' },
      { status: 502 },
    );
  }

  // -------------------------------------------------------------------
  // 5. Persist the Oracle's reply as an assistant message.
  //    Direct DB write via service role bypasses the messages_self_insert
  //    policy (which restricts authenticated users to role='user').
  // -------------------------------------------------------------------
  const [inserted] = await db
    .insert(messages)
    .values({
      channelId: body.channelId,
      employeeId: null,
      role: 'assistant',
      content: oracleText.trim(),
      extractionStatus: 'skipped', // Oracle responses don't become claims.
    })
    .returning();

  return NextResponse.json({
    ok: true,
    messageId: inserted?.id,
    model: modelName,
    latencyMs: Date.now() - startedAt,
  });
}
