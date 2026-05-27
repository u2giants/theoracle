// R6 — Claim extraction worker (refactored through OracleAIClient + staging).
//
// Spec compliance:
//   - docs/oracle/05-ai-retrofit-phase-packet.md Phase R6
//   - docs/oracle/03-candidate-before-claim-validation.md
//
// What changed vs the legacy worker:
//   - Model calls go through OracleAIClient (R2) via direct provider adapters
//     (Vertex / Anthropic / OpenAI raw SDKs — DECISIONS.md D6). The route ID
//     is the R1 curated `default_extraction_route` setting.
//   - Output flows into extraction_batches → extraction_candidates →
//     extraction_candidate_evidence first. NOTHING writes to permanent
//     `claims` / `claim_top_domains` / `claim_evidence` before R5's
//     deterministic validator passes.
//   - R5's quote validator runs per evidence row.
//   - R5.5's taxonomy validator runs per candidate.
//   - R5's decidePromotion → R6's executePromotion runs in a transaction
//     with pg_try_advisory_xact_lock for concurrency safety.
//   - Validation-loop circuit breaker (3-strike) trips when the same source
//     batch keeps producing invalid quotes.
//   - oracle_context_packs + model_run_usage_details + provider_cached_content
//     rows are written for every model call so cost/cache dashboards work.

import { schedules } from '@trigger.dev/sdk/v3';
import { and, eq, inArray, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  employees,
  extractionBatches,
  extractionCandidates,
  extractionCandidateEvidence,
  extractionValidationResults,
  jobRuns,
  messages,
  entities,
  modelRunUsageDetails,
  modelRuns,
  oracleContextPacks,
  settings,
  type OracleDb,
} from '@oracle/db';
import {
  AnthropicAdapter,
  OpenAIAdapter,
  OracleAIClient,
  VertexGeminiAdapter,
  getOracleRoute,
  resolveModelRoute,
  makeBlock,
  type OracleModelRoute,
  type OraclePromptPlan,
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  ExtractionOutputSchema,
  formatConversationSegment,
  type FormattedMessage,
  type ExtractionOutput,
} from '@oracle/ai';
import {
  computeCandidateHash,
  decideCircuitBreaker,
  executePromotion,
  mapLegacyDomainsToTopDomains,
  stageEntityProposal,
  validateQuote,
  validateSourcePointer,
  validateTaxonomy,
  AdvisoryLockBusyError,
  type RegistryEntity,
} from '@oracle/engines';
import type { EntityType, KnowledgeDomain, TopLevelDomainId } from '@oracle/shared';

const BATCH_SIZE = 100;
const SEGMENT_GAP_MS = 60 * 60 * 1000;

// Fallback route — used if the settings row is missing or points at a route
// not in the catalog. Matches the R1 default.
const FALLBACK_ROUTE_ID = 'vertex_gemini_2_5_flash_extraction_primary';

// ── Module-singletons ─────────────────────────────────────────────────────
// The OracleAIClient is constructed once per worker process with the three
// direct provider adapters (R-providers). Per DECISIONS.md D6 these talk to
// Anthropic, Vertex, and OpenAI APIs directly via @anthropic-ai/sdk,
// @google/genai, and openai — NOT through OpenRouter or the Vercel AI SDK.
function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({
    adapters: {
      anthropic: new AnthropicAdapter(),
      vertex: new VertexGeminiAdapter(),
      openai: new OpenAIAdapter(),
    },
    fallbackOnError: true,
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Top-level Trigger.dev task
// ─────────────────────────────────────────────────────────────────────────

export interface ClaimExtractionRunTotals {
  ok: boolean;
  batchesProcessed: number;
  candidatesStaged: number;
  claimsPromoted: number;
  duplicatesAppended: number;
  rejections: number;
  circuitBreakerTrips: number;
  messagesProcessed: number;
  errors: number;
}

// Core run body extracted so wet-test runners and future integration tests
// can invoke a single pass without going through the Trigger.dev runtime.
// `triggerRunId` accepts a real `ctx.run.id` from Trigger.dev OR any unique
// string for local invocation (the value is stored on the `job_runs` row).
export async function runClaimExtractionOnce(
  triggerRunId: string,
): Promise<ClaimExtractionRunTotals> {
    const db = getDirectDb();
    const client = buildOracleClient();
    const startedAt = new Date();

    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId,
        jobType: 'claim-extraction',
        status: 'running',
        startedAt,
        inputJson: { batchSize: BATCH_SIZE },
      })
      .returning({ id: jobRuns.id });
    if (!jobRun) throw new Error('[claim-extraction] failed to insert job_runs row');

    const totals = {
      batchesProcessed: 0,
      candidatesStaged: 0,
      claimsPromoted: 0,
      duplicatesAppended: 0,
      rejections: 0,
      circuitBreakerTrips: 0,
      messagesProcessed: 0,
      errors: 0,
    };

    try {
      // 1. Resolve the curated extraction route.
      const route = await resolveExtractionRoute(db);
      const activeTopDomainIds = await loadActiveTopDomainIds(db);
      const entityRegistry = await loadEntityRegistry(db);

      // 2. Pull pending user messages.
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
        .where(and(eq(messages.extractionStatus, 'pending'), eq(messages.role, 'user')))
        .orderBy(messages.createdAt)
        .limit(BATCH_SIZE);

      if (pendingMessages.length === 0) {
        await db
          .update(jobRuns)
          .set({ status: 'complete', finishedAt: new Date(), outputJson: totals })
          .where(eq(jobRuns.id, jobRun.id));
        return { ok: true, ...totals };
      }

      // 3. Mark all fetched messages as 'processing' (idempotency guard).
      const messageIds = pendingMessages.map((m) => m.id);
      await db
        .update(messages)
        .set({ extractionStatus: 'processing' })
        .where(inArray(messages.id, messageIds));

      // 4. Group by channel → 60-min conversation segments.
      const segments = groupIntoSegments(pendingMessages);

      // 5. Process each segment as an extraction_batches row.
      for (const segment of segments) {
        try {
          const outcome = await processSegment({
            db,
            client,
            route,
            activeTopDomainIds,
            entityRegistry,
            jobRunId: jobRun.id,
            segment,
          });
          totals.batchesProcessed += 1;
          totals.candidatesStaged += outcome.candidatesStaged;
          totals.claimsPromoted += outcome.claimsPromoted;
          totals.duplicatesAppended += outcome.duplicatesAppended;
          totals.rejections += outcome.rejections;
          totals.circuitBreakerTrips += outcome.circuitBreakerTripped ? 1 : 0;
          totals.messagesProcessed += outcome.messagesProcessed;
        } catch (segErr) {
          totals.errors += 1;
          console.error('[claim-extraction] segment processing failed', segErr);
          // The segment-level error path already updates the batch + messages
          // to 'failed'; nothing more to do here.
        }
      }

      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: totals })
        .where(eq(jobRuns.id, jobRun.id));

      return { ok: true, ...totals };
    } catch (fatalErr) {
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
}

// Trigger.dev scheduled wrapper — production cron entry point. Delegates
// every line of behavior to runClaimExtractionOnce so the two paths
// can never drift.
export const claimExtractionTask = schedules.task({
  id: 'claim-extraction',
  cron: '0 */4 * * *',
  maxDuration: 60 * 5,
  run: async (_payload, { ctx }) => {
    return runClaimExtractionOnce(ctx.run.id);
  },
});

// ─────────────────────────────────────────────────────────────────────────
// Per-segment processing
// ─────────────────────────────────────────────────────────────────────────

interface SegmentOutcome {
  candidatesStaged: number;
  claimsPromoted: number;
  duplicatesAppended: number;
  rejections: number;
  circuitBreakerTripped: boolean;
  messagesProcessed: number;
}

interface ProcessSegmentArgs {
  db: OracleDb;
  client: OracleAIClient;
  route: OracleModelRoute;
  activeTopDomainIds: string[];
  entityRegistry: RegistryEntity[];
  jobRunId: string;
  segment: FormattedMessage[];
}

async function processSegment(args: ProcessSegmentArgs): Promise<SegmentOutcome> {
  const { db, client, route, activeTopDomainIds, entityRegistry, jobRunId, segment } = args;
  const segmentIds = segment.map((m) => m.id);
  const userMessages = segment.filter((m) => m.role === 'user');

  const outcome: SegmentOutcome = {
    candidatesStaged: 0,
    claimsPromoted: 0,
    duplicatesAppended: 0,
    rejections: 0,
    circuitBreakerTripped: false,
    messagesProcessed: 0,
  };

  if (userMessages.length === 0) {
    await db
      .update(messages)
      .set({ extractionStatus: 'skipped', extractedAt: new Date() })
      .where(inArray(messages.id, segmentIds));
    outcome.messagesProcessed = segmentIds.length;
    return outcome;
  }

  // Compile the prompt plan.
  const formatted = formatConversationSegment(segment);
  const blocks = [
    makeBlock({
      id: 'extraction-system',
      label: 'Extraction system prompt',
      kind: 'stable_system',
      content: EXTRACTION_SYSTEM_PROMPT,
      reasonIncluded: 'extraction prompt v' + EXTRACTION_PROMPT_VERSION,
    }),
    makeBlock({
      id: 'segment',
      label: 'Conversation segment to extract from',
      kind: 'dynamic_input',
      content: formatted,
      reasonIncluded: `segment of ${segment.length} message(s) in this batch`,
    }),
  ];
  const plan = client.compile({
    taskType: 'message_claim_extraction',
    routeId: route.routeId,
    promptVersion: EXTRACTION_PROMPT_VERSION,
    blocks,
    observability: { includedMessageIds: segmentIds },
  });
  const sourceHash = createHash('sha256').update(formatted, 'utf8').digest('hex');

  // 1. Stage an extraction_batches row.
  const [batch] = await db
    .insert(extractionBatches)
    .values({
      jobRunId,
      batchType: 'message_segment',
      status: 'pending_model',
      sourceMessageIds: segmentIds,
      sourceHash,
      modelRunIdsAttempted: [],
      routeIdsAttempted: [route.routeId],
    })
    .returning({ id: extractionBatches.id });
  if (!batch) throw new Error('[claim-extraction] failed to insert extraction_batches row');

  // 2. Stage the context pack BEFORE the model call so its ID can thread
  //    through. model_run_id stays null until the model_run is logged.
  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[claim-extraction] failed to insert oracle_context_packs row');

  await db
    .update(extractionBatches)
    .set({ contextPackId: contextPack.id })
    .where(eq(extractionBatches.id, batch.id));

  // 3. Call the model.
  const callStartedAt = Date.now();
  let modelOutput: ExtractionOutput | null = null;
  let modelRunId: string | null = null;
  let modelError: unknown = null;

  try {
    const result = await client.runObject<ExtractionOutput>({
      taskType: 'message_claim_extraction',
      routeId: route.routeId,
      promptVersion: EXTRACTION_PROMPT_VERSION,
      blocks,
      schema: ExtractionOutputSchema,
      observability: { includedMessageIds: segmentIds },
    });
    const latencyMs = Date.now() - callStartedAt;

    // Log model_runs row.
    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'claim-extraction',
        model: route.modelId,
        provider: route.provider,
        promptVersion: EXTRACTION_PROMPT_VERSION,
        inputHash: plan.metadata.stablePrefixHash,
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs,
        success: result.validation.ok,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('[claim-extraction] failed to insert model_runs row');
    modelRunId = modelRun.id;

    // Log model_run_usage_details + back-link context pack.
    await db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
      contextPackId: contextPack.id,
      routeId: route.routeId,
      inputTokens: result.usage.inputTokens ?? null,
      cachedInputTokens: result.usage.cachedInputTokens ?? null,
      cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      reasoningTokens: result.usage.reasoningTokens ?? null,
      providerRequestId: result.usage.providerRequestId ?? null,
      rawUsageJson: result.usage.rawUsageJson ?? null,
    });
    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));
    await db
      .update(extractionBatches)
      .set({
        modelRunId: modelRun.id,
        modelRunIdsAttempted: [modelRun.id],
        rawModelOutput: result.object as unknown as Record<string, unknown>,
        status: result.validation.ok ? 'model_complete' : 'failed',
      })
      .where(eq(extractionBatches.id, batch.id));

    if (!result.validation.ok) {
      throw new Error(
        '[claim-extraction] model output failed Zod schema validation: ' +
          result.validation.error.message,
      );
    }
    modelOutput = result.object;
  } catch (err) {
    modelError = err;
    if (!modelRunId) {
      // The model_runs row was never inserted. Insert a failed one now so
      // the batch has provenance.
      await db.insert(modelRuns).values({
        taskType: 'claim-extraction',
        model: route.modelId,
        provider: route.provider,
        promptVersion: EXTRACTION_PROMPT_VERSION,
        latencyMs: Date.now() - callStartedAt,
        success: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
    await db
      .update(extractionBatches)
      .set({
        status: 'failed',
        error: err instanceof Error ? err.message : String(err),
        finishedAt: new Date(),
      })
      .where(eq(extractionBatches.id, batch.id));
    await db
      .update(messages)
      .set({
        extractionStatus: 'failed',
        extractionError: err instanceof Error ? err.message : String(err),
      })
      .where(inArray(messages.id, segmentIds));
    outcome.messagesProcessed = segmentIds.length;
    return outcome;
  }

  if (!modelOutput) return outcome;

  // 4. Stage candidates + evidence, run R5/R5.5 validators, run promotion.
  let consecutiveQuoteFailureCount = 0;
  let validationAttemptCount = 0;

  for (const extracted of modelOutput.claims) {
    validationAttemptCount += 1;

    // Insert the candidate row.
    const proposedTopDomainIds = mapLegacyDomainsToTopDomains(
      extracted.domains as KnowledgeDomain[],
    );
    const [candidate] = await db
      .insert(extractionCandidates)
      .values({
        extractionBatchId: batch.id,
        status: 'pending_validation',
        claimType: extracted.claimType,
        summary: extracted.summary,
        impactScore: extracted.impactScore,
        confidenceScore: extracted.confidenceScore,
        domains: proposedTopDomainIds satisfies TopLevelDomainId[],
        // P2 #1 — proposedEntities now sourced from the model (was hardcoded
        // empty pre-prompt-2.0.0). Empty array if the claim references no
        // proper-noun entities.
        proposedEntities: (extracted.proposedEntities ?? []).map((e) => ({
          entityType: e.entityType,
          rawString: e.rawString,
        })),
        stance: legacyStanceToCandidateStance(extracted.semanticRole),
        // P1 #2 — sensitivityFlags now sourced from the model. Was hardcoded
        // false on every claim pre-prompt-2.0.0, which meant the sensitivity
        // gate could never fire in production. Strict-mode definitions live
        // in EXTRACTION_SYSTEM_PROMPT.
        containsSensitivePersonalData:
          extracted.sensitivityFlags?.containsSensitivePersonalData ?? false,
        containsSensitiveHRData: extracted.sensitivityFlags?.containsSensitiveHRData ?? false,
        isPersonalConflict: extracted.sensitivityFlags?.isPersonalConflict ?? false,
        sensitivityReason: extracted.sensitivityFlags?.sensitivityReason ?? null,
        requiresReview: extracted.requiresReview,
        reviewReason: extracted.requiresReview ? 'extractor requested review' : null,
        rawCandidateJson: extracted as unknown as Record<string, unknown>,
      })
      .returning({ id: extractionCandidates.id });
    if (!candidate) {
      console.warn('[claim-extraction] candidate insert returned no row — skipping');
      continue;
    }
    outcome.candidatesStaged += 1;

    // Insert evidence (single row per candidate for now — the extraction
    // schema only emits one quote per claim).
    const sourceMsg = segment.find((m) => m.id === extracted.evidence.sourceMessageId);
    const sourcePointerCheck = validateSourcePointer({
      sourceType: 'message',
      sourceMessageId: extracted.evidence.sourceMessageId,
    });
    if (!sourcePointerCheck.ok || !sourceMsg) {
      await db.insert(extractionValidationResults).values({
        candidateId: candidate.id,
        checkName: sourcePointerCheck.failedCheckName ?? 'source_exists',
        status: 'fail',
        detail: !sourceMsg
          ? `sourceMessageId ${extracted.evidence.sourceMessageId} not in segment`
          : sourcePointerCheck.detail,
      });
      await db
        .update(extractionCandidates)
        .set({
          status: 'validation_failed',
          validationError: 'source pointer invalid',
          validatedAt: new Date(),
        })
        .where(eq(extractionCandidates.id, candidate.id));
      outcome.rejections += 1;
      continue;
    }

    const [evRow] = await db
      .insert(extractionCandidateEvidence)
      .values({
        candidateId: candidate.id,
        sourceType: 'message',
        sourceMessageId: extracted.evidence.sourceMessageId,
        assertedByEmployeeId:
          (segment.find((m) => m.id === extracted.evidence.sourceMessageId) as
            | (FormattedMessage & { employeeId?: string })
            | undefined)?.employeeId ?? null,
        exactQuoteProvided: extracted.evidence.exactQuote,
        validationStatus: 'pending',
        confidence: extracted.evidence.confidence,
      })
      .returning({ id: extractionCandidateEvidence.id });
    if (!evRow) {
      console.warn('[claim-extraction] candidate evidence insert returned no row — skipping');
      continue;
    }

    // R5 — quote validation.
    const quoteRes = validateQuote({
      sourceText: sourceMsg.content,
      exactQuoteProvided: extracted.evidence.exactQuote,
    });
    await db
      .update(extractionCandidateEvidence)
      .set({
        validationStatus: quoteRes.validationStatus,
        validationMethod: quoteRes.validationMethod,
        validatedExactQuote: quoteRes.validatedExactQuote ?? null,
        validatedCharStart: quoteRes.validatedCharStart ?? null,
        validatedCharEnd: quoteRes.validatedCharEnd ?? null,
        validatedAt: new Date(),
        validationError:
          quoteRes.verdict === 'exact_match' || quoteRes.verdict === 'normalized_match'
            ? null
            : quoteRes.detail,
      })
      .where(eq(extractionCandidateEvidence.id, evRow.id));
    await db.insert(extractionValidationResults).values({
      candidateId: candidate.id,
      candidateEvidenceId: evRow.id,
      checkName: quoteRes.failedCheckName ?? 'quote_exact_match',
      status:
        quoteRes.verdict === 'exact_match' || quoteRes.verdict === 'normalized_match'
          ? 'pass'
          : 'fail',
      detail: quoteRes.detail,
    });

    if (quoteRes.verdict !== 'exact_match' && quoteRes.verdict !== 'normalized_match') {
      consecutiveQuoteFailureCount += 1;
      await db
        .update(extractionCandidates)
        .set({
          status: 'validation_failed',
          validationError: quoteRes.detail,
          validatedAt: new Date(),
        })
        .where(eq(extractionCandidates.id, candidate.id));
      outcome.rejections += 1;

      // Circuit-breaker check after each failure.
      const cbDecision = decideCircuitBreaker({
        validationAttemptCount,
        consecutiveQuoteFailureCount,
      });
      if (cbDecision.kind === 'trip_breaker') {
        await db
          .update(extractionBatches)
          .set({
            status: 'failed_validation_loop',
            consecutiveQuoteFailureCount,
            validationAttemptCount,
            finishedAt: new Date(),
          })
          .where(eq(extractionBatches.id, batch.id));
        await db.insert(extractionValidationResults).values({
          candidateId: candidate.id,
          checkName: cbDecision.validationResultToWrite.checkName,
          status: cbDecision.validationResultToWrite.status,
          detail: cbDecision.validationResultToWrite.detail,
          metadataJson: {
            routeId: route.routeId,
            modelRunIdAttempted: modelRunId,
            sourceHash,
          },
        });
        outcome.circuitBreakerTripped = true;
        break; // stop processing this batch
      }
      continue;
    }

    // Quote passed → reset the consecutive failure counter.
    consecutiveQuoteFailureCount = 0;

    // R5.5 — taxonomy validation. proposedEntities sourced from prompt-2.0.0
    // (P2 #1). The resolver picks up licensor-vs-vendor type mismatches.
    const taxRes = validateTaxonomy({
      proposedTopDomainIds,
      activeTopDomainIds,
      proposedEntities: (extracted.proposedEntities ?? []).map((e) => ({
        entityType: e.entityType as EntityType,
        rawString: e.rawString,
      })),
      entityRegistry,
    });
    await db.insert(extractionValidationResults).values({
      candidateId: candidate.id,
      checkName: 'domain_valid',
      status: taxRes.ok ? 'pass' : 'fail',
      detail: taxRes.ok
        ? `Top-domains validated: ${taxRes.validTopDomainIds.join(', ')}`
        : taxRes.failures.map((f) => f.detail).join('; '),
    });

    // Regardless of overall taxRes.ok, stage any entity proposals so admin
    // can review unknown entities or type-mismatch corrections.
    // stageEntityProposal() uses pg_trgm fuzzy-dedup: near-duplicate surfaces
    // (similarity >= 0.85) increment proposal_count instead of creating new rows.
    for (const p of taxRes.entityProposalsToCreate) {
      await stageEntityProposal(db, {
        proposedEntityType: p.proposedEntityType,
        proposedCanonicalValue: p.proposedCanonicalValue,
        rawString: p.rawString,
        observedInSourceType: 'claim_candidate',
        observedInSourceId: candidate.id,
        proposedByModelRunId: modelRunId,
      });
    }

    if (!taxRes.ok) {
      await db
        .update(extractionCandidates)
        .set({
          status: 'validation_failed',
          validationError: taxRes.failureSummary ?? 'taxonomy invalid',
          validatedAt: new Date(),
        })
        .where(eq(extractionCandidates.id, candidate.id));
      outcome.rejections += 1;
      continue;
    }

    // P1 #2 — Sensitivity gate. If the model flagged any sensitivity, the
    // candidate is quarantined here and never reaches promotion. The
    // candidate row is preserved with the model's reason so admin can
    // review it via /admin/ai/candidates → "Sensitive" tab.
    const sensitivityFired =
      extracted.sensitivityFlags?.containsSensitiveHRData === true ||
      extracted.sensitivityFlags?.containsSensitivePersonalData === true ||
      extracted.sensitivityFlags?.isPersonalConflict === true;
    if (sensitivityFired) {
      await db.insert(extractionValidationResults).values({
        candidateId: candidate.id,
        checkName: 'sensitivity_gate',
        status: 'fail',
        detail: extracted.sensitivityFlags?.sensitivityReason ?? 'extractor flagged sensitive content',
        metadataJson: {
          containsSensitiveHRData: extracted.sensitivityFlags?.containsSensitiveHRData ?? false,
          containsSensitivePersonalData:
            extracted.sensitivityFlags?.containsSensitivePersonalData ?? false,
          isPersonalConflict: extracted.sensitivityFlags?.isPersonalConflict ?? false,
        },
      });
      await db
        .update(extractionCandidates)
        .set({
          status: 'quarantined_sensitive',
          validationError: extracted.sensitivityFlags?.sensitivityReason ?? 'sensitive content flagged by extractor',
          validatedAt: new Date(),
        })
        .where(eq(extractionCandidates.id, candidate.id));
      outcome.rejections += 1;
      continue;
    }

    // Sensitivity gate passed → record the pass row for the audit trail.
    await db.insert(extractionValidationResults).values({
      candidateId: candidate.id,
      checkName: 'sensitivity_gate',
      status: 'pass',
      detail: 'extractor reported no sensitive content',
    });

    // Mark candidate validated; the executor re-reads it inside the lock.
    await db
      .update(extractionCandidates)
      .set({ status: 'validated', validatedAt: new Date() })
      .where(eq(extractionCandidates.id, candidate.id));

    const validatedQuote = quoteRes.validatedExactQuote ?? extracted.evidence.exactQuote;
    const candidateHash = computeCandidateHash({
      summary: extracted.summary,
      topDomainIds: taxRes.validTopDomainIds,
      validatedQuotes: [validatedQuote],
      sourcePointers: [`message:${extracted.evidence.sourceMessageId}`],
    });

    // executePromotion re-reads the candidate row + validated evidence
    // INSIDE the advisory lock. We pass only the auxiliary inputs that
    // can't be reconstructed from candidate-table state: taxonomy
    // validation result (depends on the live entities/top-domains
    // registries) and metadata (caller-computed per call).
    try {
      const result = await executePromotion({
        db,
        candidateId: candidate.id,
        candidateHash,
        auxiliaryInputs: { taxonomy: taxRes },
        modelRunId: modelRunId ?? undefined,
      });
      if (result.outcome === 'inserted_new_claim') outcome.claimsPromoted += 1;
      else if (result.outcome === 'appended_to_existing_claim') outcome.duplicatesAppended += 1;
      else outcome.rejections += 1;
    } catch (promErr) {
      if (promErr instanceof AdvisoryLockBusyError) {
        // Skip — another worker has the lock. Candidate stays 'validated';
        // the next cron run will pick it up.
        await db.insert(extractionValidationResults).values({
          candidateId: candidate.id,
          checkName: 'duplicate_promotion_lock',
          status: 'skipped',
          detail: 'Advisory lock busy; another worker holds it.',
        });
      } else {
        await db.insert(extractionValidationResults).values({
          candidateId: candidate.id,
          checkName: 'promotion_transaction',
          status: 'fail',
          detail: promErr instanceof Error ? promErr.message : String(promErr),
        });
        outcome.rejections += 1;
      }
    }
  } // end claims loop

  if (!outcome.circuitBreakerTripped) {
    await db
      .update(extractionBatches)
      .set({
        status: 'validation_complete',
        consecutiveQuoteFailureCount,
        validationAttemptCount,
        finishedAt: new Date(),
      })
      .where(eq(extractionBatches.id, batch.id));
  }

  // Mark messages complete. Even when individual candidates failed, the
  // segment itself was processed; failed candidates are kept staged for
  // admin review separately.
  await db
    .update(messages)
    .set({ extractionStatus: 'complete', extractedAt: new Date() })
    .where(inArray(messages.id, segmentIds));
  outcome.messagesProcessed = segmentIds.length;

  return outcome;
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

async function resolveExtractionRoute(db: OracleDb): Promise<OracleModelRoute> {
  const row = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'default_extraction_route'))
    .limit(1);
  const modelIdOrRouteId =
    typeof row[0]?.value === 'string'
      ? (row[0]!.value as string)
      : FALLBACK_ROUTE_ID;
  const resolved = resolveModelRoute(modelIdOrRouteId, 'extraction') ?? getOracleRoute(modelIdOrRouteId);
  if (resolved) return resolved;
  const fallback = getOracleRoute(FALLBACK_ROUTE_ID);
  if (!fallback) {
    throw new Error(
      `[claim-extraction] settings.default_extraction_route="${modelIdOrRouteId}" not in catalog, and fallback "${FALLBACK_ROUTE_ID}" also missing.`,
    );
  }
  console.warn(
    `[claim-extraction] settings.default_extraction_route="${modelIdOrRouteId}" not in catalog; using fallback "${FALLBACK_ROUTE_ID}".`,
  );
  return fallback;
}

async function loadActiveTopDomainIds(db: OracleDb): Promise<string[]> {
  const rows = await db.execute<{ id: string }>(
    sql`SELECT id FROM knowledge_top_domains WHERE is_active = true`,
  );
  // postgres-js result shape variance — handle both.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const list: Array<{ id: string }> = (rows as any).rows ?? (rows as any);
  return list.map((r) => r.id);
}

/**
 * Load the entity registry slice used by R5.5 validateTaxonomy. For round 1
 * we load all rows (the seed is ~56 rows) — when the registry grows past a
 * few hundred, scope to (proposed types ∪ canonical match of raw strings).
 */
async function loadEntityRegistry(db: OracleDb): Promise<RegistryEntity[]> {
  const rows = await db
    .select({
      id: entities.id,
      entityType: entities.entityType,
      canonicalValue: entities.canonicalValue,
      aliases: entities.aliases,
    })
    .from(entities);
  return rows.map((r) => ({
    id: r.id,
    entityType: r.entityType as EntityType,
    canonicalValue: r.canonicalValue,
    aliases: (r.aliases as string[] | null) ?? null,
  }));
}

function groupIntoSegments(
  pendingMessages: Array<{
    id: string;
    channelId: string;
    employeeId: string | null;
    role: 'user' | 'assistant' | 'system' | string;
    content: string;
    createdAt: Date;
    authorName: string | null;
  }>,
): FormattedMessage[][] {
  const byChannel = new Map<string, typeof pendingMessages>();
  for (const m of pendingMessages) {
    const list = byChannel.get(m.channelId) ?? [];
    list.push(m);
    byChannel.set(m.channelId, list);
  }

  const allSegments: FormattedMessage[][] = [];

  for (const [_channelId, channelMessages] of byChannel) {
    channelMessages.sort(
      (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    );
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
    allSegments.push(...segments);
  }

  return allSegments;
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

function legacyStanceToCandidateStance(
  role: string | undefined,
): 'stated' | 'confirmed' | 'challenged' | 'refined' | 'exception_introduced' | 'ambiguity_revealed' | null {
  switch (role) {
    case 'claim_stated':
      return 'stated';
    case 'claim_confirmed':
      return 'confirmed';
    case 'claim_challenged':
      return 'challenged';
    case 'claim_refined':
      return 'refined';
    case 'exception_introduced':
      return 'exception_introduced';
    case 'process_ambiguity_revealed':
      return 'ambiguity_revealed';
    default:
      return null;
  }
}
