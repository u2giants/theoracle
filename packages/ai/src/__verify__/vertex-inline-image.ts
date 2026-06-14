/**
 * Vertex inline-image (vision input) regression gate.
 *
 * Run with:
 *   pnpm --filter @oracle/ai exec tsx src/__verify__/vertex-inline-image.ts
 *
 * Proves the multimodal message path used by the document-ingestion image
 * vision-transcription pass:
 *   - When `providerOptions.messages` carries a content array mixing a text
 *     part and an `{ type: 'image', mimeType, data }` part, the Vertex adapter
 *     translates the image into a Gemini `inlineData` part (base64) and keeps
 *     the text part, in order.
 *   - String message content still maps to a single text part (back-compat).
 *
 * No network / DB: the GoogleGenAI client is stubbed and the cache sweepers are
 * no-op'd. Caching is disabled so the request goes straight through.
 */

import { VertexGeminiAdapter, getOracleRoute, type OracleModelRoute } from '../index';
import { getContextCompiler } from '../context/context-compiler';
import { makeBlock } from '../index';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

async function main() {
  console.log('Vertex inline-image gate\n');

  process.env.GOOGLE_CLOUD_PROJECT ??= 'verify-project';
  process.env.GOOGLE_CLOUD_LOCATION ??= 'us-central1';

  const route = getOracleRoute('vertex_gemini_2_5_flash_extraction_primary') as OracleModelRoute;
  assert(route?.provider === 'vertex', 'resolved a Vertex route');

  const blocks = [
    makeBlock({
      id: 'vision-system',
      label: 'Vision system prompt',
      kind: 'stable_system',
      content: 'You are a meticulous visual analyst.',
      reasonIncluded: 'system prompt',
    }),
    makeBlock({
      id: 'vision-request',
      label: 'Vision request',
      kind: 'dynamic_input',
      content: 'Render the attached image as faithful text.',
      reasonIncluded: 'dynamic request',
    }),
  ];
  const plan = getContextCompiler().compile({
    taskType: 'document_claim_extraction',
    routeId: route.routeId,
    promptVersion: 'inline-image-gate',
    blocks,
  });

  const generateCalls: Array<Record<string, any>> = [];
  const adapter = new VertexGeminiAdapter();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const anyAdapter = adapter as any;
  anyAdapter.client = {
    caches: { create: async () => ({ name: 'unused' }), get: async () => ({}), delete: async () => ({}) },
    models: {
      generateContent: async (req: Record<string, any>) => {
        generateCalls.push(req);
        return { text: 'transcribed text', usageMetadata: {} };
      },
    },
  };
  anyAdapter.cleanupExpiredExplicitCaches = async () => {};
  anyAdapter.cleanupExpiredPersistentCaches = async () => {};

  const FAKE_B64 = Buffer.from('fake-png-bytes').toString('base64');
  const result = await adapter.generateText({
    plan,
    route,
    providerOptions: {
      cache: { disableCache: true },
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: 'Render the attached image as faithful text.' },
            { type: 'image', mimeType: 'image/png', data: FAKE_B64 },
          ],
        },
      ],
    },
  });

  assert(result.text === 'transcribed text', 'generateText returned the stubbed answer');
  assert(generateCalls.length === 1, 'exactly one generateContent call');

  const parts = generateCalls[0]!.contents?.[0]?.parts;
  assert(Array.isArray(parts) && parts.length === 2, 'user turn has a text part and an image part');
  assert(parts[0]?.text === 'Render the attached image as faithful text.', 'text part preserved, in order');
  assert(parts[1]?.inlineData?.mimeType === 'image/png', 'image part became inlineData with the png mime type');
  assert(parts[1]?.inlineData?.data === FAKE_B64, 'image part carries the base64 bytes');

  // Back-compat: string content still maps to a single text part.
  generateCalls.length = 0;
  await adapter.generateText({
    plan,
    route,
    providerOptions: {
      cache: { disableCache: true },
      messages: [{ role: 'user', content: 'plain string turn' }],
    },
  });
  const strParts = generateCalls[0]!.contents?.[0]?.parts;
  assert(
    Array.isArray(strParts) && strParts.length === 1 && strParts[0]?.text === 'plain string turn',
    'string message content still maps to a single text part',
  );

  console.log('\nVertex inline-image gate: PASS');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
