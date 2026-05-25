/**
 * OpenAIAdapter — direct `openai` SDK integration.
 *
 * R2 (this commit): interface + stub. Throws ProviderAdapterNotImplementedError
 * until R3+ wires the real SDK call.
 *
 * Implementation responsibilities (R3+):
 * - Rely on automatic prefix caching. Stable system/tools/schema at the top,
 *   dynamic input at the bottom.
 * - Use task-specific `prompt_cache_key` and `prompt_cache_retention` where
 *   supported.
 * - Strict JSON schema response_format for structured output.
 * - Read `usage.prompt_tokens_details.cached_tokens` into
 *   OracleUsage.cachedInputTokens.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "OpenAI direct".
 */

import type { OracleObjectResult, OracleTextResult } from '../client/types';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';
import { ProviderAdapterNotImplementedError } from './types';

export class OpenAIAdapter implements OracleProviderAdapter {
  readonly provider = 'openai' as const;

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async generateText(_args: GenerateTextArgs): Promise<OracleTextResult> {
    throw new ProviderAdapterNotImplementedError('openai');
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async generateObject<TSchema, TOutput>(
    _args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    throw new ProviderAdapterNotImplementedError('openai');
  }
}
