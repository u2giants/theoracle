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
import { createHash, randomUUID } from 'node:crypto';
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
  getEligibleRelationshipClaims,
  buildRetrievalPlanFromQuery,
  buildRetrievalPlanWithModel,
  lookupRegistryEntityCandidates,
  selectEntitiesWithConfiguredModel,
  type RouteCandidate,
  type OraclePromptPlan,
  type OracleRunRouteMetadata,
  type OracleUsage,
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
import { getApprovedMacroRelationships } from '@oracle/engines';
import { getServerSupabase } from '@/lib/supabase/server';
import { buildConversationRetrievalQuery, selectRelevantAttachmentMessageIds } from '@/lib/business-answer-context';
import { retrieveBusinessAnswerContext } from '@/lib/business-answer-retrieval';
import { assertKnownBusinessCitations } from '@/lib/business-answer-policy';
import {
  ATTACHMENT_ANSWER_REVIEW_SYSTEM,
  BUSINESS_ANSWER_RECONCILIATION_SYSTEM,
  BUSINESS_ANSWER_RECONCILIATION_VERSION,
  BUSINESS_ANSWER_REVIEW_SYSTEM,
  BusinessAnswerReconciliationSchema,
  BusinessAnswerSemanticReviewSchema,
  assertEvidenceLocale,
  assertReconciledBusinessAnswer,
  buildAttachmentReviewInput,
  buildReconciliationInput,
  buildSemanticReviewInput,
  hasBusinessAnswerIntent,
  providerIndependenceFamily,
  renderReconciledBusinessAnswer,
  shouldReconcileBusinessAnswer,
  validateReconciliation,
  validateSemanticReview,
  type BusinessAnswerReconciliation,
  type BusinessAnswerSemanticReview,
} from '@/lib/business-answer-reconciliation';
import {
  ChatAttachmentSafetyError,
  isAttachmentCapableRoute,
  selectAttachmentSafeCandidates,
  toCanonicalAttachmentPart,
  type ChatAttachmentPart,
} from '@/lib/chat-attachment-safety';

const BodySchema = z.object({
  channelId: z.uuid(),
  force: z.boolean().optional(),
});

// Minimum size for routing a chat-attached PDF through the Vertex GCS
// file-backed cache. Below this, Gemini's explicit-cache minimum-token floor
// makes caching unprofitable (and risky — see route logic), so we leave small
// files on the inline path.
const VERTEX_CHAT_FILE_CACHE_MIN_BYTES = 256 * 1024;
const ENTITY_AWARE_RETRIEVAL_SETTING_KEY = 'entity_aware_retrieval_enabled';

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
  // Build a RetrievalPlan from the question plus bounded user-only follow-up context.
  // Applies domain-hint inference,
  // entity-type exclusions, and document-class exclusions before vector search
  // (spec docs/oracle/07-knowledge-segmentation.md "Retrieval rule").
  const queryForClaims = buildConversationRetrievalQuery(recent, latestUserMessage.content);
  // Use the employee's departments as a soft RRF bonus — not a filter.
  // Falls back to legacy single `department` field if `departments` is empty.
  const deptHints =
    me.departments.length > 0
      ? me.departments
      : me.department ? [me.department] : [];
  const [entityAwareSetting] = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, ENTITY_AWARE_RETRIEVAL_SETTING_KEY))
    .limit(1);
  const entityAwareEnabled = entityAwareSetting?.value === true;
  const retrievalPlan = entityAwareEnabled
    ? await buildRetrievalPlanWithModel(queryForClaims, {
        topK: 8,
        departmentHints: deptHints,
        lookupCandidates: (query) => lookupRegistryEntityCandidates(db, query),
        selectWithModel: (query, candidates) =>
          selectEntitiesWithConfiguredModel(db, getOracleClient(), query, candidates),
      })
    : buildRetrievalPlanFromQuery(queryForClaims, {
        topK: 8,
        departmentHints: deptHints,
      });
  // Reader locale ('zh-CN' for the manually-routed China group, else 'en').
  // Drives claim/Brain rendering language and the answer-language instruction.
  const locale = coerceLocale(me.locale);
  const evidenceBudget = z.object({
    maxCharacters: z.coerce.number().int().min(2000).max(60000).default(18000),
    maxAdditionalDomainSearches: z.coerce.number().int().min(0).max(6).default(2),
  }).parse({
    maxCharacters: process.env.ORACLE_CHAT_EVIDENCE_MAX_CHARACTERS,
    maxAdditionalDomainSearches: process.env.ORACLE_CHAT_ADDITIONAL_DOMAIN_SEARCHES,
  });
  const answerContext = await retrieveBusinessAnswerContext({
    plan: retrievalPlan,
    search: (plan) => searchWithRetrievalPlan(db, plan, locale),
    getRelationships: (claimIds) => getApprovedMacroRelationships({
          db,
          claimIds,
          limit: 8,
        }),
    getEligibleSupports: (claimIds) => getEligibleRelationshipClaims(db, retrievalPlan, claimIds, locale),
    ...evidenceBudget,
  });
  if (answerContext.truncated || answerContext.emptySearches.length || answerContext.unexpandedDomains.length || answerContext.ineligibleRelationshipCount) {
    console.warn('[chat] bounded business evidence coverage', {
      includedClaims: answerContext.includedClaimIds.length,
      omittedClaims: answerContext.omittedClaimIds.length,
      searchCount: answerContext.searchCount,
      emptySearches: answerContext.emptySearches,
      unexpandedDomains: answerContext.unexpandedDomains,
      ineligibleRelationshipCount: answerContext.ineligibleRelationshipCount,
    });
  }

  // Load attachment presence before choosing the answer path. Any attachment in
  // the recent conversation keeps the full attachment-aware interview route;
  // approved claims alone cannot represent a new or follow-up document question.
  const recentIds = recent.map((message) => message.id);
  const attachmentRows = recentIds.length > 0
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
  const relevantAttachmentMessageIds = selectRelevantAttachmentMessageIds(
    recent,
    new Set(attachmentMap.keys()),
    latestUserMessage.id,
  );
  const relevantAttachmentMap = new Map(
    [...attachmentMap].filter(([messageId]) => relevantAttachmentMessageIds.has(messageId)),
  );
  const hasRelevantAttachments = relevantAttachmentMap.size > 0;

  // ── 4. Resolve curated interview route ───────────────────────────────
  let routeCandidates = await resolveInterviewCandidates(db);
  const route = routeCandidates[0]!.route;
  const businessAnswerIntent = hasBusinessAnswerIntent(latestUserMessage.content);
  // A file can cause the generator to answer even when its caption is only a
  // greeting, so attachment turns always require independent review.
  const answerIntegrityRequired = businessAnswerIntent || hasRelevantAttachments;
  const requiresReconciliation = !hasRelevantAttachments
    && shouldReconcileBusinessAnswer(latestUserMessage.content, answerContext.evidenceClaims.length);
  if (businessAnswerIntent && !hasRelevantAttachments && answerContext.evidenceClaims.length === 0) {
    return NextResponse.json({ error: 'no_approved_evidence' }, { status: 422 });
  }
  // Approved relationship summaries currently have no translation table.
  // Chinese answers retain their localized supporting claims and may form a
  // reviewed interpretation, but never receive an English relationship label.
  const reconciliationRelationships = locale === 'zh-CN'
    ? []
    : answerContext.evidenceRelationships;
  const reconciliationRoutes = answerIntegrityRequired ? await resolveRouteCandidates(db, 'model_merge') : null;
  const macroReviewRoutes = answerIntegrityRequired ? await resolveRouteCandidates(db, 'macro') : null;
  for (const skipped of reconciliationRoutes?.skipped ?? []) {
    console.error(`[chat] skipped configured reconciliation candidate ${skipped.modelIdOrRouteId}: ${skipped.reason}`);
  }
  for (const skipped of macroReviewRoutes?.skipped ?? []) {
    console.error(`[chat] skipped configured answer-review candidate ${skipped.modelIdOrRouteId}: ${skipped.reason}`);
  }
  const answerReviewerCandidates = [...(reconciliationRoutes?.candidates ?? []), ...(macroReviewRoutes?.candidates ?? [])]
    .filter((candidate, index, all) => all.findIndex((item) => item.route.routeId === candidate.route.routeId) === index);
  if ([...answerReviewerCandidates, ...routeCandidates].some((candidate) => !candidate.route.provider)) {
    return NextResponse.json({ error: 'answer_reconciliation_route_unavailable' }, { status: 503 });
  }
  const independentProviderCount = new Set(answerReviewerCandidates.map((candidate) => providerIndependenceFamily(candidate.route.provider))).size;
  const everyInterviewRouteHasIndependentReviewer = routeCandidates.every((interviewCandidate) =>
    answerReviewerCandidates.some((reviewCandidate) =>
      providerIndependenceFamily(reviewCandidate.route.provider) !== providerIndependenceFamily(interviewCandidate.route.provider)));
  if ((requiresReconciliation && (!reconciliationRoutes?.candidates.length || independentProviderCount < 2))
    || (answerIntegrityRequired && hasRelevantAttachments && !everyInterviewRouteHasIndependentReviewer)) {
    return NextResponse.json({ error: 'answer_reconciliation_route_unavailable' }, { status: 503 });
  }
  const visionCapable = isAttachmentCapableRoute(route);

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
  contextLines.push(answerContext.text);
  contextLines.push(`Evidence search coverage: ${JSON.stringify({
    searchCount: answerContext.searchCount,
    emptySearches: answerContext.emptySearches,
    unexpandedDomains: answerContext.unexpandedDomains,
    ineligibleRelationshipCount: answerContext.ineligibleRelationshipCount,
  })}. This is bounded retrieval, not proof of complete business coverage.`);
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
      reasonIncluded: `gaps=${openGaps.length}, claims=${answerContext.includedClaimIds.length}, relationships=${answerContext.includedRelationshipIds.length}, omitted=${answerContext.omittedClaimIds.length}, searches=${answerContext.searchCount}`,
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
      includedClaimIds: answerContext.includedClaimIds,
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
  const serviceSupabase = createServiceRoleClient();

  // ── 7a. Vertex GCS file-backed cache for a large attached PDF ────────
  // When the interview route runs on Vertex AND a GCS cache bucket is
  // configured, cache the most-recent large PDF in the thread as a Gemini
  // cachedContent prefix (gs:// fileData) instead of re-sending it as base64
  // on every turn. The conversation turns ride on top of the cache as live
  // text contents (the adapter preserves multi-turn history on the file-cache
  // path). The canonical conversation still keeps every attachment. The Vertex
  // adapter removes only the cached PDF from its own live request. This is
  // required so a later provider can receive the complete message on fallback.
  //
  // Gated on the bucket env. Without it, every attachment stays inline.
  const fileCacheEnabled =
    route.provider === 'vertex' && !!process.env.GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET;
  let vertexFileCacheSource:
    | { localPath: string; mimeType: string; fileName: string; sourceHash: string }
    | undefined;
  let cachedTempPath: string | undefined;
  let cachedPdfBytes = 0;
  if (fileCacheEnabled) {
    const candidate = pickCacheablePdf(recent, relevantAttachmentMap);
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
            cachedPdfBytes = buf.length;
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

  // Image parts use the PROVIDER-NEUTRAL shape `{ type:'image', mimeType, data }`
  // — the ONLY shape every hardened adapter translates (Gemini→inlineData,
  // OpenAI/Qwen→image_url, Anthropic→base64 block). The old `{ image: dataUrl }`
  // shape was unrecognized: Gemini stringified it to garbage and OpenAI/Anthropic
  // got an invalid part, so chat image attachments were silently broken.
  type ChatContentPart = { type: 'text'; text: string } | ChatAttachmentPart;
  type ConversationMessage = {
    role: 'user' | 'assistant';
    content: string | ChatContentPart[];
  };

  let totalBinaryAttachmentBytes = 0;
  let hasPdfAttachments = false;
  let requireVertexFileCache = false;
  let conversationMessages: ConversationMessage[];
  try {
    conversationMessages = await Promise.all(
      recent
        .filter((m) => m.role !== 'system')
        .map(async (m) => {
          const role = m.role === 'assistant' ? ('assistant' as const) : ('user' as const);
          const textContent =
            m.role === 'user' && m.authorName ? `[${m.authorName}] ${m.content}` : m.content;
          const atts = relevantAttachmentMap.get(m.id) ?? [];
          if (atts.length === 0) return { role, content: textContent };

          const parts: ChatContentPart[] = [{ type: 'text', text: textContent }];
          for (const att of atts) {
            const { data: blob, error } = await serviceSupabase.storage
              .from(att.storageBucket)
              .download(att.storagePath);
            if (error || !blob) {
              throw new ChatAttachmentSafetyError(
                'attachment_download_failed',
                `The attached file "${att.fileName}" could not be loaded. No answer was generated because it might have omitted that file.`,
              );
            }
            const buffer = Buffer.from(await blob.arrayBuffer());
            const part = toCanonicalAttachmentPart({
              fileType: att.fileType,
              fileName: att.fileName,
              buffer,
            });
            if (part.type === 'image' || part.type === 'file') {
              totalBinaryAttachmentBytes += buffer.length;
            }
            if (part.type === 'file' && part.mimeType === 'application/pdf') {
              hasPdfAttachments = true;
            }
            parts.push(part);
          }
          return { role, content: parts };
        }),
    );
  } catch (error) {
    if (cachedTempPath) await unlink(cachedTempPath).catch(() => undefined);
    const detail =
      error instanceof ChatAttachmentSafetyError
        ? error.message
        : 'An attachment could not be prepared safely. No answer was generated.';
    console.error('[chat] attachment assembly failed', error);
    return NextResponse.json({ error: 'attachment_delivery_failed', detail }, { status: 422 });
  }

  try {
    const selection = selectAttachmentSafeCandidates({
      candidates: routeCandidates,
      hasBinaryAttachments: totalBinaryAttachmentBytes > 0,
      hasPdfAttachments,
      totalBinaryBytes: totalBinaryAttachmentBytes,
      cachedPdfBytes: vertexFileCacheSource ? cachedPdfBytes : undefined,
    });
    routeCandidates = selection.candidates;
    requireVertexFileCache = selection.constrainedToVertex;
    if (selection.constrainedToVertex) {
      console.warn(
        '[chat] attachment fallback pool constrained to Vertex because the complete inline payload is too large for safe cross-provider fallback',
      );
    }
  } catch (error) {
    if (cachedTempPath) await unlink(cachedTempPath).catch(() => undefined);
    const detail =
      error instanceof ChatAttachmentSafetyError
        ? error.message
        : 'The selected models cannot receive every attachment safely.';
    console.error('[chat] attachment route safety check failed', error);
    return NextResponse.json({ error: 'attachment_delivery_failed', detail }, { status: 422 });
  }

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
  let runMetadata: OracleRunRouteMetadata | null = null;
  let finalPlan = plan;
  type AuxiliaryRun = OracleRunRouteMetadata & { usage: OracleUsage };
  const auxiliaryRuns: Array<{ stage: string; inputHash: string; result: AuxiliaryRun; plan: OraclePromptPlan; slot: 'model_merge' | 'macro'; success: boolean; error?: string }> = [];
  let reconciliationRequiredClaimCount = 0;
  let activeSlot: 'interview' | 'model_merge' | 'macro' = 'interview';
  let auxiliaryFailureRecorded = false;
  let failureStatus = 502;
  let failureCode = 'model_failed';

  try {
    if (answerIntegrityRequired) assertEvidenceLocale(answerContext.evidenceClaims, locale);
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
    const generate = (messages: ConversationMessage[]) => getOracleClient().runText({
      taskType: 'interview_chat',
      routeId: route.routeId,
      promptVersion: ORACLE_SYSTEM_PROMPT_VERSION,
      blocks,
      observability: {
        includedMessageIds: recent.map((m) => m.id),
        includedGapIds: openGaps.map((g) => g.id),
        includedClaimIds: answerContext.includedClaimIds,
      },
      providerOptions: {
        messages,
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
          requireVertexFileCache,
        },
      },
      routeCandidates,
    });
    let finalResult: AuxiliaryRun;
    if (requiresReconciliation && reconciliationRoutes) {
      activeSlot = 'model_merge';
      const plannedReconciliationRoute = reconciliationRoutes.candidates[0]!.route;
      actualRouteId = plannedReconciliationRoute.routeId;
      actualProvider = plannedReconciliationRoute.provider;
      actualModelId = plannedReconciliationRoute.modelId;
      const baseInput = buildReconciliationInput({
        question: queryForClaims,
        claims: answerContext.evidenceClaims,
        relationships: reconciliationRelationships,
        locale,
        evidenceTruncated: answerContext.truncated,
      });
      const runReconciliation = async (repairFeedback = '') => {
        activeSlot = 'model_merge';
        const content = repairFeedback ? `${baseInput}\n\nPrevious reconciliation failed independent review. Correct these violations:\n${repairFeedback}` : baseInput;
        const reconciliationBlocks = [
          makeBlock({ id: 'business-answer-reconciliation-system', label: 'Business answer reconciliation system', kind: 'stable_system', content: BUSINESS_ANSWER_RECONCILIATION_SYSTEM, reasonIncluded: BUSINESS_ANSWER_RECONCILIATION_VERSION }),
          makeBlock({ id: 'business-answer-reconciliation-input', label: 'Question and approved evidence', kind: 'dynamic_input', content, reasonIncluded: `${answerContext.evidenceClaims.length} supplied claims` }),
        ];
        const reconciliationArgs = {
          taskType: 'interview_chat' as const, routeId: reconciliationRoutes.candidates[0]!.route.routeId,
          promptVersion: BUSINESS_ANSWER_RECONCILIATION_VERSION, schema: BusinessAnswerReconciliationSchema,
          blocks: reconciliationBlocks,
          observability: {
            includedClaimIds: answerContext.includedClaimIds,
            includedMessageIds: [],
            includedGapIds: [],
            selectedDomains: scopeTag(retrievalPlan.topDomainHints, retrievalPlan.searchScope),
          },
          routeCandidates: reconciliationRoutes.candidates,
        };
        const reconciliationPlan = getOracleClient().compile(reconciliationArgs);
        // If dispatch or validation fails, the primary failure row must still
        // point at the exact reconciliation pack that was attempted.
        finalPlan = reconciliationPlan;
        const result = await getOracleClient().runObject(reconciliationArgs);
        runMetadata = result;
        inputTokens = result.usage.inputTokens;
        outputTokens = result.usage.outputTokens;
        cachedInputTokens = result.usage.cachedInputTokens;
        usageRaw = result.usage.rawUsageJson;
        providerRequestId = result.usage.providerRequestId;
        actualRouteId = result.routeId ?? plannedReconciliationRoute.routeId;
        actualProvider = (result.provider as typeof route.provider | undefined) ?? plannedReconciliationRoute.provider;
        actualModelId = result.modelId ?? plannedReconciliationRoute.modelId;
        if (!result.validation.ok) throw new Error(`Answer reconciliation schema failed: ${result.validation.error.message}`);
        const coverage = validateReconciliation(
          result.validation.value,
          answerContext.includedClaimIds,
          reconciliationRelationships,
          locale,
        );
        reconciliationRequiredClaimCount = coverage.mustAddressClaimIds.length;
        const text = renderReconciledBusinessAnswer({
          reconciliation: result.validation.value,
          claims: answerContext.evidenceClaims,
          relationships: reconciliationRelationships,
          locale,
          evidenceTruncated: answerContext.truncated,
        });
        assertReconciledBusinessAnswer({ text, includedClaimIds: answerContext.includedClaimIds, ...coverage });
        return { result, reconciliation: result.validation.value, text, inputHash: createHash('sha256').update(content).digest('hex'), plan: reconciliationPlan };
      };
      const reviewAnswer = async (answer: string, reconciliation: BusinessAnswerReconciliation, reconciliationProvider: string): Promise<BusinessAnswerSemanticReview> => {
        const reviewerCandidates = answerReviewerCandidates.filter((candidate) =>
          providerIndependenceFamily(candidate.route.provider) !== providerIndependenceFamily(reconciliationProvider));
        if (!reviewerCandidates.length) throw new AnswerRouteUnavailableError('Independent answer reviewer route is unavailable.');
        activeSlot = macroReviewRoutes?.candidates.some((candidate) => candidate.route.routeId === reviewerCandidates[0]!.route.routeId)
          ? 'macro'
          : 'model_merge';
        const reviewInput = buildSemanticReviewInput({
          question: queryForClaims,
          claims: answerContext.evidenceClaims,
          relationships: reconciliationRelationships,
          reconciliation,
          answer,
        });
        const reviewArgs = {
          taskType: 'validation_repair' as const, routeId: reviewerCandidates[0]!.route.routeId,
          promptVersion: BUSINESS_ANSWER_RECONCILIATION_VERSION, schema: BusinessAnswerSemanticReviewSchema,
          blocks: [
            makeBlock({ id: 'business-answer-review-system', label: 'Business answer semantic review', kind: 'stable_system', content: BUSINESS_ANSWER_REVIEW_SYSTEM, reasonIncluded: BUSINESS_ANSWER_RECONCILIATION_VERSION }),
            makeBlock({ id: 'business-answer-review-input', label: 'Question, evidence, ledger, and proposed answer', kind: 'dynamic_input', content: reviewInput, reasonIncluded: 'different-provider semantic acceptance gate' }),
          ],
          observability: { includedClaimIds: answerContext.includedClaimIds, includedMessageIds: [] }, routeCandidates: reviewerCandidates,
        };
        const reviewPlan = getOracleClient().compile(reviewArgs);
        const reviewInputHash = createHash('sha256').update(reviewInput).digest('hex');
        const runSemanticReview = () => getOracleClient().runObject(reviewArgs);
        let result: Awaited<ReturnType<typeof runSemanticReview>>;
        try {
          result = await runSemanticReview();
        } catch (error) {
          await persistFailedAuxiliaryChatRun({
            db, stage: 'semantic_review', inputHash: reviewInputHash, plan: reviewPlan,
            slot: activeSlot === 'macro' ? 'macro' : 'model_merge',
            plannedRoute: reviewerCandidates[0]!.route, error,
          });
          auxiliaryFailureRecorded = true;
          throw error;
        }
        try {
          if (!result.validation.ok) throw new Error(`Answer semantic review schema failed: ${result.validation.error.message}`);
          validateSemanticReview(result.validation.value, answerContext.includedClaimIds);
        } catch (error) {
          auxiliaryRuns.push({
            stage: 'semantic_review', inputHash: reviewInputHash, result, plan: reviewPlan,
            slot: activeSlot === 'macro' ? 'macro' : 'model_merge', success: false,
            error: error instanceof Error ? error.message : String(error),
          });
          auxiliaryFailureRecorded = true;
          throw error;
        }
        auxiliaryRuns.push({
          stage: 'semantic_review',
          inputHash: reviewInputHash,
          result,
          plan: reviewPlan,
          slot: activeSlot === 'macro' ? 'macro' : 'model_merge',
          success: result.validation.value.pass,
          error: result.validation.value.pass ? undefined : result.validation.value.violations.map((violation) => violation.type).join(', '),
        });
        return result.validation.value;
      };
      const adoptReconciliationRun = (current: Awaited<ReturnType<typeof runReconciliation>>) => {
        activeSlot = 'model_merge';
        finalPlan = current.plan;
        runMetadata = current.result;
        inputTokens = current.result.usage.inputTokens;
        outputTokens = current.result.usage.outputTokens;
        cachedInputTokens = current.result.usage.cachedInputTokens;
        usageRaw = current.result.usage.rawUsageJson;
        providerRequestId = current.result.usage.providerRequestId;
        actualRouteId = current.result.routeId ?? route.routeId;
        actualProvider = (current.result.provider as typeof route.provider | undefined) ?? route.provider;
        actualModelId = current.result.modelId ?? route.modelId;
      };
      let reconciled = await runReconciliation();
      adoptReconciliationRun(reconciled);
      let review = await reviewAnswer(
        reconciled.text,
        reconciled.reconciliation,
        resolveRunProvider(reconciled.result, reconciliationRoutes.candidates),
      );
      if (!review.pass) {
        auxiliaryRuns.push({
          stage: 'reconciliation_rejected', inputHash: reconciled.inputHash, result: reconciled.result,
          plan: reconciled.plan, slot: 'model_merge', success: false,
          error: review.violations.map((violation) => violation.type).join(', '),
        });
        reconciled = await runReconciliation(JSON.stringify(review.violations));
        adoptReconciliationRun(reconciled);
        review = await reviewAnswer(
          reconciled.text,
          reconciled.reconciliation,
          resolveRunProvider(reconciled.result, reconciliationRoutes.candidates),
        );
        if (!review.pass) {
          auxiliaryFailureRecorded = true;
          throw new Error(`Answer failed independent semantic review after one repair: ${review.violations.map((violation) => violation.type).join(', ')}`);
        }
      }
      oracleText = reconciled.text;
      finalResult = reconciled.result;
    } else {
      activeSlot = 'interview';
      const result = await generate(messagesWithContext);
      oracleText = result.text;
      finalResult = result;
      runMetadata = result;
      inputTokens = result.usage.inputTokens;
      outputTokens = result.usage.outputTokens;
      cachedInputTokens = result.usage.cachedInputTokens;
      usageRaw = result.usage.rawUsageJson;
      providerRequestId = result.usage.providerRequestId;
      actualRouteId = result.routeId ?? route.routeId;
      actualProvider = (result.provider as typeof route.provider | undefined) ?? route.provider;
      actualModelId = result.modelId ?? route.modelId;
      if (answerIntegrityRequired && hasRelevantAttachments) {
        const generatorProvider = resolveRunProvider(result, routeCandidates);
        const differentFamily = answerReviewerCandidates.filter((candidate) =>
          providerIndependenceFamily(candidate.route.provider) !== providerIndependenceFamily(generatorProvider));
        const attachmentCapable = totalBinaryAttachmentBytes > 0
          ? differentFamily.filter((candidate) => isAttachmentCapableRoute(candidate.route))
          : differentFamily;
        const reviewerSelection = selectAttachmentSafeCandidates({
          candidates: attachmentCapable,
          hasBinaryAttachments: totalBinaryAttachmentBytes > 0,
          hasPdfAttachments,
          totalBinaryBytes: totalBinaryAttachmentBytes,
          cachedPdfBytes: vertexFileCacheSource ? cachedPdfBytes : undefined,
        });
        if (!reviewerSelection.candidates.length) {
          throw new AnswerRouteUnavailableError('Independent attachment-answer reviewer route is unavailable.');
        }
        activeSlot = macroReviewRoutes?.candidates.some((candidate) =>
          candidate.route.routeId === reviewerSelection.candidates[0]!.route.routeId)
          ? 'macro'
          : 'model_merge';
        const reviewInput = buildAttachmentReviewInput({
          question: queryForClaims,
          claims: answerContext.evidenceClaims,
          answer: result.text,
        });
        const reviewMessages: ConversationMessage[] = [
          ...conversationMessages.map((message) => ({ ...message })),
          { role: 'user', content: `Review the proposed answer. Return only the required structured verdict.\n${reviewInput}` },
        ];
        const reviewArgs = {
          taskType: 'validation_repair' as const,
          routeId: reviewerSelection.candidates[0]!.route.routeId,
          promptVersion: BUSINESS_ANSWER_RECONCILIATION_VERSION,
          schema: BusinessAnswerSemanticReviewSchema,
          blocks: [
            makeBlock({ id: 'attachment-answer-review-system', label: 'Attachment answer semantic review', kind: 'stable_system', content: ATTACHMENT_ANSWER_REVIEW_SYSTEM, reasonIncluded: BUSINESS_ANSWER_RECONCILIATION_VERSION }),
            makeBlock({ id: 'attachment-answer-review-input', label: 'Question, approved evidence, and proposed answer', kind: 'dynamic_input', content: reviewInput, reasonIncluded: 'different-family attachment semantic acceptance gate' }),
          ],
          observability: { includedClaimIds: answerContext.includedClaimIds, includedMessageIds: recent.map((message) => message.id) },
          providerOptions: { messages: reviewMessages, temperature: 0 },
          routeCandidates: reviewerSelection.candidates,
        };
        const reviewPlan = getOracleClient().compile(reviewArgs);
        const reviewInputHash = createHash('sha256').update(reviewInput).digest('hex');
        const runAttachmentReview = () => getOracleClient().runObject(reviewArgs);
        let attachmentReview: Awaited<ReturnType<typeof runAttachmentReview>>;
        try {
          attachmentReview = await runAttachmentReview();
        } catch (error) {
          await persistFailedAuxiliaryChatRun({
            db, stage: 'attachment_semantic_review', inputHash: reviewInputHash, plan: reviewPlan,
            slot: activeSlot === 'macro' ? 'macro' : 'model_merge',
            plannedRoute: reviewerSelection.candidates[0]!.route, error,
          });
          auxiliaryFailureRecorded = true;
          throw error;
        }
        try {
          if (!attachmentReview.validation.ok) throw new Error(`Attachment answer semantic review schema failed: ${attachmentReview.validation.error.message}`);
          validateSemanticReview(attachmentReview.validation.value, answerContext.includedClaimIds);
        } catch (error) {
          auxiliaryRuns.push({
            stage: 'attachment_semantic_review', inputHash: reviewInputHash,
            result: attachmentReview, plan: reviewPlan,
            slot: activeSlot === 'macro' ? 'macro' : 'model_merge', success: false,
            error: error instanceof Error ? error.message : String(error),
          });
          auxiliaryFailureRecorded = true;
          throw error;
        }
        auxiliaryRuns.push({
          stage: 'attachment_semantic_review',
          inputHash: reviewInputHash,
          result: attachmentReview,
          plan: reviewPlan,
          slot: activeSlot === 'macro' ? 'macro' : 'model_merge',
          success: attachmentReview.validation.value.pass,
          error: attachmentReview.validation.value.pass
            ? undefined
            : attachmentReview.validation.value.violations.map((violation) => violation.type).join(', '),
        });
        if (!attachmentReview.validation.value.pass) {
          auxiliaryFailureRecorded = true;
          throw new Error(`Attachment answer failed independent semantic review: ${attachmentReview.validation.value.violations.map((violation) => violation.type).join(', ')}`);
        }
      }
    }
    runMetadata = finalResult;
    inputTokens = finalResult.usage.inputTokens;
    outputTokens = finalResult.usage.outputTokens;
    cachedInputTokens = finalResult.usage.cachedInputTokens;
    usageRaw = finalResult.usage.rawUsageJson;
    providerRequestId = finalResult.usage.providerRequestId;
    actualRouteId = finalResult.routeId ?? route.routeId;
    actualProvider = (finalResult.provider as typeof route.provider | undefined) ?? route.provider;
    actualModelId = finalResult.modelId ?? route.modelId;
    assertKnownBusinessCitations(oracleText, answerContext.includedClaimIds, {
      requireAtLeastOne: !hasRelevantAttachments
        && businessAnswerIntent
        && reconciliationRequiredClaimCount > 0,
    });
    success = true;
  } catch (err) {
    modelError = err instanceof Error ? err.message : String(err);
    if (err instanceof AnswerRouteUnavailableError) {
      failureStatus = 503;
      failureCode = 'answer_reconciliation_route_unavailable';
    }
    console.error('[chat] model error', err);
    if (!auxiliaryFailureRecorded) {
      await logAllCandidatesFailedAttempts({
        db,
        error: err,
        taskType: 'interview_chat',
        slot: activeSlot,
        contextPackId: contextPack.id,
      }).catch((logErr) => console.error('[chat] failed to record model attempts', logErr));
    }
  } finally {
    // The GCS object is reaped by the adapter's cache-TTL sweeper; we only own
    // the local temp file. Best-effort cleanup.
    if (cachedTempPath) {
      await unlink(cachedTempPath).catch(() => undefined);
    }
  }

  // ── 9. Log model_runs + model_run_usage_details + back-link pack ───
  if (finalPlan !== plan) {
    await db.update(oracleContextPacks).set(buildContextPackInsert(finalPlan)).where(eq(oracleContextPacks.id, contextPack.id));
  }
  for (const auxiliary of auxiliaryRuns) {
    await persistAuxiliaryChatRun({ db, stage: auxiliary.stage, inputHash: auxiliary.inputHash, result: auxiliary.result, plan: auxiliary.plan, slot: auxiliary.slot, success: auxiliary.success, error: auxiliary.error });
  }
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'interview_chat',
      model: actualModelId,
      provider: actualProvider,
      promptVersion: requiresReconciliation ? BUSINESS_ANSWER_RECONCILIATION_VERSION : ORACLE_SYSTEM_PROMPT_VERSION,
      inputHash: finalPlan.metadata.stablePrefixHash,
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
        slot: requiresReconciliation ? 'model_merge' : 'interview',
        contextPackId: contextPack.id,
        modelRunId: modelRun.id,
      });
    }
    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));
  }

  if (!success || !oracleText.trim()) {
    return NextResponse.json(
      { error: failureCode, detail: modelError ?? 'empty response' },
      { status: failureStatus },
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

class AnswerRouteUnavailableError extends Error {}

function resolveRunProvider(
  result: { provider?: string; routeId?: string },
  candidates: Array<{ route: { routeId: string; provider: string } }>,
): string {
  if (result.provider) return result.provider;
  const routedProvider = result.routeId
    ? candidates.find((candidate) => candidate.route.routeId === result.routeId)?.route.provider
    : undefined;
  if (!routedProvider) throw new AnswerRouteUnavailableError('Model run did not report a provider identity.');
  return routedProvider;
}
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
  const tempPath = join(
    tmpdir(),
    `oracle-chat-vertex-cache-${Date.now()}-${randomUUID()}-${safeName}`,
  );
  await writeFile(tempPath, buffer);
  return tempPath;
}

async function persistFailedAuxiliaryChatRun(args: {
  db: OracleDb;
  stage: string;
  inputHash: string;
  plan: OraclePromptPlan;
  slot: 'model_merge' | 'macro';
  plannedRoute: { routeId: string; provider: string; modelId: string };
  error: unknown;
}) {
  const message = args.error instanceof Error ? args.error.message : String(args.error);
  const [contextPack] = await args.db.insert(oracleContextPacks)
    .values(buildContextPackInsert(args.plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error(`Failed to persist ${args.stage} failure context pack.`);
  const [run] = await args.db.insert(modelRuns).values({
    taskType: args.plan.taskType,
    model: args.plannedRoute.modelId,
    provider: args.plannedRoute.provider,
    promptVersion: `${BUSINESS_ANSWER_RECONCILIATION_VERSION}:${args.stage}`,
    inputHash: args.inputHash,
    success: false,
    error: message,
  }).returning({ id: modelRuns.id });
  if (!run) throw new Error(`Failed to persist ${args.stage} failure model run.`);
  await logAllCandidatesFailedAttempts({
    db: args.db,
    error: args.error,
    taskType: args.plan.taskType,
    slot: args.slot,
    contextPackId: contextPack.id,
  });
  await args.db.update(oracleContextPacks)
    .set({ modelRunId: run.id })
    .where(eq(oracleContextPacks.id, contextPack.id));
}

async function persistAuxiliaryChatRun(args: {
  db: OracleDb;
  stage: string;
  inputHash: string;
  result: OracleRunRouteMetadata & { usage: OracleUsage };
  plan: OraclePromptPlan;
  slot: 'model_merge' | 'macro';
  success: boolean;
  error?: string;
}) {
  const resolvedRouteId = args.result.routeId ?? args.plan.routeId;
  if (!resolvedRouteId) throw new Error(`Cannot persist ${args.stage} without a resolved route.`);
  const [contextPack] = await args.db.insert(oracleContextPacks)
    .values(buildContextPackInsert(args.plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error(`Failed to persist ${args.stage} context pack.`);
  const [run] = await args.db.insert(modelRuns).values({
    taskType: args.plan.taskType,
    model: args.result.modelId ?? 'unknown',
    provider: args.result.provider ?? 'unknown',
    promptVersion: `${BUSINESS_ANSWER_RECONCILIATION_VERSION}:${args.stage}`,
    inputHash: args.inputHash,
    inputTokens: args.result.usage.inputTokens ?? null,
    outputTokens: args.result.usage.outputTokens ?? null,
    latencyMs: args.result.usage.latencyMs,
    success: args.success,
    error: args.error ?? null,
  }).returning({ id: modelRuns.id });
  if (!run) throw new Error(`Failed to persist ${args.stage} model run.`);
  await args.db.insert(modelRunUsageDetails).values({
    modelRunId: run.id,
    contextPackId: contextPack.id,
    routeId: resolvedRouteId,
    inputTokens: args.result.usage.inputTokens ?? null,
    cachedInputTokens: args.result.usage.cachedInputTokens ?? null,
    cacheWriteTokens: args.result.usage.cacheWriteTokens ?? null,
    outputTokens: args.result.usage.outputTokens ?? null,
    reasoningTokens: args.result.usage.reasoningTokens ?? null,
    providerRequestId: args.result.usage.providerRequestId ?? null,
    rawUsageJson: args.result.usage.rawUsageJson ?? null,
  });
  await logModelRunAttempts({
    db: args.db,
    metadata: args.result,
    taskType: args.plan.taskType,
    slot: args.slot,
    contextPackId: contextPack.id,
    modelRunId: run.id,
  });
  await args.db.update(oracleContextPacks)
    .set({ modelRunId: run.id })
    .where(eq(oracleContextPacks.id, contextPack.id));
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
