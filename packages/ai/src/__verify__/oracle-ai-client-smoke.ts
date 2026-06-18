/**
 * R2 acceptance gate verification script.
 *
 * Run with: pnpm --filter @oracle/ai exec tsx src/__verify__/oracle-ai-client-smoke.ts
 *
 * Proves:
 *   - OracleAIClient in test mode can dispatch a generateText call to all 3
 *     provider shapes (Anthropic, Vertex, OpenAI) via the mock adapter.
 *   - OracleAIClient can dispatch a generateObject call and the resulting
 *     output passes through the structured-output validator.
 *   - The ContextCompiler enforces stable-before-dynamic block ordering.
 *   - The ModelRouter falls back from a not-yet-implemented production
 *     adapter to its configured Fallback route when fallbackOnError=true.
 *   - The EvidenceValidator passes a perfect quote and rejects a paraphrase.
 *
 * This file is in __verify__ so it is never picked up as a production export.
 */

import { z } from 'zod';
import {
  OracleAIClient,
  makeBlock,
  getEvidenceValidator,
  ProviderAdapterNotImplementedError,
  MockProviderAdapter,
  ModelRouter,
  type OracleProviderAdapter,
  type OraclePromptPlan,
} from '../index';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

async function main() {
  console.log('R2 OracleAIClient smoke test\n');

  // ── 1. ContextCompiler stable-before-dynamic invariant ─────────────────
  const client = new OracleAIClient({ mode: 'test' });
  const baseBlocks = [
    makeBlock({
      id: 'sys',
      label: 'Oracle system prompt',
      kind: 'stable_system',
      content: 'You are the Oracle.',
      reasonIncluded: 'core identity',
    }),
    makeBlock({
      id: 'user',
      label: 'current turn',
      kind: 'dynamic_input',
      content: 'Hello Oracle.',
      reasonIncluded: 'current user message',
    }),
  ];
  const plan = client.compile({
    taskType: 'interview_chat',
    routeId: 'anthropic_claude_haiku_4_5_interview_primary',
    promptVersion: 'r2-smoke',
    blocks: baseBlocks,
  });
  assert(plan.blocks[0]!.kind === 'stable_system', 'stable_system block sorted first');
  assert(plan.blocks[1]!.kind === 'dynamic_input', 'dynamic_input block sorted last');
  assert(plan.metadata.stablePrefixHash.length === 64, 'stablePrefixHash is sha256 hex');
  assert(plan.metadata.dynamicInputHash !== plan.metadata.stablePrefixHash, 'stable and dynamic hashes differ');

  // ── 2. Mock generateText through every provider shape ───────────────────
  for (const routeId of [
    'anthropic_claude_haiku_4_5_interview_primary',   // anthropic
    'vertex_gemini_2_5_flash_extraction_primary',     // vertex
    'openai_gpt4o_interview_fallback',                // openai
  ]) {
    const result = await client.runText({
      taskType: 'interview_chat',
      routeId,
      promptVersion: 'r2-smoke',
      blocks: baseBlocks,
    });
    assert(typeof result.text === 'string' && result.text.length > 0, `runText returned text for ${routeId}`);
    assert(typeof result.usage.latencyMs === 'number', `runText returned usage.latencyMs for ${routeId}`);
  }

  // ── 3. generateObject + structured-output validator ─────────────────────
  const schema = z.object({ ok: z.boolean(), provider: z.string() });
  const objResult = await client.runObject({
    taskType: 'message_claim_extraction',
    routeId: 'vertex_gemini_2_5_flash_extraction_primary',
    promptVersion: 'r2-smoke',
    blocks: baseBlocks,
    schema,
  });
  assert(objResult.validation.ok === true, 'mock object passes Zod validation');
  assert(objResult.object.provider === 'vertex', 'mock object carries provider tag');

  // ── 4. ModelRouter fallback path ────────────────────────────────────────
  const unavailableAnthropicAdapter: OracleProviderAdapter = {
    provider: 'anthropic',
    async generateText() {
      throw new ProviderAdapterNotImplementedError('anthropic');
    },
    async generateObject() {
      throw new ProviderAdapterNotImplementedError('anthropic');
    },
  };

  // Build a router with an unavailable Anthropic adapter and a mock for openai.
  // ProviderAdapterNotImplementedError is in our fallback whitelist, so the
  // router should dispatch to the configured fallback route.
  const fallbackRouter = new ModelRouter({
    adapters: {
      anthropic: unavailableAnthropicAdapter,
      openai: new MockProviderAdapter({ provider: 'openai', cannedText: 'fallback-OK' }),
    },
    fallbackOnError: true,
  });
  const fallbackPlan: OraclePromptPlan = client.compile({
    taskType: 'interview_chat',
    routeId: 'anthropic_claude_haiku_4_5_interview_primary', // primary → throws → fallback to openai_gpt4o_interview_fallback
    promptVersion: 'r2-smoke',
    blocks: baseBlocks,
  });
  const fbResult = await fallbackRouter.generateText(fallbackPlan);
  assert(fbResult.text === 'fallback-OK', 'ModelRouter dispatched to Fallback route when primary stub threw NotImplemented');
  assert(fbResult.routeId === 'openai_gpt4o_interview_fallback', 'fallback result records the actual fallback route');
  assert(
    fbResult.fellBackFromRouteId === 'anthropic_claude_haiku_4_5_interview_primary',
    'fallback result records the original route',
  );

  // ── 4b. Dynamic provider/model route IDs ─────────────────────────────────
  const dynamicRouter = new ModelRouter({
    adapters: {
      qwen: new MockProviderAdapter({ provider: 'qwen', cannedText: 'dynamic-OK' }),
    },
    fallbackOnError: true,
  });
  const dynamicPlan: OraclePromptPlan = client.compile({
    taskType: 'document_claim_extraction',
    routeId: 'qwen/qwen3.7-plus',
    promptVersion: 'r2-smoke',
    blocks: baseBlocks,
  });
  const dynamicResult = await dynamicRouter.generateText(dynamicPlan);
  assert(dynamicResult.text === 'dynamic-OK', 'ModelRouter dispatches dynamic provider/model route IDs');
  assert(dynamicResult.routeId === 'qwen/qwen3.7-plus', 'dynamic route metadata preserves provider/model routeId');
  assert(dynamicResult.provider === 'qwen', 'dynamic route metadata records provider');
  assert(dynamicResult.modelId === 'qwen3.7-plus', 'dynamic route metadata records model id');

  const dynamicFallbackRouter = new ModelRouter({
    adapters: {
      vertex: new MockProviderAdapter({ provider: 'vertex', cannedText: 'dynamic-fallback-OK' }),
    },
    fallbackOnError: true,
  });
  const dynamicFallbackResult = await dynamicFallbackRouter.generateText(dynamicPlan);
  assert(
    dynamicFallbackResult.text === 'dynamic-fallback-OK',
    'ModelRouter falls back when a dynamic route provider adapter is unavailable',
  );
  assert(
    dynamicFallbackResult.routeId === 'vertex_gemini_2_5_flash_extraction_primary',
    'dynamic fallback result records the actual fallback route',
  );
  assert(
    dynamicFallbackResult.fellBackFromRouteId === 'qwen/qwen3.7-plus',
    'dynamic fallback result records the original provider/model route',
  );

  // ── 5. ModelRouter surfaces non-transient errors (no fallback) ──────────
  const strictRouter = new ModelRouter({
    adapters: { anthropic: unavailableAnthropicAdapter },
    fallbackOnError: false,
  });
  let threw = false;
  try {
    await strictRouter.generateText(fallbackPlan);
  } catch (err) {
    threw = err instanceof ProviderAdapterNotImplementedError;
  }
  assert(threw, 'ModelRouter with fallbackOnError=false surfaces NotImplemented error');

  // ── 6. EvidenceValidator: perfect quote passes, paraphrase fails ────────
  const ev = getEvidenceValidator();
  const sourceText = 'We always send that to China after licensor approval.';
  const exact = ev.validateQuote({ sourceText, exactQuoteProvided: 'send that to China after licensor approval' });
  assert(exact.verdict === 'exact_match', 'EvidenceValidator accepts a verbatim substring');
  const paraphrase = ev.validateQuote({
    sourceText,
    exactQuoteProvided: 'we usually send things to China after licensors approve them',
  });
  assert(paraphrase.verdict === 'failed', 'EvidenceValidator rejects a paraphrase');

  console.log('\nR2 smoke gate: PASS');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
