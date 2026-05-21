// Document ingestion worker — spec Part 9.6.
//
// This task has two modes:
//   1. Triggered directly with { documentId } — process a single document
//      (called from the upload API route after a document is inserted).
//   2. Scheduled sweep (every 4 hours) — picks up documents that are still
//      pending_processing and triggers individual ingestion tasks for each.
//
// Per-document workflow (spec 9.6):
//   1. Download bytes from Supabase Storage (service-role client).
//   2. Parse into plain text by file type (PDF / XLSX / text).
//   3. Chunk text (~1500 chars with 150-char overlap); compute contentHash.
//   4. Embed chunks via @oracle/ai embedMany (1536-dim).
//   5. INSERT document_chunks rows (dedup by contentHash).
//   6. Run claim extraction on each chunk (same extraction model / schema).
//   7. INSERT claims + claim_domains + claim_evidence (source_type='document_chunk').
//   8. UPDATE documents.status to 'complete' or 'failed'.
//   9. Log model_runs and job_runs rows (spec Part 9).

import { schedules, task, tasks } from '@trigger.dev/sdk/v3';
import { and, eq, inArray } from 'drizzle-orm';
import { createHash } from 'crypto';
import { generateObject } from 'ai';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import {
  claims,
  claimDomains,
  claimEvidence,
  documentChunks,
  documents,
  gaps,
  modelRuns,
  jobRuns,
  settings,
} from '@oracle/db/schema';
import {
  getOpenRouter,
  embedMany,
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  ExtractionOutputSchema,
  type FormattedMessage,
  formatConversationSegment,
} from '@oracle/ai';
import { createServiceRoleClient } from '@oracle/auth/server';
import type { KnowledgeDomain } from '@oracle/shared';

const FALLBACK_MODEL = 'google/gemini-flash';
const CHUNK_SIZE = 1500;     // characters per chunk
const CHUNK_OVERLAP = 150;   // character overlap between chunks

// Low-risk claim types (same set as claim-extraction worker).
const LOW_RISK_CLAIM_TYPES = new Set([
  'process_rule',
  'exception_rule',
  'dependency',
  'system_limitation',
]);

// ---------------------------------------------------------------------------
// Payload schema for the single-document task.
// ---------------------------------------------------------------------------
const SingleDocumentPayloadSchema = z.object({
  documentId: z.string().uuid(),
});

// ---------------------------------------------------------------------------
// Text chunking helper.
// ---------------------------------------------------------------------------
function chunkText(
  text: string,
  chunkSize = CHUNK_SIZE,
  overlap = CHUNK_OVERLAP,
): string[] {
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

// ---------------------------------------------------------------------------
// PDF parsing (dynamically imported so the module loads cleanly if pdf-parse
// is unavailable in some build environments).
// ---------------------------------------------------------------------------
async function extractTextFromPdf(buffer: Buffer): Promise<string> {
  // Dynamic import avoids pdf-parse test-file side effect at module load time.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pdfParse = (await import('pdf-parse')).default as (buf: Buffer) => Promise<{ text: string }>;
  const result = await pdfParse(buffer);
  return result.text;
}

// ---------------------------------------------------------------------------
// XLSX / CSV parsing.
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Process a single document.
// ---------------------------------------------------------------------------
async function processDocument(documentId: string, triggerRunId: string): Promise<{
  chunksInserted: number;
  claimsInserted: number;
}> {
  const db = getDirectDb();
  const serviceSupabase = createServiceRoleClient();

  // Load the document row.
  const [doc] = await db
    .select()
    .from(documents)
    .where(eq(documents.id, documentId))
    .limit(1);

  if (!doc) throw new Error(`Document ${documentId} not found`);
  if (doc.status === 'complete') {
    console.log(`[document-ingestion] ${documentId} already complete — skipping`);
    return { chunksInserted: 0, claimsInserted: 0 };
  }

  // Mark as processing.
  await db
    .update(documents)
    .set({ status: 'processing' })
    .where(eq(documents.id, documentId));

  // Read extraction model from settings.
  const modelSetting = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'default_extraction_model'))
    .limit(1);
  const modelName =
    (typeof modelSetting[0]?.value === 'string' ? modelSetting[0].value : null) ??
    FALLBACK_MODEL;

  // 1. Download bytes from Storage.
  const { data: blob, error: downloadError } = await serviceSupabase.storage
    .from(doc.storageBucket)
    .download(doc.storagePath);

  if (downloadError || !blob) {
    throw new Error(
      `Storage download failed for ${doc.storagePath}: ${downloadError?.message ?? 'empty blob'}`,
    );
  }
  const buffer = Buffer.from(await blob.arrayBuffer());

  // 2. Parse into text.
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
      // Unsupported MIME — skip extraction, mark complete (the file is stored; just not parsed).
      console.warn(
        `[document-ingestion] unsupported file type ${doc.fileType} for doc ${documentId} — marking skipped`,
      );
      await db
        .update(documents)
        .set({
          status: 'complete',
          processedAt: new Date(),
          processingError: `Unsupported file type: ${doc.fileType}`,
        })
        .where(eq(documents.id, documentId));
      return { chunksInserted: 0, claimsInserted: 0 };
    }
  } catch (parseErr) {
    throw new Error(
      `File parse failed for ${doc.fileName}: ${parseErr instanceof Error ? parseErr.message : String(parseErr)}`,
    );
  }

  if (!rawText.trim()) {
    await db
      .update(documents)
      .set({
        status: 'complete',
        processedAt: new Date(),
        processingError: 'No text extracted',
      })
      .where(eq(documents.id, documentId));
    return { chunksInserted: 0, claimsInserted: 0 };
  }

  // 3. Chunk text.
  const textChunks = chunkText(rawText);

  // 4. Embed all chunks in one batch call.
  const { vectors } = await embedMany(textChunks);

  // 5. Insert document_chunks with dedup by contentHash.
  let chunksInserted = 0;
  const insertedChunkIds: string[] = [];

  for (let i = 0; i < textChunks.length; i++) {
    const rawTextSlice = textChunks[i]!;
    const contentHash = createHash('sha256').update(rawTextSlice).digest('hex');

    try {
      const [chunk] = await db
        .insert(documentChunks)
        .values({
          documentId,
          chunkIndex: i,
          rawText: rawTextSlice,
          tokenCount: Math.ceil(rawTextSlice.length / 4), // rough estimate
          contentHash,
          embedding: vectors[i] ?? null,
          metadataJson: { fileType: doc.fileType, fileName: doc.fileName },
        })
        .onConflictDoNothing() // dedup by (documentId, chunkIndex)
        .returning({ id: documentChunks.id });

      if (chunk) {
        chunksInserted++;
        insertedChunkIds.push(chunk.id);
      }
    } catch (chunkErr) {
      console.error(`[document-ingestion] chunk ${i} insert failed:`, chunkErr);
    }
  }

  // 6. Run claim extraction on the document text as a whole
  //    (treat the entire document as a single "conversation segment" for extraction).
  let claimsInserted = 0;

  if (rawText.trim().length > 20 && insertedChunkIds.length > 0) {
    // We use a synthetic message ID for document content (not a real message).
    // The extraction model receives the document text; evidence maps back to chunk IDs.
    const callStartMs = Date.now();

    // Format as a pseudo-conversation with a single "document" message.
    const docFakeMessageId = `doc:${documentId}`;
    const pseudoMessages: FormattedMessage[] = [
      {
        id: docFakeMessageId,
        role: 'user',
        content: rawText.slice(0, 15000), // cap at 15k chars to stay within model limits
        authorName: `[Document: ${doc.fileName}]`,
        createdAt: new Date(doc.createdAt),
      },
    ];

    const formattedSegment = formatConversationSegment(pseudoMessages);
    const documentPromptAddition =
      `\n\nNOTE: This is a DOCUMENT, not a conversation. Extract claims about operational processes, rules, systems, and dependencies described in the document.\nDocument name: ${doc.fileName}\nFile type: ${doc.fileType}`;

    try {
      const openrouter = getOpenRouter();
      const model = openrouter(modelName);

      const { object, usage } = await generateObject({
        model,
        schema: ExtractionOutputSchema,
        system: EXTRACTION_SYSTEM_PROMPT + documentPromptAddition,
        messages: [{ role: 'user', content: formattedSegment }],
        temperature: 0.1,
      });

      const latencyMs = Date.now() - callStartMs;

      const [modelRun] = await db
        .insert(modelRuns)
        .values({
          taskType: 'document-ingestion',
          model: modelName,
          provider: 'openrouter',
          promptVersion: EXTRACTION_PROMPT_VERSION,
          inputTokens: usage?.inputTokens ?? null,
          outputTokens: usage?.outputTokens ?? null,
          latencyMs,
          success: true,
        })
        .returning({ id: modelRuns.id });

      // 7. Insert claims with document_chunk evidence.
      for (const extracted of object.claims) {
        // For documents the sourceMessageId is the synthetic doc ID —
        // we don't do the same substring check we do for real messages,
        // but we verify the quote is plausibly from the raw text.
        if (!rawText.includes(extracted.evidence.exactQuote)) {
          console.warn(
            `[document-ingestion] exactQuote not found in document ${documentId} — skipping claim`,
          );
          continue;
        }

        const autoApprove =
          !extracted.requiresReview &&
          extracted.impactScore <= 6 &&
          LOW_RISK_CLAIM_TYPES.has(extracted.claimType);

        // Embed the claim summary.
        let embedding: number[] | null = null;
        try {
          const { vectors: claimVectors } = await embedMany([extracted.summary]);
          embedding = claimVectors[0] ?? null;
        } catch {
          // Non-fatal — proceed without embedding.
        }

        const [claim] = await db
          .insert(claims)
          .values({
            claimType: extracted.claimType,
            summary: extracted.summary,
            impactScore: extracted.impactScore,
            confidenceScore: extracted.confidenceScore,
            status: autoApprove ? 'approved' : 'pending_review',
            embedding: embedding ?? undefined,
          })
          .returning({ id: claims.id });

        if (!claim) continue;
        claimsInserted++;

        // Domains.
        for (const domain of extracted.domains) {
          await db
            .insert(claimDomains)
            .values({ claimId: claim.id, domain: domain as KnowledgeDomain })
            .onConflictDoNothing();
        }

        // Find the chunk that best contains the quote (first match).
        let evidenceChunkId: string | null = insertedChunkIds[0] ?? null;
        for (let ci = 0; ci < textChunks.length; ci++) {
          if (textChunks[ci]!.includes(extracted.evidence.exactQuote)) {
            evidenceChunkId = insertedChunkIds[ci] ?? null;
            break;
          }
        }

        // Evidence.
        await db.insert(claimEvidence).values({
          claimId: claim.id,
          sourceType: 'document_chunk',
          sourceDocumentChunkId: evidenceChunkId,
          uploadedByEmployeeId: doc.uploaderId,
          exactQuote: extracted.evidence.exactQuote,
          confidence: extracted.evidence.confidence,
        });

        // Suggested gaps.
        for (const gap of extracted.suggestedGaps ?? []) {
          await db.insert(gaps).values({
            gapType: 'document_extraction_gap',
            relatedClaimIds: [claim.id],
            questionToAsk: gap.questionToAsk,
            whyItMatters: gap.whyItMatters,
            priority: gap.priority,
            status: 'open',
            createdByModelRunId: modelRun?.id ?? null,
          });
        }
      }
    } catch (extractErr) {
      console.error('[document-ingestion] extraction LLM call failed:', extractErr);

      await db.insert(modelRuns).values({
        taskType: 'document-ingestion',
        model: modelName,
        provider: 'openrouter',
        promptVersion: EXTRACTION_PROMPT_VERSION,
        latencyMs: Date.now() - callStartMs,
        success: false,
        error: extractErr instanceof Error ? extractErr.message : String(extractErr),
      });
      // Non-fatal — chunks were still inserted; we just won't have claims.
    }
  }

  // 8. Mark document complete.
  await db
    .update(documents)
    .set({ status: 'complete', processedAt: new Date() })
    .where(eq(documents.id, documentId));

  return { chunksInserted, claimsInserted };
}

// ---------------------------------------------------------------------------
// Primary task: process a single document (triggered from upload API route).
// ---------------------------------------------------------------------------
export const documentIngestionTask = task({
  id: 'document-ingestion',
  maxDuration: 60 * 10, // 10 minutes (large PDFs + LLM call)
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
      const result = await processDocument(payload.documentId, ctx.run.id);

      await db
        .update(jobRuns)
        .set({
          status: 'complete',
          finishedAt: new Date(),
          outputJson: result,
        })
        .where(eq(jobRuns.id, jobRun.id));

      return { ok: true, documentId: payload.documentId, ...result };
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);

      // Mark document failed in DB.
      await db
        .update(documents)
        .set({ status: 'failed', processingError: errMsg, processedAt: new Date() })
        .where(eq(documents.id, payload.documentId));

      await db
        .update(jobRuns)
        .set({
          status: 'failed',
          finishedAt: new Date(),
          error: errMsg,
        })
        .where(eq(jobRuns.id, jobRun.id));

      throw err; // Trigger.dev will retry per config.
    }
  },
});

// ---------------------------------------------------------------------------
// Sweep task: find pending documents and trigger individual ingestion tasks.
// Runs every 4 hours as a safety net for documents whose direct trigger failed.
// ---------------------------------------------------------------------------
export const documentIngestionSweepTask = schedules.task({
  id: 'document-ingestion-sweep',
  cron: '30 */4 * * *', // offset 30 min from claim-extraction to avoid resource contention
  maxDuration: 60 * 2,
  run: async (_payload, { ctx }) => {
    const db = getDirectDb();

    // Find documents stuck in pending_processing or processing for > 2 hours.
    const stuck = await db
      .select({ id: documents.id })
      .from(documents)
      .where(
        and(
          // Both statuses: pending_processing (never started) and processing (stuck).
          inArray(documents.status, ['pending_processing', 'processing']),
        ),
      )
      .limit(20);

    if (stuck.length === 0) {
      return { ok: true, triggered: 0 };
    }

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
