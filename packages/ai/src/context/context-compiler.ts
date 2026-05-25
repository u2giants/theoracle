/**
 * ContextCompiler — assembles an OraclePromptPlan with blocks in the correct
 * order, computes the cache-friendly hashes, and validates that no dynamic
 * content has been placed before the stable prefix.
 *
 * This compiler does NOT make a provider call. It only produces the plan.
 * The provider adapter receives the plan and renders it into a provider-
 * specific request shape.
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md "ContextCompiler rules":
 *   1. Stable system/task instructions.
 *   2. Stable tool definitions.
 *   3. Stable output schema or Zod/JSON schema description.
 *   4. Semi-stable domain/taxonomy context.
 *   5. Retrieved context.
 *   6. Dynamic input.
 *   7. Retry-specific or validation-error suffix.
 */

import type {
  OraclePromptPlan,
  PromptBlock,
  PromptPlanMetadata,
  OracleTaskType,
  OutputContract,
} from '../client/types';
import {
  compareBlocksByKind,
  getStablePrefixBlocks,
  hashBlockSequence,
  hashContent,
} from './prompt-blocks';

export interface CompileArgs {
  taskType: OracleTaskType;
  routeId: string;
  promptVersion: string;
  schemaVersion?: string;
  /** Blocks in any order; the compiler sorts them by kind. */
  blocks: PromptBlock[];
  outputContract?: OutputContract;
  /** Optional metadata to merge into the plan. */
  observability?: Partial<
    Pick<
      PromptPlanMetadata,
      | 'includedMessageIds'
      | 'includedDocumentChunkIds'
      | 'includedClaimIds'
      | 'includedGapIds'
      | 'includedContradictionIds'
      | 'retrievalPlanId'
      | 'selectedDomains'
      | 'selectedSourceTypes'
      | 'selectedProcessStages'
      | 'selectedEntityIds'
    >
  >;
}

export class ContextCompiler {
  compile(args: CompileArgs): OraclePromptPlan {
    if (args.blocks.length === 0) {
      throw new Error('ContextCompiler.compile requires at least one PromptBlock.');
    }

    // Sort by kind. The kind ordering enforces stable-before-dynamic.
    const ordered = [...args.blocks].sort(compareBlocksByKind);

    // Defensive invariant: a dynamic_input block must not precede any stable_* block.
    this.assertStableBeforeDynamic(ordered);

    const stableBlocks = getStablePrefixBlocks(ordered);
    const semiStableBlocks = ordered.filter((b) => b.kind === 'semi_stable_domain_context');
    const retrievedBlocks = ordered.filter((b) => b.kind === 'retrieved_context');
    const dynamicBlocks = ordered.filter((b) => b.kind === 'dynamic_input');

    const stablePrefixHash = hashBlockSequence(stableBlocks);
    const semiStableContextHash = semiStableBlocks.length > 0 ? hashBlockSequence(semiStableBlocks) : undefined;
    const retrievedContextHash = retrievedBlocks.length > 0 ? hashBlockSequence(retrievedBlocks) : undefined;
    const dynamicInputHash = dynamicBlocks.length > 0 ? hashBlockSequence(dynamicBlocks) : hashContent('');

    const toolSchemaBlock = ordered.find((b) => b.kind === 'stable_tool_definition');
    const outputSchemaBlock = ordered.find((b) => b.kind === 'stable_schema' || b.kind === 'output_contract');

    const metadata: PromptPlanMetadata = {
      stablePrefixHash,
      semiStableContextHash,
      retrievedContextHash,
      dynamicInputHash,
      toolSchemaHash: toolSchemaBlock?.hash,
      outputSchemaHash: outputSchemaBlock?.hash,
      ...args.observability,
    };

    return {
      taskType: args.taskType,
      routeId: args.routeId,
      promptVersion: args.promptVersion,
      schemaVersion: args.schemaVersion,
      blocks: ordered,
      outputContract: args.outputContract,
      metadata,
    };
  }

  /**
   * Internal invariant — dynamic blocks must come after every stable_* block.
   * If they don't, the cache will be permanently busted. Fail loudly.
   */
  private assertStableBeforeDynamic(orderedBlocks: PromptBlock[]): void {
    let sawDynamic = false;
    for (const block of orderedBlocks) {
      if (block.kind === 'dynamic_input') sawDynamic = true;
      else if (
        sawDynamic &&
        (block.kind === 'stable_system' ||
          block.kind === 'stable_tool_definition' ||
          block.kind === 'stable_schema' ||
          block.kind === 'output_contract')
      ) {
        throw new Error(
          `ContextCompiler invariant violated: stable block "${block.id}" (${block.kind}) appears after a dynamic_input block. Stable content must always precede dynamic content for cache friendliness.`,
        );
      }
    }
  }
}

/** Singleton accessor for the default compiler. */
let cached: ContextCompiler | null = null;
export function getContextCompiler(): ContextCompiler {
  if (!cached) cached = new ContextCompiler();
  return cached;
}
