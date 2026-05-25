/**
 * VertexGeminiAdapter — direct @google/genai Vertex AI integration.
 *
 * R2 (this commit): interface + stub. Throws ProviderAdapterNotImplementedError
 * until R3+ wires the real SDK call.
 *
 * Implementation responsibilities (R3+):
 * - Use implicit caching by default for repeated stable prefixes.
 * - Use explicit `cachedContent` only when the cost heuristic justifies it:
 *     useExplicitGeminiCache = (sourceTokenEstimate >= 25_000 && expectedReuseCount >= 3)
 *                           || (sourceTokenEstimate >= 100_000 && expectedReuseCount >= 2)
 *   See docs/oracle/02-provider-native-ai-architecture.md "Explicit Cache Heuristic".
 * - Track explicit caches in `provider_cached_content` and delete in a `finally`
 *   when the planned reuse window completes.
 * - Read `usageMetadata.cachedContentTokenCount` into OracleUsage.cachedInputTokens.
 * - Native JSON schema structured output.
 * - Authenticate via workload identity or service-account credentials passed
 *   through env vars (GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION,
 *   GOOGLE_CLIENT_EMAIL, GOOGLE_PRIVATE_KEY).
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "Google Vertex AI
 * / Gemini direct".
 */

import type { OracleObjectResult, OracleTextResult } from '../client/types';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';
import { ProviderAdapterNotImplementedError } from './types';

export class VertexGeminiAdapter implements OracleProviderAdapter {
  readonly provider = 'vertex' as const;

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async generateText(_args: GenerateTextArgs): Promise<OracleTextResult> {
    throw new ProviderAdapterNotImplementedError('vertex');
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async generateObject<TSchema, TOutput>(
    _args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    throw new ProviderAdapterNotImplementedError('vertex');
  }
}
