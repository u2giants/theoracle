# Oracle MCP server

A remote, read-only [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the Oracle's **approved** business knowledge to external AI agents (coding assistants building software for POP Creations / Spruce Line).

Endpoint: `POST https://oracle.designflow.app/api/mcp/mcp` — auth: `Authorization: Bearer $ORACLE_MCP_TOKEN`.

## Why lazy loading

> **Do not eagerly register hidden operations as MCP tools.**

`tools/list` stays tiny **forever**. Real operations live in a hidden registry and are reached through a generic dispatcher. This keeps the always-on context small and—critically—survives MCP clients that **cache the initial `tools/list`** and never refetch. We deliberately do **not** rely on `tools/list_changed` as a discovery mechanism.

An agent's flow is always: **search → inspect → invoke**.

```
tool_search { query: "naming rules for files" }      # discover
get_capability_details { name: "search_business_knowledge" }   # inspect contract
invoke_tool { name: "search_business_knowledge", args: { query: "...", limit: 5 } }   # run
```

## Always-on tools (the entire `tools/list`)

| Tool | Purpose |
|---|---|
| `health` | Server status, version, enabled-capability count, groups, visible tools |
| `list_capabilities` | Browse enabled hidden capabilities by group / safety tier |
| `tool_search` | Find capabilities by intent or keyword; returns ranked contracts |
| `get_capability_details` | Full contract for one capability (exact `invoke_tool` shape) |
| `invoke_tool` | Execute one capability by exact name + args |

Do not add more always-on tools unless the context cost is explicitly accepted.

## Hidden registry

All operations live in [`capabilities.ts`](./capabilities.ts) as `Capability` objects (see [`types.ts`](./types.ts)). Each declares `name`, `title`, `group`, `safety`, `description`, `argsDescription`, `argsSchema` (zod), `exampleArgs`, `commonFailures`, `relatedTools`, and `invoke`.

Current capabilities (all tier-1 read-only):

| Name | Group | What it returns |
|---|---|---|
| `search_business_knowledge` | `knowledge` | Approved claims for a query (optional evidence quotes), via `searchWithRetrievalPlan` — the same path employee chat uses |
| `list_knowledge_domains` | `taxonomy` | Curated top-domains + boundary rules |
| `list_brain_sections` | `brain` | Approved synthesized process narratives (list) |
| `get_brain_section` | `brain` | One approved Brain section's markdown + source claim IDs |

Only `status='approved'` claims and `review_status='approved'` Brain versions are ever returned. The server reuses `@oracle/ai` / `@oracle/db` as the source of truth — it does **not** duplicate business logic or expose raw SQL.

### How search works (`tool_search`)

[`registry.ts`](./registry.ts) `searchCapabilities()` tokenizes the query and scores each **enabled** capability on: exact name (10), name substring (5), title (4), exact group (4), `KEYWORD_GROUPS` intent→group routing (3), and description hit (2). Non-matches (score 0) are dropped; results are ranked, default limit 8, hard cap 30.

### Adding a capability

1. Append a `Capability` to `CAPABILITIES` in `capabilities.ts`.
2. If it introduces new vocabulary, add `KEYWORD_GROUPS` entries so `tool_search` can route to it.
3. Add an assertion or two to [`__verify__/mcp-registry.ts`](./__verify__/mcp-registry.ts).

Nothing in the route or the always-on tools changes.

## Safety tiers

| Tier | Meaning | Dispatcher behavior |
|---|---|---|
| 1 | read-only | Runs immediately |
| 2 | reversible write | `invoke_tool` returns a **preview** unless `args.confirmed === true` |
| 3 | destructive | Preview + `confirmed` + stronger approval |

This server is tier-1 only today. The preview/confirm gate in `invoke_tool` already exists so a future write capability is safe by construction; the verify guard asserts every shipped capability stays tier 1.

## Enablement config

Capabilities can exist in code without being discoverable:

- Default: all of `CAPABILITIES` are enabled.
- `ORACLE_MCP_ENABLED_TOOLS` (csv) — if set, **only** these names are enabled.
- `ORACLE_MCP_DISABLED_TOOLS` (csv) — these names are always disabled.
- **Disabled wins** over enabled.

Disabled capabilities never appear in `tool_search` / `list_capabilities` and are rejected by `invoke_tool` (all enforced through `getEnabledCapabilities()`).

## Auth model

A single static bearer token, `ORACLE_MCP_TOKEN`, compared in constant time. Machine-to-machine only — not tied to a Supabase user session. If the env var is unset, the endpoint rejects every request. Rotate by changing the env var. No secrets, tokens, or raw env values are ever returned in tool output.

## Deployment mode

In-app Next.js route on Vercel (Node runtime), **Streamable HTTP**, stateless (no Redis). SSE is disabled — modern MCP clients use Streamable HTTP. The `[transport]` route segment is required by `mcp-handler`; with `basePath: '/api/mcp'` the live endpoint is `/api/mcp/mcp`.

## Must not change

- Do not register capabilities directly as MCP tools — keep `tools/list` to the five always-on tools.
- Do not rename a shipped capability `name` (clients pin to it).
- Do not return unapproved claims/Brain versions, raw SQL access, or secrets.
- Do not add write (tier 2+) capabilities without the preview/confirm gate and an audit log.

## Tests

`pnpm --filter @oracle/web verify:mcp` (a `tsx` guard, wired into the Vercel build before `@oracle/web build`). Covers: the visible surface is only the always-on tools, capability metadata/tiers are complete, `tool_search` finds enabled tools by intent, disabled tools vanish from search and lookup, contracts carry the exact `invoke_tool` shape, and arg validation rejects bad input.
