// Oracle MCP — shared types for the lazy-loaded capability registry.
//
// See lib/mcp/README.md for why this server uses a hidden registry behind a
// tiny always-on tool surface instead of registering every operation as an
// MCP tool.

import type { z } from 'zod';
import type { OracleDb } from '@oracle/db/client';

/**
 * Safety tier for a capability.
 *   1 — read-only           → may execute automatically.
 *   2 — reversible write    → must preview first, requires `confirmed: true`.
 *   3 — destructive         → preview + `confirmed: true` + stronger approval.
 *
 * This server is read-only today: every capability is tier 1. The tier-2/3
 * machinery exists so write capabilities can be added safely later without
 * changing the dispatcher contract.
 */
export type SafetyTier = 1 | 2 | 3;

export interface SafetyInfo {
  tier: SafetyTier;
  label: string;
  description: string;
}

/** Execution context handed to every capability's `invoke`. */
export interface CapabilityContext {
  /** Read-capable Oracle DB handle. Every query in this server is a SELECT. */
  db: OracleDb;
}

/**
 * One hidden operation. Capabilities are NOT registered as MCP tools — they
 * live in the registry and are discovered via tool_search / get_capability_details
 * and executed via invoke_tool.
 */
export interface Capability {
  /** Stable, unique operation name. Never rename once shipped. */
  name: string;
  title: string;
  /** Coarse grouping for browsing/searching, e.g. 'knowledge', 'taxonomy', 'brain'. */
  group: string;
  safety: SafetyInfo;
  description: string;
  /** Human-readable arg shape, e.g. "{ query: string, limit?: number }". */
  argsDescription: string;
  /** Zod schema used to validate `invoke_tool` args before dispatch. */
  argsSchema: z.ZodType;
  /** A valid example arguments object (shown in discovery output). */
  exampleArgs: Record<string, unknown>;
  /** Plain-language failure modes, surfaced in the contract. */
  commonFailures: string[];
  /** Names of related capabilities to suggest next. */
  relatedTools: string[];
  /** Execute the operation. `args` is already validated against `argsSchema`. */
  invoke: (args: unknown, ctx: CapabilityContext) => Promise<unknown>;
}
