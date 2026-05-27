/**
 * Catalog-refresh smoke test.
 * Run: pwsh -Command "& { $env:ANTHROPIC_API_KEY=...; node_modules\.bin\tsx.CMD scripts/verify-catalog.ts }"
 */

import { fetchAnthropicModels } from '../packages/ai/src/model-capabilities/sources/anthropic';
import { fetchOpenAIModels } from '../packages/ai/src/model-capabilities/sources/openai';
import { fetchGoogleModels } from '../packages/ai/src/model-capabilities/sources/google';
import { fetchDeepSeekModels } from '../packages/ai/src/model-capabilities/sources/deepseek';
import { fetchQwenModels } from '../packages/ai/src/model-capabilities/sources/qwen';
import { fetchOpenRouterEnrichment } from '../packages/ai/src/model-capabilities/sources/openrouter';
import type { OpenRouterEnrichment } from '../packages/ai/src/model-capabilities/sources/openrouter';

const EMPTY: OpenRouterEnrichment = {
  contextLength: null, maxOutputTokens: null,
  promptPer1mUsd: null, completionPer1mUsd: null,
  vision: false, pdf: false, thinking: false,
  structuredOutputs: false, toolCalling: false,
  promptCaching: false, knowledgeCutoff: null,
};

function lookupEnrichment(
  map: Map<string, OpenRouterEnrichment>,
  modelId: string,
): { enrichment: OpenRouterEnrichment; matched: boolean; via: string } {
  const tried: string[] = [];

  const tryKey = (key: string, label: string) => {
    tried.push(key);
    const hit = map.get(key);
    if (hit) return { enrichment: hit, matched: true, via: label };
    return null;
  };

  // 1. Exact
  let r = tryKey(modelId, 'exact');
  if (r) return r;

  // 2. Strip date / version-stamp suffixes
  const stripped = modelId
    .replace(/-\d{4}-\d{2}-\d{2}$/, '') // -YYYY-MM-DD
    .replace(/-\d{8}$/, '')              // -YYYYMMDD
    .replace(/-\d{4}$/, '');             // -MMDD / 4-digit version
  if (stripped !== modelId) {
    r = tryKey(stripped, `→ ${stripped}`);
    if (r) return r;
  }

  // 3. Dash → dot for version numbers (claude-opus-4-7 → claude-opus-4.7)
  const dotted = stripped.replace(/-(\d)-(\d)(?=-|$)/g, '-$1.$2');
  if (dotted !== stripped) {
    r = tryKey(dotted, `→ ${dotted}`);
    if (r) return r;
  }

  // 4. Original-with-dotted-version (in case stripping was wrong but dot helps)
  const origDotted = modelId.replace(/-(\d)-(\d)(?=-|$)/g, '-$1.$2');
  if (origDotted !== modelId && origDotted !== dotted) {
    r = tryKey(origDotted, `→ ${origDotted}`);
    if (r) return r;
  }

  return { enrichment: EMPTY, matched: false, via: `none (tried: ${tried.join(', ')})` };
}

async function main() {
  console.log('=== Oracle catalog verify ===\n');

  console.log('Fetching OpenRouter enrichment map…');
  const orMap = await fetchOpenRouterEnrichment();
  console.log(`  ✓ ${orMap.size} OpenRouter models indexed\n`);

  // Debug: show what OpenRouter actually has for "claude-opus" / "claude-haiku" / "claude-sonnet"
  console.log('── OpenRouter keys matching /claude-(opus|haiku|sonnet)/');
  const claudeKeys = [...orMap.keys()].filter((k) => /anthropic\/claude-(opus|haiku|sonnet)/.test(k)).sort();
  claudeKeys.forEach((k) => console.log(`    ${k}`));
  console.log();

  console.log('── OpenRouter keys matching /gpt-4o-(transcribe|mini-transcribe)/');
  const oaKeys = [...orMap.keys()].filter((k) => /gpt-4o.*transcribe/.test(k)).sort();
  oaKeys.forEach((k) => console.log(`    ${k}`));
  if (oaKeys.length === 0) console.log('    (none)');
  console.log();

  const providers = [
    { name: 'Anthropic', fn: fetchAnthropicModels, envKey: 'ANTHROPIC_API_KEY' },
    { name: 'OpenAI',    fn: fetchOpenAIModels,    envKey: 'OPENAI_API_KEY' },
    { name: 'Google',    fn: fetchGoogleModels,    envKey: 'GOOGLE_APPLICATION_CREDENTIALS_JSON' },
    { name: 'DeepSeek',  fn: fetchDeepSeekModels,  envKey: 'DEEPSEEK_API_KEY' },
    { name: 'Qwen',      fn: fetchQwenModels,      envKey: 'DASHSCOPE_API_KEY' },
  ] as const;

  for (const { name, fn, envKey } of providers) {
    if (!process.env[envKey]) {
      console.log(`── ${name}: SKIPPED (${envKey} not set)\n`);
      continue;
    }
    console.log(`── ${name}`);
    try {
      const models = await fn();
      const matched: string[] = [];
      const unmatched: string[] = [];
      for (const m of models) {
        const { matched: hit, via } = lookupEnrichment(orMap, m.id);
        if (hit) matched.push(`${m.id}  [${via}]`);
        else unmatched.push(`${m.id}  ${via}`);
      }
      console.log(`  enriched: ${matched.length}/${models.length}`);
      if (matched.length) {
        console.log('  matched:');
        matched.forEach((s) => console.log(`    ✓ ${s}`));
      }
      if (unmatched.length) {
        console.log('  unmatched:');
        unmatched.forEach((s) => console.log(`    ✗ ${s}`));
      }
      console.log();
    } catch (e) {
      console.error(`  ✗ ${name} failed:`, e instanceof Error ? e.message : e);
      console.log();
    }
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
