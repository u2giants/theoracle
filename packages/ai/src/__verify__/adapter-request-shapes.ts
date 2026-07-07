import { z } from 'zod';
import { AnthropicAdapter } from '../providers/anthropic-adapter';
import { DeepSeekAdapter } from '../providers/deepseek-adapter';
import { QwenAdapter } from '../providers/qwen-adapter';
import { missingRequirements } from '../routes/capability-requirements';
import type { OraclePromptPlan } from '../client/types';
import type { OracleModelRoute } from '../routes';
import type { ModelCapability } from '../model-capabilities';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const plan: OraclePromptPlan = {
  taskType: 'admin_explanation',
  routeId: 'verify-adapter-shapes',
  promptVersion: 'verify',
  blocks: [
    {
      id: 'system',
      label: 'system',
      kind: 'stable_system',
      content: 'Return concise answers.',
      hash: 's',
      cacheEligible: true,
      reasonIncluded: 'verify',
    },
    {
      id: 'user',
      label: 'user',
      kind: 'dynamic_input',
      content: 'Return the requested object.',
      hash: 'u',
      cacheEligible: false,
      reasonIncluded: 'verify',
    },
  ],
  metadata: { stablePrefixHash: 's', dynamicInputHash: 'u' },
};

function route(provider: OracleModelRoute['provider'], modelId: string): OracleModelRoute {
  return {
    routeId: `verify-${provider}-${modelId}`,
    role: null,
    tier: 'internal_subroute',
    internalPurpose: 'schema_repair',
    provider,
    modelId,
    displayName: modelId,
    recommendedUse: 'verify adapter request shape',
    costTier: 'cheap_default',
    cacheStrategy: 'none',
    structuredOutputStrategy: 'native_json_schema',
    supportsVision: false,
    supportsStreaming: false,
    supportsToolCalling: true,
    supportsStructuredOutput: true,
    supportsReasoningControls: false,
    enabled: true,
  };
}

async function verifyAnthropicTemperature(): Promise<void> {
  process.env.ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY || 'test-key';
  const adapter = new AnthropicAdapter({ apiKey: 'test-key' });
  const calls: Array<Record<string, unknown>> = [];
  (adapter as unknown as { client: { messages: { create: (body: unknown) => Promise<unknown> } } }).client.messages.create =
    async (body: unknown) => {
      calls.push(body as Record<string, unknown>);
      return {
        id: 'msg_test',
        content: [{ type: 'tool_use', input: { value: 'ok' } }],
        usage: { input_tokens: 1, output_tokens: 1 },
        stop_reason: 'tool_use',
      };
    };

  const schema = z.object({ value: z.string() });
  await adapter.generateObject({
    plan,
    route: route('anthropic', 'claude-sonnet-5'),
    schema,
  });
  assert(!('temperature' in calls[0]!), 'claude-sonnet-5 request must omit temperature');

  await adapter.generateObject({
    plan,
    route: route('anthropic', 'claude-sonnet-4-5'),
    schema,
  });
  assert(calls[1]!.temperature === 0.1, 'claude-sonnet-4-5 structured request should keep deterministic temperature');

  const thinkingRoute = { ...route('anthropic', 'claude-sonnet-4-5'), reasoningEffort: 'low' as const };
  await adapter.generateText({ plan, route: thinkingRoute });
  assert(calls[2]!.temperature === 1, 'Anthropic thinking requests should use default temperature on models that accept it');
}

async function verifyDeepSeekJsonMode(): Promise<void> {
  process.env.DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY || 'test-key';
  const adapter = new DeepSeekAdapter({ apiKey: 'test-key' });
  const captured: {
    response_format?: { type?: string };
    max_tokens?: number;
    messages?: Array<{ content: unknown }>;
  } = {};
  (adapter as unknown as { client: { chat: { completions: { create: (body: unknown) => Promise<unknown> } } } }).client.chat.completions.create =
    async (body: unknown) => {
      Object.assign(captured, body as {
        response_format?: { type?: string };
        max_tokens?: number;
        messages?: Array<{ content: unknown }>;
      });
      return {
        id: 'chatcmpl_test',
        choices: [{ message: { content: '{"value":"ok"}' }, finish_reason: 'stop' }],
        usage: { prompt_tokens: 1, completion_tokens: 1, prompt_cache_hit_tokens: 0 },
      };
    };

  await adapter.generateObject({
    plan,
    route: route('deepseek', 'deepseek-chat'),
    schema: z.object({ value: z.string() }),
    providerOptions: { maxOutputTokens: 1234 },
  });
  assert(captured.response_format?.type === 'json_object', 'DeepSeek must request json_object mode');
  assert(captured.max_tokens === 1234, 'DeepSeek generateObject must honor maxOutputTokens');
  const messages = captured.messages;
  assert(
    JSON.stringify(messages).toLowerCase().includes('json'),
    'DeepSeek json_object mode must include JSON guidance in messages',
  );
}

async function verifyQwenUsage(): Promise<void> {
  process.env.DASHSCOPE_API_KEY = process.env.DASHSCOPE_API_KEY || 'test-key';
  const adapter = new QwenAdapter({ apiKey: 'test-key' });
  (adapter as unknown as { client: { chat: { completions: { create: () => Promise<unknown> } } } }).client.chat.completions.create =
    async () => ({
      id: 'chatcmpl_test',
      choices: [{ message: { content: 'ok' }, finish_reason: 'stop' }],
      usage: {
        prompt_tokens: 10,
        completion_tokens: 20,
        prompt_tokens_details: { cached_tokens: 3, cache_creation_input_tokens: 7 },
        completion_tokens_details: { reasoning_tokens: 5 },
      },
    });

  const result = await adapter.generateText({
    plan,
    route: { ...route('qwen', 'qwen3.7-plus-us'), reasoningEffort: 'low' },
  });
  assert(result.usage.cachedInputTokens === 3, 'Qwen cached token reads should be normalized');
  assert(result.usage.cacheWriteTokens === 7, 'Qwen cache creation tokens should be normalized');
  assert(result.usage.reasoningTokens === 5, 'Qwen reasoning tokens should be normalized');
}

function verifyCapabilityGates(): void {
  const base: ModelCapability = {
    id: 'google/gemini-2.5-pro',
    provider: 'google',
    displayName: 'gemini-2.5-pro',
    contextLength: 1_000_000,
    maxOutputTokens: 65_536,
    promptPer1mUsd: 1,
    completionPer1mUsd: 1,
    vision: true,
    pdf: true,
    thinking: true,
    structuredOutputs: true,
    toolCalling: true,
    promptCaching: true,
    outputCap: true,
    knowledgeCutoff: null,
    source: 'google_api',
  };
  assert(
    missingRequirements(base, 'extraction').length === 0,
    'Gemini should remain allowed for ordinary extraction schemas',
  );
  assert(
    missingRequirements(base, 'workflow_read').includes('complex structured outputs (Gemini schema complexity limit)'),
    'Gemini should not satisfy workflow_read complex-schema requirements',
  );
  assert(
    missingRequirements({ ...base, provider: 'qwen', structuredOutputs: false }, 'macro')
      .includes('strict JSON Schema enforcement'),
    'Qwen json_object models should not satisfy strict macro structured-output requirements',
  );
}

async function main(): Promise<void> {
  await verifyAnthropicTemperature();
  await verifyDeepSeekJsonMode();
  await verifyQwenUsage();
  verifyCapabilityGates();
  console.log('PASS adapter request shapes');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
