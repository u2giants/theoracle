// Oracle MCP — registry access: enablement, search, and contract formatting.
//
// Enablement (so compiled capabilities can exist without being discoverable):
//   - Default: every capability in CAPABILITIES is enabled.
//   - ORACLE_MCP_ENABLED_TOOLS (csv) — if set, ONLY these names are enabled.
//   - ORACLE_MCP_DISABLED_TOOLS (csv) — these names are always disabled.
//   - Disabled overrides enabled (a name in both is disabled).
// Disabled capabilities must not appear in tool_search or list_capabilities and
// must be rejected by invoke_tool. All three go through getEnabledCapabilities().

import { CAPABILITIES, KEYWORD_GROUPS, type Capability } from './capabilities';

export const ALWAYS_ON_TOOLS = [
  'health',
  'list_capabilities',
  'tool_search',
  'get_capability_details',
  'invoke_tool',
] as const;

const DEFAULT_SEARCH_LIMIT = 8;
const MAX_SEARCH_LIMIT = 30;

function parseCsvEnv(value: string | undefined): Set<string> {
  return new Set(
    (value ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  );
}

/** Capabilities currently enabled, honoring env overrides (disabled wins). */
export function getEnabledCapabilities(env: Record<string, string | undefined> = process.env): Capability[] {
  const enabledOverride = parseCsvEnv(env.ORACLE_MCP_ENABLED_TOOLS);
  const disabledOverride = parseCsvEnv(env.ORACLE_MCP_DISABLED_TOOLS);
  return CAPABILITIES.filter((c) => {
    if (disabledOverride.has(c.name)) return false;
    if (enabledOverride.size > 0 && !enabledOverride.has(c.name)) return false;
    return true;
  });
}

/** Look up an enabled capability by exact name (undefined if missing/disabled). */
export function getEnabledCapability(
  name: string,
  env: Record<string, string | undefined> = process.env,
): Capability | undefined {
  return getEnabledCapabilities(env).find((c) => c.name === name);
}

/** Distinct groups among enabled capabilities. */
export function getEnabledGroups(env: Record<string, string | undefined> = process.env): string[] {
  return [...new Set(getEnabledCapabilities(env).map((c) => c.group))].sort();
}

export interface SearchHit {
  capability: Capability;
  score: number;
}

/**
 * Rank enabled capabilities by intent. Scores exact-name, name/title/group/
 * description hits, and keyword→group routing. Multi-word queries accumulate
 * score on the right capability and drop non-matches (score 0).
 */
export function searchCapabilities(
  query: string,
  limit = DEFAULT_SEARCH_LIMIT,
  env: Record<string, string | undefined> = process.env,
): SearchHit[] {
  const caps = getEnabledCapabilities(env);
  const cappedLimit = Math.min(Math.max(1, limit), MAX_SEARCH_LIMIT);
  const tokens = query.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  if (tokens.length === 0) {
    return caps.slice(0, cappedLimit).map((capability) => ({ capability, score: 0 }));
  }

  const hits: SearchHit[] = [];
  for (const capability of caps) {
    const name = capability.name.toLowerCase();
    const title = capability.title.toLowerCase();
    const group = capability.group.toLowerCase();
    const desc = capability.description.toLowerCase();
    let score = 0;
    for (const token of tokens) {
      if (name === token) score += 10;
      else if (name.includes(token)) score += 5;
      if (title.includes(token)) score += 4;
      if (group === token) score += 4;
      const mappedGroups = KEYWORD_GROUPS[token];
      if (mappedGroups?.includes(capability.group)) score += 3;
      if (desc.includes(token)) score += 2;
    }
    if (score > 0) hits.push({ capability, score });
  }
  hits.sort((a, b) => b.score - a.score || a.capability.name.localeCompare(b.capability.name));
  return hits.slice(0, cappedLimit);
}

/** Full structured-text contract for one capability (get_capability_details). */
export function formatContract(c: Capability): string {
  const invokeExample = JSON.stringify(
    { name: c.name, args: c.exampleArgs },
    null,
    2,
  );
  return [
    `# ${c.name}`,
    ``,
    `Title: ${c.title}`,
    ``,
    `Group: ${c.group}`,
    ``,
    `Safety: tier ${c.safety.tier} ${c.safety.label} — ${c.safety.description}`,
    ``,
    `Description:`,
    c.description,
    ``,
    `Arguments:`,
    c.argsDescription,
    ``,
    `Example invoke_tool arguments:`,
    '```json',
    invokeExample,
    '```',
    ``,
    `Common failures:`,
    ...c.commonFailures.map((f) => `- ${f}`),
    ``,
    `Related tools:`,
    c.relatedTools.length > 0 ? c.relatedTools.join(', ') : '(none)',
  ].join('\n');
}

/** Compact one-line-ish summary used in tool_search / list_capabilities output. */
export function formatSummary(c: Capability): string {
  return `${c.name} [${c.group}, tier ${c.safety.tier} ${c.safety.label}] — ${c.description}`;
}

export { DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT };
