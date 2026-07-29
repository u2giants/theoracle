import assert from 'node:assert/strict';
import {
  ModelRouter,
  getContextCompiler,
  getOracleRoute,
  makeBlock,
  type GenerateObjectArgs,
  type GenerateTextArgs,
  type OracleObjectResult,
  type OracleProviderAdapter,
  type RouteCandidate,
} from '@oracle/ai';
import {
  ChatAttachmentSafetyError,
  MAX_SAFE_INLINE_ATTACHMENT_BYTES,
  selectAttachmentSafeCandidates,
  toCanonicalAttachmentPart,
} from '../chat-attachment-safety';

const vertexRoute = getOracleRoute('vertex_gemini_2_5_flash_extraction_primary')!;
const anthropicRoute = getOracleRoute('anthropic_claude_haiku_4_5_interview_primary')!;
const candidates: RouteCandidate[] = [
  {
    route: vertexRoute,
    slot: 'interview',
    isPrimary: true,
    approvedModelId: vertexRoute.routeId,
  },
  {
    route: anthropicRoute,
    slot: 'interview',
    isPrimary: false,
    approvedModelId: anthropicRoute.routeId,
  },
];

function part(fileType: string, fileName: string, text: string) {
  return toCanonicalAttachmentPart({
    fileType,
    fileName,
    buffer: Buffer.from(text),
  });
}

const pdfOne = part('application/pdf', 'one.pdf', 'pdf one');
const pdfTwo = part('application/pdf', 'two.pdf', 'pdf two');
const image = part('image/png', 'diagram.png', 'image');

assert.equal(pdfOne.type, 'file');
assert.equal(pdfTwo.type, 'file');
assert.equal(image.type, 'image');
assert.deepEqual(
  [pdfOne, pdfTwo].map((item) => item.type),
  ['file', 'file'],
  'two-PDF fixture retains both canonical file parts',
);
assert.deepEqual(
  [pdfOne, image].map((item) => item.type),
  ['file', 'image'],
  'PDF-plus-image fixture retains both canonical parts',
);

const safeSelection = selectAttachmentSafeCandidates({
  candidates,
  hasBinaryAttachments: true,
  hasPdfAttachments: true,
  totalBinaryBytes: 1024,
  cachedPdfBytes: 512,
});
assert.deepEqual(
  safeSelection.candidates.map((candidate) => candidate.route.provider),
  ['vertex', 'anthropic'],
  'small attachments preserve the approved cross-provider fallback chain',
);

let anthropicMessages: unknown;
const failingVertex: OracleProviderAdapter = {
  provider: 'vertex',
  async generateText() {
    throw new Error('forced Vertex failure');
  },
  async generateObject<TSchema, TOutput>(
    _args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    throw new Error('not used');
  },
};
const capturingAnthropic: OracleProviderAdapter = {
  provider: 'anthropic',
  async generateText(args: GenerateTextArgs) {
    anthropicMessages = args.providerOptions?.messages;
    return {
      text: 'fallback answer',
      usage: { latencyMs: 1 },
      rawResponse: null,
    };
  },
  async generateObject<TSchema, TOutput>(
    _args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    throw new Error('not used');
  },
};

const plan = getContextCompiler().compile({
  taskType: 'interview_chat',
  routeId: vertexRoute.routeId,
  promptVersion: 'gap-5-fixture',
  blocks: [
    makeBlock({
      id: 'system',
      label: 'System',
      kind: 'stable_system',
      content: 'Read every attachment.',
      reasonIncluded: 'fixture',
    }),
    makeBlock({
      id: 'turn',
      label: 'Turn',
      kind: 'dynamic_input',
      content: 'Compare the files.',
      reasonIncluded: 'fixture',
    }),
  ],
});
const router = new ModelRouter({
  adapters: {
    vertex: failingVertex,
    anthropic: capturingAnthropic,
  },
});

async function runForcedFallback(content: unknown[]) {
  anthropicMessages = undefined;
  const messages = [
    {
      role: 'user',
      content,
    },
  ];
  const result = await router.generateText(
    plan,
    { messages },
    safeSelection.candidates,
  );
  return { result, messages };
}

const twoPdfFallback = await runForcedFallback([
  { type: 'text', text: 'Compare the two PDFs.' },
  pdfOne,
  pdfTwo,
]);
assert.equal(twoPdfFallback.result.provider, 'anthropic');
assert.equal(twoPdfFallback.result.usedNonPrimary, true);
assert.deepEqual(
  twoPdfFallback.result.attemptedRoutes?.map((attempt) => attempt.success),
  [false, true],
  'forced Vertex failure reaches Anthropic',
);
assert.deepEqual(
  anthropicMessages,
  twoPdfFallback.messages,
  'two-PDF fallback receives the canonical message unchanged',
);
const capturedTwoPdfParts = (
  anthropicMessages as Array<{ content: Array<Record<string, unknown>> }>
)[0]!.content;
const capturedPdfNames = capturedTwoPdfParts
  .filter((item) => item.type === 'file')
  .map((item) => item.fileName);
assert.equal(capturedPdfNames.length, 2, 'two-PDF fallback carries exactly two files');
assert.deepEqual(
  capturedPdfNames,
  ['one.pdf', 'two.pdf'],
  'two-PDF fallback preserves both file names and order',
);
assert.deepEqual(
  capturedTwoPdfParts
    .filter((item) => item.type === 'file')
    .map((item) => item.mimeType),
  ['application/pdf', 'application/pdf'],
  'two-PDF fallback preserves the PDF mime type for both files',
);

const pdfImageFallback = await runForcedFallback([
  { type: 'text', text: 'Compare the PDF and image.' },
  pdfOne,
  image,
]);
assert.equal(pdfImageFallback.result.provider, 'anthropic');
assert.deepEqual(
  anthropicMessages,
  pdfImageFallback.messages,
  'PDF-plus-image fallback receives the canonical message unchanged',
);
const capturedPdfImageParts = (
  anthropicMessages as Array<{ content: Array<Record<string, unknown>> }>
)[0]!.content;
assert.equal(
  capturedPdfImageParts.filter((item) => item.type === 'file').length,
  1,
  'PDF-plus-image fallback carries exactly one PDF',
);
assert.equal(
  capturedPdfImageParts.find((item) => item.type === 'file')?.fileName,
  'one.pdf',
  'PDF-plus-image fallback preserves the PDF name',
);
assert.equal(
  capturedPdfImageParts.find((item) => item.type === 'file')?.mimeType,
  'application/pdf',
  'PDF-plus-image fallback preserves the PDF mime type',
);
assert.equal(
  capturedPdfImageParts.filter((item) => item.type === 'image').length,
  1,
  'PDF-plus-image fallback carries exactly one image',
);
assert.equal(
  capturedPdfImageParts.find((item) => item.type === 'image')?.mimeType,
  'image/png',
  'PDF-plus-image fallback preserves the image mime type',
);

const constrained = selectAttachmentSafeCandidates({
  candidates,
  hasBinaryAttachments: true,
  hasPdfAttachments: true,
  totalBinaryBytes: MAX_SAFE_INLINE_ATTACHMENT_BYTES + 1024,
  cachedPdfBytes: 2048,
});
assert.deepEqual(
  constrained.candidates.map((candidate) => candidate.route.provider),
  ['vertex'],
  'oversized complete fallback payload is constrained to Vertex when the cached PDF makes its live request safe',
);
assert.equal(constrained.constrainedToVertex, true);

assert.throws(
  () =>
    selectAttachmentSafeCandidates({
      candidates,
      hasBinaryAttachments: true,
      hasPdfAttachments: true,
      totalBinaryBytes: MAX_SAFE_INLINE_ATTACHMENT_BYTES + 1,
    }),
  (error) =>
    error instanceof ChatAttachmentSafetyError &&
    error.code === 'attachments_too_large' &&
    error.message.includes('too large'),
  'unsafe oversized payload fails with a clear attachment error',
);

console.log('PASS: GAP-5 attachment and fallback safety fixtures');
