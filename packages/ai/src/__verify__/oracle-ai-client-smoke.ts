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
 *   - The ModelRouter tries an explicit ordered candidate chain and fails loud
 *     when every approved candidate fails.
 *   - The EvidenceValidator passes a perfect quote and rejects a paraphrase.
 *
 * This file is in __verify__ so it is never picked up as a production export.
 */

import { z } from 'zod';
import {
  OracleAIClient,
  makeBlock,
  getOracleRoute,
  getEvidenceValidator,
  AllCandidatesFailedError,
  ProviderAdapterNotImplementedError,
  MockProviderAdapter,
  ModelRouter,
  type OracleProviderAdapter,
  type OraclePromptPlan,
  type RouteCandidate,
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

  // ── 4. ModelRouter approved candidate chain ─────────────────────────────
  const unavailableAnthropicAdapter: OracleProviderAdapter = {
    provider: 'anthropic',
    async generateText() {
      throw new ProviderAdapterNotImplementedError('anthropic');
    },
    async generateObject() {
      throw new ProviderAdapterNotImplementedError('anthropic');
    },
  };

  const candidateRouter = new ModelRouter({
    adapters: {
      anthropic: unavailableAnthropicAdapter,
      openai: new MockProviderAdapter({ provider: 'openai', cannedText: 'fallback-OK' }),
    },
  });
  const fallbackPlan: OraclePromptPlan = client.compile({
    taskType: 'interview_chat',
    routeId: 'anthropic_claude_haiku_4_5_interview_primary',
    promptVersion: 'r2-smoke',
    blocks: baseBlocks,
  });
  const anthropicRoute = getOracleRoute('anthropic_claude_haiku_4_5_interview_primary');
  const openAiRoute = getOracleRoute('openai_gpt4o_interview_fallback');
  assert(anthropicRoute !== null, 'anthropic smoke route resolves');
  assert(openAiRoute !== null, 'openai smoke route resolves');
  const candidates: RouteCandidate[] = [
    {
      route: anthropicRoute,
      slot: 'interview',
      isPrimary: true,
      approvedModelId: 'anthropic/claude-haiku-4-5',
    },
    {
      route: openAiRoute,
      slot: 'interview',
      isPrimary: false,
      approvedModelId: 'openai/gpt-4o',
    },
  ];
  const fbResult = await candidateRouter.generateText(fallbackPlan, undefined, candidates);
  assert(fbResult.text === 'fallback-OK', 'ModelRouter dispatches to the next approved candidate when the primary fails');
  assert(fbResult.routeId === 'openai_gpt4o_interview_fallback', 'candidate-chain result records the actual route');
  assert(fbResult.usedNonPrimary === true, 'candidate-chain result records non-primary usage');
  assert(fbResult.attemptedRoutes?.length === 2, 'candidate-chain result records both attempts');

  // ── 4b. Dynamic provider/model route IDs ─────────────────────────────────
  const dynamicRouter = new ModelRouter({
    adapters: {
      qwen: new MockProviderAdapter({ provider: 'qwen', cannedText: 'dynamic-OK' }),
    },
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

  // ── 5. ModelRouter fails loud when all candidates fail ──────────────────
  const strictRouter = new ModelRouter({
    adapters: { anthropic: unavailableAnthropicAdapter },
  });
  let threw = false;
  try {
    await strictRouter.generateText(fallbackPlan, undefined, [candidates[0]!]);
  } catch (err) {
    threw = err instanceof AllCandidatesFailedError;
  }
  assert(threw, 'ModelRouter throws AllCandidatesFailedError when every approved candidate fails');

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
