/**
 * R-providers smoke runner.
 *
 * Fires generateText + generateObject against each direct provider adapter
 * with a minimal fixture plan. Confirms:
 *   - The adapter connects to the real provider.
 *   - Structured-output schema parsing works.
 *   - Usage tokens normalize correctly.
 *
 * Usage (from repo root):
 *   pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts vertex
 *   pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts anthropic
 *   pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts openai
 *   pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts google
 *   pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts deepseek
 *   pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts qwen
 *   pnpm --filter @oracle/ai tsx src/__verify__/r-providers-smoke.ts all
 *
 * Costs roughly $0.001 per provider per run.
 */

import { config as loadEnv } from 'dotenv';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import { AnthropicAdapter } from '../providers/anthropic-adapter';
import { DeepSeekAdapter } from '../providers/deepseek-adapter';
import { GoogleGeminiAdapter } from '../providers/google-gemini-adapter';
import { OpenAIAdapter } from '../providers/openai-adapter';
import { QwenAdapter } from '../providers/qwen-adapter';
import { VertexGeminiAdapter } from '../providers/vertex-gemini-adapter';
import type {
  OracleObjectResult,
  OraclePromptPlan,
  OracleTextResult,
} from '../client/types';
import type { OracleModelRoute, OracleProvider } from '../routes';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..', '..');
// override: true so .env.local wins over any shell-level empty placeholders
// (some harnesses inject ANTHROPIC_API_KEY="" / OPENAI_API_KEY="" as a
// credential-redaction safeguard, which would otherwise mask our real keys).
loadEnv({ path: resolve(repoRoot, '.env.local'), override: true });
loadEnv({ path: resolve(repoRoot, '.env'), override: false });

// ─── Fixture data ──────────────────────────────────────────────────────────

const fixturePlan: OraclePromptPlan = {
  taskType: 'message_claim_extraction',
  routeId: 'smoke-fixture',
  promptVersion: 'smoke-1',
  blocks: [
    {
      id: 'sys',
      label: 'system',
      kind: 'stable_system',
      content:
        'You are a helpful assistant. Reply concisely. When asked to return structured output, always include both fields exactly as requested.',
      hash: 'h-sys',
      cacheEligible: true,
      reasonIncluded: 'smoke test system prompt',
    },
    {
      id: 'user',
      label: 'user-input',
      kind: 'dynamic_input',
      content:
        'Return a single fact: the capital of Japan is Tokyo. Provide it as a structured fact with subject and predicate.',
      hash: 'h-user',
      cacheEligible: false,
      reasonIncluded: 'smoke test input',
    },
  ],
  metadata: {
    stablePrefixHash: 'smoke-stable',
    dynamicInputHash: 'smoke-dynamic',
  },
};

const factSchema = z.object({
  subject: z.string(),
  predicate: z.string(),
});

function smokeRoute(
  provider: OracleProvider,
  modelId: string,
): OracleModelRoute {
  return {
    routeId: `smoke-${provider}`,
    role: null,
    tier: 'internal_subroute',
    internalPurpose: 'message_triage',
    provider,
    modelId,
    displayName: `Smoke test (${provider})`,
    recommendedUse: 'r-providers-smoke',
    costTier: 'cheap_default',
    cacheStrategy:
      provider === 'vertex'
        ? 'vertex_implicit'
        : provider === 'anthropic'
          ? 'anthropic_automatic'
          : provider === 'deepseek'
            ? 'deepseek_automatic_prefix'
            : provider === 'qwen'
              ? 'qwen_explicit_context_cache'
              : 'openai_automatic_prefix',
    structuredOutputStrategy:
      provider === 'anthropic'
        ? 'tool_call'
        : provider === 'deepseek' || provider === 'qwen'
          ? 'schema_prompt_plus_validator'
          : 'native_json_schema',
    supportsVision: false,
    supportsStreaming: false,
    supportsToolCalling: true,
    supportsStructuredOutput: true,
    supportsReasoningControls: false,
    enabled: true,
  };
}

// ─── Per-provider drivers ──────────────────────────────────────────────────

async function smokeVertex(): Promise<void> {
  console.log('\n══ vertex ════════════════════════════════════════════════════');
  if (!process.env.GOOGLE_CLOUD_PROJECT) {
    console.warn('  SKIP: GOOGLE_CLOUD_PROJECT not set.');
    return;
  }
  const adapter = new VertexGeminiAdapter();
  const route = smokeRoute('vertex', 'gemini-2.5-flash-lite');

  await runOne('vertex.generateText', () =>
    adapter.generateText({ plan: fixturePlan, route }),
  );
  await runOne('vertex.generateObject', () =>
    adapter.generateObject({ plan: fixturePlan, route, schema: factSchema }),
  );
}

async function smokeAnthropic(): Promise<void> {
  console.log('\n══ anthropic ═════════════════════════════════════════════════');
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn('  SKIP: ANTHROPIC_API_KEY not set.');
    return;
  }
  const adapter = new AnthropicAdapter();
  const route = smokeRoute('anthropic', 'claude-haiku-4-5');

  await runOne('anthropic.generateText', () =>
    adapter.generateText({ plan: fixturePlan, route }),
  );
  await runOne('anthropic.generateObject', () =>
    adapter.generateObject({ plan: fixturePlan, route, schema: factSchema }),
  );
}

async function smokeOpenAI(): Promise<void> {
  console.log('\n══ openai ════════════════════════════════════════════════════');
  if (!process.env.OPENAI_API_KEY) {
    console.warn('  SKIP: OPENAI_API_KEY not set.');
    return;
  }
  const adapter = new OpenAIAdapter();
  const route = smokeRoute('openai', 'gpt-4o-mini');

  await runOne('openai.generateText', () =>
    adapter.generateText({ plan: fixturePlan, route }),
  );
  await runOne('openai.generateObject', () =>
    adapter.generateObject({ plan: fixturePlan, route, schema: factSchema }),
  );
}

async function smokeGoogle(): Promise<void> {
  console.log('\n══ google ════════════════════════════════════════════════════');
  if (!process.env.GEMINI_API_KEY && !process.env.GOOGLE_API_KEY && !process.env.GOOGLE_APPLICATION_CREDENTIALS_JSON) {
    console.warn('  SKIP: GEMINI_API_KEY / GOOGLE_API_KEY / GOOGLE_APPLICATION_CREDENTIALS_JSON not set.');
    return;
  }
  const adapter = new GoogleGeminiAdapter();
  const route = smokeRoute('google', 'gemini-2.5-flash-lite');

  await runOne('google.generateText', () =>
    adapter.generateText({ plan: fixturePlan, route }),
  );
  await runOne('google.generateObject', () =>
    adapter.generateObject({ plan: fixturePlan, route, schema: factSchema }),
  );
}

async function smokeDeepSeek(): Promise<void> {
  console.log('\n══ deepseek ══════════════════════════════════════════════════');
  if (!process.env.DEEPSEEK_API_KEY) {
    console.warn('  SKIP: DEEPSEEK_API_KEY not set.');
    return;
  }
  const adapter = new DeepSeekAdapter();
  const route = smokeRoute('deepseek', 'deepseek-chat');

  await runOne('deepseek.generateText', () =>
    adapter.generateText({ plan: fixturePlan, route }),
  );
  await runOne('deepseek.generateObject', () =>
    adapter.generateObject({ plan: fixturePlan, route, schema: factSchema }),
  );
}

async function smokeQwen(): Promise<void> {
  console.log('\n══ qwen ══════════════════════════════════════════════════════');
  if (!process.env.DASHSCOPE_API_KEY) {
    console.warn('  SKIP: DASHSCOPE_API_KEY not set.');
    return;
  }
  const adapter = new QwenAdapter();
  const route = smokeRoute('qwen', process.env.QWEN_SMOKE_MODEL ?? 'qwen3.7-plus-us');

  await runOne('qwen.generateText', () =>
    adapter.generateText({ plan: fixturePlan, route }),
  );
  await runOne('qwen.generateObject', () =>
    adapter.generateObject({ plan: fixturePlan, route, schema: factSchema }),
  );
}

// ─── Helpers ───────────────────────────────────────────────────────────────

async function runOne(
  label: string,
  fn: () =>
    | Promise<OracleTextResult>
    | Promise<OracleObjectResult<{ subject: string; predicate: string }>>,
): Promise<void> {
  const startedAt = Date.now();
  try {
    const r = await fn();
    const elapsed = Date.now() - startedAt;
    const isObj = 'object' in r;
    console.log(`  ✓ ${label} (${elapsed}ms)`);
    if (isObj) {
      console.log(`    object: ${JSON.stringify(r.object)}`);
    } else {
      console.log(`    text:   ${r.text.slice(0, 120).replace(/\n/g, ' ')}`);
    }
    console.log(
      `    usage:  input=${r.usage.inputTokens ?? '?'} output=${r.usage.outputTokens ?? '?'} cached=${r.usage.cachedInputTokens ?? 0} cacheWrite=${r.usage.cacheWriteTokens ?? 0}`,
    );
  } catch (err) {
    const elapsed = Date.now() - startedAt;
    console.error(`  ✗ ${label} (${elapsed}ms) FAILED:`, err instanceof Error ? err.message : err);
    process.exitCode = 1;
  }
}

// ─── Main ──────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const target = (process.argv[2] ?? 'all').toLowerCase();
  console.log(`r-providers-smoke target=${target}`);

  if (target === 'vertex' || target === 'all') await smokeVertex();
  if (target === 'anthropic' || target === 'all') await smokeAnthropic();
  if (target === 'openai' || target === 'all') await smokeOpenAI();
  if (target === 'google' || target === 'all') await smokeGoogle();
  if (target === 'deepseek' || target === 'all') await smokeDeepSeek();
  if (target === 'qwen' || target === 'all') await smokeQwen();

  console.log('\nDone.');
}

main()
  .then(() => process.exit(process.exitCode ?? 0))
  .catch((err) => {
    console.error('FATAL:', err);
    process.exit(1);
  });
