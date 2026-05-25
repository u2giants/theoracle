/**
 * AnthropicAdapter — direct @anthropic-ai/sdk integration.
 *
 * R2 (this commit): interface + stub. Throws ProviderAdapterNotImplementedError
 * until R3+ wires the real SDK call.
 *
 * Implementation responsibilities (R3+):
 * - Use `cache_control: { type: 'ephemeral' }` on the stable prefix block.
 * - Place stable system + tool definitions + schema before any dynamic input.
 * - Tool-call structured output mode.
 * - Read `usage.cache_read_input_tokens` and `usage.cache_creation_input_tokens`
 *   into OracleUsage.{cachedInputTokens, cacheWriteTokens}.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md → "Anthropic direct".
 */

import type { OracleObjectResult, OracleTextResult } from '../client/types';
import type {
  GenerateObjectArgs,
  GenerateTextArgs,
  OracleProviderAdapter,
} from './types';
import { ProviderAdapterNotImplementedError } from './types';

export class AnthropicAdapter implements OracleProviderAdapter {
  readonly provider = 'anthropic' as const;

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async generateText(_args: GenerateTextArgs): Promise<OracleTextResult> {
    throw new ProviderAdapterNotImplementedError('anthropic');
  }

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  async generateObject<TSchema, TOutput>(
    _args: GenerateObjectArgs<TSchema>,
  ): Promise<OracleObjectResult<TOutput>> {
    throw new ProviderAdapterNotImplementedError('anthropic');
  }
}
