// Meta Muse, Z.ai GLM and Xiaomi MiMo model list sources.
// Each vendor exposes an OpenAI-compatible /models endpoint; we keep only the
// chat model family and tag rows with the Oracle provider id. Pricing/caps
// come from OpenRouter enrichment where a slug matches.

import OpenAI from 'openai';
import type { RawProviderModel } from './types';
import type { ModelCapabilitySource, ModelProvider } from '../types';
import {
  META_MUSE_BASE_URL,
  MIMO_BASE_URL,
  ZAI_BASE_URL,
} from '../../providers/openai-compatible-adapter';

async function fetchVendorModels(
  provider: ModelProvider,
  source: ModelCapabilitySource,
  apiKeyEnv: string,
  baseUrlEnv: string,
  defaultBaseURL: string,
  isChatModel: (id: string) => boolean,
): Promise<RawProviderModel[]> {
  const apiKey = process.env[apiKeyEnv];
  if (!apiKey) throw new Error(`${apiKeyEnv} not set`);
  const client = new OpenAI({ apiKey, baseURL: process.env[baseUrlEnv] ?? defaultBaseURL });
  const page = await client.models.list();
  return page.data
    .filter((m) => isChatModel(m.id.toLowerCase()))
    .map((m) => ({
      id: `${provider}/${m.id}`,
      provider,
      displayName: m.id,
      contextLength: null,
      maxOutputTokens: null,
      source,
    }));
}

export const fetchMetaMuseModels = () =>
  fetchVendorModels('meta_muse', 'meta_muse_api', 'META_MUSE_API_KEY', 'META_MUSE_BASE_URL', META_MUSE_BASE_URL,
    (id) => id.startsWith('muse-spark'));

export const fetchZaiModels = () =>
  fetchVendorModels('zai', 'zai_api', 'ZAI_API_KEY', 'ZAI_BASE_URL', ZAI_BASE_URL,
    (id) => id.startsWith('glm-'));

export const fetchMimoModels = () =>
  fetchVendorModels('mimo', 'mimo_api', 'MIMO_API_KEY', 'MIMO_BASE_URL', MIMO_BASE_URL,
    (id) => id.startsWith('mimo-') && !id.includes('tts') && !id.includes('audio'));
