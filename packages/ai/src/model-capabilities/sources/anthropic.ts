// Anthropic model list source.
// Calls Anthropic's /v1/models endpoint to get the authoritative list of
// available models. Capabilities and pricing come separately from OpenRouter.

import Anthropic from '@anthropic-ai/sdk';
import type { RawProviderModel } from './types';

export async function fetchAnthropicModels(): Promise<RawProviderModel[]> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY not set');

  const client = new Anthropic({ apiKey });
  const results: RawProviderModel[] = [];

  // Paginate through all available models.
  for await (const model of await client.models.list({ limit: 100 })) {
    results.push({
      id: `anthropic/${model.id}`,
      provider: 'anthropic',
      displayName: model.display_name ?? model.id,
      contextLength: null,     // not returned by Anthropic's model list endpoint
      maxOutputTokens: null,
      source: 'anthropic_api',
    });
  }

  return results;
}
