/**
 * Retrieval filter-parity guard.
 *
 * Run with: pnpm --filter @oracle/ai exec tsx src/__verify__/retrieval-filter-parity.ts
 * (aliased as `pnpm --filter @oracle/ai verify:retrieval-filter-parity`)
 *
 * The recurring bug class in retrieval.ts is: a new narrowing filter is added
 * to the shared buildPlanMetadataFilters() helper and wired into the main
 * hybrid query (searchWithRetrievalPlan) but NOT into the tsvector fallback
 * (_searchFallbackTsvector) — or vice versa — silently making one path weaker.
 *
 * This guard is a static, DB-free, dependency-free check: it parses
 * retrieval.ts and asserts that EVERY key returned by buildPlanMetadataFilters
 * is interpolated (`${key}`) into BOTH consuming query bodies. It fails loudly
 * if a filter exists in the helper but is missing from either path, or is
 * destructured in a path but never interpolated into that path's SQL.
 *
 * Static parsing (rather than executing SQL) is deliberate: it keeps the helper
 * private (no API surface widening just to test it) and needs no database.
 *
 * This file is in __verify__ so it is never picked up as a production export.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RETRIEVAL_PATH = join(__dirname, '..', 'retrieval.ts');

function fail(msg: string): never {
  console.error(`✗ ${msg}`);
  process.exit(1);
}
function pass(msg: string): void {
  console.log(`✓ ${msg}`);
}

/**
 * Extract the body of a function by brace-matching from its declaration.
 * `signature` must be a literal substring that appears once, at the function's
 * declaration (e.g. "function buildPlanMetadataFilters").
 */
function extractFunctionBody(source: string, signature: string): string {
  const start = source.indexOf(signature);
  if (start === -1) fail(`could not find "${signature}" in retrieval.ts`);
  const braceStart = source.indexOf('{', start);
  if (braceStart === -1) fail(`no opening brace after "${signature}"`);
  let depth = 0;
  for (let i = braceStart; i < source.length; i++) {
    const ch = source[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return source.slice(braceStart, i + 1);
    }
  }
  fail(`unbalanced braces after "${signature}"`);
}

function main(): void {
  console.log('Retrieval filter-parity guard\n');
  const source = readFileSync(RETRIEVAL_PATH, 'utf8');

  // 1. Extract the keys returned by buildPlanMetadataFilters from its `return
  //    { ... }` object literal.
  const helperBody = extractFunctionBody(source, 'function buildPlanMetadataFilters');
  const returnMatch = helperBody.match(/return\s*\{([\s\S]*?)\}\s*;/);
  if (!returnMatch || returnMatch[1] === undefined) {
    fail('buildPlanMetadataFilters has no `return { ... };` block');
  }
  const keys = returnMatch[1]
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    // Object shorthand only — `topDomainFilter`, not `topDomainFilter: x`.
    .map((s) => s.split(':')[0]?.trim() ?? '')
    .filter((s) => /^[a-zA-Z0-9_]+$/.test(s));

  if (keys.length === 0) fail('parsed zero filter keys from buildPlanMetadataFilters');
  pass(`buildPlanMetadataFilters returns ${keys.length} filter keys: ${keys.join(', ')}`);

  // 2. Extract the two consuming function bodies.
  const hybridBody = extractFunctionBody(source, 'export async function searchWithRetrievalPlan');
  const fallbackBody = extractFunctionBody(source, 'async function _searchFallbackTsvector');

  // 3. Every key must be interpolated as `${key}` in BOTH bodies.
  const paths: Array<[string, string]> = [
    ['searchWithRetrievalPlan (hybrid)', hybridBody],
    ['_searchFallbackTsvector (fallback)', fallbackBody],
  ];

  let ok = true;
  for (const key of keys) {
    const token = '${' + key + '}';
    for (const [label, body] of paths) {
      if (!body.includes(token)) {
        console.error(`✗ filter "${key}" is NOT interpolated into ${label}`);
        ok = false;
      }
    }
  }
  if (!ok) {
    fail(
      'filter parity broken — every buildPlanMetadataFilters key must appear as ${key} ' +
        'in BOTH the hybrid and fallback query bodies.',
    );
  }
  pass(`all ${keys.length} filters are interpolated into both the hybrid and fallback paths`);

  console.log('\nFilter parity holds.');
}

main();
