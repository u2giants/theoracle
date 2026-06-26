/**
 * adapter-bugs-live.ts — live-API proof for the four model-adapter bug fixes.
 *
 * Proves each fix against the REAL provider APIs using the REAL extraction
 * schema and a dense diagram-style transcript (the shape that originally
 * exposed the bugs):
 *
 *   Bug 1 — OpenAI strict structured output: gpt-4o-mini AND gpt-4.1-mini
 *           complete a real extraction with the nullable-optional schema and
 *           return schema-valid claims (no 400, optional fields come back null).
 *   Bug 2 — Gemini Google-API timeout: gemini-2.5-flash extraction completes
 *           on a dense transcript without a 60s abort (configurable 180s).
 *   Bug 3 — Gemini thinkingLevel: gemini-2.5-flash VISION-style call carrying a
 *           reasoning effort completes with no "Thinking level not supported"
 *           400, because the adapter emits the field shape the model supports
 *           (thinkingBudget for 2.5, thinkingLevel for 3.x).
 *
 * Bug 4 (settings double-encoding) is proven separately by
 * settings-encoding.ts (a pure round-trip guard, no provider call).
 *
 * Run (from repo root):
 *   corepack pnpm --filter @oracle/ai exec tsx src/__verify__/adapter-bugs-live.ts
 * Requires a .env.verify.local (or .env.local) with OPENAI_API_KEY + GEMINI_API_KEY.
 */

import { config as loadEnv } from 'dotenv';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { OpenAIAdapter } from '../providers/openai-adapter';
import { GoogleGeminiAdapter } from '../providers/google-gemini-adapter';
import {
  ExtractionOutputSchema,
  EXTRACTION_SYSTEM_PROMPT,
} from '../prompts/extraction-system';
import { resolveModelRoute } from '../routes/resolve';
import type { OraclePromptPlan } from '../client/types';
import type { OracleModelRoute } from '../routes';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..', '..');
loadEnv({ path: resolve(repoRoot, '.env.verify.local'), override: true });
loadEnv({ path: resolve(repoRoot, '.env.local'), override: false });
loadEnv({ path: resolve(repoRoot, '.env'), override: false });

// A dense diagram-style transcript with one self-contained line per edge — the
// shape document-ingestion produces for a flowchart, and the shape that took
// >60s on Gemini and 400'd OpenAI strict mode before the fixes.
const TRANSCRIPT = `### Swimlane: Gina
[Rectangle:"Review Audit and send to factory"] --(Arrow:"If Audit: Pass")--> [Rectangle:"Factory production start"]
### Swimlane: Carlos
[Rectangle:"SKUs creation"] --(Arrow:"after art finalized")--> [Rectangle:"Upload to ColdLion"]
### Swimlane: Sourcing
[Rectangle:"Send RFQ to factories"] --(Arrow:"Before an Order")--> [Rectangle:"Collect factory quotes"]
[Rectangle:"Collect factory quotes"] --(Arrow:"Sales confirms buyer price")--> [Rectangle:"Finalize factory pricing"]
### Swimlane: Licensor
[Rectangle:"Approve PPS sample"] --(Arrow:"required before")--> [Rectangle:"Mass production"]
chunk-id: chunk-001`;

const SOURCE_ID = 'chunk-001';

function extractionPlan(): OraclePromptPlan {
  return {
    taskType: 'document_claim_extraction',
    routeId: 'verify-fixture',
    promptVersion: 'verify-1',
    blocks: [
      {
        id: 'sys',
        label: 'system',
        kind: 'stable_system',
        content: EXTRACTION_SYSTEM_PROMPT,
        hash: 'h-sys',
        cacheEligible: true,
        reasonIncluded: 'extraction system prompt',
      },
      {
        id: 'user',
        label: 'user-input',
        kind: 'dynamic_input',
        content:
          `Extract operational claims from this flowchart transcription. ` +
          `Use sourceMessageId="${SOURCE_ID}" and quote whole edge lines verbatim.\n\n${TRANSCRIPT}`,
        hash: 'h-user',
        cacheEligible: false,
        reasonIncluded: 'extraction input',
      },
    ],
    metadata: { stablePrefixHash: 'verify-stable', dynamicInputHash: 'verify-dynamic' },
  };
}

function route(
  modelIdOrRouteId: string,
  caps?: Parameters<typeof resolveModelRoute>[3],
  reasoningEffort?: 'off' | 'low' | 'medium' | 'high',
): OracleModelRoute {
  const r = resolveModelRoute(modelIdOrRouteId, 'extraction', reasoningEffort, caps);
  if (!r) throw new Error(`could not resolve route ${modelIdOrRouteId}`);
  return r;
}

let failures = 0;

async function proveExtraction(label: string, adapter: OpenAIAdapter | GoogleGeminiAdapter, r: OracleModelRoute): Promise<void> {
  const start = Date.now();
  try {
    const res = await adapter.generateObject({
      plan: extractionPlan(),
      route: r,
      schema: ExtractionOutputSchema,
      providerOptions: { maxOutputTokens: 8192 },
    });
    const elapsed = Date.now() - start;
    // Re-validate with the real schema so we PROVE schema-validity, including
    // null optional fields parsing cleanly.
    const parsed = ExtractionOutputSchema.parse(res.object);
    const n = parsed.claims.length;
    const nullableSeen = parsed.claims.some(
      (c) =>
        c.sensitivityFlags == null ||
        c.proposedEntities == null ||
        c.semanticRole == null ||
        c.suggestedGaps == null,
    );
    if (n === 0) {
      console.error(`  ✗ ${label} (${elapsed}ms): returned 0 claims`);
      failures++;
      return;
    }
    console.log(
      `  ✓ ${label} (${elapsed}ms): ${n} schema-valid claims; ` +
        `nullable-optional-as-null observed=${nullableSeen}; ` +
        `tokens in=${res.usage.inputTokens ?? '?'} out=${res.usage.outputTokens ?? '?'}`,
    );
    console.log(`    sample claim[0].summary: ${parsed.claims[0]!.summary.slice(0, 90)}`);
  } catch (err) {
    const elapsed = Date.now() - start;
    console.error(`  ✗ ${label} (${elapsed}ms) FAILED:`, err instanceof Error ? err.message : err);
    failures++;
  }
}

async function proveVisionThinking(label: string, r: OracleModelRoute): Promise<void> {
  // Bug 3: a reasoning-bearing Gemini call on gemini-2.5-flash must NOT 400 with
  // "Thinking level not supported". We use a plain generateText carrying the
  // effort; the adapter must emit thinkingBudget (2.5) not thinkingLevel.
  const start = Date.now();
  try {
    const adapter = new GoogleGeminiAdapter();
    const res = await adapter.generateText({
      plan: {
        taskType: 'admin_explanation',
        routeId: 'verify-vision',
        promptVersion: 'verify-1',
        blocks: [
          {
            id: 'sys', label: 'system', kind: 'stable_system',
            content: 'You transcribe diagrams to text faithfully.',
            hash: 'h', cacheEligible: true, reasonIncluded: 'sys',
          },
          {
            id: 'u', label: 'user-input', kind: 'dynamic_input',
            content: 'Reply with the single word: OK',
            hash: 'h2', cacheEligible: false, reasonIncluded: 'u',
          },
        ],
        metadata: { stablePrefixHash: 's', dynamicInputHash: 'd' },
      },
      route: r,
    });
    const elapsed = Date.now() - start;
    console.log(`  ✓ ${label} (${elapsed}ms): no thinking-400; text="${res.text.slice(0, 40).replace(/\n/g, ' ')}"`);
  } catch (err) {
    const elapsed = Date.now() - start;
    console.error(`  ✗ ${label} (${elapsed}ms) FAILED:`, err instanceof Error ? err.message : err);
    failures++;
  }
}

async function main(): Promise<void> {
  console.log('adapter-bugs-live — live-API proof of the four fixes\n');

  // ── Bug 1: OpenAI strict structured output ────────────────────────────────
  console.log('Bug 1 — OpenAI strict structured output (nullable optionals):');
  if (process.env.OPENAI_API_KEY) {
    const openai = new OpenAIAdapter();
    // OpenAI strict native_json_schema, no reasoning controls.
    const openaiCaps = { supportsReasoningControls: false } as const;
    await proveExtraction('gpt-4o-mini extraction', openai, route('openai/gpt-4o-mini', openaiCaps));
    await proveExtraction('gpt-4.1-mini extraction', openai, route('openai/gpt-4.1-mini', openaiCaps));
  } else {
    console.error('  ✗ SKIP: OPENAI_API_KEY absent — UNVERIFIED');
    failures++;
  }

  // ── Bug 2 + Bug 3 share the Google Gemini adapter ─────────────────────────
  const geminiKey = process.env.GEMINI_API_KEY ?? process.env.GOOGLE_API_KEY;
  const geminiSa = process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON;
  console.log('\nBug 2 — Gemini Google-API timeout (no hard 60s):');
  if (geminiKey || geminiSa) {
    const gemini = new GoogleGeminiAdapter();
    // gemini-2.5-flash: thinking-capable per catalog, but only via thinkingBudget.
    const g25 = route('google/gemini-2.5-flash', { supportsReasoningControls: true }, 'low');
    await proveExtraction('gemini-2.5-flash extraction (dense transcript)', gemini, g25);

    console.log('\nBug 3 — Gemini thinkingLevel on gemini-2.5-flash (vision/reasoning call):');
    // Carry a reasoning effort; pre-fix this 400'd with thinkingLevel.
    await proveVisionThinking(
      'gemini-2.5-flash reasoning-bearing call',
      route('google/gemini-2.5-flash', { supportsReasoningControls: true }, 'medium'),
    );
    // Also prove a model that genuinely takes thinkingLevel (3.x) still gets it.
    await proveVisionThinking(
      'gemini-3.1-flash-lite reasoning-bearing call (thinkingLevel path)',
      route('google/gemini-3.1-flash-lite', { supportsReasoningControls: true }, 'low'),
    );
  } else {
    console.error('  ✗ SKIP: GEMINI_API_KEY / GOOGLE_APPLICATION_CREDENTIALS_JSON absent — UNVERIFIED');
    failures++;
  }

  console.log(`\n${failures === 0 ? 'ALL PROOFS PASSED' : `${failures} PROOF(S) FAILED`}`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error('FATAL:', err);
  process.exit(1);
});
