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
import { writeFile, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import {
  documentChunks,
  documents,
  documentTopDomains,
  documentChunkTopDomains,
  entities,
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
  OracleAIClient,
  buildStandardAdapters,
  embedMany,
  getOracleRoute,
  resolveRouteFromSettings,
  resolveAuxiliaryRouteFromSettings,
  VISION_AUXILIARY_MODEL,
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
  executePromotion,
  mapLegacyDomainsToTopDomains,
  stageEntityProposal,
  validateQuote,
  validateSourcePointer,
  validateTaxonomy,
  AdvisoryLockBusyError,
  type RegistryEntity,
} from '@oracle/engines';
import { createServiceRoleClient } from '@oracle/auth/server';
import type { EntityType, KnowledgeDomain, TopLevelDomainId } from '@oracle/shared';

const CHUNK_SIZE = 1500;
const CHUNK_OVERLAP = 150;
const MAX_DOCUMENT_TEXT_CHARS = 15_000;
const VERTEX_FILE_CACHE_MIN_BYTES = 10 * 1024 * 1024;
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
    adapters: buildStandardAdapters(),
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

async function extractTextFromDocx(buffer: Buffer): Promise<string> {
  // mammoth is CommonJS; normalize the namespace whether it comes through as a
  // default export or a flat module object.
  const mod = (await import('mammoth')) as unknown as {
    extractRawText?: (opts: { buffer: Buffer }) => Promise<{ value: string }>;
    default?: { extractRawText: (opts: { buffer: Buffer }) => Promise<{ value: string }> };
  };
  const extractRawText = mod.extractRawText ?? mod.default?.extractRawText;
  if (!extractRawText) throw new Error('mammoth.extractRawText unavailable');
  const result = await extractRawText({ buffer });
  return result.value;
}

const DOCX_MIME =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

const IMAGE_TRANSCRIPTION_SYSTEM = `You are a meticulous visual analyst for an operations knowledge base. You will be shown ONE image an employee uploaded. Produce a faithful, self-contained TEXT rendering of everything the image conveys — downstream extraction reads only your text and cannot see the image.

Include, in natural reading order:
- Every piece of visible text, transcribed VERBATIM (labels, headings, every table cell, handwriting, captions, callouts, stamps, axis labels, legends).
- The structure and meaning of any diagram, flowchart, org chart, table, map, or schematic: what the nodes/boxes are, how arrows or lines connect them, and what that connection implies.
- Spatial layout and grouping when it carries meaning (columns, swimlanes, before/after, hierarchy, sequence).
- Concrete operational content: rules, steps, routing, ownership, dates, quantities, statuses, conditions, exceptions.

Rules:
- Transcribe text exactly as written; never paraphrase quoted text.
- Describe visual relationships in plain prose so a reader who cannot see the image understands the process or data.
- Do NOT invent anything that is not visible. If something is unreadable or ambiguous, say so explicitly.
- Output plain text only — no markdown code fences, no preamble such as "Here is".`;

/**
 * Format the inline image part for whichever provider the admin-selected vision
 * model uses. Each adapter forwards `providerOptions.messages` content to its
 * provider natively, so we emit the provider's own image-part shape:
 *   - vertex (Gemini): a generic { type:'image', mimeType, data } that the
 *     Vertex adapter translates to an inlineData part.
 *   - anthropic:       a native Anthropic image block (base64 source).
 *   - openai:          a native OpenAI image_url block (data: URL).
 */
function buildVisionMessageContent(
  provider: OracleModelRoute['provider'],
  mimeType: string,
  base64: string,
  requestText: string,
): Array<Record<string, unknown>> {
  if (provider === 'anthropic') {
    return [
      { type: 'text', text: requestText },
      { type: 'image', source: { type: 'base64', media_type: mimeType, data: base64 } },
    ];
  }
  if (provider === 'openai') {
    return [
      { type: 'text', text: requestText },
      { type: 'image_url', image_url: { url: `data:${mimeType};base64,${base64}` } },
    ];
  }
  // vertex / default — our Vertex adapter turns this into a Gemini inlineData part.
  return [
    { type: 'text', text: requestText },
    { type: 'image', mimeType, data: base64 },
  ];
}

/**
 * Pass 1 of image ingestion: send the raw image to the admin-selected
 * vision-capable model and get back a faithful text rendering (verbatim text +
 * described visual meaning). That text then flows through the SAME chunk →
 * extract → validate → promote pipeline as every other document, which keeps
 * the quote-validation provenance guarantee intact (claims quote the
 * transcription, which is persisted as document_chunks).
 *
 * The model is chosen in Admin → Settings ("Image vision model") and read here
 * via the auxiliary-model registry; the registry's defaultRouteId is only the
 * unset/unresolvable fallback.
 */
async function transcribeImageToText(
  client: OracleAIClient,
  db: OracleDb,
  buffer: Buffer,
  doc: { fileName: string; fileType: string; context?: string | null },
): Promise<string> {
  const fallbackRouteId = VISION_AUXILIARY_MODEL.defaultRouteId;
  const route =
    (await resolveAuxiliaryRouteFromSettings(db, VISION_AUXILIARY_MODEL.id)) ??
    (fallbackRouteId ? getOracleRoute(fallbackRouteId) : null);
  if (!route) {
    throw new Error(
      `vision route unresolvable and default "${fallbackRouteId ?? '(none)'}" is not registered`,
    );
  }
  const mimeType = imageMimeFor(doc.fileType, doc.fileName);
  const contextLine =
    doc.context && doc.context.trim()
      ? ` Context from the uploader about this image: "${doc.context.trim()}". Use it to interpret ambiguous labels, but transcribe only what is actually visible — do not add details that are not in the image.`
      : '';
  const requestText = `Render the attached image "${doc.fileName}" as faithful, complete text.${contextLine}`;

  const blocks = [
    makeBlock({
      id: 'image-vision-system',
      label: 'Image vision transcription system prompt',
      kind: 'stable_system',
      content: IMAGE_TRANSCRIPTION_SYSTEM,
      reasonIncluded: 'vision transcription pass for an uploaded image',
    }),
    makeBlock({
      id: 'image-vision-request',
      label: 'Image vision transcription request',
      kind: 'dynamic_input',
      content: requestText,
      reasonIncluded: 'dynamic request paired with the inline image',
    }),
  ];

  const result = await client.runText({
    taskType: 'document_claim_extraction',
    routeId: route.routeId,
    promptVersion: EXTRACTION_PROMPT_VERSION,
    blocks,
    providerOptions: {
      // One-shot vision call — nothing reusable to cache.
      cache: { disableCache: true },
      messages: [
        {
          role: 'user',
          content: buildVisionMessageContent(
            route.provider,
            mimeType,
            buffer.toString('base64'),
            requestText,
          ),
        },
      ],
    },
  });
  return result.text ?? '';
}

/**
 * Decide how to parse a document from its declared MIME type, falling back to
 * the filename extension when the browser/OS sends a generic
 * `application/octet-stream` (common for .docx on some platforms).
 */
function resolveParseKind(
  fileType: string,
  fileName: string,
): 'pdf' | 'xlsx' | 'docx' | 'image' | 'text' | 'unsupported' {
  const ext = fileName.toLowerCase().split('.').pop() ?? '';
  if (fileType === 'application/pdf' || ext === 'pdf') return 'pdf';
  if (
    fileType === 'application/vnd.ms-excel' ||
    fileType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
    fileType === 'text/csv' ||
    ext === 'xlsx' ||
    ext === 'xls' ||
    ext === 'csv'
  ) {
    return 'xlsx';
  }
  if (fileType === DOCX_MIME || ext === 'docx') return 'docx';
  // Images go through a vision-model transcription pass. Only the formats
  // Gemini accepts natively are routed here; GIF/BMP/TIFF fall through to
  // 'unsupported' so we don't hand the model a mime type it rejects.
  if (
    fileType === 'image/png' ||
    fileType === 'image/jpeg' ||
    fileType === 'image/jpg' ||
    fileType === 'image/webp' ||
    fileType === 'image/heic' ||
    fileType === 'image/heif' ||
    ['png', 'jpg', 'jpeg', 'webp', 'heic', 'heif'].includes(ext)
  ) {
    return 'image';
  }
  if (fileType.startsWith('text/') || ext === 'txt' || ext === 'md' || ext === 'vtt') {
    return 'text';
  }
  return 'unsupported';
}

/** Map a stored file type / name to a Gemini-accepted image MIME type. */
function imageMimeFor(fileType: string, fileName: string): string {
  if (fileType.startsWith('image/')) return fileType === 'image/jpg' ? 'image/jpeg' : fileType;
  const ext = fileName.toLowerCase().split('.').pop() ?? '';
  switch (ext) {
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'webp':
      return 'image/webp';
    case 'heic':
      return 'image/heic';
    case 'heif':
      return 'image/heif';
    default:
      return 'image/png';
  }
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

  const parseKind = resolveParseKind(doc.fileType, doc.fileName);
  const route = await resolveExtractionRoute(db);
  const activeTopDomainIds = await loadActiveTopDomainIds(db);
  const topDomainNameMap = await loadTopDomainNameMap(db);
  const entityRegistry = await loadEntityRegistry(db);

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
  // The file-backed Vertex cache feeds the raw artifact to the EXTRACTION pass.
  // For images that pass runs over the vision transcription (text), not the
  // image, so never attach the raw image as a file-backed cache source.
  const fileBackedCachePath =
    route.provider === 'vertex' &&
    parseKind !== 'image' &&
    buffer.length > VERTEX_FILE_CACHE_MIN_BYTES
      ? await materializeVertexCacheTempFile(buffer, doc.fileName)
      : null;

  // 3. Parse.
  let rawText: string;
  try {
    if (parseKind === 'pdf') {
      rawText = await extractTextFromPdf(buffer);
    } else if (parseKind === 'xlsx') {
      rawText = await extractTextFromXlsx(buffer);
    } else if (parseKind === 'docx') {
      rawText = await extractTextFromDocx(buffer);
    } else if (parseKind === 'image') {
      // Pass 1: vision model renders the image to faithful text. Prefix a
      // provenance header so the persisted chunk is self-describing.
      const transcription = await transcribeImageToText(client, db, buffer, doc);
      rawText = transcription.trim()
        ? `Visual transcription of uploaded image "${doc.fileName}" (${doc.fileType}), produced by a vision model because the source is an image rather than text.\n\n${transcription}`
        : '';
    } else if (parseKind === 'text') {
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
  const baseDocumentNote =
    parseKind === 'image'
      ? `\n\nNOTE: The text below is a VISION-MODEL TRANSCRIPTION of an uploaded image (not a conversation, not a native text document). Extract claims about operational processes, rules, systems, and dependencies that are explicitly supported by this transcription.\nImage name: ${doc.fileName}\nFile type: ${doc.fileType}`
      : `\n\nNOTE: This is a DOCUMENT, not a conversation. Extract claims about operational processes, rules, systems, and dependencies described in the document.\nDocument name: ${doc.fileName}\nFile type: ${doc.fileType}`;
  const documentNote = baseDocumentNote + buildUploaderContextNote(doc, topDomainNameMap);
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
      kind: 'retrieved_context',
      content: truncatedText,
      reasonIncluded: `${insertedChunkIds.length} chunks → truncated to ${truncatedText.length} chars`,
    }),
    makeBlock({
      id: 'document-request',
      label: 'Document extraction request',
      kind: 'dynamic_input',
      content:
        'Extract operational claims from the provided document corpus. Return only claims that are explicitly supported by the document text.',
      reasonIncluded: 'small dynamic request so the document corpus can be cached as reusable prefix',
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

  // 7. Call the model. The adapter now owns the real Vertex explicit-cache
  //    lifecycle, including cross-process reuse via provider_cached_content.
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
      providerOptions: {
        cache: {
          preferLongLivedCache: true,
          preferExplicitCache: route.provider === 'vertex',
          cacheTtlSeconds: 60 * 60,
          expectedReuseCount: 2,
          persistProviderCacheRecord: route.provider === 'vertex',
          sourceDescription: `${doc.fileName} (${doc.fileType})`,
          cleanupOwner: 'document-ingestion-worker',
          createdByJobRunId: jobRunId,
          latestPlannedReuseStep: 'document_claim_extraction',
          vertexFileCacheSource: fileBackedCachePath
            ? {
                localPath: fileBackedCachePath,
                mimeType: doc.fileType,
                fileName: doc.fileName,
                sourceHash,
              }
            : undefined,
        },
      },
    });
    const latencyMs = Date.now() - callStartedAt;
    const actualRouteId = result.routeId ?? route.routeId;
    const actualProvider = result.provider ?? route.provider;
    const actualModelId = result.modelId ?? route.modelId;

    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'document-ingestion',
        model: actualModelId,
        provider: actualProvider,
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
      routeId: actualRouteId,
      inputTokens: result.usage.inputTokens ?? null,
      cachedInputTokens: result.usage.cachedInputTokens ?? null,
      cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      reasoningTokens: result.usage.reasoningTokens ?? null,
      providerRequestId: result.usage.providerRequestId ?? null,
      rawUsageJson: result.usage.rawUsageJson ?? null,
      fellBackFromRouteId: result.fellBackFromRouteId ?? null,
      fallbackReason: result.fallbackReason ?? null,
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
    // Document still has chunks — mark complete with the error noted.
    await db
      .update(documents)
      .set({
        status: 'complete',
        processedAt: new Date(),
        processingError: err instanceof Error ? err.message : String(err),
      })
      .where(eq(documents.id, documentId));
    if (fileBackedCachePath) {
      await unlink(fileBackedCachePath).catch(() => undefined);
    }
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
          // P2 #1 — proposedEntities now sourced from prompt-2.0.0.
          proposedEntities: (extracted.proposedEntities ?? []).map((e) => ({
            entityType: e.entityType,
            rawString: e.rawString,
          })),
          // P1 #2 — sensitivityFlags now sourced from prompt-2.0.0.
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

      // Taxonomy validation. proposedEntities sourced from prompt-2.0.0 (P2 #1).
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
      // Stage entity proposals regardless of overall taxRes.ok so admin can
      // review unknown entities surfaced by the model.
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
          .set({ status: 'validation_failed', validationError: taxRes.failureSummary ?? 'taxonomy invalid', validatedAt: new Date() })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }

      // P1 #2 — Sensitivity gate. Mirrors claim-extraction.ts.
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
            validationError:
              extracted.sensitivityFlags?.sensitivityReason ?? 'sensitive content flagged by extractor',
            validatedAt: new Date(),
          })
          .where(eq(extractionCandidates.id, candidate.id));
        outcome.rejections += 1;
        continue;
      }
      await db.insert(extractionValidationResults).values({
        candidateId: candidate.id,
        checkName: 'sensitivity_gate',
        status: 'pass',
        detail: 'extractor reported no sensitive content',
      });

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

  // 10. Mark batch validation_complete.
  await db
    .update(extractionBatches)
    .set({ status: 'validation_complete', finishedAt: new Date() })
    .where(eq(extractionBatches.id, batch.id));

  await db
    .update(documents)
    .set({ status: 'complete', processedAt: new Date() })
    .where(eq(documents.id, documentId));

  if (fileBackedCachePath) {
    await unlink(fileBackedCachePath).catch(() => undefined);
  }

  return outcome;
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

async function resolveExtractionRoute(db: OracleDb): Promise<OracleModelRoute> {
  const resolved = await resolveRouteFromSettings(db, 'extraction');
  if (resolved) return resolved;
  const fb = getOracleRoute(FALLBACK_ROUTE_ID);
  if (!fb) {
    throw new Error(
      `[document-ingestion] default_extraction_route unset/unresolvable and fallback "${FALLBACK_ROUTE_ID}" missing.`,
    );
  }
  console.warn(
    `[document-ingestion] default_extraction_route unset/unresolvable; using fallback "${FALLBACK_ROUTE_ID}".`,
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

/** Map of active top-domain id -> human name, for rendering uploader hints. */
async function loadTopDomainNameMap(db: OracleDb): Promise<Map<string, string>> {
  const { sql } = await import('drizzle-orm');
  const rows = await db.execute<{ id: string; name: string }>(
    sql`SELECT id, name FROM knowledge_top_domains WHERE is_active = true`,
  );
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const list: Array<{ id: string; name: string }> = (rows as any).rows ?? (rows as any);
  return new Map(list.map((r) => [r.id, r.name]));
}

/**
 * Build the uploader-context addendum for the extraction prompt from a
 * document's optional `context` and `domainHints`. Domain hints are rendered as
 * a non-binding prior — per-claim domain validation stays authoritative.
 */
function buildUploaderContextNote(
  doc: { context?: string | null; domainHints?: string[] | null },
  nameMap: Map<string, string>,
): string {
  let note = '';
  if (doc.context && doc.context.trim()) {
    note += `\nUploader-provided context for this document: "${doc.context.trim()}"`;
  }
  if (doc.domainHints && doc.domainHints.length > 0) {
    const names = doc.domainHints.map((id) => nameMap.get(id) ?? id);
    note +=
      `\nThe uploader suggests these knowledge areas are likely relevant: ${names.join(', ')}. ` +
      `Treat this only as a prior — classify each claim on its own merits and do not force claims into these areas.`;
  }
  return note;
}

/**
 * Load the entity registry slice used by R5.5 validateTaxonomy. For round 1
 * we load all rows (the seed is ~56 rows) — see claim-extraction.ts for the
 * scoping plan when the registry grows.
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

async function materializeVertexCacheTempFile(buffer: Buffer, fileName: string): Promise<string> {
  const safeName = fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
  const tempPath = join(
    tmpdir(),
    `oracle-vertex-cache-${Date.now()}-${safeName}`,
  );
  await writeFile(tempPath, buffer);
  return tempPath;
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
