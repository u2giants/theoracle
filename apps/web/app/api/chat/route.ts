// R8 — Oracle chat route (refactored through OracleAIClient).
//
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R8.
//
// What changed vs the legacy route:
//   - The model call goes through OracleAIClient.runText via the direct
//     provider adapters (Vertex / Anthropic / OpenAI raw SDKs —
//     DECISIONS.md D6 / D9) using the curated interview route from
//     `settings.default_interview_route` (R1 setting key) — not via
//     `getOpenRouter()` directly.
//   - oracle_context_packs + model_run_usage_details rows are written
//     for every chat turn so cache-hit / fallback dashboards work.
//   - The chat route executes retrieval deterministically before the model call
//     (recent messages, open gaps, approved claims); multi-turn message history
//     and temperature are passed through providerOptions.
//
// What stays the same:
//   - Auth + channel-participation check.
//   - Direct-mention gate for group chats (spec Part 10 group chat rules).
//   - Retrieval bundle: recent messages, employee profile, top open gaps,
//     top relevant approved claims. No full Brain stuffing.
//   - Vision-capable model detection + selective attachment downloads.
//   - Assistant message inserted via service-role client.

import { NextResponse, type NextRequest } from 'next/server';
import { eq, and, inArray } from 'drizzle-orm';
import { desc } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { writeFile, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { z } from 'zod';
import { coerceLocale } from '@oracle/shared';
import { createServiceRoleClient } from '@oracle/auth/server';
import {
  ORACLE_SYSTEM_PROMPT,
  ORACLE_SYSTEM_PROMPT_VERSION,
  OracleAIClient,
  buildStandardAdapters,
  resolveRouteCandidates,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  getRecentMessages,
  getRelevantOpenGaps,
  makeBlock,
  searchWithRetrievalPlan,
  buildRetrievalPlanFromQuery,
  type OracleModelRoute,
  type RouteCandidate,
  type OraclePromptPlan,
  type RetrievalPlanSearchScope,
} from '@oracle/ai';
import { getDirectDb } from '@oracle/db/client';
import {
  channels,
  channelParticipants,
  documents,
  employeeIdentities,
  employees,
  messageAttachments,
  messages,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  providerResponseSessions,
  settings,
  type OracleDb,
} from '@oracle/db';
import { getApprovedMacroRelationships } from '@oracle/engines';
import { getServerSupabase } from '@/lib/supabase/server';

const BodySchema = z.object({
  channelId: z.uuid(),
  force: z.boolean().optional(),
});

// Minimum size for routing a chat-attached PDF through the Vertex GCS
// file-backed cache. Below this, Gemini's explicit-cache minimum-token floor
// makes caching unprofitable (and risky — see route logic), so we leave small
// files on the inline path.
const VERTEX_CHAT_FILE_CACHE_MIN_BYTES = 256 * 1024;

// Lazy singleton OracleAIClient with direct provider adapters (R-providers).
// Anthropic / Vertex / OpenAI raw SDKs per DECISIONS.md D6 — no Vercel AI
// SDK, no OpenRouter in this path.
//
// The adapter constructors throw when their provider API key is missing, so
// we MUST defer instantiation until the first request. At Next.js build time,
// the "Collect page data" phase imports this module without the runtime env
// vars in scope — eagerly constructing the singleton there fails the build.
let _oracleClient: OracleAIClient | null = null;
function getOracleClient(): OracleAIClient {
  if (!_oracleClient) {
    _oracleClient = new OracleAIClient({
      adapters: buildStandardAdapters(),
    });
  }
  return _oracleClient;
}

export async function POST(req: NextRequest) {
  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse(await req.json());
  } catch (err) {
    return NextResponse.json({ error: 'bad_request', detail: String(err) }, { status: 400 });
  }

  // ── 1. Auth ──────────────────────────────────────────────────────────
  const supabase = await getServerSupabase();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }

  const db = getDirectDb();
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

  // ── 2. Channel membership + group-chat detection ─────────────────────
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

  // ── 3. Retrieval bundle ──────────────────────────────────────────────
  const recent = await getRecentMessages(db, body.channelId);
  if (recent.length === 0) {
    return NextResponse.json(
      { error: 'no_user_message', detail: 'Channel has no messages.' },
      { status: 400 },
    );
  }

  // Direct-mention gate (group chats only; DM is always direct).
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
  // Build a RetrievalPlan from the latest message — applies domain-hint inference,
  // entity-type exclusions, and document-class exclusions before vector search
  // (spec docs/oracle/07-knowledge-segmentation.md "Retrieval rule").
  const queryForClaims = latestUserMessage.content;
  // Use the employee's departments as a soft RRF bonus — not a filter.
  // Falls back to legacy single `department` field if `departments` is empty.
  const deptHints =
    me.departments.length > 0
      ? me.departments
      : me.department ? [me.department] : [];
  const retrievalPlan = buildRetrievalPlanFromQuery(queryForClaims, {
    topK: 8,
    departmentHints: deptHints,
  });
  // Reader locale ('zh-CN' for the manually-routed China group, else 'en').
  // Drives claim/Brain rendering language and the answer-language instruction.
  const locale = coerceLocale(me.locale);
  const relevantClaims = queryForClaims
    ? await searchWithRetrievalPlan(db, retrievalPlan, locale)
    : [];
  const macroRelationships =
    relevantClaims.length > 0
      ? await getApprovedMacroRelationships({
          db,
          claimIds: relevantClaims.map((claim) => claim.id),
          limit: 8,
        })
      : [];

  // ── 4. Resolve curated interview route ───────────────────────────────
  const routeCandidates = await resolveInterviewCandidates(db);
  const route = routeCandidates[0]!.route;
  const visionCapable = isVisionCapableRoute(route);

  // ── 5. Compile prompt blocks (stable system + dynamic context) ───────
  const contextLines: string[] = [];
  contextLines.push(`---\nCONTEXT FOR THIS TURN:`);
  // Bilingual (china_imp.md): instruct the model to converse in the reader's
  // language. Claims/Brain context above is already rendered in this locale.
  if (locale === 'zh-CN') {
    contextLines.push(
      `Respond to this employee entirely in Simplified Chinese (简体中文). ` +
        `Write your questions, explanations, and summaries in Chinese.`,
    );
  }
  const deptDisplay = me.departments.length > 0
    ? me.departments.join(', ')
    : (me.department ?? 'Unknown');
  contextLines.push(`You are speaking with ${me.name} (${me.role}, ${deptDisplay}).`);
  if (openGaps.length > 0) {
    contextLines.push(`\nOpen gaps you may weave in if relevant:`);
    for (const g of openGaps) {
      contextLines.push(`- [${g.priority}] ${g.questionToAsk}`);
    }
  }
  if (relevantClaims.length > 0) {
    if (macroRelationships.length > 0) {
      contextLines.push(`\nApproved macro relationships (workflow backbone):`);
      contextLines.push(
        'Treat these as reviewed structure. Atomic claims below are supporting details, examples, exceptions, or local observations.',
      );
      for (const relationship of macroRelationships) {
        contextLines.push(
          `- [${relationship.relationshipType}] ${relationship.summary} (impact ${relationship.impactScore}; support claims ${relationship.supportClaims.map((c) => c.id).join(', ')})`,
        );
      }
    }
    contextLines.push(`\nApproved claims that may be relevant:`);
    for (const c of relevantClaims) {
      const reviewedKind = c.claimKindReviewStatus === 'reviewed' ? (c.claimKind ?? 'uncertain') : 'uncertain';
      contextLines.push(`- ${c.summary} (impact ${c.impactScore}; kind ${reviewedKind})`);
    }
  }
  const dynamicContext = contextLines.join('\n');

  const blocks = [
    makeBlock({
      id: 'oracle-system',
      label: 'Oracle interview system prompt',
      kind: 'stable_system',
      content: ORACLE_SYSTEM_PROMPT,
      reasonIncluded: 'oracle prompt v' + ORACLE_SYSTEM_PROMPT_VERSION,
    }),
    makeBlock({
      id: 'turn-context',
      label: 'Per-turn retrieval bundle (employee + gaps + relevant claims)',
      kind: 'retrieved_context',
      content: dynamicContext,
      reasonIncluded: `gaps=${openGaps.length}, claims=${relevantClaims.length}`,
    }),
  ];

  const plan = getOracleClient().compile({
    taskType: 'interview_chat',
    routeId: route.routeId,
    promptVersion: ORACLE_SYSTEM_PROMPT_VERSION,
    blocks,
    observability: {
      includedMessageIds: recent.map((m) => m.id),
      includedGapIds: openGaps.map((g) => g.id),
      includedClaimIds: Array.from(
        new Set([
          ...relevantClaims.map((c) => c.id),
          ...macroRelationships.flatMap((relationship) =>
            relationship.supportClaims.map((claim) => claim.id),
          ),
        ]),
      ),
      // Retrieval scope audit — stored in oracle_context_packs.selected_domains.
      // domain_filtered → actual domain IDs used for pre-filtering.
      // global_fallback → '_global_fallback' tag; query
      //   WHERE selected_domains @> ARRAY['_global_fallback'] to find heuristic gaps.
      // global_explicit → '_global_explicit' tag (intentional wide search).
      selectedDomains: scopeTag(retrievalPlan.topDomainHints, retrievalPlan.searchScope),
    },
  });

  // ── 6. Stage context pack BEFORE the model call ──────────────────────
  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) {
    return NextResponse.json({ error: 'context_pack_failed' }, { status: 500 });
  }

  // ── 7. Build multi-turn conversation (with attachments for vision routes) ─
  const recentIds = recent.map((m) => m.id);
  const attachmentRows =
    visionCapable && recentIds.length > 0
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

  // ── 7a. Vertex GCS file-backed cache for a large attached PDF ────────
  // When the interview route runs on Vertex AND a GCS cache bucket is
  // configured, cache the most-recent large PDF in the thread as a Gemini
  // cachedContent prefix (gs:// fileData) instead of re-sending it as base64
  // on every turn. The conversation turns ride on top of the cache as live
  // text contents (the adapter preserves multi-turn history on the file-cache
  // path). When this activates we EXCLUDE inline attachment parts so the doc
  // is not double-sent; v1 limitation: only this single cached document is
  // provided to the model, other attachments are not separately inlined.
  //
  // Gated on the bucket env: without it the adapter no-ops the file path, so
  // excluding the inline copy would leave the model with no document at all.
  const fileCacheEnabled =
    route.provider === 'vertex' && !!process.env.GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET;
  let vertexFileCacheSource:
    | { localPath: string; mimeType: string; fileName: string; sourceHash: string }
    | undefined;
  let cachedTempPath: string | undefined;
  if (fileCacheEnabled) {
    const candidate = pickCacheablePdf(recent, attachmentMap);
    if (candidate) {
      try {
        const { data: blob, error } = await serviceSupabase.storage
          .from(candidate.storageBucket)
          .download(candidate.storagePath);
        if (error || !blob) {
          console.warn('[chat] file-cache candidate download failed', candidate.storagePath, error?.message);
        } else {
          const buf = Buffer.from(await blob.arrayBuffer());
          if (buf.length >= VERTEX_CHAT_FILE_CACHE_MIN_BYTES) {
            cachedTempPath = await materializeVertexCacheTempFile(buf, candidate.fileName);
            vertexFileCacheSource = {
              localPath: cachedTempPath,
              mimeType: candidate.fileType,
              fileName: candidate.fileName,
              // `documents` has no content hash column — hash the bytes so the
              // cache key + GCS object name are stable across turns (enables reuse).
              sourceHash: createHash('sha256').update(buf).digest('hex'),
            };
          }
        }
      } catch (err) {
        console.warn('[chat] file-cache candidate preparation failed', candidate.storagePath, err);
      }
    }
  }
  // Only exclude inline attachment parts once we are certain the file cache
  // will carry the document; otherwise keep the existing inline behavior.
  const excludeInlineAttachments = !!vertexFileCacheSource;

  // Image parts use the PROVIDER-NEUTRAL shape `{ type:'image', mimeType, data }`
  // — the ONLY shape every hardened adapter translates (Gemini→inlineData,
  // OpenAI/Qwen→image_url, Anthropic→base64 block). The old `{ image: dataUrl }`
  // shape was unrecognized: Gemini stringified it to garbage and OpenAI/Anthropic
  // got an invalid part, so chat image attachments were silently broken.
  type ChatContentPart =
    | { type: 'text'; text: string }
    | { type: 'image'; mimeType: string; data: string }
    | { type: 'file'; data: string; mimeType: string; fileName?: string };
  type ConversationMessage = {
    role: 'user' | 'assistant';
    content: string | ChatContentPart[];
  };

  const conversationMessages: ConversationMessage[] = await Promise.all(
    recent
      .filter((m) => m.role !== 'system')
      .map(async (m) => {
        const role = m.role === 'assistant' ? ('assistant' as const) : ('user' as const);
        const textContent =
          m.role === 'user' && m.authorName ? `[${m.authorName}] ${m.content}` : m.content;
        const atts = attachmentMap.get(m.id) ?? [];
        if (atts.length === 0 || excludeInlineAttachments) return { role, content: textContent };

        const parts: ChatContentPart[] = [{ type: 'text', text: textContent }];
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
              parts.push({ type: 'image', mimeType: att.fileType, data: b64 });
            } else if (att.fileType === 'application/pdf') {
              // Provider-neutral FILE part. Every hardened adapter now translates
              // it at dispatch (Gemini → inlineData, OpenAI → file/file_data,
              // Anthropic → document block); large PDFs may instead be served via
              // the Vertex file-cache path above. fileName is carried because the
              // OpenAI `file` part requires a filename.
              parts.push({
                type: 'file',
                data: b64,
                mimeType: 'application/pdf',
                fileName: att.fileName,
              });
            } else if (att.fileType.startsWith('text/')) {
              const text = buf.toString('utf8');
              parts.push({ type: 'text', text: `\n\n[File: ${att.fileName}]\n${text}\n[/File]` });
            }
          } catch (err) {
            console.error('[chat] attachment fetch failed', att.storagePath, err);
          }
        }
        return { role, content: parts.length === 1 ? textContent : parts };
      }),
  );

  const safeMessages: ConversationMessage[] = visionCapable
    ? conversationMessages
    : conversationMessages.map((m) => {
        if (!Array.isArray(m.content)) return m;
        const textOnly = m.content
          .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
          .map((p) => p.text)
          .join('\n');
        return { ...m, content: textOnly };
      });

  // ── 8. Dispatch through OracleAIClient ───────────────────────────────
  const startedAt = Date.now();
  const qwenSessionKey = route.provider === 'qwen' ? `interview-chat:${body.channelId}` : null;
  const previousQwenSession =
    qwenSessionKey
      ? await db
          .select({
            latestResponseId: providerResponseSessions.latestResponseId,
            modelId: providerResponseSessions.modelId,
          })
          .from(providerResponseSessions)
          .where(
            and(
              eq(providerResponseSessions.provider, 'qwen'),
              eq(providerResponseSessions.sessionKey, qwenSessionKey),
            ),
          )
          .orderBy(desc(providerResponseSessions.updatedAt))
          .limit(1)
      : [];
  let oracleText = '';
  let inputTokens: number | undefined;
  let outputTokens: number | undefined;
  let cachedInputTokens: number | undefined;
  let modelError: string | undefined;
  let success = false;
  let usageRaw: unknown = null;
  let providerRequestId: string | undefined;
  let actualRouteId = route.routeId;
  let actualProvider = route.provider;
  let actualModelId = route.modelId;
  let runMetadata: Awaited<ReturnType<OracleAIClient['runText']>> | null = null;

  try {
    // Cache-friendly ordering: fold the volatile per-turn runtime context
    // (gaps + freshly-retrieved claims, which change every turn) into the LAST
    // user turn so the system prompt + prior conversation history stay a stable,
    // cacheable prefix. Prepending it (the old behavior) changed message index 1
    // on every turn and busted provider prefix caching for the whole thread.
    const runtimeBlock =
      '[Oracle runtime context - not part of the employee chat transcript]\n' +
      dynamicContext;
    const messagesWithContext: ConversationMessage[] = safeMessages.map((m) => ({ ...m }));
    const lastTurn = messagesWithContext[messagesWithContext.length - 1];
    if (!lastTurn || lastTurn.role !== 'user') {
      messagesWithContext.push({ role: 'user', content: runtimeBlock });
    } else if (typeof lastTurn.content === 'string') {
      lastTurn.content = `${lastTurn.content}\n\n${runtimeBlock}`;
    } else {
      lastTurn.content = [...lastTurn.content, { type: 'text', text: runtimeBlock }];
    }
    const result = await getOracleClient().runText({
      taskType: 'interview_chat',
      routeId: route.routeId,
      promptVersion: ORACLE_SYSTEM_PROMPT_VERSION,
      blocks,
      observability: {
        includedMessageIds: recent.map((m) => m.id),
        includedGapIds: openGaps.map((g) => g.id),
        includedClaimIds: relevantClaims.map((c) => c.id),
      },
      providerOptions: {
        messages: messagesWithContext,
        temperature: 0.4,
        cache: {
          preferLongLivedCache: true,
          // 30 min when caching an attached document for an active chat;
          // otherwise the default short interview-context TTL.
          cacheTtlSeconds: vertexFileCacheSource ? 30 * 60 : 10 * 60,
          expectedReuseCount: 6,
          // Activates the adapter's explicit file-cache path (Vertex only).
          preferExplicitCache: !!vertexFileCacheSource,
          persistProviderCacheRecord: route.provider === 'vertex',
          sourceDescription: `channel ${body.channelId} interview context`,
          cleanupOwner: 'chat-route',
          latestPlannedReuseStep: 'interview_chat',
          vertexFileCacheSource,
          sessionCacheKey:
            qwenSessionKey ?? undefined,
          previousResponseId:
            route.provider === 'qwen'
              ? previousQwenSession[0]?.modelId === route.modelId
                ? previousQwenSession[0]?.latestResponseId
                : undefined
              : undefined,
        },
      },
      routeCandidates,
    });
    runMetadata = result;
    oracleText = result.text;
    inputTokens = result.usage.inputTokens;
    outputTokens = result.usage.outputTokens;
    cachedInputTokens = result.usage.cachedInputTokens;
    usageRaw = result.usage.rawUsageJson;
    providerRequestId = result.usage.providerRequestId;
    actualRouteId = result.routeId ?? route.routeId;
    actualProvider = (result.provider as typeof route.provider | undefined) ?? route.provider;
    actualModelId = result.modelId ?? route.modelId;
    success = true;
  } catch (err) {
    modelError = err instanceof Error ? err.message : String(err);
    console.error('[chat] model error', err);
    await logAllCandidatesFailedAttempts({
      db,
      error: err,
      taskType: 'interview_chat',
      slot: 'interview',
      contextPackId: contextPack.id,
    }).catch((logErr) => console.error('[chat] failed to record model attempts', logErr));
  } finally {
    // The GCS object is reaped by the adapter's cache-TTL sweeper; we only own
    // the local temp file. Best-effort cleanup.
    if (cachedTempPath) {
      await unlink(cachedTempPath).catch(() => undefined);
    }
  }

  // ── 9. Log model_runs + model_run_usage_details + back-link pack ───
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'interview_chat',
      model: actualModelId,
      provider: actualProvider,
      promptVersion: ORACLE_SYSTEM_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: inputTokens ?? null,
      outputTokens: outputTokens ?? null,
      latencyMs: Date.now() - startedAt,
      success,
      error: modelError ?? null,
    })
    .returning({ id: modelRuns.id });

  if (modelRun) {
    await db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
      contextPackId: contextPack.id,
      routeId: actualRouteId,
      inputTokens: inputTokens ?? null,
      cachedInputTokens: cachedInputTokens ?? null,
      outputTokens: outputTokens ?? null,
      providerRequestId: providerRequestId ?? null,
      rawUsageJson: usageRaw ?? null,
    });
    if (runMetadata) {
      await logModelRunAttempts({
        db,
        metadata: runMetadata,
        taskType: 'interview_chat',
        slot: 'interview',
        contextPackId: contextPack.id,
        modelRunId: modelRun.id,
      });
    }
    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));

    if (actualProvider === 'qwen' && providerRequestId && qwenSessionKey) {
      await db
        .insert(providerResponseSessions)
        .values({
          provider: 'qwen',
          sessionKey: qwenSessionKey,
          scopeKind: 'channel',
          scopeId: body.channelId,
          modelId: actualModelId,
          latestResponseId: providerRequestId,
          lastContextPackId: contextPack.id,
          lastModelRunId: modelRun.id,
          metadataJson: {
            routeId: actualRouteId,
          },
        })
        .onConflictDoUpdate({
          target: [
            providerResponseSessions.provider,
            providerResponseSessions.sessionKey,
          ],
          set: {
            modelId: actualModelId,
            latestResponseId: providerRequestId,
            lastContextPackId: contextPack.id,
            lastModelRunId: modelRun.id,
            metadataJson: {
              routeId: actualRouteId,
            },
            updatedAt: new Date(),
          },
        });
    }
  }

  if (!success || !oracleText.trim()) {
    return NextResponse.json(
      { error: 'model_failed', detail: modelError ?? 'empty response' },
      { status: 502 },
    );
  }

  // ── 10. Persist Oracle reply as assistant message ───────────────────
  const [inserted] = await db
    .insert(messages)
    .values({
      channelId: body.channelId,
      employeeId: null,
      role: 'assistant',
      content: oracleText.trim(),
      extractionStatus: 'skipped',
    })
    .returning();

  return NextResponse.json({
    ok: true,
    messageId: inserted?.id,
    routeId: actualRouteId,
    model: actualModelId,
    provider: actualProvider,
    contextPackId: contextPack.id,
    modelRunId: modelRun?.id ?? null,
    latencyMs: Date.now() - startedAt,
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

/**
 * Build the selectedDomains array for the context pack.
 * - domain_filtered: return the actual domain IDs.
 * - global_fallback / global_explicit: return a single sentinel tag so
 *   operators can query: WHERE selected_domains @> ARRAY['_global_fallback'].
 */
function scopeTag(topDomainHints: string[], scope: RetrievalPlanSearchScope): string[] {
  if (topDomainHints.length > 0) return topDomainHints;
  return [`_${scope}`]; // '_global_fallback' or '_global_explicit'
}

async function resolveInterviewCandidates(db: OracleDb): Promise<RouteCandidate[]> {
  const resolved = await resolveRouteCandidates(db, 'interview');
  for (const skipped of resolved.skipped) {
    console.error(`[chat] skipped configured interview candidate ${skipped.modelIdOrRouteId}: ${skipped.reason}`);
  }
  return resolved.candidates;
}

/**
 * Pick at most ONE document to route through the Vertex GCS file cache: the
 * most-recent PDF attachment in the recent-message window. Walks newest→oldest
 * so an attachment on the latest turn wins.
 */
function pickCacheablePdf<T extends { fileType: string }>(
  recentMessages: Array<{ id: string }>,
  attachmentMap: Map<string, T[]>,
): T | null {
  for (let i = recentMessages.length - 1; i >= 0; i -= 1) {
    const atts = attachmentMap.get(recentMessages[i]!.id) ?? [];
    const pdf = atts.find((a) => a.fileType === 'application/pdf');
    if (pdf) return pdf;
  }
  return null;
}

async function materializeVertexCacheTempFile(buffer: Buffer, fileName: string): Promise<string> {
  const safeName = fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
  const tempPath = join(tmpdir(), `oracle-chat-vertex-cache-${Date.now()}-${safeName}`);
  await writeFile(tempPath, buffer);
  return tempPath;
}

function isVisionCapableRoute(route: OracleModelRoute): boolean {
  // Vision detection from the route's flags + a name regex fallback. The
  // curated catalog already encodes supportsVision on each route; the
  // regex is a defensive belt-and-suspenders in case a catalog entry
  // gets misconfigured.
  if (route.supportsVision) return true;
  return /claude|gpt-4o|gemini|llava|pixtral|qwen.*vl|minicpm/i.test(route.modelId);
}

function buildContextPackInsert(plan: OraclePromptPlan) {
  return {
    taskType: plan.taskType,
    routeId: plan.routeId,
    promptVersion: plan.promptVersion,
    schemaVersion: plan.schemaVersion ?? null,
    stablePrefixHash: plan.metadata.stablePrefixHash,
    semiStableContextHash: plan.metadata.semiStableContextHash ?? null,
    retrievedContextHash: plan.metadata.retrievedContextHash ?? null,
    dynamicInputHash: plan.metadata.dynamicInputHash,
    toolSchemaHash: plan.metadata.toolSchemaHash ?? null,
    outputSchemaHash: plan.metadata.outputSchemaHash ?? null,
    blocksJson: plan.blocks.map((b) => ({
      id: b.id,
      label: b.label,
      kind: b.kind,
      hash: b.hash,
      tokenEstimate: b.tokenEstimate ?? null,
      cacheEligible: b.cacheEligible,
      reasonIncluded: b.reasonIncluded,
    })),
    retrievalPlanId: plan.metadata.retrievalPlanId ?? null,
    selectedDomains: plan.metadata.selectedDomains ?? null,
    selectedSourceTypes: plan.metadata.selectedSourceTypes ?? null,
    selectedProcessStages: plan.metadata.selectedProcessStages ?? null,
    selectedEntityIds: plan.metadata.selectedEntityIds ?? null,
    includedMessageIds: plan.metadata.includedMessageIds ?? null,
    includedDocumentChunkIds: plan.metadata.includedDocumentChunkIds ?? null,
    includedClaimIds: plan.metadata.includedClaimIds ?? null,
    includedGapIds: plan.metadata.includedGapIds ?? null,
    includedContradictionIds: plan.metadata.includedContradictionIds ?? null,
  };
}
