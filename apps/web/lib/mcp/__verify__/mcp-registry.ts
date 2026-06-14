// Static verification for the Oracle MCP lazy-loaded registry.
//
// DB-free: exercises discovery, search, enablement overrides, contract shape,
// arg validation, and safety-tier semantics WITHOUT invoking any capability
// (so it never touches Postgres). Run: pnpm --filter @oracle/web verify:mcp
//
// Mirrors the repo's other `verify:*` guards (tsx + node:assert, non-zero exit
// on failure) so it can gate CI the same way.

import assert from 'node:assert/strict';
import { z } from 'zod';
import { CAPABILITIES } from '../capabilities';
import {
  ALWAYS_ON_TOOLS,
  formatContract,
  getEnabledCapabilities,
  getEnabledCapability,
  searchCapabilities,
} from '../registry';

function section(name: string, fn: () => void) {
  fn();
  console.log(`✓ ${name}`);
}

// 1. The always-on surface is exactly the five lazy-loading tools — no domain
//    operation may leak into tools/list.
section('always-on tools are exactly the 5 dispatcher tools', () => {
  assert.deepEqual(
    [...ALWAYS_ON_TOOLS],
    ['health', 'list_capabilities', 'tool_search', 'get_capability_details', 'invoke_tool'],
  );
  const capNames = new Set(CAPABILITIES.map((c) => c.name));
  for (const t of ALWAYS_ON_TOOLS) {
    assert.ok(!capNames.has(t), `Always-on tool "${t}" must not also be a hidden capability`);
  }
});

// 2. Every capability carries complete, valid metadata + safety tier.
section('every capability has complete metadata and a safety tier', () => {
  const seen = new Set<string>();
  for (const c of CAPABILITIES) {
    assert.ok(c.name && !seen.has(c.name), `duplicate/empty capability name: ${c.name}`);
    seen.add(c.name);
    assert.ok(c.title && c.group && c.description, `${c.name}: missing title/group/description`);
    assert.ok(c.argsDescription, `${c.name}: missing argsDescription`);
    assert.ok([1, 2, 3].includes(c.safety.tier), `${c.name}: bad safety tier`);
    assert.ok(c.safety.label && c.safety.description, `${c.name}: incomplete safety info`);
    assert.ok(c.argsSchema instanceof z.ZodType, `${c.name}: argsSchema must be a zod schema`);
    assert.ok(Array.isArray(c.commonFailures) && c.commonFailures.length > 0, `${c.name}: needs commonFailures`);
    // exampleArgs must satisfy the schema.
    const parsed = c.argsSchema.safeParse(c.exampleArgs);
    assert.ok(parsed.success, `${c.name}: exampleArgs must validate against argsSchema`);
    // relatedTools must reference real capabilities.
    for (const rel of c.relatedTools) {
      assert.ok(
        CAPABILITIES.some((o) => o.name === rel),
        `${c.name}: relatedTools references unknown "${rel}"`,
      );
    }
  }
});

// 3. tool_search finds enabled capabilities by intent (not just exact name).
section('tool_search finds capabilities by intent', () => {
  const byKeyword = searchCapabilities('naming rules for files');
  assert.ok(
    byKeyword.some((h) => h.capability.name === 'search_business_knowledge'),
    'intent search should surface search_business_knowledge',
  );
  const byDomain = searchCapabilities('knowledge domains taxonomy');
  assert.equal(byDomain[0]?.capability.name, 'list_knowledge_domains', 'taxonomy query should rank domains first');
  const byBrain = searchCapabilities('brain section narrative');
  assert.ok(byBrain.some((h) => h.capability.group === 'brain'), 'brain query should surface brain group');
  // No-match returns empty (not everything).
  assert.equal(searchCapabilities('zzzznotarealthing').length, 0);
});

// 4. Disabled tools disappear from discovery and lookup; disabled overrides enabled.
section('enablement overrides hide tools (disabled wins)', () => {
  const onlyDomains = getEnabledCapabilities({
    ORACLE_MCP_ENABLED_TOOLS: 'list_knowledge_domains',
  });
  assert.deepEqual(onlyDomains.map((c) => c.name), ['list_knowledge_domains']);

  const disabledEnv = { ORACLE_MCP_DISABLED_TOOLS: 'search_business_knowledge' };
  assert.ok(
    !getEnabledCapabilities(disabledEnv).some((c) => c.name === 'search_business_knowledge'),
    'disabled capability must not be enabled',
  );
  assert.equal(
    getEnabledCapability('search_business_knowledge', disabledEnv),
    undefined,
    'disabled capability must not be found by lookup',
  );

  // In both lists → disabled wins.
  const both = getEnabledCapabilities({
    ORACLE_MCP_ENABLED_TOOLS: 'search_business_knowledge',
    ORACLE_MCP_DISABLED_TOOLS: 'search_business_knowledge',
  });
  assert.equal(both.length, 0, 'a name in both enabled and disabled must be disabled');
});

// 5. get_capability_details output contains the exact invoke_tool shape.
section('contract output shows the exact invoke_tool call shape', () => {
  const cap = getEnabledCapability('search_business_knowledge');
  assert.ok(cap);
  const contract = formatContract(cap);
  assert.match(contract, /# search_business_knowledge/);
  assert.match(contract, /Safety: tier 1 read-only/);
  assert.match(contract, /Example invoke_tool arguments:/);
  // The embedded JSON must be a real invoke_tool args object: { name, args }.
  const json = contract.slice(contract.indexOf('```json') + 7, contract.indexOf('```', contract.indexOf('```json') + 7));
  const parsed = JSON.parse(json) as { name: string; args: unknown };
  assert.equal(parsed.name, 'search_business_knowledge');
  assert.ok(parsed.args && typeof parsed.args === 'object', 'example must carry an args object');
  assert.ok(cap.argsSchema.safeParse(parsed.args).success, 'embedded example args must validate');
});

// 6. Arg validation rejects bad input (the dispatcher relies on this).
section('argsSchema rejects invalid input', () => {
  const cap = getEnabledCapability('search_business_knowledge')!;
  assert.equal(cap.argsSchema.safeParse({}).success, false, 'missing query must fail');
  assert.equal(cap.argsSchema.safeParse({ query: 'x', limit: 999 }).success, false, 'limit over max must fail');
  assert.equal(cap.argsSchema.safeParse({ query: 'valid question' }).success, true);
});

// 7. This server is read-only: every capability is tier 1.
section('all shipped capabilities are tier-1 read-only', () => {
  for (const c of CAPABILITIES) {
    assert.equal(c.safety.tier, 1, `${c.name} must be tier 1 in a read-only server`);
  }
});

console.log(`\nAll MCP registry checks passed (${CAPABILITIES.length} capabilities).`);
