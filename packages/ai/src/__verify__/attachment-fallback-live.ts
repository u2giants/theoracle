/**
 * Credentialed GAP-5 fallback gate.
 *
 * Run only with an approved Anthropic credential:
 *   pnpm --filter @oracle/ai verify:attachment-fallback-live
 *
 * The Vertex attempt is deliberately failed in-process before network I/O.
 * Anthropic is live. The fixture contains only generated marker PDFs and
 * proves the fallback provider can read both files from the unchanged
 * canonical message. It does not touch a database, GCS, or production.
 */
import assert from 'node:assert/strict';
import {
  AnthropicAdapter,
  ModelRouter,
  getContextCompiler,
  getOracleRoute,
  makeBlock,
  type GenerateObjectArgs,
  type OracleObjectResult,
  type OracleProviderAdapter,
  type RouteCandidate,
} from '../index';

if (!process.env.ANTHROPIC_API_KEY) {
  throw new Error(
    'ANTHROPIC_API_KEY is required for the credentialed GAP-5 fallback gate.',
  );
}

function makeMarkerPdf(marker: string): Buffer {
  const escaped = marker.replaceAll('\\', '\\\\').replaceAll('(', '\\(').replaceAll(')', '\\)');
  const stream = `BT /F1 18 Tf 72 720 Td (${escaped}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  for (let index = 0; index < objects.length; index += 1) {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${objects[index]}\nendobj\n`;
  }
  const xrefOffset = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n`;
  pdf += '0000000000 65535 f \n';
  for (const offset of offsets.slice(1)) {
    pdf += `${String(offset).padStart(10, '0')} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n`;
  pdf += `startxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(pdf);
}

const markerOne = 'GAP5_PDF_ONE_VISIBLE';
const markerTwo = 'GAP5_PDF_TWO_VISIBLE';
const pdfOne = makeMarkerPdf(markerOne);
const pdfTwo = makeMarkerPdf(markerTwo);
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
const forcedVertexFailure: OracleProviderAdapter = {
  provider: 'vertex',
  async generateText() {
    throw new Error('intentional GAP-5 Vertex failure before network I/O');
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
  promptVersion: 'gap-5-live-fallback-1.0.0',
  blocks: [
    makeBlock({
      id: 'system',
      label: 'Fixture instruction',
      kind: 'stable_system',
      content:
        'Read both attached PDFs. Reply with only the two uppercase marker strings, separated by a space.',
      reasonIncluded: 'GAP-5 live attachment proof',
    }),
    makeBlock({
      id: 'turn',
      label: 'Fixture question',
      kind: 'dynamic_input',
      content: 'Report the marker from each attached PDF.',
      reasonIncluded: 'GAP-5 live attachment proof',
    }),
  ],
});
const result = await new ModelRouter({
  adapters: {
    vertex: forcedVertexFailure,
    anthropic: new AnthropicAdapter(),
  },
}).generateText(
  plan,
  {
    maxOutputTokens: 64,
    messages: [
      {
        role: 'user',
        content: [
          { type: 'text', text: 'Read both PDFs and report both markers.' },
          {
            type: 'file',
            mimeType: 'application/pdf',
            fileName: 'one.pdf',
            data: pdfOne.toString('base64'),
          },
          {
            type: 'file',
            mimeType: 'application/pdf',
            fileName: 'two.pdf',
            data: pdfTwo.toString('base64'),
          },
        ],
      },
    ],
  },
  candidates,
);

assert.equal(result.provider, 'anthropic');
assert.equal(result.usedNonPrimary, true);
assert.match(result.text, new RegExp(markerOne));
assert.match(result.text, new RegExp(markerTwo));
console.log('PASS: live Anthropic fallback read both generated PDFs after forced Vertex failure');
