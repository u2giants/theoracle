import { createHash } from 'node:crypto';
import type { OraclePromptPlan, OracleTaskType, PromptBlock } from '../client/types';

export interface VertexFileCacheSource {
  gcsUri?: string;
  localPath?: string;
  mimeType: string;
  fileName?: string;
  sourceHash?: string;
}

export interface CacheHints {
  disableCache?: boolean;
  preferLongLivedCache?: boolean;
  preferExplicitCache?: boolean;
  cacheTtlSeconds?: number;
  expectedReuseCount?: number;
  persistProviderCacheRecord?: boolean;
  sourceDescription?: string;
  cleanupOwner?: string;
  createdByJobRunId?: string;
  latestPlannedReuseStep?: string;
  sessionCacheKey?: string;
  previousResponseId?: string;
  vertexFileCacheSource?: VertexFileCacheSource;
}

export interface ProviderCacheOptions {
  messages?: Array<Record<string, unknown>>;
  cache?: CacheHints;
  [key: string]: unknown;
}

export function estimateTextTokens(text: string): number {
  if (!text) return 0;
  return Math.ceil(text.length / 4);
}

export function estimatePlanStableTokens(plan: OraclePromptPlan): number {
  const stableText = plan.blocks
    .filter((block) =>
      block.kind === 'stable_system' ||
      block.kind === 'stable_schema' ||
      block.kind === 'stable_tool_definition' ||
      block.kind === 'output_contract',
    )
    .map((block) => block.content)
    .join('\n\n');
  return estimateTextTokens(stableText);
}

export function pickAnthropicCacheTtl(
  taskType: OracleTaskType,
  providerOptions?: Record<string, unknown>,
): '5m' | '1h' {
  const hints = getCacheHints(providerOptions);
  if (hints?.cacheTtlSeconds && hints.cacheTtlSeconds > 5 * 60) return '1h';
  if (hints?.preferLongLivedCache) return '1h';
  return taskType === 'interview_chat' ? '5m' : '1h';
}

export function pickOpenAICacheRetention(
  taskType: OracleTaskType,
  providerOptions?: Record<string, unknown>,
): 'in_memory' | '24h' {
  const hints = getCacheHints(providerOptions);
  if (hints?.preferLongLivedCache) return '24h';
  if (hints?.cacheTtlSeconds && hints.cacheTtlSeconds > 10 * 60) return '24h';
  return taskType === 'interview_chat' ? 'in_memory' : '24h';
}

export function pickVertexCacheTtlSeconds(
  taskType: OracleTaskType,
  providerOptions?: Record<string, unknown>,
): number {
  const hints = getCacheHints(providerOptions);
  if (typeof hints?.cacheTtlSeconds === 'number' && hints.cacheTtlSeconds > 0) {
    return Math.floor(hints.cacheTtlSeconds);
  }
  return taskType === 'interview_chat' ? 3600 : 86400;
}

export function getCacheHints(
  providerOptions?: Record<string, unknown>,
): CacheHints | undefined {
  const cache = providerOptions?.cache;
  if (!cache || typeof cache !== 'object') return undefined;
  return cache as CacheHints;
}

export function shouldDisableCache(providerOptions?: Record<string, unknown>): boolean {
  return getCacheHints(providerOptions)?.disableCache === true;
}

export function normalizeMessageContentArray(
  content: unknown,
): Array<Record<string, unknown>> {
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (part && typeof part === 'object') return { ...(part as Record<string, unknown>) };
      return { type: 'text', text: String(part) };
    });
  }
  if (typeof content === 'string') return [{ type: 'text', text: content }];
  if (content && typeof content === 'object') return [{ ...(content as Record<string, unknown>) }];
  return [{ type: 'text', text: String(content ?? '') }];
}

export function markLastTextPartCacheable(
  content: Array<Record<string, unknown>>,
  ttl?: '5m' | '1h',
): Array<Record<string, unknown>> {
  const next = content.map((part) => ({ ...part }));
  for (let i = next.length - 1; i >= 0; i -= 1) {
    const part = next[i]!;
    const type = part.type;
    if (type === 'text' || type === undefined) {
      part.cache_control = ttl
        ? { type: 'ephemeral', ttl }
        : { type: 'ephemeral' };
      return next;
    }
  }
  if (next.length > 0) {
    next[next.length - 1]!.cache_control = ttl
      ? { type: 'ephemeral', ttl }
      : { type: 'ephemeral' };
  }
  return next;
}

export function hashCacheKey(parts: Array<string | undefined | null>): string {
  return createHash('sha256')
    .update(parts.filter(Boolean).join('::'), 'utf8')
    .digest('hex');
}

export interface FlattenedPlanSegments {
  systemPrompt: string;
  prefixContext: string;
  dynamicInput: string;
}

export function splitPlanForCaching(plan: OraclePromptPlan): FlattenedPlanSegments {
  const stable: string[] = [];
  const prefix: string[] = [];
  const dynamic: string[] = [];

  for (const block of plan.blocks) {
    if (isStableBlock(block)) stable.push(block.content);
    else if (block.kind === 'dynamic_input') dynamic.push(block.content);
    else prefix.push(block.content);
  }

  return {
    systemPrompt: stable.join('\n\n'),
    prefixContext: prefix.join('\n\n'),
    dynamicInput: dynamic.join('\n\n'),
  };
}

function isStableBlock(block: PromptBlock): boolean {
  return (
    block.kind === 'stable_system' ||
    block.kind === 'stable_schema' ||
    block.kind === 'stable_tool_definition' ||
    block.kind === 'output_contract'
  );
}
