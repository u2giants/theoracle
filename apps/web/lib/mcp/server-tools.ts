// Oracle MCP — always-on tool surface.
//
// These are the ONLY tools that appear in tools/list. Real operations live in
// the hidden registry (capabilities.ts) and are reached through tool_search /
// get_capability_details / invoke_tool. This keeps tools/list tiny forever, so
// MCP clients that cache the initial list never miss capabilities (we do not
// rely on tools/list_changed). See README.md.

import { z } from 'zod';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import {
  ALWAYS_ON_TOOLS,
  DEFAULT_SEARCH_LIMIT,
  MAX_SEARCH_LIMIT,
  formatContract,
  formatSummary,
  getEnabledCapabilities,
  getEnabledCapability,
  getEnabledGroups,
  searchCapabilities,
} from './registry';
import type { CapabilityContext } from './types';

const SERVER_VERSION = '1.0.0';

function textResult(text: string) {
  return { content: [{ type: 'text' as const, text }] };
}
function jsonResult(payload: unknown) {
  return textResult(JSON.stringify(payload, null, 2));
}
function errorResult(message: string) {
  return { content: [{ type: 'text' as const, text: message }], isError: true as const };
}

/**
 * Register the five always-on tools. `ctx` carries the DB handle used by
 * capability invocations.
 */
export function registerOracleMcpTools(server: McpServer, ctx: CapabilityContext): void {
  // ── health ────────────────────────────────────────────────────────────
  server.registerTool(
    'health',
    {
      title: 'Health',
      description:
        'Return Oracle MCP server status: version, how many hidden capabilities are enabled, ' +
        'their groups, and the always-on tool list. Start here to confirm connectivity.',
      inputSchema: {},
    },
    async () => {
      const enabled = getEnabledCapabilities();
      return jsonResult({
        status: 'ok',
        server: 'oracle-knowledge',
        version: SERVER_VERSION,
        enabledCapabilityCount: enabled.length,
        groups: getEnabledGroups(),
        visibleTools: [...ALWAYS_ON_TOOLS],
        hint: 'Use tool_search to find a capability, get_capability_details to inspect it, then invoke_tool to run it.',
      });
    },
  );

  // ── list_capabilities ───────────────────────────────────────────────────
  server.registerTool(
    'list_capabilities',
    {
      title: 'List capabilities',
      description:
        'Browse the enabled hidden capabilities, optionally filtered by group or safety tier. ' +
        'Returns compact summaries; use get_capability_details for a full contract.',
      inputSchema: {
        group: z.string().optional().describe('Filter to one group (see health.groups).'),
        safetyTier: z
          .number()
          .int()
          .min(1)
          .max(3)
          .optional()
          .describe('Filter to one safety tier (1 read-only, 2 write, 3 destructive).'),
      },
    },
    async ({ group, safetyTier }) => {
      let caps = getEnabledCapabilities();
      if (group) caps = caps.filter((c) => c.group === group);
      if (safetyTier) caps = caps.filter((c) => c.safety.tier === safetyTier);
      return jsonResult({
        count: caps.length,
        capabilities: caps.map((c) => ({
          name: c.name,
          title: c.title,
          group: c.group,
          safetyTier: c.safety.tier,
          summary: formatSummary(c),
        })),
      });
    },
  );

  // ── tool_search ─────────────────────────────────────────────────────────
  server.registerTool(
    'tool_search',
    {
      title: 'Search capabilities',
      description:
        'Find hidden capabilities by intent or keyword (matches name, title, description, ' +
        'group, and a domain keyword map). Returns ranked contracts. This is the entry point ' +
        'for discovering what the Oracle can answer.',
      inputSchema: {
        query: z.string().min(1).describe('What you are trying to do, in words or keywords.'),
        limit: z
          .number()
          .int()
          .min(1)
          .max(MAX_SEARCH_LIMIT)
          .optional()
          .describe(`Max results (default ${DEFAULT_SEARCH_LIMIT}, max ${MAX_SEARCH_LIMIT}).`),
      },
    },
    async ({ query, limit }) => {
      const hits = searchCapabilities(query, limit ?? DEFAULT_SEARCH_LIMIT);
      if (hits.length === 0) {
        return textResult(
          `No capabilities matched "${query}". Try broader terms, or call list_capabilities to browse everything.`,
        );
      }
      return textResult(
        hits.map((h) => formatContract(h.capability)).join('\n\n---\n\n'),
      );
    },
  );

  // ── get_capability_details ───────────────────────────────────────────────
  server.registerTool(
    'get_capability_details',
    {
      title: 'Get capability details',
      description:
        'Return the full contract for one hidden capability by exact name: description, ' +
        'arguments, an example invoke_tool call, common failures, and related tools.',
      inputSchema: {
        name: z.string().describe('Exact capability name (from tool_search / list_capabilities).'),
      },
    },
    async ({ name }) => {
      const cap = getEnabledCapability(name);
      if (!cap) {
        return errorResult(
          `No enabled capability named "${name}". Use tool_search or list_capabilities to find valid names.`,
        );
      }
      return textResult(formatContract(cap));
    },
  );

  // ── invoke_tool ──────────────────────────────────────────────────────────
  server.registerTool(
    'invoke_tool',
    {
      title: 'Invoke capability',
      description:
        'Execute one hidden capability by exact name with its arguments. Read-only (tier 1) ' +
        'capabilities run immediately. Write capabilities (tier 2+) return a preview unless ' +
        '`args.confirmed` is true.',
      inputSchema: {
        name: z.string().describe('Exact capability name to run.'),
        args: z
          .record(z.string(), z.unknown())
          .optional()
          .describe('Arguments object for the capability (see its contract).'),
      },
    },
    async ({ name, args }) => {
      const cap = getEnabledCapability(name);
      if (!cap) {
        return errorResult(
          `No enabled capability named "${name}". Use tool_search or list_capabilities to find valid names.`,
        );
      }

      const rawArgs = args ?? {};

      // Write-safety gate: tier 2+ must preview unless explicitly confirmed.
      if (cap.safety.tier >= 2 && (rawArgs as { confirmed?: unknown }).confirmed !== true) {
        return jsonResult({
          preview: true,
          wouldRun: cap.name,
          tier: cap.safety.tier,
          requiresConfirmation: true,
          requiredArgs: { confirmed: true },
          note: `${cap.name} is a tier-${cap.safety.tier} (${cap.safety.label}) operation. Re-invoke with args.confirmed = true to execute.`,
        });
      }

      const parsed = cap.argsSchema.safeParse(rawArgs);
      if (!parsed.success) {
        return errorResult(
          `Invalid arguments for "${name}". Expected ${cap.argsDescription}. Issues: ` +
            parsed.error.issues
              .map((i) => `${i.path.join('.') || '(root)'}: ${i.message}`)
              .join('; '),
        );
      }

      try {
        const result = await cap.invoke(parsed.data, ctx);
        return jsonResult(result);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error(`[mcp] invoke "${name}" failed:`, message);
        return errorResult(`Capability "${name}" failed: ${message}`);
      }
    },
  );
}
