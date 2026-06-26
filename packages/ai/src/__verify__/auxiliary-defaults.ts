/**
 * Auxiliary-model routing invariant gate.
 *
 * Run with:
 *   pnpm --filter @oracle/ai exec tsx src/__verify__/auxiliary-defaults.ts
 *
 * Auxiliary models are explicit single-pick slots. They must not declare
 * baked-in default routes; an unset setting is a configuration error.
 *
 * No network / DB — pure registry assertions.
 */

import {
  AUXILIARY_MODELS,
  GENERAL_PURPOSE_AUXILIARY_MODEL,
  TRANSLATION_AUXILIARY_MODEL,
  VISION_AUXILIARY_MODEL,
} from '../index';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

function main() {
  console.log('Auxiliary-model routing gate\n');

  assert(AUXILIARY_MODELS.length > 0, 'registry is non-empty');

  const ids = new Set<string>();
  for (const def of AUXILIARY_MODELS) {
    assert(!ids.has(def.id), `${def.id}: registry id is unique`);
    ids.add(def.id);
    assert(
      !('defaultRouteId' in def),
      `${def.id}: no defaultRouteId is declared`,
    );
    assert(
      typeof def.routeSettingKey === 'string' && def.routeSettingKey.length > 0,
      `${def.id}: route setting key is configured`,
    );
  }

  assert(VISION_AUXILIARY_MODEL.id === 'vision', 'vision auxiliary id is stable');
  assert(GENERAL_PURPOSE_AUXILIARY_MODEL.id === 'general', 'general auxiliary id is stable');
  assert(TRANSLATION_AUXILIARY_MODEL.id === 'translation', 'translation auxiliary id is stable');

  console.log('\nAuxiliary-model routing gate: PASS');
}

main();
