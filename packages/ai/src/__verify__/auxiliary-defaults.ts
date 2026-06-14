/**
 * Auxiliary-model default-route invariant gate.
 *
 * Run with:
 *   pnpm --filter @oracle/ai exec tsx src/__verify__/auxiliary-defaults.ts
 *
 * Guarantees the fallback used by workers when an admin clears (or never set)
 * an auxiliary-model setting is always resolvable:
 *   - Every AUXILIARY_MODELS entry that declares a `defaultRouteId` must
 *     resolve via getOracleRoute() — i.e. it points at a LIVE catalog route,
 *     not a dangling id. Otherwise the worker fallback (e.g. the image-vision
 *     transcription pass) throws "vision route unresolvable" exactly when the
 *     setting is empty.
 *   - The image-vision model MUST declare a defaultRouteId (it has no other
 *     safety net), and that route must support vision.
 *
 * No network / DB — pure registry + catalog assertions.
 */

import {
  AUXILIARY_MODELS,
  VISION_AUXILIARY_MODEL,
  getOracleRoute,
} from '../index';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

function main() {
  console.log('Auxiliary-model default-route gate\n');

  assert(AUXILIARY_MODELS.length > 0, 'registry is non-empty');

  for (const def of AUXILIARY_MODELS) {
    if (def.defaultRouteId === undefined) {
      console.log(`• ${def.id}: no defaultRouteId (allowed) — skipping`);
      continue;
    }
    const route = getOracleRoute(def.defaultRouteId);
    assert(
      route !== null,
      `${def.id}: defaultRouteId "${def.defaultRouteId}" resolves to a live catalog route`,
    );
  }

  // The image-vision pass has no other fallback, so its default is mandatory.
  assert(
    typeof VISION_AUXILIARY_MODEL.defaultRouteId === 'string' &&
      VISION_AUXILIARY_MODEL.defaultRouteId.length > 0,
    'vision model declares a defaultRouteId (mandatory — it is the only fallback)',
  );
  const visionRoute = getOracleRoute(VISION_AUXILIARY_MODEL.defaultRouteId!);
  assert(visionRoute !== null, 'vision defaultRouteId resolves in the catalog');
  assert(
    visionRoute!.supportsVision === true,
    `vision default route "${visionRoute!.routeId}" supportsVision === true`,
  );

  console.log('\nAuxiliary-model default-route gate: PASS');
}

main();
