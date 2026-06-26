/**
 * settings-encoding.ts — regression guard for Bug 4 (settings double-encoding).
 *
 * Asserts the round-trip invariant of normalizeSettingValue: every value a
 * writer might hand the `/api/admin/settings` route ends up single-encoded in
 * the jsonb column, whether it arrives bare (correct) or already JSON-encoded
 * (the double-encode pathology). Also asserts the detector flags exactly the
 * double-encoded shapes and nothing legitimate.
 *
 * Pure (no DB, no network) so it runs in the static gates.
 *
 * Run: corepack pnpm --filter @oracle/ai exec tsx src/__verify__/settings-encoding.ts
 */

import { isDoubleEncodedSettingValue, normalizeSettingValue } from '../routes/settings-encoding';

let failures = 0;
function check(label: string, cond: boolean): void {
  if (cond) {
    console.log(`  ✓ ${label}`);
  } else {
    console.error(`  ✗ ${label}`);
    failures++;
  }
}
function eq(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

console.log('settings-encoding guard\n');

console.log('normalizeSettingValue — legitimate (bare) values pass through unchanged:');
check('bare effort string "off"', normalizeSettingValue('off') === 'off');
check('bare dispatch "sync"', normalizeSettingValue('sync') === 'sync');
check('model id with slash', normalizeSettingValue('google/gemini-2.5-flash') === 'google/gemini-2.5-flash');
check('curated route id', normalizeSettingValue('anthropic_claude_3_5_sonnet_synthesis_primary') === 'anthropic_claude_3_5_sonnet_synthesis_primary');
check('real array stays array', eq(normalizeSettingValue(['a', 'b']), ['a', 'b']));
check('real boolean stays boolean', normalizeSettingValue(true) === true);
check('real number stays number', normalizeSettingValue(24000) === 24000);

console.log('\nnormalizeSettingValue — accidental double-encodes are unwrapped (self-healing):');
check('double-encoded effort \'"off"\' -> "off"', normalizeSettingValue('"off"') === 'off');
check('double-encoded empty string \'""\' -> ""', normalizeSettingValue('""') === '');
check(
  'stringified pool -> real array',
  eq(normalizeSettingValue('["openai/gpt-4o-mini","google/gemini-2.5-flash"]'), [
    'openai/gpt-4o-mini',
    'google/gemini-2.5-flash',
  ]),
);
check('triple-encoded \'"\\\\"off\\\\""\' collapses to "off"', normalizeSettingValue(JSON.stringify(JSON.stringify('off'))) === 'off');
// A BARE numeric string ("24000", no JSON wrapper) is intentionally NOT coerced:
// it is ambiguous and only a double-encode has a wrapper. Left untouched.
check('bare numeric string "24000" left as-is (no wrapper)', normalizeSettingValue('24000') === '24000');

console.log('\nnormalizeSettingValue — output is never itself double-encoded (idempotent):');
for (const v of ['off', '"off"', '""', '["a","b"]', JSON.stringify(JSON.stringify('high')), 'google/gemini-2.5-flash']) {
  const once = normalizeSettingValue(v);
  const twice = normalizeSettingValue(once);
  check(`idempotent for ${JSON.stringify(v)}`, eq(once, twice) && !isDoubleEncodedSettingValue(once));
}

console.log('\nisDoubleEncodedSettingValue — detector:');
check('flags \'"off"\'', isDoubleEncodedSettingValue('"off"') === true);
check('flags stringified array', isDoubleEncodedSettingValue('["a","b"]') === true);
check('does NOT flag bare "off"', isDoubleEncodedSettingValue('off') === false);
check('does NOT flag model id', isDoubleEncodedSettingValue('google/gemini-2.5-flash') === false);
check('does NOT flag a real array', isDoubleEncodedSettingValue(['a', 'b']) === false);
check('does NOT flag a boolean', isDoubleEncodedSettingValue(true) === false);

console.log(`\n${failures === 0 ? 'PASS — settings encoding invariant holds' : `FAIL — ${failures} assertion(s)`}`);
process.exit(failures === 0 ? 0 : 1);
