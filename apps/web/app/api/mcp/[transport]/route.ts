// Oracle remote MCP server.
//
// Exposes the Oracle's approved business knowledge to external AI agents over
// the Model Context Protocol (Streamable HTTP transport). Endpoint:
//
//   POST https://oracle.designflow.app/api/mcp/mcp
//
// Auth: a single static bearer token in `ORACLE_MCP_TOKEN`. Every request must
// send `Authorization: Bearer <token>`. This is a machine-to-machine endpoint
// for trusted agents building software for us — it is NOT tied to a Supabase
// user session. Rotate the token by changing the env var.
//
// Transport: Streamable HTTP, stateless (no Redis). SSE is disabled — the
// current MCP spec (2025-03-26+) uses Streamable HTTP, which every modern
// client speaks. The `[transport]` route segment is required by mcp-handler;
// with basePath '/api/mcp' the live endpoint is '/api/mcp/mcp'.
//
// tools/list is intentionally tiny: it exposes only the five always-on tools
// (health, list_capabilities, tool_search, get_capability_details, invoke_tool).
// Real operations live in a hidden registry (apps/web/lib/mcp/capabilities.ts)
// reached via invoke_tool. They are read-only and route through the same
// retrieval path as employee chat, so they cannot surface unapproved knowledge.
// See apps/web/lib/mcp/README.md.

import { timingSafeEqual } from 'node:crypto';
import { createMcpHandler, withMcpAuth } from 'mcp-handler';
import type { AuthInfo } from '@modelcontextprotocol/sdk/server/auth/types.js';
import { getDirectDb } from '@oracle/db/client';
import { registerOracleMcpTools } from '@/lib/mcp/server-tools';

// Drizzle/postgres need the Node runtime; retrieval is dynamic per request.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 60;

const baseHandler = createMcpHandler(
  (server) => {
    registerOracleMcpTools(server, { db: getDirectDb() });
  },
  {
    serverInfo: { name: 'oracle-knowledge', version: '1.0.0' },
  },
  {
    basePath: '/api/mcp',
    disableSse: true,
    maxDuration: 60,
    verboseLogs: process.env.NODE_ENV !== 'production',
  },
);

/** Constant-time bearer-token check against ORACLE_MCP_TOKEN. */
function verifyToken(_req: Request, bearerToken?: string): AuthInfo | undefined {
  const expected = process.env.ORACLE_MCP_TOKEN;
  if (!expected) {
    // Misconfiguration: never accept requests when no token is set.
    console.error('[mcp] ORACLE_MCP_TOKEN is not set — rejecting all MCP requests.');
    return undefined;
  }
  if (!bearerToken) return undefined;

  const a = Buffer.from(bearerToken);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return undefined;

  return {
    token: bearerToken,
    clientId: 'oracle-mcp-client',
    scopes: [],
  };
}

const handler = withMcpAuth(baseHandler, verifyToken, { required: true });

export { handler as GET, handler as POST, handler as DELETE };
