/**
 * @deprecated Legacy OpenRouter provider for Vercel AI SDK.
 *
 * OpenRouter is DEPRECATED for production Oracle code. All new model calls
 * must go through the OracleAIClient (R2) with provider-native adapters
 * (Anthropic, Vertex Gemini, OpenAI direct).
 *
 * See:
 *   docs/oracle/02-provider-native-ai-architecture.md
 *   docs/oracle/05-ai-retrofit-phase-packet.md
 *
 * This file remains only to keep the legacy chat route and legacy workers
 * compiling during the R1–R10.5 retrofit. Do not add new callers.
 */

import { createOpenRouter } from '@openrouter/ai-sdk-provider';

let cached: ReturnType<typeof createOpenRouter> | null = null;

/**
 * @deprecated Use the OracleAIClient (R2) once available. Do not add new
 * callers to this function.
 */
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
