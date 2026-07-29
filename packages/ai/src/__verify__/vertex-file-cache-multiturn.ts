/**
 * Vertex file-backed cache + multi-turn regression gate.
 *
 * Run with:
 *   pnpm --filter @oracle/ai exec tsx src/__verify__/vertex-file-cache-multiturn.ts
 *
 * Proves the chat-attachment file-cache enhancement (v1):
 *   - When a `vertexFileCacheSource` is supplied with `preferExplicitCache`,
 *     the adapter creates a Gemini cachedContent from systemInstruction + a
 *     gs:// fileData part (the document corpus).
 *   - The generateContent request references that cache via `cachedContent`,
 *     omits `systemInstruction` (it lives in the cache), AND preserves the
 *     FULL multi-turn conversation as live contents — the regression this
 *     gate exists to prevent (the old file-cache path collapsed the request
 *     to a single dynamicInput turn, which would erase chat history).
 *   - The structured-output path (generateObject) is intentionally NOT
 *     exercised here — it keeps its single-turn shape for extraction.
 *
 * No network / DB: the GoogleGenAI client + Storage client are stubbed and
 * the cache-lifecycle DB sweepers are no-op'd. persistProviderCacheRecord is
 * false so no provider_cached_content rows are touched.
 *
 * This file is in __verify__ so it is never picked up as a production export.
 */

import { VertexGeminiAdapter, getOracleRoute, type OracleModelRoute } from '../index';
import { getContextCompiler } from '../context/context-compiler';
import { makeBlock } from '../index';
import { createHash } from 'node:crypto';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

async function main() {
  console.log('Vertex file-cache multi-turn gate\n');

  // The adapter constructor needs a project; GoogleGenAI does no network I/O
  // at construction. The GCS bucket env activates the file-backed cache path.
  process.env.GOOGLE_CLOUD_PROJECT ??= 'verify-project';
  process.env.GOOGLE_CLOUD_LOCATION ??= 'us-central1';
  process.env.GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET ??= 'verify-bucket';

  const route = getOracleRoute('vertex_gemini_2_5_flash_extraction_primary') as OracleModelRoute;
  assert(route?.provider === 'vertex', 'resolved a Vertex route');

  // Two stable chat blocks, mirroring the interview chat route.
  const blocks = [
    makeBlock({
      id: 'oracle-system',
      label: 'Oracle interview system prompt',
      kind: 'stable_system',
      content: 'You are the Oracle. Answer from approved knowledge.',
      reasonIncluded: 'system prompt',
    }),
    makeBlock({
      id: 'turn-context',
      label: 'Per-turn retrieval bundle',
      kind: 'retrieved_context',
      content: 'CONTEXT: speaking with Albert.',
      reasonIncluded: 'turn context',
    }),
  ];
  const plan = getContextCompiler().compile({
    taskType: 'interview_chat',
    routeId: route.routeId,
    promptVersion: 'file-cache-gate',
    blocks,
  });

  // Multi-turn conversation (the document is in the cache, so turns are text).
  const cachedPdf = Buffer.from('cached pdf fixture');
  const secondPdf = Buffer.from('second pdf fixture');
  const image = Buffer.from('image fixture');
  const cachedPdfHash = createHash('sha256').update(cachedPdf).digest('hex');
  const messages = [
    { role: 'user' as const, content: '[Oracle runtime context]\nCONTEXT: speaking with Albert.' },
    { role: 'user' as const, content: 'What does the spec say about returns?' },
    { role: 'assistant' as const, content: 'Let me check the document.' },
    {
      role: 'user' as const,
      content: [
        { type: 'text', text: 'SECOND_TURN_MARKER: compare both PDFs and the image.' },
        {
          type: 'file',
          mimeType: 'application/pdf',
          data: cachedPdf.toString('base64'),
          fileName: 'cached.pdf',
        },
        {
          type: 'file',
          mimeType: 'application/pdf',
          data: secondPdf.toString('base64'),
          fileName: 'second.pdf',
        },
        {
          type: 'image',
          mimeType: 'image/png',
          data: image.toString('base64'),
        },
      ],
    },
  ];

  // ── Stub the provider client + storage; neutralize DB sweepers ──────────
  const createCalls: Array<Record<string, any>> = [];
  const generateCalls: Array<Record<string, any>> = [];
  const adapter = new VertexGeminiAdapter();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const anyAdapter = adapter as any;
  anyAdapter.client = {
    caches: {
      create: async (cfg: Record<string, any>) => {
        createCalls.push(cfg);
        return { name: 'projects/p/locations/l/cachedContents/CACHE123' };
      },
      get: async () => ({}),
      delete: async () => ({}),
    },
    models: {
      generateContent: async (req: Record<string, any>) => {
        generateCalls.push(req);
        return { text: 'answer', usageMetadata: {} };
      },
    },
  };
  anyAdapter.storageClient = {
    bucket: () => ({
      upload: async () => [{}],
      file: () => ({ delete: async () => {} }),
    }),
  };
  // Sweepers hit getDirectDb(); no DB in this gate.
  anyAdapter.cleanupExpiredExplicitCaches = async () => {};
  anyAdapter.cleanupExpiredPersistentCaches = async () => {};

  const result = await adapter.generateText({
    plan,
    route,
    providerOptions: {
      messages,
      cache: {
        preferExplicitCache: true,
        persistProviderCacheRecord: false, // no DB
        cacheTtlSeconds: 30 * 60,
        vertexFileCacheSource: {
          localPath: '/tmp/verify-fake.pdf',
          mimeType: 'application/pdf',
          fileName: 'verify-fake.pdf',
          sourceHash: cachedPdfHash,
        },
      },
    },
  });

  assert(result.text === 'answer', 'generateText returned the stubbed answer');

  // ── 1. Cache built from systemInstruction + gs:// fileData ──────────────
  assert(createCalls.length === 1, 'exactly one cachedContent created');
  const cacheCfg = createCalls[0]!.config;
  assert(
    typeof cacheCfg.systemInstruction === 'string' && cacheCfg.systemInstruction.includes('Oracle'),
    'cache carries the Oracle system instruction',
  );
  const cachePart = cacheCfg.contents?.[0]?.parts?.[0];
  assert(
    cachePart?.fileData?.fileUri?.startsWith('gs://'),
    'cache contents reference a gs:// fileData URI',
  );
  assert(cachePart?.fileData?.mimeType === 'application/pdf', 'cached fileData carries the PDF mime type');

  // ── 2. Request references the cache, omits systemInstruction ────────────
  assert(generateCalls.length === 1, 'exactly one generateContent call');
  const req = generateCalls[0]!;
  assert(
    req.config?.cachedContent === 'projects/p/locations/l/cachedContents/CACHE123',
    'generateContent references the created cache',
  );
  assert(req.config?.systemInstruction === undefined, 'systemInstruction omitted (lives in the cache)');

  // ── 3. REGRESSION GUARD: full multi-turn conversation preserved ─────────
  assert(
    Array.isArray(req.contents) && req.contents.length === messages.length,
    `all ${messages.length} conversation turns sent as live contents (got ${req.contents?.length})`,
  );
  const flatText = JSON.stringify(req.contents);
  assert(flatText.includes('SECOND_TURN_MARKER'), 'latest user turn present in live contents');
  assert(flatText.includes('Let me check the document.'), 'prior assistant turn present in live contents');
  // The cached document must NOT be re-sent inline in the live contents.
  assert(!flatText.includes('gs://'), 'document not duplicated into live contents (cache-only)');
  assert(
    !flatText.includes(cachedPdf.toString('base64')),
    'the one cached PDF is removed from Vertex live contents',
  );
  assert(
    flatText.includes(secondPdf.toString('base64')),
    'the second PDF remains in Vertex live contents',
  );
  assert(
    flatText.includes(image.toString('base64')),
    'the image remains in Vertex live contents',
  );

  // ── 4. Oversized requests fail closed when the required upload fails ──
  const failedUploadGenerateCalls: Array<Record<string, any>> = [];
  const failedUploadAdapter = new VertexGeminiAdapter();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const anyFailedUploadAdapter = failedUploadAdapter as any;
  anyFailedUploadAdapter.client = {
    caches: {
      create: async () => {
        throw new Error('cache create must not run after upload failure');
      },
      get: async () => ({}),
      delete: async () => ({}),
    },
    models: {
      generateContent: async (request: Record<string, any>) => {
        failedUploadGenerateCalls.push(request);
        return { text: 'inline answer', usageMetadata: {} };
      },
    },
  };
  anyFailedUploadAdapter.storageClient = {
    bucket: () => ({
      upload: async () => {
        throw new Error('forced GCS upload failure');
      },
      file: () => ({ delete: async () => {} }),
    }),
  };
  anyFailedUploadAdapter.cleanupExpiredExplicitCaches = async () => {};
  anyFailedUploadAdapter.cleanupExpiredPersistentCaches = async () => {};

  let requiredCacheError = '';
  try {
    await failedUploadAdapter.generateText({
      plan,
      route,
      providerOptions: {
        messages,
        cache: {
          preferExplicitCache: true,
          requireVertexFileCache: true,
          persistProviderCacheRecord: false,
          vertexFileCacheSource: {
            localPath: '/tmp/verify-fake.pdf',
            mimeType: 'application/pdf',
            fileName: 'verify-fake.pdf',
            sourceHash: cachedPdfHash,
          },
        },
      },
    });
  } catch (error) {
    requiredCacheError = error instanceof Error ? error.message : String(error);
  }
  assert(
    requiredCacheError.includes('required') && requiredCacheError.includes('could not be prepared'),
    'required oversized file-cache upload failure returns a clear error',
  );
  assert(
    failedUploadGenerateCalls.length === 0,
    'required cache failure never falls through to an unsafe oversized inline Vertex request',
  );

  const optionalCacheResult = await failedUploadAdapter.generateText({
    plan,
    route,
    providerOptions: {
      messages,
      cache: {
        preferExplicitCache: true,
        requireVertexFileCache: false,
        persistProviderCacheRecord: false,
        vertexFileCacheSource: {
          localPath: '/tmp/verify-fake.pdf',
          mimeType: 'application/pdf',
          fileName: 'verify-fake.pdf',
          sourceHash: cachedPdfHash,
        },
      },
    },
  });
  assert(
    optionalCacheResult.text === 'inline answer',
    'optional cache upload failure safely continues through the inline request',
  );
  assert(
    JSON.stringify(failedUploadGenerateCalls[0]?.contents).includes(cachedPdf.toString('base64')),
    'safe inline continuation retains the PDF that could not be cached',
  );

  console.log('\nVertex file-cache multi-turn gate: PASS');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
