// R7 — Document ingestion worker (refactored through OracleAIClient + staging).
//
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R7.
//
// What changed vs the legacy worker:
//   - Model calls go through OracleAIClient (R2) via direct provider adapters
//     (Vertex / Anthropic / OpenAI raw SDKs — DECISIONS.md D6 / D9) using
//     the curated route ID from `settings.default_extraction_route`. R7
//     ships the explicit-cache profitability heuristic +
//     provider_cached_content lifecycle bookkeeping and releases document-owned
//     explicit Vertex caches once extraction/follow-up dispatch finishes.
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
import { and, desc, eq, inArray } from 'drizzle-orm';
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
  sourceGroups,
  sourceOutlineSources,
  sourceOutlines,
  type OracleDb,
} from '@oracle/db';
import {
  OracleAIClient,
  buildStandardAdapters,
  embedMany,
  resolveRouteCandidates,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  releaseVertexExplicitCaches,
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  ExtractionOutputSchema,
  loadClaimCorrectionLessonPack,
  type ExtractionOutput,
  type OracleModelRoute,
  type RouteCandidate,
  type OraclePromptPlan,
} from '@oracle/ai';
import {
  computeCandidateHash,
  executePromotion,
  mapLegacyDomainsToTopDomains,
  MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
  stageEntityProposal,
  validateQuote,
  validateSourcePointer,
  validateTaxonomy,
  AdvisoryLockBusyError,
  type RegistryEntity,
} from '@oracle/engines';
import { createServiceRoleClient } from '@oracle/auth/server';
import type { EntityType, KnowledgeDomain, TopLevelDomainId } from '@oracle/shared';
import { autoApproveDocumentClaimIfEligible } from '../lib/document-claim-auto-approval';

const CHUNK_SIZE = 4000;
// Extraction-window budget: how much chunk text a single extraction call sees.
// Meaning lives in CONTEXT that spans chunk boundaries — a multi-paragraph SOP
// rule, a debated decision, and (worst case) a diagram whose meaning is entirely
// in cross-node arrows. Narrow windows extracted independently fragment that
// context, so we keep windows wide. Quote validation is unaffected —
// pickEvidenceChunk maps each verbatim quote back to its covering chunk.
const MAX_DOCUMENT_TEXT_CHARS = 24_000;
// Image transcriptions (especially diagrams/flowcharts) are one connected graph;
// give them an even wider window so the whole flow is reasoned over in one call.
const MAX_IMAGE_TEXT_CHARS = 32_000;
// Vision (Pass 1) sampling. A *thinking* VL model (e.g. qwen3-vl-*-thinking)
// spends a reasoning trace BEFORE the transcription text, so the output cap must
// be high or it truncates mid-thought (a dense diagram transcription alone is
// ~3-4k tokens). Temperature is non-zero on purpose: Qwen recommends AGAINST
// greedy decoding for thinking models (temp 0 → repetition loops); 0.6 is their
// guidance. Format consistency is enforced by the prompt, not by temperature.
const VISION_MAX_OUTPUT_TOKENS = 32_000;
const VISION_TEMPERATURE = 0.6;
// Extraction output budget. A dense window (a diagram with many handoffs) can
// produce dozens of claims; without a generous cap the JSON truncates mid-array,
// parses as a raw string, and fails the schema ("expected object").
const EXTRACTION_MAX_OUTPUT_TOKENS = 32_000;
const VERTEX_FILE_CACHE_MIN_BYTES = 10 * 1024 * 1024;

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
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Text helpers
// ─────────────────────────────────────────────────────────────────────────

interface TextChunk {
  text: string;
  /** Inclusive start offset into the source rawText. */
  start: number;
  /** Exclusive end offset into the source rawText. */
  end: number;
}

type InsertedDocumentChunk = TextChunk & { id: string };

/**
 * Offsets where a new chunk is ALLOWED to start, in increasing order (always
 * includes 0). Boundaries are semantic seams: the start of the line after a
 * blank-line gap, and the start of any heading line (`### …`, `#### …`, or a
 * numbered section like `2. ### …`). Splitting on these keeps a paragraph, a
 * numbered process section, or a swimlane block intact instead of severing it.
 */
function computeStructuralBoundaries(text: string): number[] {
  const set = new Set<number>([0]);
  // Alt 1: a blank-line gap → boundary is the start of the following line.
  // Alt 2: a newline immediately before a heading line → boundary at the heading.
  const re = /\n[ \t]*\n|\n(?=[ \t]*(?:\d+\.\s+)?#{1,6}\s)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    set.add(m.index + m[0].length);
  }
  return [...set].sort((a, b) => a - b);
}

/**
 * Structure-aware chunker. Packs text up to `chunkSize`, but cuts only at
 * semantic boundaries (headings / paragraph breaks; then line breaks; only a
 * single over-long line forces a hard char cut). Chunks stay contiguous and
 * non-overlapping with exact offsets into the source text, so the persisted
 * `document_chunks` and `pickEvidenceChunk`'s offset math keep working. This
 * replaces the byte-slice fallback that could sever a flowchart arrow line or a
 * sentence mid-word.
 */
function chunkTextStructured(text: string, chunkSize = CHUNK_SIZE): TextChunk[] {
  if (text.length <= chunkSize) return [{ text, start: 0, end: text.length }];
  const boundaries = computeStructuralBoundaries(text);
  const chunks: TextChunk[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const hardEnd = Math.min(cursor + chunkSize, text.length);
    if (hardEnd >= text.length) {
      chunks.push({ text: text.slice(cursor, text.length), start: cursor, end: text.length });
      break;
    }
    // Latest structural boundary that fits in (cursor, hardEnd].
    let cut = -1;
    for (const b of boundaries) {
      if (b > cursor && b <= hardEnd) cut = b;
      else if (b > hardEnd) break;
    }
    if (cut === -1) {
      // No structural seam fits — fall back to the latest line break, then a
      // hard char cut for a single line longer than chunkSize.
      const nl = text.slice(cursor, hardEnd).lastIndexOf('\n');
      cut = nl > 0 ? cursor + nl + 1 : hardEnd;
    }
    chunks.push({ text: text.slice(cursor, cut), start: cursor, end: cut });
    cursor = cut;
  }
  return chunks;
}

function formatDocumentChunksForExtraction(chunks: Array<{ id: string; text: string }>): string {
  const parts: string[] = [];
  for (const chunk of chunks) {
    const header = `DOCUMENT CHUNK\nDocument Chunk ID: ${chunk.id}\nContent:\n`;
    const footer = '\n---\n';
    parts.push(`${header}${chunk.text}${footer}`);
  }
  return parts.join('\n');
}

function buildDocumentChunkWindows<TChunk extends { id: string; text: string }>(
  chunks: TChunk[],
  maxChars = MAX_DOCUMENT_TEXT_CHARS,
): Array<{ chunks: TChunk[]; content: string }> {
  const windows: Array<{ chunks: TChunk[]; content: string }> = [];
  let current: TChunk[] = [];

  for (const chunk of chunks) {
    const next = [...current, chunk];
    const nextContent = formatDocumentChunksForExtraction(next);
    if (current.length > 0 && nextContent.length > maxChars) {
      windows.push({ chunks: current, content: formatDocumentChunksForExtraction(current) });
      current = [chunk];
    } else {
      current = next;
    }
  }

  if (current.length > 0) {
    windows.push({ chunks: current, content: formatDocumentChunksForExtraction(current) });
  }

  return windows;
}

async function extractTextFromPdf(buffer: Buffer): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pdfParse = (await import('pdf-parse')).default as (
    buf: Buffer,
  ) => Promise<{ text: string }>;
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

const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

const IMAGE_TRANSCRIPTION_SYSTEM = `You are a meticulous visual analyst for an operations knowledge base. You will be shown ONE image an employee uploaded. Produce a faithful, self-contained TEXT rendering of everything the image conveys. Downstream extraction reads ONLY your text — it cannot see the image — and it quotes your text verbatim, so it must be able to reconstruct both the content and the structure from your output alone.

1. TRANSCRIBE ALL TEXT VERBATIM
Reproduce every piece of visible text exactly as written — labels, headings, every table cell, captions, callouts, stamps, axis labels, legends, handwriting. Never paraphrase, summarize, or normalize wording.

2. RENDER STRUCTURE AS A TEXT TOPOLOGY (not free-form prose)
When the image contains a diagram, flowchart, org chart, decision tree, map, or schematic, encode its topology so relationships are unambiguous:
- Nodes:  [Shape/Color: "verbatim label"]   e.g.  [Blue Diamond: "Credit Check"]
- Edges:  CRITICAL — write EACH connection as ONE self-contained line that contains the FULL source node, the arrow (with its label/color/style if any), AND the full target node, e.g.
          [Blue Diamond: "Credit Check"] --(Red Arrow: "If Score < 600")--> [Gray Box: "Trigger Manual Deny Email"]
  NEVER split a connection across multiple lines, and NEVER put a node on one line and its outgoing arrow/target on the next line. A connection that spans two lines is wrong.
- If one node has several outgoing connections, write ONE complete edge line per connection and REPEAT the full source node on each line.
- Group swimlanes / columns / sections under headers, e.g.  ### Swimlane: Finance Department
Keep the verbatim label text INSIDE the node brackets so it stays exactly quotable. Downstream extraction quotes a WHOLE edge line verbatim to record a handoff, so a complete single-line edge is what lets a relationship become a validated claim — a split edge cannot be quoted and is lost.

3. TABLES
Render as text preserving rows and columns — one row per line, columns separated consistently, including the header row.

4. READING ORDER & GROUPING
Present content in natural reading order. Use headers to mark spatial groups, sequence, or hierarchy when they carry meaning.

5. OPERATIONAL CONTENT
Ensure concrete rules, steps, routing, ownership, dates, quantities, statuses, conditions, and exceptions are explicit.

Rules:
- Do NOT invent anything that is not visible. If something is unreadable or ambiguous, write [unreadable] or note the ambiguity — never guess.
- Output plain text only. You MAY use the simple structural markers above (### headers, the [Node] --(edge)--> [Node] notation, table rows). Do NOT use code fences, and do NOT add commentary or preamble such as "Here is".`;

/**
 * Build the vision-pass user content with a PROVIDER-NEUTRAL inline image part:
 * `{ type:'image', mimeType, data }`. Each adapter translates this to its own
 * native shape AT DISPATCH (OpenAI/Qwen/DeepSeek → `image_url`, Anthropic →
 * base64 source block, Gemini/Vertex → inlineData).
 *
 * Why neutral and not provider-shaped here: the route can change between this
 * call and actual dispatch (ModelRouter falls back on error). Shaping the image
 * for the pre-dispatch provider meant a fallback to a different provider got a
 * payload its adapter couldn't read, so the image was silently dropped and the
 * model confabulated. Letting the dispatching adapter own the translation makes
 * fallback safe.
 */
function buildVisionMessageContent(
  mimeType: string,
  base64: string,
  requestText: string,
): Array<Record<string, unknown>> {
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
  const resolution = await resolveRouteCandidates(db, 'vision');
  for (const skipped of resolution.skipped) {
    console.error(
      `[document-ingestion] skipped configured vision candidate ${skipped.modelIdOrRouteId}: ${skipped.reason}`,
    );
  }
  const routeCandidates = resolution.candidates;
  const route = routeCandidates[0]!.route;
  const mimeType = imageMimeFor(doc.fileType, doc.fileName);
  const contextLine =
    doc.context && doc.context.trim()
      ? ` Context from the uploader about this image: "${doc.context.trim()}". Use it to interpret ambiguous labels, but transcribe only what is actually visible - do not add details that are not in the image.`
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

  const callStartedAt = Date.now();
  const result = await client.runText({
    taskType: 'document_claim_extraction',
    routeId: route.routeId,
    promptVersion: EXTRACTION_PROMPT_VERSION,
    blocks,
    providerOptions: {
      cache: { disableCache: true },
      temperature: VISION_TEMPERATURE,
      maxOutputTokens: VISION_MAX_OUTPUT_TOKENS,
      highResolutionVision: true,
      messages: [
        {
          role: 'user',
          content: buildVisionMessageContent(mimeType, buffer.toString('base64'), requestText),
        },
      ],
    },
    routeCandidates,
  });

  const actualProvider = result.provider ?? route.provider;
  const actualModel = result.modelId ?? route.modelId;
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'document-ingestion-vision',
      model: actualModel,
      provider: actualProvider,
      promptVersion: EXTRACTION_PROMPT_VERSION,
      inputTokens: result.usage?.inputTokens ?? null,
      outputTokens: result.usage?.outputTokens ?? null,
      latencyMs: Date.now() - callStartedAt,
      success: true,
    })
    .returning({ id: modelRuns.id })
    .catch((e) => {
      console.error('[document-ingestion] failed to record vision model_run', e);
      return [];
    });

  if (modelRun?.id) {
    await logModelRunAttempts({
      db,
      metadata: result,
      taskType: 'document-ingestion-vision',
      slot: 'vision',
      modelRunId: modelRun.id,
    }).catch((e) =>
      console.error('[document-ingestion] failed to record vision model attempts', e),
    );
  }

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
  if (fileType.startsWith('text/') || ['txt', 'md', 'markdown', 'vtt'].includes(ext)) {
    return 'text';
  }
  return 'unsupported';
}

/**
 * Heuristic: does an image transcription look like a diagram (flowchart, swimlane
 * map, decision tree) rather than a plain screenshot of prose? The vision prompt
 * renders diagrams with `[Lane: "label"]` nodes, `--(Arrow: "…")-->` edges, and
 * `### Swimlane` headers, so their presence is a strong signal. Drives a
 * relationship-first extraction addendum instead of the box-by-box default.
 */
function looksLikeDiagramTranscription(text: string): boolean {
  return /-->/.test(text) || /--\(Arrow/i.test(text) || /###\s*Swimlane/i.test(text);
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
  claimsAutoApproved: number;
  duplicatesAppended: number;
  rejections: number;
}

type ExtractedClaim = ExtractionOutput['claims'][number];

async function processDocument(
  documentId: string,
  jobRunId: string,
): Promise<ProcessDocumentResult> {
  const db = getDirectDb();
  const client = buildOracleClient();
  const serviceSupabase = createServiceRoleClient();
  const outcome: ProcessDocumentResult = {
    chunksInserted: 0,
    candidatesStaged: 0,
    claimsPromoted: 0,
    claimsAutoApproved: 0,
    duplicatesAppended: 0,
    rejections: 0,
  };
  const documentExtractionCacheSourceHashes = new Set<string>();

  // 1. Load + mark processing.
  const [doc] = await db.select().from(documents).where(eq(documents.id, documentId)).limit(1);
  if (!doc) throw new Error(`Document ${documentId} not found`);
  if (doc.status === 'complete') {
    console.log(`[document-ingestion] ${documentId} already complete — skipping`);
    return outcome;
  }
  await db
    .update(documents)
    .set({ status: 'processing', processingError: null, processedAt: null })
    .where(eq(documents.id, documentId));

  const parseKind = resolveParseKind(doc.fileType, doc.fileName);
  const routeCandidates = await resolveExtractionCandidates(db);
  const route = routeCandidates[0]!.route;
  const activeTopDomainIds = await loadActiveTopDomainIds(db);
  const topDomainNameMap = await loadTopDomainNameMap(db);
  const entityRegistry = await loadEntityRegistry(db);
  const correctionLessons = await loadClaimCorrectionLessonPack(db);

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
      if (fileBackedCachePath) {
        await unlink(fileBackedCachePath).catch(() => undefined);
      }
      return outcome;
    }
  } catch (parseErr) {
    if (fileBackedCachePath) {
      await unlink(fileBackedCachePath).catch(() => undefined);
    }
    throw new Error(
      `File parse failed for ${doc.fileName}: ${parseErr instanceof Error ? parseErr.message : String(parseErr)}`,
    );
  }

  if (!rawText.trim()) {
    await db
      .update(documents)
      .set({ status: 'complete', processedAt: new Date(), processingError: 'No text extracted' })
      .where(eq(documents.id, documentId));
    if (fileBackedCachePath) {
      await unlink(fileBackedCachePath).catch(() => undefined);
    }
    return outcome;
  }

  // 4. Chunk + embed + insert chunks (idempotent dedup by content hash).
  //    Structure-aware: cut on headings/paragraphs/lines, never mid-line, so a
  //    flowchart arrow line or a sentence is never severed across chunks.
  const textChunks = chunkTextStructured(rawText);
  let chunkVectors: (number[] | null)[] = [];
  // Track degraded outcomes so they are SURFACED on the document, not hidden:
  // chunks stored without embeddings are invisible to semantic retrieval, and a
  // failed chunk insert means lost text — both previously only console.warn'd.
  let embeddingDegraded = false;
  let chunkInsertFailures = 0;
  try {
    const { vectors } = await embedMany(textChunks.map((c) => c.text));
    chunkVectors = vectors;
  } catch (embedErr) {
    embeddingDegraded = true;
    console.error(
      '[document-ingestion] EMBED FAILED — chunks will be stored WITHOUT vectors and will not be ' +
        'retrievable by semantic search until re-embedded:',
      embedErr,
    );
    chunkVectors = textChunks.map(() => null);
  }

  const insertedChunkIds: InsertedDocumentChunk[] = [];
  for (let i = 0; i < textChunks.length; i++) {
    const chunkTextWindow = textChunks[i]!;
    const contentHash = createHash('sha256').update(chunkTextWindow.text).digest('hex');
    try {
      const [chunk] = await db
        .insert(documentChunks)
        .values({
          documentId,
          chunkIndex: i,
          rawText: chunkTextWindow.text,
          tokenCount: Math.ceil(chunkTextWindow.text.length / 4),
          contentHash,
          embedding: chunkVectors[i] ?? null,
          metadataJson: { fileType: doc.fileType, fileName: doc.fileName },
        })
        .onConflictDoNothing()
        .returning({ id: documentChunks.id });
      if (chunk) {
        outcome.chunksInserted += 1;
        insertedChunkIds.push({ id: chunk.id, ...chunkTextWindow });
      } else {
        const [existingChunk] = await db
          .select({ id: documentChunks.id })
          .from(documentChunks)
          .where(
            and(
              eq(documentChunks.documentId, documentId),
              eq(documentChunks.contentHash, contentHash),
            ),
          )
          .limit(1);
        if (existingChunk) {
          insertedChunkIds.push({ id: existingChunk.id, ...chunkTextWindow });
        }
      }
    } catch (chunkErr) {
      chunkInsertFailures += 1;
      console.error(`[document-ingestion] chunk ${i} insert failed (text will be lost):`, chunkErr);
    }
  }

  if (insertedChunkIds.length === 0 || rawText.trim().length <= 20) {
    await db
      .update(documents)
      .set({ status: 'complete', processedAt: new Date() })
      .where(eq(documents.id, documentId));
    if (fileBackedCachePath) {
      await unlink(fileBackedCachePath).catch(() => undefined);
    }
    return outcome;
  }

  // 5. Process every chunk window. Each model call is bounded, but the
  // document itself is not silently truncated.
  const extractionWindows = buildDocumentChunkWindows(
    insertedChunkIds,
    parseKind === 'image' ? MAX_IMAGE_TEXT_CHARS : MAX_DOCUMENT_TEXT_CHARS,
  );
  const outlineContext = await loadDocumentOutlineContext(db, documentId).catch((err) => {
    console.warn(
      '[document-ingestion] source outline context unavailable; continuing without it',
      err,
    );
    return null;
  });
  for (let windowIndex = 0; windowIndex < extractionWindows.length; windowIndex++) {
    const extractionWindow = extractionWindows[windowIndex]!;
    const windowChunks = extractionWindow.chunks;
    const documentCorpus = extractionWindow.content;
    const sourceHash = createHash('sha256').update(documentCorpus, 'utf8').digest('hex');
    documentExtractionCacheSourceHashes.add(sourceHash);
    const [batch] = await db
      .insert(extractionBatches)
      .values({
        jobRunId,
        batchType: 'document_page',
        status: 'pending_model',
        sourceDocumentChunkIds: windowChunks.map((c) => c.id),
        sourceHash,
        modelRunIdsAttempted: [],
        routeIdsAttempted: [route.routeId],
      })
      .returning({ id: extractionBatches.id });
    if (!batch) throw new Error('[document-ingestion] failed to insert extraction_batches row');

    // 6. Compile prompt + context pack. The document text becomes the dynamic
    //    block; the extraction system prompt + the document-specific addendum
    //    are stable.
    const isDiagram = parseKind === 'image' && looksLikeDiagramTranscription(rawText);
    const baseDocumentNote =
      parseKind === 'image'
        ? isDiagram
          ? `\n\nNOTE: The text below is a VISION-MODEL TRANSCRIPTION of an uploaded DIAGRAM (flowchart / swimlane / process map). Nodes are written as [Lane/Color: "label"] and connections as [A] --(Arrow: "condition")--> [B]. The MEANING of this document is the FLOW — who hands off to whom, in what sequence, and under which conditions — NOT the existence of individual boxes.\nImage name: ${doc.fileName}\nFile type: ${doc.fileType}\n\nDIAGRAM EXTRACTION GUIDANCE:\n- Prefer claims that capture HANDOFFS and SEQUENCE. Represent each arrow as a dependency claim — "After/from X, Y happens" or "X is handed off to <role/lane> who does Y" — and include the arrow's condition label when one is present.\n- Capture DECISION/BRANCH rules (e.g. "If Audit: Fail", "Existing Product" vs "New Product Type", "Before an Order") as exception or process rules that state the condition AND the resulting path.\n- Record OWNERSHIP only when it adds information (which lane/role performs a step). Do NOT emit a separate claim for every box: a bare node label with no relationship is low-value — fold it into the handoff claim it participates in.\n- Aim for fewer, higher-altitude, CONNECTED claims rather than many disconnected "box X exists" statements.\n- Every exactQuote must still be copied verbatim from within ONE provided document chunk. For a handoff, quote the full \`[A] --(Arrow: "…")--> [B]\` line; for a branch, quote the line that contains the condition.`
          : `\n\nNOTE: The text below is a VISION-MODEL TRANSCRIPTION of an uploaded image (not a conversation, not a native text document). Extract claims about operational processes, rules, systems, and dependencies that are explicitly supported by this transcription.\nImage name: ${doc.fileName}\nFile type: ${doc.fileType}`
        : `\n\nNOTE: This is a DOCUMENT, not a conversation. Extract claims about operational processes, rules, systems, and dependencies described in the document.\nDocument name: ${doc.fileName}\nFile type: ${doc.fileType}\n\nDOCUMENT EXTRACTION DENSITY:\n- If the document is an SOP, checklist, responsibility list, training guide, or numbered/bulleted workflow, treat each actionable responsibility, required input, required output, system update, file-save rule, approval step, exception, handoff, or escalation as its own candidate claim when it has distinct evidence.\n- Do not summarize an entire section into one broad claim when the section contains multiple concrete steps.\n- It is acceptable and expected for a dense responsibilities document to produce many small claims from one chunk.`;
    const documentNote = baseDocumentNote + buildUploaderContextNote(doc, topDomainNameMap);
    const blocks = [
      makeBlock({
        id: 'extraction-system',
        label: 'Extraction system prompt + document addendum',
        kind: 'stable_system',
        content: EXTRACTION_SYSTEM_PROMPT + documentNote,
        reasonIncluded: 'extraction prompt v' + EXTRACTION_PROMPT_VERSION + ' (document mode)',
      }),
      ...(correctionLessons.promptBlock
        ? [
            makeBlock({
              id: 'reviewer-correction-lessons',
              label: 'Approved reviewer correction lessons',
              kind: 'semi_stable_domain_context' as const,
              content: correctionLessons.promptBlock,
              reasonIncluded: 'approved claim revisions teach extraction corrections',
            }),
          ]
        : []),
      ...(outlineContext
        ? [
            makeBlock({
              id: 'source-outline-guidance',
              label: 'Provisional source outline',
              kind: 'semi_stable_domain_context' as const,
              content: outlineContext,
              reasonIncluded: 'macro source outline guidance only; not valid evidence for claims',
            }),
          ]
        : []),
      makeBlock({
        id: 'document-text',
        label: 'Document chunks',
        kind: 'retrieved_context',
        content: documentCorpus,
        reasonIncluded: `window ${windowIndex + 1}/${extractionWindows.length}: ${windowChunks.length} chunks → formatted to ${documentCorpus.length} chars`,
      }),
      makeBlock({
        id: 'document-request',
        label: 'Document extraction request',
        kind: 'dynamic_input',
        content:
          'Read the document chunks as a whole, infer the operational process flow they describe, and extract dense, evidence-backed operational claims. For SOP/checklist/responsibility-list text, extract each concrete actionable step or handoff as a separate claim; do not collapse a numbered list or section into one broad summary. Classify by meaning and handoff structure, not by literal keywords. Every exactQuote must be copied verbatim from within ONE provided document chunk, and sourceMessageId must be that exact Document Chunk ID. Return only claims that are explicitly supported by the document text.',
        reasonIncluded:
          'small dynamic request so the document corpus can be cached as reusable prefix',
      }),
    ];
    const plan = client.compile({
      taskType: 'document_claim_extraction',
      routeId: route.routeId,
      promptVersion: EXTRACTION_PROMPT_VERSION,
      blocks,
      observability: { includedDocumentChunkIds: windowChunks.map((c) => c.id) },
    });

    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values(buildContextPackInsert(plan))
      .returning({ id: oracleContextPacks.id });
    if (!contextPack)
      throw new Error('[document-ingestion] failed to insert oracle_context_packs row');
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
        observability: { includedDocumentChunkIds: windowChunks.map((c) => c.id) },
        providerOptions: {
          maxOutputTokens: EXTRACTION_MAX_OUTPUT_TOKENS,
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
        routeCandidates,
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
      });
      await logModelRunAttempts({
        db,
        metadata: result,
        taskType: 'document-ingestion',
        slot: 'extraction',
        contextPackId: contextPack.id,
        modelRunId: modelRun.id,
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
          '[document-ingestion] model output failed Zod schema validation: ' +
            result.validation.error.message,
        );
      }
      modelOutput = result.object;
    } catch (err) {
      if (!modelRunId) {
        await logAllCandidatesFailedAttempts({
          db,
          error: err,
          taskType: 'document-ingestion',
          slot: 'extraction',
          contextPackId: contextPack.id,
        }).catch((logErr) =>
          console.error('[document-ingestion] failed to record extraction model attempts', logErr),
        );
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
      // Extraction FAILED — mark the document failed, not complete. Chunks were
      // still inserted (retrieval works at the chunk level), but reporting a
      // failed extraction as "complete" hides the failure from admins and makes
      // a broken model/route look like a successful ingest.
      await db
        .update(documents)
        .set({
          status: 'failed',
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
        const sourceIdChunk = windowChunks.find((c) => c.id === extracted.evidence.sourceMessageId);
        const chunkForEvidence = pickEvidenceChunk(
          rawText,
          extracted.evidence.exactQuote,
          windowChunks,
          sourceIdChunk,
        );

        const proposedTopDomainIds = mapLegacyDomainsToTopDomains(
          extracted.domains as KnowledgeDomain[],
        );

        const [candidate] = await db
          .insert(extractionCandidates)
          .values({
            extractionBatchId: batch.id,
            status: 'pending_validation',
            claimType: extracted.claimType,
            claimKind: extracted.claimKind ?? 'uncertain',
            claimKindConfidence: extracted.claimKindConfidence ?? 5,
            summary: extracted.summary,
            impactScore: extracted.impactScore,
            confidenceScore: extracted.confidenceScore,
            domains: proposedTopDomainIds satisfies TopLevelDomainId[],
            // P2 #1 — proposedEntities now sourced from prompt-2.x.
            proposedEntities: (extracted.proposedEntities ?? []).map((e) => ({
              entityType: e.entityType,
              rawString: e.rawString,
            })),
            // P1 #2 — sensitivityFlags now sourced from prompt-2.x.
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
          normalizationPolicy:
            parseKind === 'text' ? MARKDOWN_DOCUMENT_NORMALIZATION_POLICY : undefined,
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
            .set({
              status: 'validation_failed',
              validationError: quoteRes.detail,
              validatedAt: new Date(),
            })
            .where(eq(extractionCandidates.id, candidate.id));
          outcome.rejections += 1;
          continue;
        }

        // Taxonomy validation. proposedEntities sourced from prompt-2.x (P2 #1).
        const taxRes = validateTaxonomy({
          proposedTopDomainIds,
          activeTopDomainIds,
          proposedEntities: (extracted.proposedEntities ?? []).map((e) => ({
            entityType: e.entityType as EntityType,
            rawString: e.rawString,
          })),
          entityRegistry,
        });
        const taxonomyAllowsPromotion = taxRes.ok || taxRes.blockedByOnlyUnknownEntities;
        await db.insert(extractionValidationResults).values({
          candidateId: candidate.id,
          checkName: 'domain_valid',
          status: taxonomyAllowsPromotion ? 'pass' : 'fail',
          detail: taxRes.ok
            ? `Top-domains validated: ${taxRes.validTopDomainIds.join(', ')}`
            : taxRes.blockedByOnlyUnknownEntities
              ? `Top-domains validated: ${taxRes.validTopDomainIds.join(', ')}; unknown entity proposals staged for admin review.`
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

        if (!taxonomyAllowsPromotion) {
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
            detail:
              extracted.sensitivityFlags?.sensitivityReason ??
              'extractor flagged sensitive content',
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
                extracted.sensitivityFlags?.sensitivityReason ??
                'sensitive content flagged by extractor',
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
            const autoApproved = await autoApproveDocumentClaimIfEligible({
              db,
              candidateId: candidate.id,
              extracted,
              result,
              quoteVerdict: quoteRes.verdict,
              validTopDomainIds: taxRes.validTopDomainIds,
            });
            if (autoApproved) outcome.claimsAutoApproved += 1;

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
  }

  // Surface any degraded outcome on the document rather than reporting a clean
  // "complete". The doc is still usable (chunks/claims exist), but a reader must
  // know retrieval is degraded or some text was lost.
  const degradedNotes: string[] = [];
  if (embeddingDegraded)
    degradedNotes.push(
      'embeddings failed: chunks stored without vectors and are NOT retrievable by semantic search until re-embedded',
    );
  if (chunkInsertFailures > 0)
    degradedNotes.push(`${chunkInsertFailures} chunk insert(s) failed: that text was lost`);
  await db
    .update(documents)
    .set({
      status: 'complete',
      processingError: degradedNotes.length > 0 ? `DEGRADED — ${degradedNotes.join('; ')}` : null,
      processedAt: new Date(),
    })
    .where(eq(documents.id, documentId));

  await tasks
    .trigger('source-outline', { documentId })
    .catch((err) =>
      console.warn('[document-ingestion] failed to trigger source outline orchestration', err),
    );

  if (fileBackedCachePath) {
    await unlink(fileBackedCachePath).catch(() => undefined);
  }
  let releasedCaches = 0;
  let failedCacheReleases = 0;
  for (const extractionSourceHash of documentExtractionCacheSourceHashes) {
    const cacheRelease = await releaseVertexExplicitCaches({
      db,
      sourceHash: extractionSourceHash,
      cleanupOwner: 'document-ingestion-worker',
      createdByJobRunId: jobRunId,
      reason: 'document ingestion completed and macro followups were queued or skipped',
    });
    releasedCaches += cacheRelease.deleted;
    failedCacheReleases += cacheRelease.failed;
  }
  if (releasedCaches > 0 || failedCacheReleases > 0) {
    console.log('[document-ingestion] explicit cache release', {
      deleted: releasedCaches,
      failed: failedCacheReleases,
    });
  }

  return outcome;
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

async function resolveExtractionCandidates(db: OracleDb): Promise<RouteCandidate[]> {
  const resolved = await resolveRouteCandidates(db, 'extraction');
  for (const skipped of resolved.skipped) {
    console.error(
      `[document-ingestion] skipped configured extraction candidate ${skipped.modelIdOrRouteId}: ${skipped.reason}`,
    );
  }
  return resolved.candidates;
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
      `Treat this only as a prior — classify each claim on its own merits and do not force claims into these areas. ` +
      `If a suggested area is Business Process, represent cross-functional or end-to-end workflow claims with the general output domain.`;
  }
  return note;
}

function settingEnabled(value: unknown): boolean {
  if (value === true) return true;
  if (typeof value === 'string') return value.toLowerCase() === 'true';
  return false;
}

async function loadDocumentOutlineContext(
  db: OracleDb,
  documentId: string,
): Promise<string | null> {
  const [flag] = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'macro_outline_injection_enabled'))
    .limit(1);
  if (!settingEnabled(flag?.value)) return null;

  const [outline] = await db
    .select({
      id: sourceOutlines.id,
      summary: sourceOutlines.summary,
      outlineJson: sourceOutlines.outlineJson,
    })
    .from(sourceOutlines)
    .innerJoin(sourceOutlineSources, eq(sourceOutlineSources.sourceOutlineId, sourceOutlines.id))
    .where(
      and(
        eq(sourceOutlineSources.sourceType, 'document'),
        eq(sourceOutlineSources.documentId, documentId),
        eq(sourceOutlines.status, 'provisional'),
      ),
    )
    .orderBy(desc(sourceOutlines.createdAt))
    .limit(1);
  if (!outline) return null;

  const groups = await db
    .select({
      title: sourceGroups.title,
      groupType: sourceGroups.groupType,
      description: sourceGroups.description,
      metadataJson: sourceGroups.metadataJson,
      sortOrder: sourceGroups.sortOrder,
    })
    .from(sourceGroups)
    .where(eq(sourceGroups.sourceOutlineId, outline.id))
    .orderBy(sourceGroups.sortOrder);

  const outlineJson = outline.outlineJson as {
    recommendedLenses?: string[];
    openQuestions?: string[];
  };
  const lines = [
    'PROVISIONAL SOURCE OUTLINE (GUIDANCE ONLY; NOT CLAIM EVIDENCE)',
    'You may use this to resolve acronyms, pronouns, workflow shape, and likely extraction lenses.',
    'Never quote this outline. Every exactQuote must still come from one Document Chunk ID in the document text block.',
    '',
    `Summary: ${outline.summary ?? 'No summary.'}`,
  ];

  if (outlineJson.recommendedLenses?.length) {
    lines.push('', `Recommended lenses: ${outlineJson.recommendedLenses.join(', ')}`);
  }
  if (groups.length > 0) {
    lines.push('', 'Source groups:');
    for (const group of groups) {
      const meta = group.metadataJson as {
        recommendedLenses?: string[];
        uncertainty?: string | null;
      } | null;
      lines.push(
        `- ${group.title} (${group.groupType})${group.description ? `: ${group.description}` : ''}`,
      );
      if (meta?.recommendedLenses?.length) {
        lines.push(`  Lenses: ${meta.recommendedLenses.join(', ')}`);
      }
      if (meta?.uncertainty) {
        lines.push(`  Uncertainty: ${meta.uncertainty}`);
      }
    }
  }
  if (outlineJson.openQuestions?.length) {
    lines.push('', 'Open questions:');
    for (const question of outlineJson.openQuestions.slice(0, 8)) {
      lines.push(`- ${question}`);
    }
  }
  return lines.join('\n');
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

/**
 * Choose the document chunk to attach as the evidence pointer for a quote.
 *
 * Searches the full rawText first, then maps the match offset into the current
 * extraction window. This catches quotes that straddle chunk-overlap boundaries
 * better than checking each chunk's text independently.
 */
function pickEvidenceChunk<TChunk extends InsertedDocumentChunk>(
  rawText: string,
  exactQuote: string,
  chunks: TChunk[],
  sourceIdFallback?: TChunk,
): TChunk {
  const fallback = sourceIdFallback ?? chunks[0]!;
  if (!exactQuote) return fallback;

  let matchOffset = rawText.indexOf(exactQuote);
  if (matchOffset < 0) {
    const collapsedRaw = rawText.replace(/\s+/g, ' ');
    const collapsedQuote = exactQuote.replace(/\s+/g, ' ').trim();
    const collapsedIdx = collapsedQuote ? collapsedRaw.indexOf(collapsedQuote) : -1;
    if (collapsedIdx < 0) return fallback;
    let consumed = 0;
    for (let i = 0; i < rawText.length; i++) {
      if (consumed >= collapsedIdx) {
        matchOffset = i;
        break;
      }
      if (/\s/.test(rawText[i]!)) {
        if (i === 0 || !/\s/.test(rawText[i - 1]!)) consumed += 1;
      } else {
        consumed += 1;
      }
    }
    if (matchOffset < 0) return fallback;
  }

  const covering = chunks.find((c) => matchOffset >= c.start && matchOffset < c.end);
  return covering ?? fallback;
}

async function materializeVertexCacheTempFile(buffer: Buffer, fileName: string): Promise<string> {
  const safeName = fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
  const tempPath = join(tmpdir(), `oracle-vertex-cache-${Date.now()}-${safeName}`);
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
