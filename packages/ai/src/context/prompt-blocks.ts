/**
 * PromptBlock helpers — content hashing, token estimation, kind ordering.
 *
 * The hash function MUST be deterministic across processes. Cache hit ratio
 * depends on the stable prefix hashing the same way every time, every place.
 */

import { createHash } from 'node:crypto';
import type { PromptBlock, PromptBlockKind } from '../client/types';

/** Deterministic sha256 over a string, returned as hex. */
export function hashContent(content: string): string {
  return createHash('sha256').update(content, 'utf8').digest('hex');
}

/** Hash over the ordered list of block hashes — used as a composite key. */
export function hashBlockSequence(blocks: PromptBlock[]): string {
  return createHash('sha256').update(blocks.map((b) => b.hash).join('|'), 'utf8').digest('hex');
}

/**
 * Rough token estimate. 4 chars/token is the well-known approximation; we
 * pick it deliberately because it's predictable and provider-agnostic. Real
 * usage numbers are reconciled later via OracleUsage.inputTokens from the
 * provider response.
 */
export function estimateTokens(content: string): number {
  return Math.ceil(content.length / 4);
}

/**
 * Order in which kinds must be emitted to the provider. Stable kinds come
 * first so providers' prefix caches (Anthropic auto, Vertex implicit, OpenAI
 * automatic prefix) can recognize the stable prefix across calls.
 */
const KIND_ORDER: Record<PromptBlockKind, number> = {
  stable_system: 0,
  stable_tool_definition: 1,
  stable_schema: 2,
  output_contract: 3,
  semi_stable_domain_context: 4,
  retrieved_context: 5,
  dynamic_input: 6,
};

export function compareBlocksByKind(a: PromptBlock, b: PromptBlock): number {
  return KIND_ORDER[a.kind] - KIND_ORDER[b.kind];
}

/** Filter blocks down to the stable prefix (cache-eligible stable_* kinds). */
export function getStablePrefixBlocks(blocks: PromptBlock[]): PromptBlock[] {
  return blocks.filter(
    (b) =>
      b.kind === 'stable_system' ||
      b.kind === 'stable_tool_definition' ||
      b.kind === 'stable_schema' ||
      b.kind === 'output_contract',
  );
}

/** Build a PromptBlock with the hash filled in correctly. */
export function makeBlock(args: {
  id: string;
  label: string;
  kind: PromptBlockKind;
  content: string;
  cacheEligible?: boolean;
  reasonIncluded: string;
}): PromptBlock {
  const cacheEligible =
    args.cacheEligible ??
    (args.kind === 'stable_system' ||
      args.kind === 'stable_tool_definition' ||
      args.kind === 'stable_schema' ||
      args.kind === 'output_contract');
  return {
    id: args.id,
    label: args.label,
    kind: args.kind,
    content: args.content,
    hash: hashContent(args.content),
    tokenEstimate: estimateTokens(args.content),
    cacheEligible,
    reasonIncluded: args.reasonIncluded,
  };
}
