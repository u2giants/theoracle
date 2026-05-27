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
//   - Tools (search_company_knowledge, check_open_gaps), multi-turn
//     message history, stopWhen step cap, and temperature are passed
//     through providerOptions — the chat-specific knobs that don't fit
//     OracleAIClient's narrow runText/runObject contract.
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
import { z } from 'zod';
import { stepCountIs, tool } from 'ai';
import { createServiceRoleClient } from '@oracle/auth/server';
import {
  AnthropicAdapter,
  OpenAIAdapter,
  ORACLE_SYSTEM_PROMPT,
  ORACLE_SYSTEM_PROMPT_VERSION,
  OracleAIClient,
  VertexGeminiAdapter,
  getOracleRoute,
  resolveModelRoute,
  getRecentMessages,
  getRelevantOpenGaps,
  makeBlock,
  searchWithRetrievalPlan,
  buildRetrievalPlanFromQuery,
  getOpenGapsForChannel,
  type OracleModelRoute,
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
  settings,
  type OracleDb,
} from '@oracle/db';
import { getServerSupabase } from '@/lib/supabase/server';

const BodySchema = z.object({
  channelId: z.uuid(),
  force: z.boolean().optional(),
});

const FALLBACK_ROUTE_ID = 'anthropic_claude_haiku_4_5_interview_primary';

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
      adapters: {
        anthropic: new AnthropicAdapter(),
        vertex: new VertexGeminiAdapter(),
        openai: new OpenAIAdapter(),
      },
      fallbackOnError: true,
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
  const retrievalPlan = buildRetrievalPlanFromQuery(queryForClaims, { topK: 8 });
  const relevantClaims = queryForClaims
    ? await searchWithRetrievalPlan(db, retrievalPlan)
    : [];

  // ── 4. Resolve curated interview route ───────────────────────────────
  const route = await resolveInterviewRoute(db);
  const visionCapable = isVisionCapableRoute(route);

  // ── 5. Compile prompt blocks (stable system + dynamic context) ───────
  const contextLines: string[] = [];
  contextLines.push(`---\nCONTEXT FOR THIS TURN:`);
  contextLines.push(`You are speaking with ${me.name} (${me.role}, ${me.department}).`);
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
      includedClaimIds: relevantClaims.map((c) => c.id),
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

  // ── 7. Tools (preserved verbatim from legacy route) ──────────────────
  const tools = {
    search_company_knowledge: tool({
      description:
        "Search the Oracle's approved claims and brain sections for operational knowledge. Filter by top-level domain hints if relevant.",
      inputSchema: z.object({
        query: z.string().describe('Free-text question or topic to search for.'),
        topDomainHints: z
          .array(z.string())
          .optional()
          .describe(
            'Optional list of top-level domain IDs to restrict the search ' +
              '(e.g. it_systems, licensing_approvals, customer_ops, supply_chain, ' +
              'logistics_shipping, product_development, production_lifecycle, ' +
              'import_compliance, finance_pricing, people_org). Leave empty to search all.',
          ),
        limit: z.number().int().min(1).max(20).optional(),
      }),
      execute: async ({ query, topDomainHints, limit }) => {
        const toolPlan = buildRetrievalPlanFromQuery(query, {
          topDomainHints: topDomainHints ?? [],
          topK: limit ?? 8,
        });
        const results = await searchWithRetrievalPlan(db, toolPlan);
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
      inputSchema: z.object({ limit: z.number().int().min(1).max(10).optional() }),
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

  // ── 8. Build multi-turn conversation (with attachments for vision routes) ─
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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const conversationMessages: any[] = await Promise.all(
    recent
      .filter((m) => m.role !== 'system')
      .map(async (m) => {
        const role = m.role === 'assistant' ? ('assistant' as const) : ('user' as const);
        const textContent =
          m.role === 'user' && m.authorName ? `[${m.authorName}] ${m.content}` : m.content;
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
          } catch (err) {
            console.error('[chat] attachment fetch failed', att.storagePath, err);
          }
        }
        return { role, content: parts.length === 1 ? textContent : parts };
      }),
  );

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const safeMessages = visionCapable
    ? conversationMessages
    : // eslint-disable-next-line @typescript-eslint/no-explicit-any
      conversationMessages.map((m: any) => {
        if (!Array.isArray(m.content)) return m;
        const textOnly = m.content
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          .filter((p: any) => p.type === 'text')
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          .map((p: any) => p.text as string)
          .join('\n');
        return { ...m, content: textOnly };
      });

  // ── 9. Dispatch through OracleAIClient ───────────────────────────────
  const startedAt = Date.now();
  let oracleText = '';
  let inputTokens: number | undefined;
  let outputTokens: number | undefined;
  let cachedInputTokens: number | undefined;
  let modelError: string | undefined;
  let success = false;
  let usageRaw: unknown = null;
  let providerRequestId: string | undefined;

  try {
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
        messages: safeMessages,
        tools,
        stopWhen: stepCountIs(4),
        temperature: 0.4,
      },
    });
    oracleText = result.text;
    inputTokens = result.usage.inputTokens;
    outputTokens = result.usage.outputTokens;
    cachedInputTokens = result.usage.cachedInputTokens;
    usageRaw = result.usage.rawUsageJson;
    providerRequestId = result.usage.providerRequestId;
    success = true;
  } catch (err) {
    modelError = err instanceof Error ? err.message : String(err);
    console.error('[chat] model error', err);
  }

  // ── 10. Log model_runs + model_run_usage_details + back-link pack ───
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'interview_chat',
      model: route.modelId,
      provider: route.provider,
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
      routeId: route.routeId,
      inputTokens: inputTokens ?? null,
      cachedInputTokens: cachedInputTokens ?? null,
      outputTokens: outputTokens ?? null,
      providerRequestId: providerRequestId ?? null,
      rawUsageJson: usageRaw ?? null,
    });
    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));
  }

  if (!success || !oracleText.trim()) {
    return NextResponse.json(
      { error: 'model_failed', detail: modelError ?? 'empty response' },
      { status: 502 },
    );
  }

  // ── 11. Persist Oracle reply as assistant message ───────────────────
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
    routeId: route.routeId,
    model: route.modelId,
    provider: route.provider,
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

async function resolveInterviewRoute(db: OracleDb): Promise<OracleModelRoute> {
  const row = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'default_interview_route'))
    .limit(1);
  const modelIdOrRouteId =
    typeof row[0]?.value === 'string' ? (row[0]!.value as string) : FALLBACK_ROUTE_ID;
  // resolveModelRoute handles both catalog routeIds and OpenRouter model IDs
  // (e.g. "anthropic/claude-haiku-4-5" saved by the model-pool picker).
  const resolved = resolveModelRoute(modelIdOrRouteId, 'interview') ?? getOracleRoute(modelIdOrRouteId);
  if (resolved) return resolved;
  const fb = getOracleRoute(FALLBACK_ROUTE_ID);
  if (!fb) {
    throw new Error(
      `[chat] settings.default_interview_route="${modelIdOrRouteId}" not resolvable and fallback "${FALLBACK_ROUTE_ID}" missing.`,
    );
  }
  console.warn(
    `[chat] settings.default_interview_route="${modelIdOrRouteId}" not resolvable; using fallback "${FALLBACK_ROUTE_ID}".`,
  );
  return fb;
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
