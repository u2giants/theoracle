// Claim extraction worker — spec Part 9.4, 9.5.
//
// Cron: every 4 hours.
// Picks up messages with extractionStatus='pending' AND role='user', groups them
// into conversation segments by channel + time window, calls the extraction model
// (generateObject), validates exact quotes, inserts claims / claim_domains /
// claim_evidence, suggests gaps, and marks messages complete/failed/skipped.
//
// Spec compliance notes:
//   - Every LLM call → model_runs row (spec Part 9).
//   - This task → job_runs row (spec Part 9).
//   - Exact-quote validation is mandatory (spec 9.4).
//   - Auto-approve vs pending_review triage per spec 9.4.
//   - Group chat semantics tracked per spec 9.5.

import { schedules } from '@trigger.dev/sdk/v3';
import { and, desc, eq, inArray, sql } from 'drizzle-orm';
import { generateObject } from 'ai';
import { getDirectDb } from '@oracle/db/client';
import {
  claims,
  claimDomains,
  claimEvidence,
  gaps,
  messages,
  settings,
  modelRuns,
  jobRuns,
  employees,
} from '@oracle/db/schema';
import {
  getOpenRouter,
  embedText,
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  ExtractionOutputSchema,
  formatConversationSegment,
  type FormattedMessage,
} from '@oracle/ai';
import type { KnowledgeDomain } from '@oracle/shared';

const BATCH_SIZE = 100; // max messages per cron run
const SEGMENT_GAP_MS = 60 * 60 * 1000; // 60-minute gaps → new conversation segment
const FALLBACK_MODEL = 'google/gemini-2.5-flash';

// Claim types that are low-risk for auto-approval.
const LOW_RISK_CLAIM_TYPES = new Set([
  'process_rule',
  'exception_rule',
  'dependency',
  'system_limitation',
]);

export const claimExtractionTask = schedules.task({
  id: 'claim-extraction',
  // Spec 9.4: "Cron schedule, for example every 4 hours or nightly".
  cron: '0 */4 * * *',
  maxDuration: 60 * 5, // 5-minute hard cap per Trigger.dev run
  run: async (_payload, { ctx }) => {
    const db = getDirectDb();
    const startedAt = new Date();

    // -----------------------------------------------------------------------
    // 1. Insert job_runs row (spec requirement — every job must have one).
    // -----------------------------------------------------------------------
    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'claim-extraction',
        status: 'running',
        startedAt,
        inputJson: { batchSize: BATCH_SIZE },
      })
      .returning({ id: jobRuns.id });

    if (!jobRun) throw new Error('[claim-extraction] failed to insert job_runs row');

    let totalClaimsInserted = 0;
    let totalMessagesProcessed = 0;
    let totalErrors = 0;

    try {
      // -----------------------------------------------------------------------
      // 2. Read extraction model from settings.
      // -----------------------------------------------------------------------
      const modelSetting = await db
        .select({ value: settings.value })
        .from(settings)
        .where(eq(settings.key, 'default_extraction_model'))
        .limit(1);

      const modelName =
        (typeof modelSetting[0]?.value === 'string' ? modelSetting[0].value : null) ??
        FALLBACK_MODEL;

      // -----------------------------------------------------------------------
      // 3. Fetch pending user messages, with author names.
      // -----------------------------------------------------------------------
      const pendingMessages = await db
        .select({
          id: messages.id,
          channelId: messages.channelId,
          employeeId: messages.employeeId,
          role: messages.role,
          content: messages.content,
          createdAt: messages.createdAt,
          authorName: employees.name,
        })
        .from(messages)
        .leftJoin(employees, eq(employees.id, messages.employeeId))
        .where(
          and(
            eq(messages.extractionStatus, 'pending'),
            eq(messages.role, 'user'),
          ),
        )
        .orderBy(messages.createdAt)
        .limit(BATCH_SIZE);

      if (pendingMessages.length === 0) {
        await db
          .update(jobRuns)
          .set({
            status: 'complete',
            finishedAt: new Date(),
            outputJson: { claimsInserted: 0, messagesProcessed: 0, errors: 0 },
          })
          .where(eq(jobRuns.id, jobRun.id));
        return { ok: true, claimsInserted: 0, messagesProcessed: 0, errors: 0 };
      }

      // -----------------------------------------------------------------------
      // 4. Mark all fetched messages as 'processing' (idempotency guard).
      // -----------------------------------------------------------------------
      const messageIds = pendingMessages.map((m) => m.id);
      await db
        .update(messages)
        .set({ extractionStatus: 'processing' })
        .where(inArray(messages.id, messageIds));

      // -----------------------------------------------------------------------
      // 5. Group by channel, then by conversation segment (60-min windows).
      // -----------------------------------------------------------------------
      const byChannel = new Map<string, typeof pendingMessages>();
      for (const m of pendingMessages) {
        const list = byChannel.get(m.channelId) ?? [];
        list.push(m);
        byChannel.set(m.channelId, list);
      }

      for (const [_channelId, channelMessages] of byChannel) {
        // Sort ascending so segments are chronological.
        channelMessages.sort(
          (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
        );

        // Split into time-bounded segments.
        const segments: FormattedMessage[][] = [];
        let current: FormattedMessage[] = [];

        for (const m of channelMessages) {
          if (current.length > 0) {
            const last = current[current.length - 1]!;
            const gap = new Date(m.createdAt).getTime() - new Date(last.createdAt).getTime();
            if (gap > SEGMENT_GAP_MS) {
              segments.push(current);
              current = [];
            }
          }
          current.push({
            id: m.id,
            role: m.role as 'user' | 'assistant' | 'system',
            content: m.content,
            authorName: m.authorName ?? null,
            createdAt: new Date(m.createdAt),
          });
        }
        if (current.length > 0) segments.push(current);

        // -------------------------------------------------------------------
        // 6. Extract claims from each segment.
        // -------------------------------------------------------------------
        for (const segment of segments) {
          const segmentIds = segment.map((m) => m.id);
          const userMessagesInSegment = segment.filter((m) => m.role === 'user');

          if (userMessagesInSegment.length === 0) {
            await db
              .update(messages)
              .set({ extractionStatus: 'skipped', extractedAt: new Date() })
              .where(inArray(messages.id, segmentIds));
            continue;
          }

          const formattedSegment = formatConversationSegment(segment);
          const callStartMs = Date.now();

          try {
            const openrouter = getOpenRouter();
            const model = openrouter(modelName);

            const { object, usage } = await generateObject({
              model,
              schema: ExtractionOutputSchema,
              system: EXTRACTION_SYSTEM_PROMPT,
              messages: [{ role: 'user', content: formattedSegment }],
              temperature: 0.1,
            });

            const latencyMs = Date.now() - callStartMs;

            // Log model_runs row (spec requirement).
            const [modelRun] = await db
              .insert(modelRuns)
              .values({
                taskType: 'claim-extraction',
                model: modelName,
                provider: 'openrouter',
                promptVersion: EXTRACTION_PROMPT_VERSION,
                inputTokens: usage?.inputTokens ?? null,
                outputTokens: usage?.outputTokens ?? null,
                latencyMs,
                success: true,
              })
              .returning({ id: modelRuns.id });

            // -----------------------------------------------------------------
            // 7. Process extracted claims.
            // -----------------------------------------------------------------
            for (const extracted of object.claims) {
              // Exact-quote validation (spec 9.4, mandatory).
              const sourceMsg = segment.find(
                (m) => m.id === extracted.evidence.sourceMessageId,
              );
              if (!sourceMsg) {
                console.warn(
                  `[claim-extraction] sourceMessageId ${extracted.evidence.sourceMessageId} not in segment — skipping claim`,
                );
                continue;
              }
              if (!sourceMsg.content.includes(extracted.evidence.exactQuote)) {
                console.warn(
                  `[claim-extraction] exactQuote not found verbatim in message ${sourceMsg.id} — skipping claim`,
                );
                continue;
              }

              // Triage: auto-approve vs pending_review (spec 9.4).
              const autoApprove =
                !extracted.requiresReview &&
                extracted.impactScore <= 6 &&
                LOW_RISK_CLAIM_TYPES.has(extracted.claimType);

              const claimStatus: 'approved' | 'pending_review' = autoApprove
                ? 'approved'
                : 'pending_review';

              // Embed the claim summary (zero vector if OPENAI_API_KEY is absent).
              let embedding: number[] | null = null;
              try {
                const { vector } = await embedText(extracted.summary);
                embedding = vector;
              } catch (embedErr) {
                console.warn('[claim-extraction] embedding failed, storing without vector', embedErr);
              }

              // Insert claim.
              const [claim] = await db
                .insert(claims)
                .values({
                  claimType: extracted.claimType,
                  summary: extracted.summary,
                  impactScore: extracted.impactScore,
                  confidenceScore: extracted.confidenceScore,
                  status: claimStatus,
                  embedding: embedding ?? undefined,
                })
                .returning({ id: claims.id });

              if (!claim) {
                console.error('[claim-extraction] claim insert returned no row — skipping');
                continue;
              }

              totalClaimsInserted++;

              // Insert claim_domains.
              for (const domain of extracted.domains) {
                await db
                  .insert(claimDomains)
                  .values({ claimId: claim.id, domain: domain as KnowledgeDomain })
                  .onConflictDoNothing();
              }

              // Locate the char offsets for evidence.
              const charStart = sourceMsg.content.indexOf(extracted.evidence.exactQuote);
              const charEnd =
                charStart >= 0
                  ? charStart + extracted.evidence.exactQuote.length
                  : undefined;

              // Locate employee ID for asserted_by.
              const sourcePending = pendingMessages.find(
                (m) => m.id === extracted.evidence.sourceMessageId,
              );

              // Insert claim_evidence.
              await db.insert(claimEvidence).values({
                claimId: claim.id,
                sourceType: 'message',
                sourceMessageId: extracted.evidence.sourceMessageId,
                assertedByEmployeeId: sourcePending?.employeeId ?? null,
                exactQuote: extracted.evidence.exactQuote,
                charStart: charStart >= 0 ? charStart : null,
                charEnd: charEnd ?? null,
                confidence: extracted.evidence.confidence,
              });

              // Insert suggested gaps.
              for (const gap of extracted.suggestedGaps ?? []) {
                await db.insert(gaps).values({
                  gapType: 'extraction_gap',
                  relatedClaimIds: [claim.id],
                  questionToAsk: gap.questionToAsk,
                  whyItMatters: gap.whyItMatters,
                  priority: gap.priority,
                  status: 'open',
                  createdByModelRunId: modelRun?.id ?? null,
                });
              }
            } // end claim loop

            // Mark messages complete.
            await db
              .update(messages)
              .set({ extractionStatus: 'complete', extractedAt: new Date() })
              .where(inArray(messages.id, segmentIds));

            totalMessagesProcessed += segmentIds.length;
          } catch (segErr) {
            console.error('[claim-extraction] segment processing failed', segErr);
            totalErrors++;

            // Log failed model_runs row.
            await db.insert(modelRuns).values({
              taskType: 'claim-extraction',
              model: modelName,
              provider: 'openrouter',
              promptVersion: EXTRACTION_PROMPT_VERSION,
              latencyMs: Date.now() - callStartMs,
              success: false,
              error: segErr instanceof Error ? segErr.message : String(segErr),
            });

            // Mark messages failed.
            await db
              .update(messages)
              .set({
                extractionStatus: 'failed',
                extractionError: segErr instanceof Error ? segErr.message : String(segErr),
              })
              .where(inArray(messages.id, segmentIds));
          }
        } // end segment loop
      } // end channel loop

      // -----------------------------------------------------------------------
      // 8. Update job_runs row.
      // -----------------------------------------------------------------------
      await db
        .update(jobRuns)
        .set({
          status: 'complete',
          finishedAt: new Date(),
          outputJson: {
            claimsInserted: totalClaimsInserted,
            messagesProcessed: totalMessagesProcessed,
            errors: totalErrors,
          },
        })
        .where(eq(jobRuns.id, jobRun.id));

      return {
        ok: true,
        claimsInserted: totalClaimsInserted,
        messagesProcessed: totalMessagesProcessed,
        errors: totalErrors,
      };
    } catch (fatalErr) {
      // Unexpected top-level failure — update job_runs and re-throw so Trigger.dev retries.
      await db
        .update(jobRuns)
        .set({
          status: 'failed',
          finishedAt: new Date(),
          error: fatalErr instanceof Error ? fatalErr.message : String(fatalErr),
        })
        .where(eq(jobRuns.id, jobRun.id));
      throw fatalErr;
    }
  },
});
