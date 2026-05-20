// OpenRouter provider for Vercel AI SDK.
//
// Usage:
//   import { openrouter } from '@oracle/ai/openrouter';
//   const model = openrouter('anthropic/claude-sonnet-4.6');
//
// Single shared instance so callers don't accidentally create N providers.

import { createOpenRouter } from '@openrouter/ai-sdk-provider';

let cached: ReturnType<typeof createOpenRouter> | null = null;

export function getOpenRouter(): ReturnType<typeof createOpenRouter> {
  if (cached) return cached;
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    throw new Error(
      'OPENROUTER_API_KEY is missing. See DECISIONS.md D0.4 — populate Vercel env first.',
    );
  }
  cached = createOpenRouter({
    apiKey,
    // Optional headers for analytics on openrouter.ai
    headers: {
      'HTTP-Referer': 'https://theoracle.popcreations.local',
      'X-Title': 'The Oracle',
    },
  });
  return cached;
}
