/**
 * OpenAI + Qwen cache request-shape regression gate.
 *
 * Run with:
 *   pnpm --filter @oracle/ai exec tsx src/__verify__/openai-qwen-cache-requests.ts
 *
 * No network: SDK clients are stubbed after construction. This verifies only
 * the request fields our adapters are responsible for emitting.
 */

import { getContextCompiler } from '../context/context-compiler';
import { makeBlock } from '../context/prompt-blocks';
import { OpenAIAdapter } from '../providers/openai-adapter';
import { QwenAdapter } from '../providers/qwen-adapter';
import type { OracleModelRoute } from '../routes';
import { z } from 'zod';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`x ${msg}`);
    process.exit(1);
  }
  console.log(`ok ${msg}`);
}

function route(provider: 'openai' | 'qwen', modelId: string): OracleModelRoute {
  return {
    routeId: `${provider}/${modelId}`,
    role: 'interview',
    tier: 'primary',
    internalPurpose: null,
    provider,
    modelId,
    displayName: modelId,
    recommendedUse: 'cache request verification',
    costTier: 'balanced_default',
    cacheStrategy:
      provider === 'openai'
        ? 'openai_automatic_with_retention'
        : 'qwen_explicit_context_cache',
    structuredOutputStrategy: 'schema_prompt_plus_validator',
    supportsVision: false,
    supportsStreaming: false,
    supportsToolCalling: false,
    supportsStructuredOutput: true,
    supportsReasoningControls: false,
    enabled: true,
  };
}

const plan = getContextCompiler().compile({
  taskType: 'interview_chat',
  routeId: 'verify-route',
  promptVersion: 'cache-request-gate',
  blocks: [
    makeBlock({
      id: 'system',
      label: 'System',
      kind: 'stable_system',
      content: 'Stable Oracle instructions.',
      reasonIncluded: 'stable prompt',
    }),
    makeBlock({
      id: 'dynamic',
      label: 'Dynamic',
      kind: 'dynamic_input',
      content: 'Current user turn.',
      reasonIncluded: 'current request',
    }),
  ],
});

async function verifyOpenAI() {
  const calls: Array<Record<string, unknown>> = [];
  const adapter = new OpenAIAdapter({ apiKey: 'test-key' });
  (adapter as unknown as { client: unknown }).client = {
    chat: {
      completions: {
        create: async (req: Record<string, unknown>) => {
          calls.push(req);
          return {
            id: `openai-${calls.length}`,
            choices: [
              {
                message: {
                  content: calls.length === 1 ? 'hello' : '{"ok":true}',
                },
                finish_reason: 'stop',
              },
            ],
            usage: {
              prompt_tokens: 1200,
              completion_tokens: 20,
              prompt_tokens_details: { cached_tokens: 700 },
            },
          };
        },
      },
    },
  };

  const openaiRoute = route('openai', 'gpt-4.1-mini');
  await adapter.generateText({
    plan,
    route: openaiRoute,
    providerOptions: {
      cache: { preferLongLivedCache: false },
    },
  });
  await adapter.generateObject({
    plan,
    route: openaiRoute,
    schema: z.object({ ok: z.boolean() }),
    providerOptions: {
      cache: { preferLongLivedCache: true },
    },
  });

  assert(calls.length === 2, 'OpenAI made text and object requests');
  assert(calls[0]?.prompt_cache_retention === 'in_memory', 'OpenAI chat uses in-memory cache retention');
  assert(calls[1]?.prompt_cache_retention === '24h', 'OpenAI long-lived object call uses 24h retention');
  assert(!('prompt_cache_key' in calls[0]!), 'OpenAI request does not invent prompt_cache_key');
  assert(
    (calls[1]?.response_format as { type?: string } | undefined)?.type === 'json_schema',
    'OpenAI object request keeps strict JSON schema response_format',
  );
}

async function verifyQwen() {
  const chatCalls: Array<Record<string, unknown>> = [];
  const responseCalls: Array<{ body: Record<string, unknown>; options: Record<string, unknown> }> = [];
  const adapter = new QwenAdapter({ apiKey: 'test-key' });
  (adapter as unknown as { client: unknown }).client = {
    chat: {
      completions: {
        create: async (req: Record<string, unknown>) => {
          chatCalls.push(req);
          return {
            id: 'qwen-chat-1',
            choices: [{ message: { content: 'hello' }, finish_reason: 'stop' }],
            usage: {
              prompt_tokens: 1500,
              completion_tokens: 20,
              prompt_tokens_details: { cached_tokens: 900 },
            },
          };
        },
      },
    },
    responses: {
      create: async (body: Record<string, unknown>, options: Record<string, unknown>) => {
        responseCalls.push({ body, options });
        return {
          id: 'qwen-response-1',
          output_text: 'hello via response',
          usage: {
            input_tokens: 1500,
            output_tokens: 20,
            input_tokens_details: { cached_tokens: 950 },
          },
        };
      },
    },
  };

  const qwenRoute = route('qwen', 'qwen3.7-max');
  await adapter.generateText({
    plan,
    route: qwenRoute,
    providerOptions: {
      messages: [
        { role: 'user', content: 'first turn' },
        { role: 'assistant', content: 'prior answer' },
        { role: 'user', content: 'latest turn' },
      ],
    },
  });

  assert(chatCalls.length === 1, 'Qwen chat-completions path was used without session hints');
  const messages = chatCalls[0]?.messages as Array<{ content?: unknown }> | undefined;
  const penultimate = messages?.[messages.length - 2]?.content as Array<Record<string, unknown>> | undefined;
  assert(
    Array.isArray(penultimate) && penultimate.some((part) => part.cache_control),
    'Qwen marks the reusable penultimate message with cache_control',
  );

  await adapter.generateText({
    plan,
    route: qwenRoute,
    providerOptions: {
      cache: {
        sessionCacheKey: 'interview-chat:channel-1',
        previousResponseId: 'resp_prev',
        preferLongLivedCache: true,
      },
    },
  });

  assert(responseCalls.length === 1, 'Qwen Responses path was used with session hints');
  assert(
    responseCalls[0]?.body.prompt_cache_key === 'interview-chat:channel-1',
    'Qwen Responses request includes prompt_cache_key',
  );
  assert(
    responseCalls[0]?.body.previous_response_id === 'resp_prev',
    'Qwen Responses request includes previous_response_id',
  );
  assert(
    responseCalls[0]?.body.prompt_cache_retention === '24h',
    'Qwen Responses request uses long-lived retention when requested',
  );
  assert(
    (responseCalls[0]?.options.headers as Record<string, unknown> | undefined)?.['x-dashscope-session-cache'] === 'enable',
    'Qwen Responses request enables DashScope session cache header',
  );
}

async function main() {
  console.log('OpenAI + Qwen cache request gate\n');
  await verifyOpenAI();
  await verifyQwen();
  console.log('\nOpenAI + Qwen cache request gate: PASS');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
