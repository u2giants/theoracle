// R7 — Document ingestion worker (refactored through OracleAIClient + staging).
//
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R7.
//
// What changed vs the legacy worker:
//   - Model calls go through OracleAIClient (R2) via direct provider adapters
//     (Vertex / Anthropic / OpenAI raw SDKs — DECISIONS.md D6 / D9) using
//     the curated route ID from `settings.default_extraction_route`. R7
//     ships the explicit-cache profitability heuristic +
//     provider_cached_content lifecycle bookkeeping; native Vertex
//     cachedContent lifecycle creation is a round-2 follow-up to R-providers.
//   - Output flows through extraction_batches → extraction_candidates →
//     extraction_candidate_evidence first. NOTHING writes to permanent
//     claims tables before R5's deterministic validator passes.
//   - Per-claim quote validation against the matching document_chunk's text
//     (not the full document).
//   - Per-claim taxonomy validation against active knowledge_top_domains.
//   - Race-safe promotion via executePromotion (snapshotInputs path) —
//     uses claims.candidate_hash to detect historical duplicates across
//     ingestion runs.
//   - document_top_domains + document_chunk_top_domains rows written for
//     each successfully-promoted claim's domains, so retrieval works at
//     the document level even before claims accumulate.
//
// What stays the same:
//   - Download from Supabase Storage via service-role client (private).
//   - PDF / XLSX / CSV / text parsing.
//   - Chunking + embedding + document_chunks insert (with dedup by hash).
//   - Direct + sweep task variants (single document + cron safety net).

import { schedules, task, tasks } from '@trigger.dev/sdk/v3';
import { and, eq, inArray } from 'drizzle-orm';
import { createHash } from 'crypto';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import {
  documentChunks,
  documents,
  documentTopDomains,
  documentChunkTopDomains,
  extractionBatches,
  extractionCandidates,
  extractionCandidateEvidence,
  extractionValidationResults,
  jobRuns,
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
  embedMany,
  getOracleRoute,
  makeBlock,
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  ExtractionOutputSchema,
  type ExtractionOutput,
  type OracleModelRoute,
  type OraclePromptPlan,
} from '@oracle/ai';
import {
  computeCandidateHash,
  decideCacheProfitability,
  estimateTokensForCache,
  executePromotion,
  mapLegacyDomainsToTopDomains,
  recordCacheCreation,
  recordCacheTermination,
  validateQuote,
  validateSourcePointer,
  validateTaxonomy,
  AdvisoryLockBusyError,
} from '@oracle/engines';
import { createServiceRoleClient } from '@oracle/auth/server';
import type { KnowledgeDomain, TopLevelDomainId } from '@oracle/shared';

const CHUNK_SIZE = 1500;
const CHUNK_OVERLAP = 150;
const MAX_DOCUMENT_TEXT_CHARS = 15_000;
const FALLBACK_ROUTE_ID = 'vertex_gemini_2_5_flash_extraction_primary';

// ─────────────────────────────────────────────────────────────────────────
// Payload schema for the single-document task
// ─────────────────────────────────────────────────────────────────────────
const SingleDocumentPayloadSchema = z.object({
  documentId: z.string().uuid(),
});

// ─────────────────────────────────────────────────────────────────────────
// Shared OracleAIClient (one per worker process, direct provider adapters)
// ─────────────────────────────────────────────────────────────────────────
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
// Text helpers
// ─────────────────────────────────────────────────────────────────────────

function chunkText(text: string, chunkSize = CHUNK_SIZE, overlap = CHUNK_OVERLAP): string[] {
  if (text.length <= chunkSize) return [text];
  const chunks: string[] = [];
  let start = 0;
  while (start < text.length) {
    const end = Math.min(start + chunkSize, text.length);
    chunks.push(text.slice(start, end));
    start += chunkSize - overlap;
    if (start >= text.length) break;
  }
  return chunks;
}

async function extractTextFromPdf(buffer: Buffer): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pdfParse = (await import('pdf-parse')).default as (buf: Buffer) => Promise<{ text: string }>;
  const result = await pdfParse(buffer);
  return result.text;
}

async function extractTextFromXlsx(buffer: Buffer): Promise<string> {
  const XLSX = await import('xlsx');
  const workbook = XLSX.read(buffer, { type: 'buffer' });
  const lines: string[] = [];
  for (const sheetName of workbook.SheetNames) {
    lines.push(`[Sheet: ${sheetName}]`);
    const sheet = workbook.Sheets[sheetName];
    if (sheet) {
      const csv = XLSX.utils.sheet_to_csv(sheet);
      lines.push(csv);
    }
  }
  return lines.join('\n');
}

// ─────────────────────────────────────────────────────────────────────────
// Per-document processor
// ─────────────────────────────────────────────────────────────────────────

interface ProcessDocumentResult {
  chunksInserted: number;
  candidatesStaged: number;
  claimsPromoted: number;
  duplicatesAppended: number;
  rejections: number;
}

async function processDocument(documentId: string, jobRunId: string): Promise<ProcessDocumentResult> {
  const db = getDirectDb();
  const client = buildOracleClient();
  const serviceSupabase = createServiceRoleClient();
  const outcome: ProcessDocumentResult = {
    chunksInserted: 0,
    candidatesStaged: 0,
    claimsPromoted: 0,
    duplicatesAppended: 0,
    rejections: 0,
  };

  // 1. Load + mark processing.
  const [doc] = await db.select().from(documents).where(eq(documents.id, documentId)).limit(1);
  if (!doc) throw new Error(`Document ${documentId} not found`);
  if (doc.status === 'complete') {
    console.log(`[document-ingestion] ${documentId} already complete — skipping`);
    return outcome;
  }
  await db.update(documents).set({ status: 'processing' }).where(eq(documents.id, documentId));

  const route = await resolveExtractionRoute(db);
  const activeTopDomainIds = await loadActiveTopDomainIds(db);

  // 2. Download.
  const { data: blob, error: downloadError } = await serviceSupabase.storage
    .from(doc.storageBucket)
    .download(doc.storagePath);
  if (downloadError || !blob) {
    throw new Error(
      `Storage download failed for ${doc.storagePath}: ${downloadError?.message ?? 'empty blob'}`,
    );
  }
  const buffer = Buffer.from(await blob.arrayBuffer());

  // 3. Parse.
  let rawText: string;
  try {
    if (doc.fileType === 'application/pdf') {
      rawText = await extractTextFromPdf(buffer);
    } else if (
      doc.fileType === 'application/vnd.ms-excel' ||
      doc.fileType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
      doc.fileType === 'text/csv'
    ) {
      rawText = await extractTextFromXlsx(buffer);
    } else if (doc.fileType.startsWith('text/')) {
      rawText = buffer.toString('utf-8');
    } else {
      console.warn(
        `[document-ingestion] unsupported file type ${doc.fileType} for doc ${documentId} — marking complete with note`,
      );
      await db
        .update(documents)
        .set({
          status: 'complete',
          processedAt: new Date(),
          processingError: `Unsupported file type: ${doc.fileType}`,
        })
        .where(eq(documents.id, documentId));
      return outcome;
    }
  } catch (parseErr) {
    throw new Error(
      `File parse failed for ${doc.fileName}: ${parseErr instanceof Error ? parseErr.message : String(parseErr)}`,
    );
  }

  if (!rawText.trim()) {
    await db
      .update(documents)
      .set({ status: 'complete', processedAt: new Date(), processingError: 'No text extracted' })
      .where(eq(documents.id, documentId));
    return outcome;
  }

  // 4. Chunk + embed + insert chunks (idempotent dedup by content hash).
  const textChunks = chunkText(rawText);
  let chunkVectors: (number[] | null)[] = [];
  try {
    const { vectors } = await embedMany(textChunks);
    chunkVectors = vectors;
  } catch (embedErr) {
    console.warn('[document-ingestion] embed failed; inserting chunks without vectors', embedErr);
    chunkVectors = textChunks.map(() => null);
  }

  const insertedChunkIds: Array<{ id: string; text: string }> = [];
  for (let i = 0; i < textChunks.length; i++) {
    const text = textChunks[i]!;
    const contentHash = createHash('sha256').update(text).digest('hex');
    try {
      const [chunk] = await db
        .insert(documentChunks)
        .values({
          documentId,
          chunkIndex: i,
          rawText: text,
          tokenCount: Math.ceil(text.length / 4),
          contentHash,
          embedding: chunkVectors[i] ?? null,
          metadataJson: { fileType: doc.fileType, fileName: doc.fileName },
        })
        .onConflictDoNothing()
        .returning({ id: documentChunks.id });
      if (chunk) {
        outcome.chunksInserted += 1;
        insertedChunkIds.push({ id: chunk.id, text });
      }
    } catch (chunkErr) {
      console.error(`[document-ingestion] chunk ${i} insert failed:`, chunkErr);
    }
  }

  if (insertedChunkIds.length === 0 || rawText.trim().length <= 20) {
    await db
      .update(documents)
      .set({ status: 'complete', processedAt: new Date() })
      .where(eq(documents.id, documentId));
    return outcome;
  }

  // 5. Stage extraction_batches row.
  const truncatedText = rawText.slice(0, MAX_DOCUMENT_TEXT_CHARS);
  const sourceHash = createHash('sha256').update(truncatedText, 'utf8').digest('hex');
  const [batch] = await db
    .insert(extractionBatches)
    .values({
      jobRunId,
      batchType: 'document_page',
      status: 'pending_model',
      sourceDocumentChunkIds: insertedChunkIds.map((c) => c.id),
      sourceHash,
      modelRunIdsAttempted: [],
      routeIdsAttempted: [route.routeId],
    })
    .returning({ id: extractionBatches.id });
  if (!batch) throw new Error('[document-ingestion] failed to insert extraction_batches row');

  // 6. Compile prompt + context pack. The document text becomes the dynamic
  //    block; the extraction system prompt + the document-specific addendum
  //    are stable.
  const documentNote =
    `\n\nNOTE: This is a DOCUMENT, not a conversation. Extract claims about operational processes, rules, systems, and dependencies described in the document.\nDocument name: ${doc.fileName}\nFile type: ${doc.fileType}`;
  const blocks = [
    makeBlock({
      id: 'extraction-system',
      label: 'Extraction system prompt + document addendum',
      kind: 'stable_system',
      content: EXTRACTION_SYSTEM_PROMPT + documentNote,
      reasonIncluded: 'extraction prompt v' + EXTRACTION_PROMPT_VERSION + ' (document mode)',
    }),
    makeBlock({
      id: 'document-text',
      label: 'Document content (truncated)',
      kind: 'dynamic_input',
      content: truncatedText,
      reasonIncluded: `${insertedChunkIds.length} chunks → truncated to ${truncatedText.length} chars`,
    }),
  ];
  const plan = client.compile({
    taskType: 'document_claim_extraction',
    routeId: route.routeId,
    promptVersion: EXTRACTION_PROMPT_VERSION,
    blocks,
    observability: { includedDocumentChunkIds: insertedChunkIds.map((c) => c.id) },
  });

  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[document-ingestion] failed to insert oracle_context_packs row');
  await db
    .update(extractionBatches)
    .set({ contextPackId: contextPack.id })
    .where(eq(extractionBatches.id, batch.id));

  // 7. Cache profitability bookkeeping. R7 records the decision and (when
  //    the heuristic says yes) creates a provider_cached_content row even
  //    though no real Vertex cache exists yet — so when @google/genai
  //    lands, the lifecycle audit trail is already in place. The row is
  //    marked deleted in `finally` below.
  const cacheDecision = decideCacheProfitability({
    sourceTokenEstimate: estimateTokensForCache(truncatedText),
    expectedReuseCount: 1, // R7 makes a single extraction call per document
  });
  let cacheHandle: Awaited<ReturnType<typeof recordCacheCreation>> | null = null;
  if (cacheDecision.kind === 'create_explicit_cache') {
    cacheHandle = await recordCacheCreation({
      db,
      provider: 'vertex',
      cacheKind: 'explicit',
      sourceHash,
      sourceTokenEstimate: estimateTokensForCache(truncatedText),
      sourceDescription: `${doc.fileName} (${doc.fileType})`,
      // providerResourceName: filled when a real Vertex cache resource exists (R7+ SDK wiring).
      expectedReuseCount: 1,
      latestPlannedReuseStep: 'document_claim_extraction',
      hardExpirationAt: new Date(Date.now() + 60 * 60 * 1000), // 1h hard cap
      cleanupOwner: 'document-ingestion-worker',
      createdByJobRunId: jobRunId,
    });
  }

  // 8. Call the model.
  let modelOutput: ExtractionOutput | null = null;
  let modelRunId: string | null = null;
  const callStartedAt = Date.now();
  try {
    const result = await client.runObject<ExtractionOutput>({
      taskType: 'document_claim_extraction',
      routeId: route.routeId,
      promptVersion: EXTRACTION_PROMPT_VERSION,
      blocks,
      schema: ExtractionOutputSchema,
      observability: { includedDocumentChunkIds: insertedChunkIds.map((c) => c.id) },
    });
    const latencyMs = Date.now() - callStartedAt;

    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'document-ingestion',
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
    if (!modelRun) throw new Error('[document-ingestion] failed to insert model_runs row');
    modelRunId = modelRun.id;

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
        '[document-ingestion] model output failed Zod schema validation: ' + result.validation.error.message,
      );
    }
    modelOutput = result.object;
  } catch (err) {
    if (!modelRunId) {
      await db.insert(modelRuns).values({
        taskType: 'document-ingestion',
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
    if (cacheHandle) {
      await recordCacheTermination({
        db,
        handle: cacheHandle,
        status: 'failed',
        reason: 'extraction call failed; cache resource never used',
      });
    }
    // Document still has chunks — mark complete with the error noted.
    await db
      .update(documents)
      .set({
        status: 'complete',
        processedAt: new Date(),
        processingError: err instanceof Error ? err.message : String(err),
      })
      .where(eq(documents.id, documentId));
    return outcome;
  }

  // 9. For each extracted claim: stage candidate + evidence, validate,
  //    promote. The promoter writes claim_top_domains for the claim; we
  //    additionally write document_chunk_top_domains so retrieval works
  //    against the chunk independently.
  if (modelOutput) {
    for (const extracted of modelOutput.claims) {
      // Pick the chunk whose text contains the quote. If none does, the
      // quote validator will reject it as 'failed' anyway.
      const matchingChunk = insertedChunkIds.find((c) => c.text.includes(extracted.evidence.exactQuote));
      const chunkForEvidence = matchingChunk ?? insertedChunkIds[0]!;

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
          proposedEntities: [],
          containsSensitivePersonalData: false,
          containsSensitiveHRData: false,
          isPersonalConflict: false,
          requiresReview: extracted.requiresReview,
          reviewReason: extracted.requiresReview ? 'extractor requested review' : null,
          rawCandidateJson: extracted as unknown as Record<string, unknown>,
        })
        .returning({ id: extractionCandidates.id });
      if (!candidate) continue;
      outcome.candidatesStaged += 1;

      // Stage candidate evidence (source_type='document_chunk').
      const sourcePointerRes = validateSourcePointer({
        sourceType: 'document_chunk',
        sourceDocumentChunkId: chunkForEvidence.id,
      });
      if (!sourcePointerRes.ok) {
        await db.insert(extractionValidationResults).values({
          candidateId: candidate.id,
          checkName: sourcePointerRes.failedCheckName ?? 'source_exists',
          status: 'fail',
          detail: sourcePointerRes.detail,
        });
        await db
          .update(extractionCandidates)
          .set({ status: 'validation_failed', validationError: 'source pointer invalid', validatedAt: new Date() })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }
      const [evRow] = await db
        .insert(extractionCandidateEvidence)
        .values({
          candidateId: candidate.id,
          sourceType: 'document_chunk',
          sourceDocumentChunkId: chunkForEvidence.id,
          uploadedByEmployeeId: doc.uploaderId,
          exactQuoteProvided: extracted.evidence.exactQuote,
          validationStatus: 'pending',
          confidence: extracted.evidence.confidence,
          documentClass: null,
          processStage: null,
        })
        .returning({ id: extractionCandidateEvidence.id });
      if (!evRow) continue;

      // Quote validation against the matching chunk's text.
      const quoteRes = validateQuote({
        sourceText: chunkForEvidence.text,
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
        await db
          .update(extractionCandidates)
          .set({ status: 'validation_failed', validationError: quoteRes.detail, validatedAt: new Date() })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }

      // Taxonomy validation.
      const taxRes = validateTaxonomy({
        proposedTopDomainIds,
        activeTopDomainIds,
        proposedEntities: [],
        entityRegistry: [],
      });
      await db.insert(extractionValidationResults).values({
        candidateId: candidate.id,
        checkName: 'domain_valid',
        status: taxRes.ok ? 'pass' : 'fail',
        detail: taxRes.ok
          ? `Top-domains validated: ${taxRes.validTopDomainIds.join(', ')}`
          : taxRes.failures.map((f) => f.detail).join('; '),
      });
      if (!taxRes.ok) {
        await db
          .update(extractionCandidates)
          .set({ status: 'validation_failed', validationError: 'taxonomy invalid', validatedAt: new Date() })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }

      // Mark validated; the executor re-reads the candidate + evidence
      // INSIDE the advisory lock. We pass only auxiliary inputs that can't
      // be reconstructed from candidate-table state.
      await db
        .update(extractionCandidates)
        .set({ status: 'validated', validatedAt: new Date() })
        .where(eq(extractionCandidates.id, candidate.id));

      const validatedQuote = quoteRes.validatedExactQuote ?? extracted.evidence.exactQuote;
      const candidateHash = computeCandidateHash({
        summary: extracted.summary,
        topDomainIds: taxRes.validTopDomainIds,
        validatedQuotes: [validatedQuote],
        sourcePointers: [`document_chunk:${chunkForEvidence.id}`],
      });

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

        // Write document-level + chunk-level top-domain tags for retrieval.
        if (result.outcome !== 'recorded_rejection') {
          for (const topDomainId of taxRes.validTopDomainIds) {
            await db
              .insert(documentTopDomains)
              .values({
                documentId,
                topDomainId,
                assignmentReason: 'ingestion',
              })
              .onConflictDoNothing();
            await db
              .insert(documentChunkTopDomains)
              .values({
                documentChunkId: chunkForEvidence.id,
                topDomainId,
                assignmentReason: 'ingestion',
              })
              .onConflictDoNothing();
          }
        }
      } catch (promErr) {
        if (promErr instanceof AdvisoryLockBusyError) {
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
    }
  }

  // 10. Mark batch validation_complete + cache lifecycle teardown.
  await db
    .update(extractionBatches)
    .set({ status: 'validation_complete', finishedAt: new Date() })
    .where(eq(extractionBatches.id, batch.id));

  if (cacheHandle) {
    await recordCacheTermination({
      db,
      handle: cacheHandle,
      status: 'deleted',
      reason: 'document ingestion complete; no further reuse expected',
    });
  }

  await db
    .update(documents)
    .set({ status: 'complete', processedAt: new Date() })
    .where(eq(documents.id, documentId));

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
  const routeId =
    typeof row[0]?.value === 'string' ? (row[0]!.value as string) : FALLBACK_ROUTE_ID;
  const resolved = getOracleRoute(routeId);
  if (resolved) return resolved;
  const fb = getOracleRoute(FALLBACK_ROUTE_ID);
  if (!fb) {
    throw new Error(
      `[document-ingestion] settings.default_extraction_route="${routeId}" not in catalog and fallback "${FALLBACK_ROUTE_ID}" missing.`,
    );
  }
  console.warn(
    `[document-ingestion] settings.default_extraction_route="${routeId}" not in catalog; using fallback "${FALLBACK_ROUTE_ID}".`,
  );
  return fb;
}

async function loadActiveTopDomainIds(db: OracleDb): Promise<string[]> {
  const { sql } = await import('drizzle-orm');
  const rows = await db.execute<{ id: string }>(
    sql`SELECT id FROM knowledge_top_domains WHERE is_active = true`,
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const list: Array<{ id: string }> = (rows as any).rows ?? (rows as any);
  return list.map((r) => r.id);
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

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────

export const documentIngestionTask = task({
  id: 'document-ingestion',
  maxDuration: 60 * 10,
  run: async (payload: z.infer<typeof SingleDocumentPayloadSchema>, { ctx }) => {
    SingleDocumentPayloadSchema.parse(payload);
    const db = getDirectDb();

    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'document-ingestion',
        status: 'running',
        startedAt: new Date(),
        inputJson: { documentId: payload.documentId },
      })
      .returning({ id: jobRuns.id });
    if (!jobRun) throw new Error('[document-ingestion] failed to insert job_runs row');

    try {
      const result = await processDocument(payload.documentId, jobRun.id);
      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: result })
        .where(eq(jobRuns.id, jobRun.id));
      return { ok: true, documentId: payload.documentId, ...result };
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      await db
        .update(documents)
        .set({ status: 'failed', processingError: errMsg, processedAt: new Date() })
        .where(eq(documents.id, payload.documentId));
      await db
        .update(jobRuns)
        .set({ status: 'failed', finishedAt: new Date(), error: errMsg })
        .where(eq(jobRuns.id, jobRun.id));
      throw err;
    }
  },
});

export const documentIngestionSweepTask = schedules.task({
  id: 'document-ingestion-sweep',
  cron: '30 */4 * * *',
  maxDuration: 60 * 2,
  run: async (_payload) => {
    const db = getDirectDb();
    const stuck = await db
      .select({ id: documents.id })
      .from(documents)
      .where(and(inArray(documents.status, ['pending_processing', 'processing'])))
      .limit(20);
    if (stuck.length === 0) return { ok: true, triggered: 0 };
    let triggered = 0;
    for (const doc of stuck) {
      try {
        await tasks.trigger('document-ingestion', { documentId: doc.id });
        triggered++;
      } catch (err) {
        console.error(`[document-ingestion-sweep] failed to trigger for ${doc.id}:`, err);
      }
    }
    return { ok: true, triggered, total: stuck.length };
  },
});
