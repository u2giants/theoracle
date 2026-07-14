import { config as loadEnv } from 'dotenv';
import { eq, sql } from 'drizzle-orm';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import {
  OracleAIClient,
  SOURCE_SEGMENTATION_PROMPT_VERSION,
  SOURCE_SEGMENTATION_SYSTEM_PROMPT,
  SourceSegmentationSchema,
  buildStandardAdapters,
  makeBlock,
  resolveRouteCandidates,
  type SourceSegmentationOutput,
  type SourceStructureShape,
} from '@oracle/ai';
import { messages } from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import { __sourceWorkflowReadTestHooks } from '../lib/source-workflow-read';

const repoRoot = resolve(import.meta.dirname, '..', '..', '..', '..');
loadEnv({ path: resolve(repoRoot, '.env.verify.local'), override: true });
loadEnv({ path: resolve(repoRoot, '.env.local'), override: false });
loadEnv({ path: resolve(repoRoot, '.env'), override: false });

const sourceRoot =
  process.env.ORACLE_REAL_DOC_ROOT ?? 'Z:\\Documentation\\company process - Oracle';
const chunkSize = 4_000;
const selectedFixtureNames = new Set(
  (process.env.ORACLE_SEGMENTATION_FIXTURES ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
);
const includeAllFixtures = selectedFixtureNames.size === 0;

type Fixture = {
  name: string;
  fileName: string;
  text: string;
  requiredShapes: SourceStructureShape[];
};

function computeStructuralBoundaries(text: string): number[] {
  const set = new Set<number>([0]);
  const re = /\n[ \t]*\n|\n(?=[ \t]*(?:\d+\.\s+)?#{1,6}\s)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) set.add(match.index + match[0].length);
  return [...set].sort((a, b) => a - b);
}

function chunkTextStructured(text: string): string[] {
  if (text.length <= chunkSize) return [text];
  const boundaries = computeStructuralBoundaries(text);
  const chunks: string[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const hardEnd = Math.min(cursor + chunkSize, text.length);
    if (hardEnd >= text.length) {
      chunks.push(text.slice(cursor));
      break;
    }
    let cut = -1;
    for (const boundary of boundaries) {
      if (boundary > cursor && boundary <= hardEnd) cut = boundary;
      else if (boundary > hardEnd) break;
    }
    if (cut === -1) {
      const newline = text.slice(cursor, hardEnd).lastIndexOf('\n');
      cut = newline > 0 ? cursor + newline + 1 : hardEnd;
    }
    chunks.push(text.slice(cursor, cut));
    cursor = cut;
  }
  return chunks;
}

async function extractText(fileName: string): Promise<string> {
  const path = resolve(sourceRoot, fileName);
  const buffer = await readFile(path);
  if (fileName.endsWith('.md') || fileName.endsWith('.txt')) return buffer.toString('utf8');
  if (fileName.endsWith('.pdf')) {
    const pdfParse = (await import('pdf-parse')).default as (
      input: Buffer,
    ) => Promise<{ text: string }>;
    return (await pdfParse(buffer)).text;
  }
  if (fileName.endsWith('.docx')) {
    const mammoth = (await import('mammoth')) as unknown as {
      extractRawText?: (options: { buffer: Buffer }) => Promise<{ value: string }>;
      default?: {
        extractRawText: (options: { buffer: Buffer }) => Promise<{ value: string }>;
      };
    };
    const extractRawText = mammoth.extractRawText ?? mammoth.default?.extractRawText;
    if (!extractRawText) throw new Error('mammoth.extractRawText unavailable');
    return (await extractRawText({ buffer })).value;
  }
  throw new Error(`Unsupported validation file: ${fileName}`);
}

async function loadLatestTeamsTranscript(): Promise<Fixture | null> {
  const db = getDirectDb();
  const latest = await db
    .select({ channelId: messages.channelId })
    .from(messages)
    .where(sql`${messages.metadataJson}->>'source' = 'teams_transcript'`)
    .orderBy(sql`${messages.createdAt} DESC`)
    .limit(1);
  const channelId = latest[0]?.channelId;
  if (!channelId) return null;

  const rows = await db
    .select({ content: messages.content, metadata: messages.metadataJson })
    .from(messages)
    .where(eq(messages.channelId, channelId))
    .orderBy(messages.createdAt);
  const text = rows
    .map((row) => {
      const metadata = (row.metadata ?? {}) as Record<string, unknown>;
      const speaker =
        (typeof metadata.speakerName === 'string' && metadata.speakerName) ||
        (typeof metadata.speaker === 'string' && metadata.speaker) ||
        'Speaker';
      return `${speaker}: ${row.content}`;
    })
    .join('\n');
  if (!text.trim()) return null;
  return {
    name: 'latest-ingested-teams-transcript',
    fileName: `database-channel-${channelId}`,
    text,
    requiredShapes: ['conversation'],
  };
}

async function runFixture(
  fixture: Fixture,
  client: OracleAIClient,
  routeCandidates: Awaited<ReturnType<typeof resolveRouteCandidates>>['candidates'],
) {
  const chunks = chunkTextStructured(fixture.text).map((rawText, chunkIndex) => ({
    id: randomUUID(),
    chunkIndex,
    pageNumber: null,
    rawText,
    contentHash: null,
  }));
  const corpus = chunks
    .map(
      (chunk) =>
        `--- Document Chunk ID: ${chunk.id} index=${chunk.chunkIndex} ---\n${chunk.rawText}`,
    )
    .join('\n\n');
  const route = routeCandidates[0]!.route;
  const callModel = async (repairFeedback?: string) => {
    const result = await client.runObject<SourceSegmentationOutput>({
      taskType: 'source_segmentation',
      routeId: route.routeId,
      promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      schema: SourceSegmentationSchema,
      routeCandidates,
      providerOptions: { maxOutputTokens: 12_000 },
      observability: { includedDocumentChunkIds: chunks.map((chunk) => chunk.id) },
      blocks: [
        makeBlock({
          id: 'source-segmentation-system',
          label: 'Source segmentation system prompt',
          kind: 'stable_system',
          content: SOURCE_SEGMENTATION_SYSTEM_PROMPT,
          reasonIncluded: 'real-document Stage 2 validation',
        }),
        makeBlock({
          id: 'document-metadata',
          label: 'Document metadata',
          kind: 'semi_stable_domain_context',
          content: `Document name: ${fixture.fileName}`,
          reasonIncluded: 'real-document fixture identity',
        }),
        makeBlock({
          id: 'document-chunks',
          label: 'Document chunks',
          kind: 'retrieved_context',
          content: corpus,
          reasonIncluded: 'complete real source document',
        }),
        makeBlock({
          id: 'source-segmentation-request',
          label: 'Source segmentation request',
          kind: 'dynamic_input',
          content:
            'Segment these chunks into the fewest coherent shape-focused passages. Cover every supplied chunk at least once and preserve source order. A genuinely composite chunk may appear in multiple differently shaped segments.' +
            (repairFeedback
              ? `\n\nREPAIR REQUIRED: Return a complete corrected segmentation and copy chunk IDs exactly from this list:\n${chunks.map((chunk) => chunk.id).join('\n')}\n\nValidator feedback:\n${repairFeedback}`
              : ''),
          reasonIncluded: repairFeedback
            ? 'real-document Stage 2 repair gate'
            : 'real-document Stage 2 gate',
        }),
      ],
    });
    if (!result.validation.ok) throw result.validation.error;
    return result;
  };

  const attempts = [await callModel()];
  let result = attempts[0]!;
  let validated = __sourceWorkflowReadTestHooks.validateSegmentation(result.object, chunks);
  if (validated.integrityRepairCount > 0) {
    const retry = await callModel(JSON.stringify(validated.validationJson));
    const retryValidation = __sourceWorkflowReadTestHooks.validateSegmentation(
      retry.object,
      chunks,
    );
    attempts.push(retry);
    if (retryValidation.integrityRepairCount <= validated.integrityRepairCount) {
      result = retry;
      validated = retryValidation;
    }
  }
  const actualShapes = new Set(validated.segments.map((segment) => segment.shape));
  const missingRequiredShapes = fixture.requiredShapes.filter((shape) => !actualShapes.has(shape));
  return {
    name: fixture.name,
    fileName: fixture.fileName,
    characterCount: fixture.text.length,
    chunkCount: chunks.length,
    routeId: result.routeId ?? route.routeId,
    provider: result.provider ?? route.provider,
    modelId: result.modelId ?? route.modelId,
    segmentationAttemptCount: attempts.length,
    status: validated.status,
    documentShape: validated.documentShape,
    segments: validated.segments.map((segment) => ({
      segmentId: segment.segmentId,
      shape: segment.shape,
      title: segment.title,
      chunkCount: segment.chunkIds.length,
      summary: segment.summary ?? null,
    })),
    requiredShapes: fixture.requiredShapes,
    missingRequiredShapes,
    validation: validated.validationJson,
    passed: validated.status === 'validated' && missingRequiredShapes.length === 0,
  };
}

const localFixtureSpecs = [
  {
    name: 'business-process',
    fileName: 'business-process.md',
    requiredShapes: ['process', 'responsibilities', 'reference', 'ruleset'],
  },
  {
    name: 'licensed-team-responsibilities',
    fileName: 'Licensed Team Responsibilities 2 - tagged.txt',
    requiredShapes: ['responsibilities'],
  },
  {
    name: 'book-report-transcript-file',
    fileName: 'transcript-Book report overview.txt',
    requiredShapes: ['conversation'],
  },
  {
    name: 'team-communication-and-product-details',
    fileName: 'Team Communication and Product Details 2.docx',
    requiredShapes: ['narrative'],
  },
  {
    name: 'sku-naming-convention',
    fileName: 'SKU descriptions naming convention.pdf',
    requiredShapes: ['reference', 'ruleset'],
  },
] as const satisfies ReadonlyArray<{
  name: string;
  fileName: string;
  requiredShapes: readonly SourceStructureShape[];
}>;

const fixtures: Fixture[] = [];
for (const spec of localFixtureSpecs) {
  if (!includeAllFixtures && !selectedFixtureNames.has(spec.name)) continue;
  fixtures.push({
    ...spec,
    requiredShapes: [...spec.requiredShapes],
    text: await extractText(spec.fileName),
  });
}
const teamsRequested =
  includeAllFixtures || selectedFixtureNames.has('latest-ingested-teams-transcript');
const teamsFixture = teamsRequested ? await loadLatestTeamsTranscript() : null;
if (teamsFixture) fixtures.push(teamsFixture);

const db = getDirectDb();
const resolved = await resolveRouteCandidates(db, 'workflow_read');
for (const skipped of resolved.skipped) console.warn('Skipped route candidate:', skipped);
const client = new OracleAIClient({ adapters: buildStandardAdapters() });
const results = [];
for (const fixture of fixtures) {
  console.error(`Validating ${fixture.name} (${fixture.text.length} characters)...`);
  const result = await runFixture(fixture, client, resolved.candidates);
  results.push(result);
  console.error(JSON.stringify(result));
  await writeFile(
    resolve(repoRoot, '.cache', 'shape-stage2-validation.partial.json'),
    JSON.stringify(results, null, 2),
  );
}

const output = {
  generatedAt: new Date().toISOString(),
  sourceRoot,
  teamsTranscriptFound: Boolean(teamsFixture),
  passed: results.every((result) => result.passed) && (!teamsRequested || Boolean(teamsFixture)),
  results,
};
await new Promise<void>((resolveWrite, rejectWrite) => {
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`, (error) => {
    if (error) rejectWrite(error);
    else resolveWrite();
  });
});
process.exit(output.passed ? 0 : 1);
